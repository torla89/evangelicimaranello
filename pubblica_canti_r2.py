"""
Pubblica su Cloudflare R2 quello che serve al Gestore Canti (MusicPlayer):

  1. i testi (.docx) della cartella "testi" che mancano o sono cambiati
  2. il programma: versione.txt + programma_update.zip (la cartella "sorgente"),
     solo se la versione scritta in app.py e' diversa da quella online
  3. lo zip completo "MusicLibraryApp.zip" (per chi scarica da zero), solo se
     manca online oppure con l'opzione --completo
  4. gli elenchi "indice.json" delle cartelle Cem-basi-inni e Cem-Canti, che il
     Gestore Canti legge per sapere quali file scaricare

Le basi (mp3) si caricano dal Gestore Sito; le registrazioni guida (Cem-Canti)
dalla dashboard di Cloudflare. Dopo aver aggiunto file a mano dalla dashboard,
rilancia questo programma per aggiornare gli elenchi.

Uso:
    python pubblica_canti_r2.py              pubblicazione normale
    python pubblica_canti_r2.py --forza      ricarica il programma anche se la versione e' uguale
    python pubblica_canti_r2.py --completo   ricrea e ricarica anche lo zip completo
"""
import os
import re
import sys
import tempfile
import zipfile

import r2_storage

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
BASI = "Cem-basi-inni"
GUIDA = "Cem-Canti"
ESCLUSI_ZIP = {"__pycache__", "build_tmp", "build", "dist", "Claude outputs", "_to_delete"}
FILE_ESCLUSI_ZIP = {".durate_cache.json", ".impostazioni.json"}


def trova_cartella_canti():
    candidati = [
        os.path.join(SITE_DIR, "..", "..", "Gestore canti", "MusicLibraryApp"),
        os.path.join(SITE_DIR, "..", "Gestore canti", "MusicLibraryApp"),
    ]
    for c in candidati:
        if os.path.isfile(os.path.join(c, "sorgente", "app.py")):
            return os.path.abspath(c)
    while True:
        c = input("Non trovo la cartella MusicLibraryApp. Incolla il percorso: ").strip().strip('"')
        if os.path.isfile(os.path.join(c, "sorgente", "app.py")):
            return os.path.abspath(c)
        print("  li' dentro non c'e' sorgente\\app.py, riprova.")


def elenco_bucket(s3, cfg, prefisso):
    """{nome: dimensione} dei file sotto il prefisso."""
    out = {}
    for pagina in s3.get_paginator("list_objects_v2").paginate(
            Bucket=cfg["bucket"], Prefix=prefisso):
        for o in pagina.get("Contents", []):
            out[o["Key"][len(prefisso):]] = o["Size"]
    return out


def carica_file(s3, cfg, path, key, tipo=None):
    s3.upload_file(path, cfg["bucket"], key,
                   ExtraArgs={"ContentType": tipo or r2_storage.tipo_file(key)})


def zippa(cartella, dest, radice=""):
    """Zip della cartella; con 'radice' i file finiscono dentro quella cartella nello zip."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for base, cartelle, files in os.walk(cartella):
            cartelle[:] = [c for c in cartelle if c not in ESCLUSI_ZIP]
            for f in files:
                if f in FILE_ESCLUSI_ZIP or f.endswith((".pyc", ".part")):
                    continue
                p = os.path.join(base, f)
                rel = os.path.relpath(p, cartella)
                z.write(p, os.path.join(radice, rel) if radice else rel)


def main():
    cfg = r2_storage.leggi_config(SITE_DIR)
    if not cfg:
        print("Cloudflare R2 non e' configurato: lancia prima \"Migra su R2.bat\" "
              "oppure configura il Gestore Sito (pulsante Cloudflare R2).")
        return 1
    s3 = r2_storage.client(cfg)
    app = trova_cartella_canti()
    print(f"Gestore Canti: {app}\n")
    online = elenco_bucket(s3, cfg, BASI + "/")
    online_minuscole = {n.lower() for n in online}

    # 1. testi
    testi_dir = os.path.join(app, "testi")
    caricati = 0
    for f in sorted(os.listdir(testi_dir)) if os.path.isdir(testi_dir) else []:
        if not f.lower().endswith(".docx") or f.startswith("~$"):
            continue
        p = os.path.join(testi_dir, f)
        if online.get(f) == os.path.getsize(p):
            continue
        print(f"  carico testo: {f}")
        carica_file(s3, cfg, p, f"{BASI}/{f}",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        caricati += 1
    print(f"Testi: {caricati} caricati.")

    # basi presenti solo in locale: solo un avviso
    canti_dir = os.path.join(app, "canti")
    solo_locali = [f for f in sorted(os.listdir(canti_dir)) if os.path.isdir(canti_dir)
                   and f.lower().endswith(".mp3") and f.lower() not in online_minuscole] \
        if os.path.isdir(canti_dir) else []
    if solo_locali:
        print(f"\nATTENZIONE: {len(solo_locali)} basi sono in locale ma non su R2 "
              "(caricale dal Gestore Sito, «Aggiungi base»):")
        for f in solo_locali:
            print(f"  {f}")

    # 2. programma
    sorgente = os.path.join(app, "sorgente")
    with open(os.path.join(sorgente, "app.py"), encoding="utf-8") as fh:
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', fh.read(), re.M)
    versione = m.group(1) if m else ""
    try:
        remota = s3.get_object(Bucket=cfg["bucket"], Key=f"{BASI}/versione.txt")["Body"] \
            .read().decode("utf-8", "ignore").strip()
    except Exception:
        remota = ""
    print(f"\nVersione del programma: locale {versione or '?'}, online {remota or 'nessuna'}")
    tmp = tempfile.mkdtemp(prefix="pubblica_canti_")
    if versione and (versione != remota or "--forza" in sys.argv):
        z = os.path.join(tmp, "programma_update.zip")
        zippa(sorgente, z)
        print("  carico programma_update.zip...")
        carica_file(s3, cfg, z, f"{BASI}/programma_update.zip")
        # versione.txt per ultimo: cosi' chi vede la versione nuova trova gia' lo zip
        s3.put_object(Bucket=cfg["bucket"], Key=f"{BASI}/versione.txt",
                      Body=versione.encode("utf-8"),
                      ContentType="text/plain; charset=utf-8",
                      CacheControl="no-cache, max-age=0")
        print(f"  pubblicata la versione {versione}.")
    else:
        print("  programma gia' aggiornato online (usa --forza per ricaricarlo).")

    # 3. zip completo
    if "MusicLibraryApp.zip" not in online or "--completo" in sys.argv:
        print("\nPreparo lo zip completo (puo' richiedere qualche minuto)...")
        z = os.path.join(tmp, "MusicLibraryApp.zip")
        zippa(app, z, "MusicLibraryApp")
        print(f"  carico MusicLibraryApp.zip ({os.path.getsize(z) // (1024 * 1024)} MB)...")
        carica_file(s3, cfg, z, f"{BASI}/MusicLibraryApp.zip")
        try:
            os.remove(z)
        except OSError:
            pass

    # 4. elenchi
    print()
    for coll in (BASI, GUIDA):
        n = r2_storage.aggiorna_indice(cfg, coll)
        print(f"Elenco {coll}/indice.json aggiornato: {n} file.")
    print("\nFinito.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrotto.")
        sys.exit(1)
