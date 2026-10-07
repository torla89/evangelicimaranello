"""
Archivio dei media del sito su Cloudflare R2 (compatibile S3).

La configurazione sta nel file locale ".r2config" (escluso da git):
    {"endpoint": "https://<account>.r2.cloudflarestorage.com",
     "access_key": "...", "secret_key": "...",
     "bucket": "evangelicimaranello-media",
     "public_url": "https://pub-xxxx.r2.dev"}

I file vengono salvati come "<collezione>/<nome file>", la stessa struttura
che avevano su Archive.org.
"""
import io
import json
import mimetypes
import os
from urllib.parse import quote, urlsplit

CONFIG_NAME = ".r2config"
CAMPI = ("endpoint", "access_key", "secret_key", "bucket", "public_url")

_TIPI = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".ogg": "audio/ogg", ".mp4": "video/mp4",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".pdf": "application/pdf", ".zip": "application/zip",
    ".txt": "text/plain; charset=utf-8",
}


def tipo_file(nome: str, predefinito: str = "application/octet-stream") -> str:
    ext = os.path.splitext(nome)[1].lower()
    return _TIPI.get(ext) or mimetypes.guess_type(nome)[0] or predefinito


def pulisci_config(cfg: dict) -> dict:
    """Sistema i valori incollati dall'utente (spazi, barre finali, ecc.)."""
    cfg = {k: str(cfg.get(k, "")).strip() for k in CAMPI}
    ep = cfg["endpoint"]
    if ep and not ep.startswith("http"):
        ep = "https://" + ep
    if ep:
        # Cloudflare a volte mostra l'endpoint con "/nome-bucket" in fondo: va tolto
        p = urlsplit(ep)
        ep = f"{p.scheme}://{p.netloc}"
    cfg["endpoint"] = ep
    pu = cfg["public_url"].rstrip("/")
    if pu and not pu.startswith("http"):
        pu = "https://" + pu
    cfg["public_url"] = pu
    return cfg


def leggi_config(site_dir: str):
    """Restituisce la configurazione, oppure None se R2 non e' configurato."""
    path = os.path.join(site_dir, CONFIG_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            cfg = pulisci_config(json.load(f))
    except Exception:
        return None
    return cfg if all(cfg.get(k) for k in CAMPI) else None


def salva_config(site_dir: str, cfg: dict) -> dict:
    cfg = pulisci_config(cfg)
    with open(os.path.join(site_dir, CONFIG_NAME), "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def client(cfg: dict):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=cfg["endpoint"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name="auto",
        config=Config(signature_version="s3v4",
                      retries={"max_attempts": 5, "mode": "standard"}),
    )


def url_pubblico(cfg: dict, collezione: str, filename: str) -> str:
    return f"{cfg['public_url']}/{quote(collezione, safe='')}/{quote(filename, safe='')}"


def carica_dati(cfg: dict, collezione: str, filename: str, data: bytes,
                content_type: str = "", progresso=None) -> str:
    """Carica i byte su R2 e restituisce l'indirizzo pubblico del file.
    progresso(n) viene chiamata con il numero di byte inviati a ogni blocco."""
    key = f"{collezione}/{filename}"
    extra = {"ContentType": content_type or tipo_file(filename)}
    client(cfg).upload_fileobj(io.BytesIO(data), cfg["bucket"], key,
                               ExtraArgs=extra, Callback=progresso)
    return url_pubblico(cfg, collezione, filename)


def prova(cfg: dict) -> None:
    """Carica un file di prova e lo rilegge dal link pubblico; errore se non va."""
    import requests
    s3 = client(cfg)
    s3.put_object(Bucket=cfg["bucket"], Key="_prova/prova.txt", Body=b"ok",
                  ContentType="text/plain")
    r = requests.get(f"{cfg['public_url']}/_prova/prova.txt", timeout=30)
    if r.status_code != 200 or r.text != "ok":
        raise IOError(f"caricamento riuscito, ma l'indirizzo pubblico risponde "
                      f"HTTP {r.status_code}: controlla l'indirizzo pubblico")
    try:
        s3.delete_object(Bucket=cfg["bucket"], Key="_prova/prova.txt")
    except Exception:
        pass


# ── PAGINA MUSICA ─────────────────────────────────────────────
# musica.html contiene il nome della collezione e l'elenco dei brani: R2 non
# ha un elenco pubblico, quindi l'elenco va riscritto nella pagina leggendo
# il contenuto del bucket.
import re as _re

_RE_ID = _re.compile(r'const ARCHIVE_ID\s*=\s*"([^"]+)";')
_RE_BASE = _re.compile(r'const ARCHIVE_BASE\s*=\s*[^\n]*;')
_RE_ELENCO = _re.compile(r'const BRANI_FALLBACK = \[.*?\];', _re.S)
_RE_FETCH = _re.compile(r"(async function caricaElencoBrani\(\) \{\n)(?!  if \(!ARCHIVE_BASE)")


def collezione_pagina_musica(site_dir: str) -> str:
    """Nome della collezione usata da musica.html ('' se non riconosciuta)."""
    try:
        with open(os.path.join(site_dir, "musica.html"), encoding="utf-8") as f:
            m = _RE_ID.search(f.read())
        return m.group(1) if m else ""
    except Exception:
        return ""


def aggiorna_pagina_musica(site_dir: str, cfg: dict) -> int:
    """Riscrive in musica.html l'elenco dei brani presenti nel bucket.
    Restituisce il numero di brani; errore se la pagina non e' riconosciuta."""
    path = os.path.join(site_dir, "musica.html")
    with open(path, encoding="utf-8", newline="") as f:
        testo = f.read()
    m_id = _RE_ID.search(testo)
    if not (m_id and _RE_BASE.search(testo) and _RE_ELENCO.search(testo)):
        raise ValueError("struttura di musica.html non riconosciuta")
    coll = m_id.group(1)
    prefisso = coll + "/"
    brani = []
    for pagina in client(cfg).get_paginator("list_objects_v2").paginate(
            Bucket=cfg["bucket"], Prefix=prefisso):
        for o in pagina.get("Contents", []):
            nome = o["Key"][len(prefisso):]
            if nome.lower().endswith(".mp3"):
                brani.append(nome)
    brani.sort()
    if not brani:
        raise ValueError(f"nessun brano nel bucket sotto '{prefisso}': "
                         "completa prima la migrazione (Migra su R2.bat)")
    base = f"{cfg['public_url']}/{quote(coll, safe='')}/"
    righe = ",\n".join("  " + json.dumps(b, ensure_ascii=False) for b in brani)
    nuovo = _RE_BASE.sub(lambda m: f'const ARCHIVE_BASE = "{base}";', testo, count=1)
    nuovo = _RE_ELENCO.sub(lambda m: "const BRANI_FALLBACK = [\n" + righe + "\n];", nuovo, count=1)
    nuovo = _RE_FETCH.sub(
        lambda m: m.group(1) + "  if (!ARCHIVE_BASE.includes('archive.org')) "
                               "{ renderBrani(BRANI_FALLBACK); return; }\n",
        nuovo, count=1)
    if nuovo != testo:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(nuovo)
    return len(brani)
