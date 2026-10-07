"""
Sposta i media del sito da Archive.org a Cloudflare R2.

Cosa fa, in ordine:
  1. alla prima esecuzione chiede i dati di R2 e li salva in ".r2config"
  2. cerca nelle pagine del sito tutti i link "archive.org/download/..."
  3. scarica ogni file in una cartella locale (resta come copia di sicurezza)
  4. lo carica su R2 con lo stesso nome e controlla che il link pubblico risponda
  5. solo alla fine, e solo dopo conferma, sostituisce i link nelle pagine

Si puo' interrompere e rilanciare quando si vuole: riparte da dove era arrivato.
Non pubblica nulla: dopo, il sito si pubblica dal Gestore Sito come sempre.

Uso:
    python migra_su_r2.py            migrazione completa
    python migra_su_r2.py --elenco   mostra solo i file trovati, senza fare nulla
"""
import glob
import json
import os
import re
import sys
import time
from urllib.parse import unquote

import r2_storage

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(os.path.expanduser("~"), "media_evangelicimaranello")
VECCHIO = "https://archive.org/download/"
RE_URL = re.compile(r"https?://archive\.org/download/([^\"'\s<>\\)]+)")
# file che NON vanno toccati (il programma stesso, registri, copie)
ESCLUSI = {"gestore.html", "upload_log.txt"}
CARTELLE_ESCLUSE = {".git", "backup", "build", "dist", "build_tmp", "__pycache__"}


def file_del_sito():
    trovati = []
    for radice, cartelle, files in os.walk(SITE_DIR):
        cartelle[:] = [c for c in cartelle if c not in CARTELLE_ESCLUSE]
        for f in files:
            if f in ESCLUSI or not f.lower().endswith((".html", ".json")):
                continue
            trovati.append(os.path.join(radice, f))
    return sorted(trovati)


def leggi(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def raccogli_link():
    """{resto_del_link: [file in cui compare]}; resto = 'Collezione/nome%20file.mp3'"""
    link = {}
    for path in file_del_sito():
        try:
            testo = leggi(path)
        except Exception as e:
            print(f"  (salto {os.path.relpath(path, SITE_DIR)}: {e})")
            continue
        for m in RE_URL.finditer(testo):
            resto = m.group(1)
            if "{" in resto or "/" not in resto or resto.endswith("/"):
                continue
            link.setdefault(resto, set()).add(os.path.relpath(path, SITE_DIR))
    return link


def percorso_locale(key):
    parti = [re.sub(r'[<>:"|?*\\]', "_", p) for p in key.split("/")]
    return os.path.join(MEDIA_DIR, *parti)


def scarica(resto, dest):
    import requests
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return
    parz = dest + ".part"
    ultimo = None
    for tentativo in range(1, 7):
        try:
            with requests.get(VECCHIO + resto, stream=True, timeout=(30, 300)) as r:
                if r.status_code == 404:
                    # il file non esiste su Archive.org: inutile riprovare
                    raise FileNotFoundError("il file non esiste su Archive.org (link gia' rotto)")
                r.raise_for_status()
                atteso = int(r.headers.get("Content-Length") or 0)
                with open(parz, "wb") as f:
                    for blocco in r.iter_content(1024 * 256):
                        f.write(blocco)
            if atteso and os.path.getsize(parz) != atteso:
                raise IOError("download incompleto")
            if os.path.getsize(parz) == 0:
                raise IOError("file vuoto")
            os.replace(parz, dest)
            return
        except FileNotFoundError:
            raise
        except Exception as e:
            ultimo = e
            print(f"      tentativo {tentativo} fallito ({e}); riprovo...")
            time.sleep(min(60, 5 * tentativo))
    raise RuntimeError(f"download non riuscito: {ultimo}")


def carica(s3, cfg, key, path):
    dim = os.path.getsize(path)
    try:
        h = s3.head_object(Bucket=cfg["bucket"], Key=key)
        if h.get("ContentLength") == dim:
            return
    except Exception:
        pass
    s3.upload_file(path, cfg["bucket"], key,
                   ExtraArgs={"ContentType": r2_storage.tipo_file(key)})


def verifica_pubblico(cfg, resto, dim):
    import requests
    url = f"{cfg['public_url']}/{resto}"
    for tentativo in range(5):
        r = requests.head(url, timeout=30, allow_redirects=True)
        if r.status_code == 200:
            lung = int(r.headers.get("Content-Length") or dim)
            if lung != dim:
                raise IOError(f"dimensione diversa ({lung} invece di {dim})")
            return
        if r.status_code in (429, 500, 502, 503):
            time.sleep(5 * (tentativo + 1))
            continue
        raise IOError(f"il link pubblico risponde HTTP {r.status_code}")
    raise IOError("il link pubblico non risponde")


def chiedi_config():
    print("\nConfigurazione di Cloudflare R2 (si fa una volta sola).")
    print("Incolla i valori che hai salvato quando hai creato il token.\n")
    cfg = {
        "endpoint": input("Endpoint S3 (https://....r2.cloudflarestorage.com): "),
        "access_key": input("Access Key ID: "),
        "secret_key": input("Secret Access Key: "),
        "bucket": input("Nome del bucket [evangelicimaranello-media]: ") or "evangelicimaranello-media",
        "public_url": input("Indirizzo pubblico (https://pub-....r2.dev oppure il tuo dominio): "),
    }
    return r2_storage.salva_config(SITE_DIR, cfg)


def prova_config(cfg):
    """Carica un file di prova e lo rilegge dal link pubblico."""
    import requests
    s3 = r2_storage.client(cfg)
    s3.put_object(Bucket=cfg["bucket"], Key="_prova/prova.txt", Body=b"ok",
                  ContentType="text/plain")
    r = requests.get(f"{cfg['public_url']}/_prova/prova.txt", timeout=30)
    if r.status_code != 200 or r.text != "ok":
        raise IOError(f"caricamento riuscito, ma il link pubblico risponde HTTP {r.status_code}: "
                      "controlla l'indirizzo pubblico")
    try:
        s3.delete_object(Bucket=cfg["bucket"], Key="_prova/prova.txt")
    except Exception:
        pass
    return s3


def sostituisci_link(cfg, fatti):
    cambiati = 0
    for path in file_del_sito():
        testo = leggi(path)

        def cambia(m):
            return f"{cfg['public_url']}/{m.group(1)}" if m.group(1) in fatti else m.group(0)

        nuovo = RE_URL.sub(cambia, testo)
        if nuovo != testo:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(nuovo)
            cambiati += 1
            print(f"  aggiornato {os.path.relpath(path, SITE_DIR)}")
    return cambiati


def collega():
    """Chiede (se serve) i dati di R2 e prova il collegamento. -> (s3, cfg) o None"""
    cfg = r2_storage.leggi_config(SITE_DIR)
    while True:
        if not cfg:
            cfg = chiedi_config()
        try:
            print("\nProvo il collegamento a R2...")
            s3 = prova_config(cfg)
            print("Collegamento a R2 funzionante.")
            return s3, cfg
        except Exception as e:
            print(f"\nERRORE: {e}")
            if input("Vuoi reinserire i dati? (s/n): ").strip().lower() != "s":
                return None
            cfg = None


def migra_gruppo(s3, cfg, elenco, facoltativi=()):
    """Scarica, carica e verifica ogni file. -> (fatti, errori)
    I 'facoltativi' sono file che potrebbero non esistere: se mancano non e' un errore."""
    fatti, errori = set(), {}
    for i, resto in enumerate(elenco, 1):
        key = unquote(resto)
        print(f"[{i}/{len(elenco)}] {key}")
        try:
            locale = percorso_locale(key)
            scarica(resto, locale)
            carica(s3, cfg, key, locale)
            verifica_pubblico(cfg, resto, os.path.getsize(locale))
            fatti.add(resto)
        except FileNotFoundError as e:
            if resto in facoltativi:
                print("      (non presente, salto)")
            else:
                errori[resto] = str(e)
                print(f"      ERRORE: {e}")
        except Exception as e:
            errori[resto] = str(e)
            print(f"      ERRORE: {e}")
    return fatti, errori


def migra_link(s3, cfg, link):
    print(f"\nCopia locale dei file in: {MEDIA_DIR}\n")
    elenco = sorted(link)
    fatti, errori = migra_gruppo(s3, cfg, elenco)

    print(f"\nFile migrati e verificati: {len(fatti)} su {len(elenco)}")
    if errori:
        print(f"File NON migrati: {len(errori)}")
        for resto, e in errori.items():
            print(f"  {unquote(resto)}: {e}")
        print("\nI link di questi file restano su Archive.org. "
              "Rilancia il programma per riprovare solo quelli.")
    if not fatti:
        return
    domanda = ("Sostituisco nelle pagine i link dei file migrati? (s/n): " if errori
               else "Tutto a posto. Sostituisco i link nelle pagine del sito? (s/n): ")
    if input("\n" + domanda).strip().lower() != "s":
        print("Nessun link modificato. Puoi rilanciare il programma quando vuoi.")
        return
    n = sostituisci_link(cfg, fatti)
    print(f"\nFatto: {n} file del sito aggiornati.")


# ── PAGINA MUSICA ─────────────────────────────────────────────
# La pagina musica.html non ha un link per ogni brano: ha il nome di una
# collezione e un elenco di file. Qui si sposta la collezione su R2 e si
# riscrive l'elenco dentro la pagina. Rilanciando il programma l'elenco viene
# aggiornato con quello che c'e' nel bucket (per aggiungere brani nuovi).
PAGINA_MUSICA = os.path.join(SITE_DIR, "musica.html")
RE_ID = re.compile(r'const ARCHIVE_ID\s*=\s*"([^"]+)";')
RE_BASE = re.compile(r'const ARCHIVE_BASE\s*=\s*[^\n]*;')
RE_ELENCO = re.compile(r'const BRANI_FALLBACK = \[.*?\];', re.S)
RE_FETCH = re.compile(r"(async function caricaElencoBrani\(\) \{\n)(?!  if \(!ARCHIVE_BASE)")
EST_AUDIO = (".mp3",)
EST_EXTRA = (".txt", ".jpg", ".jpeg", ".png")


def _elenco_r2(s3, cfg, prefisso):
    nomi = []
    for pagina in s3.get_paginator("list_objects_v2").paginate(
            Bucket=cfg["bucket"], Prefix=prefisso):
        for o in pagina.get("Contents", []):
            nomi.append(o["Key"][len(prefisso):])
    return nomi


def _scrivi_pagina_musica(cfg, coll, brani):
    from urllib.parse import quote
    testo = leggi(PAGINA_MUSICA)
    base = f"{cfg['public_url']}/{quote(coll, safe='')}/"
    righe = ",\n".join("  " + json.dumps(b, ensure_ascii=False) for b in brani)
    testo = RE_BASE.sub(lambda m: f'const ARCHIVE_BASE = "{base}";', testo, count=1)
    testo = RE_ELENCO.sub(lambda m: "const BRANI_FALLBACK = [\n" + righe + "\n];", testo, count=1)
    # con R2 l'elenco e' quello scritto qui sopra: niente richiesta ad archive.org
    testo = RE_FETCH.sub(
        lambda m: m.group(1) + "  if (!ARCHIVE_BASE.includes('archive.org')) "
                               "{ renderBrani(BRANI_FALLBACK); return; }\n",
        testo, count=1)
    with open(PAGINA_MUSICA, "w", encoding="utf-8", newline="") as f:
        f.write(testo)


def pagina_musica(s3, cfg):
    from urllib.parse import quote
    if not os.path.exists(PAGINA_MUSICA):
        return
    testo = leggi(PAGINA_MUSICA)
    m_id, m_base, m_el = RE_ID.search(testo), RE_BASE.search(testo), RE_ELENCO.search(testo)
    if not (m_id and m_base and m_el):
        print("\nPagina Musica: struttura non riconosciuta, la lascio com'e'.")
        return
    coll = m_id.group(1)
    prefisso = coll + "/"
    print(f"\n=== Pagina Musica (collezione {coll}) ===")

    if "archive.org" not in m_base.group(0):
        # gia' passata a R2: aggiorno solo l'elenco con il contenuto del bucket
        brani = sorted(n for n in _elenco_r2(s3, cfg, prefisso) if n.lower().endswith(EST_AUDIO))
        if not brani:
            print("Nessun brano trovato nel bucket: non modifico la pagina.")
            return
        vecchi = json.loads("[" + m_el.group(0).split("[", 1)[1].rsplit("]", 1)[0] + "]")
        if brani == vecchi:
            print(f"Elenco gia' aggiornato ({len(brani)} brani).")
            return
        _scrivi_pagina_musica(cfg, coll, brani)
        print(f"Elenco aggiornato: {len(brani)} brani (prima {len(vecchi)}).")
        return

    # ancora su Archive.org: raccolgo i nomi dei file
    try:
        vecchi = json.loads("[" + m_el.group(0).split("[", 1)[1].rsplit("]", 1)[0] + "]")
    except Exception:
        vecchi = []
    sicuri, forse = set(vecchi), set()
    try:
        import requests
        dati = requests.get(f"https://archive.org/metadata/{coll}", timeout=60).json()
        for f in dati.get("files", []):
            nome = f.get("name", "")
            if f.get("source") != "original":
                continue
            if nome.lower().endswith(EST_AUDIO):
                sicuri.add(nome)
            elif nome.lower().endswith(EST_EXTRA):
                forse.add(nome)
    except Exception as e:
        print(f"  (elenco di Archive.org non leggibile: {e}; uso quello della pagina)")
    # testi e copertine hanno lo stesso nome del brano: li provo tutti
    for b in sicuri:
        radice = os.path.splitext(b)[0]
        for est in EST_EXTRA:
            forse.add(radice + est)
    forse -= sicuri

    def resto(n):
        return f"{quote(coll, safe='')}/{quote(n, safe='')}"

    elenco = [resto(n) for n in sorted(sicuri)] + [resto(n) for n in sorted(forse)]
    facoltativi = {resto(n) for n in forse}
    print(f"Brani: {len(sicuri)}; testi e copertine da cercare: {len(forse)}\n")
    fatti, errori = migra_gruppo(s3, cfg, elenco, facoltativi)

    brani_ok = sorted(n for n in sicuri if resto(n) in fatti)
    print(f"\nBrani migrati: {len(brani_ok)} su {len(sicuri)}")
    if errori:
        print(f"File NON migrati: {len(errori)}")
        for r, e in errori.items():
            print(f"  {unquote(r)}: {e}")
    if not brani_ok:
        print("\nNessun brano migrato: la pagina Musica resta com'e'.")
        return
    mancanti = sorted(n for n in sicuri if resto(n) not in fatti)
    if mancanti:
        print(f"\nATTENZIONE: {len(mancanti)} brani non sono arrivati su R2:")
        for n in mancanti:
            print(f"  {n}")
        print("Se passi la pagina a R2 adesso, questi brani spariscono dall'elenco.\n"
              "(Se invece vuoi riprovarli, rispondi n e rilancia il programma piu' tardi.)")
        domanda = f"Passo la pagina Musica a R2 SENZA questi {len(mancanti)} brani? (s/n): "
    else:
        domanda = "Passo la pagina Musica a R2? (s/n): "
    if input("\n" + domanda).strip().lower() != "s":
        print("Pagina Musica non modificata.")
        return
    _scrivi_pagina_musica(cfg, coll, brani_ok)
    print("Pagina Musica aggiornata.")


def main():
    link = raccogli_link()
    per_coll = {}
    for resto in link:
        per_coll[resto.split("/")[0]] = per_coll.get(resto.split("/")[0], 0) + 1
    print(f"Link ad Archive.org ancora presenti nelle pagine: {len(link)}")
    for c, n in sorted(per_coll.items()):
        print(f"  {c}: {n}")
    if "--elenco" in sys.argv:
        return 0

    collegamento = collega()
    if not collegamento:
        return 1
    s3, cfg = collegamento
    os.makedirs(MEDIA_DIR, exist_ok=True)

    if link:
        migra_link(s3, cfg, link)
    pagina_musica(s3, cfg)

    print("\nFinito. Controlla il sito in locale, poi pubblica dal Gestore Sito come al solito.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrotto. Rilancia il programma per riprendere.")
        sys.exit(1)
