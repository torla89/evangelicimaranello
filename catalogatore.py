# -*- coding: utf-8 -*-
"""
catalogatore.py — caricamento automatico dei libri da una cartella di foto.

Lo usano sia il Gestore Sito sia il Gestore Biblioteca: il file e' identico in
    Gestore sito/evangelicimaranello/catalogatore.py
    Gestore biblioteca/sorgente/catalogatore.py
Se lo modifichi in uno dei due posti, copialo anche nell'altro.

Tutto gratuito e sul computer, senza servizi a pagamento:
  1. mette le foto nell'ordine in cui sono state scattate;
  2. le raddrizza: prima con i dati EXIF del telefono, poi provando a leggere
     il testo nei vari versi e tenendo quello che si legge meglio;
  3. accoppia fronte e retro: dal nome del file quando lo dice ("... fronte",
     "... retro"), altrimenti dall'ordine di scatto e da com'e' fatta la
     pagina (il retro ha piu' testo minuto, il prezzo, il codice a barre);
  4. legge il testo con Tesseract e cerca l'ISBN nel codice a barre e nel testo;
  5. con l'ISBN chiede i dati a Google Books e a Open Library; senza ISBN
     prova una ricerca per titolo, che resta un suggerimento da controllare;
  6. ricava titolo, autore, editore, anno, genere e sintesi dal testo;
  7. segnala editori cattolici, libri gia' a catalogo e retri mancanti;
  8. se nella cartella c'e' un file di testo "titolo  numero" (come
     quantita.py) ne prende il numero di copie.

Nulla viene pubblicato da qui: il risultato passa dalla schermata di
revisione, dove si corregge e si conferma.
"""

import base64
import concurrent.futures
import difflib
import io
import json
import os
import re
import shutil
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime

try:
    from PIL import Image, ImageOps, ImageStat
except ImportError:          # senza Pillow non si fa nulla: lo dice la pagina
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import zxingcpp
except ImportError:
    zxingcpp = None


ESTENSIONI = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
LATO_OCR = 1500          # px: abbastanza per il testo minuto delle quarte
LATO_SITO = 900          # px: come le copertine gia' pubblicate
LATO_MINI = 340          # px: anteprime della schermata di revisione
TIPI_LIBRO = ["Libro", "Libretto", "Opuscolo", "Rivista", "Calendario", "Bibbia", "Altro"]


def tipo_da(pagine, titolo=""):
    """Una prima ipotesi sul tipo di pubblicazione, da correggere nella revisione."""
    t = chiave(titolo)
    if t.startswith("calendario"):
        return "Calendario"
    if pagine and pagine <= 40:
        return "Opuscolo"
    if pagine and pagine <= 100:
        return "Libretto"
    return "Libro"


TESSERACT_SETUP_URL = ("https://github.com/UB-Mannheim/tesseract/releases/download/"
                       "v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe")


# ══════════════════════════════════════════════════════════════════════
#  Testo: normalizzazione e somiglianze
# ══════════════════════════════════════════════════════════════════════
def senza_accenti(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def chiave(s):
    """Forma confrontabile: minuscole, niente accenti ne' punteggiatura."""
    s = senza_accenti(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def somiglianza(a, b):
    a, b = chiave(a), chiave(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def slug(s):
    """Nome di file: la stessa regola usata per le copertine gia' nel sito."""
    s = re.sub(r"['\u2019\u02bc`]", "-", s or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return re.sub(r"-{2,}", "-", s) or "libro"


PAROLE_MAIUSCOLE = {
    "dio": "Dio", "gesu": "Gesù", "gesù": "Gesù", "cristo": "Cristo",
    "bibbia": "Bibbia", "vangelo": "Vangelo", "vangeli": "Vangeli",
    "evangeli": "Evangeli", "spirito": "Spirito", "chiesa": "Chiesa",
}


def titolo_leggibile(s):
    """Da "gesu è l'unica via" a "Gesù è l'unica via"."""
    s = re.sub(r"\s+", " ", (s or "").replace("_", " ")).strip(" .-")
    if not s:
        return ""
    if s.isupper() and len(s) > 6 and " " in s:        # "IL VERO DISCEPOLO", non "JHWH"
        s = s.lower()
    parole = s.split(" ")
    for i, p in enumerate(parole):
        base = re.sub(r"[^\wàèéìòù]", "", p.lower())
        if base in PAROLE_MAIUSCOLE and (i == 0 or base in ("dio", "gesu", "gesù", "cristo", "bibbia")):
            parole[i] = p.lower().replace(base, PAROLE_MAIUSCOLE[base])
    s = " ".join(parole)
    return s[0].upper() + s[1:]


def accenti_da(titolo, testo_ocr):
    """
    Il nome del file e' scritto di corsa ("gesu e l'unica via"): se la stessa
    frase compare nel testo letto dalla copertina, ne prende gli accenti.
    """
    if not titolo or not testo_ocr:
        return titolo
    # solo parole di almeno tre lettere: "e" ed "è" sono due parole diverse
    # e il testo di una quarta contiene sempre qualche "è"
    accentate = {}
    for w in re.findall(r"[A-Za-zÀ-ÿ]+", testo_ocr):
        if w != senza_accenti(w) and len(w) >= 3:
            accentate[chiave(w)] = w.lower()
    out = []
    for w in titolo.split(" "):
        k = chiave(w)
        if len(k) >= 3 and k in accentate and w.lower() == senza_accenti(w).lower():
            out.append(accentate[k] if w[:1].islower() else accentate[k].capitalize())
        else:
            out.append(w)
    return " ".join(out)


# ══════════════════════════════════════════════════════════════════════
#  Tesseract
# ══════════════════════════════════════════════════════════════════════
def trova_tesseract(cartelle_extra=()):
    """
    Dove sta tesseract.exe. Oltre ai posti soliti di Windows guarda in
    "strumenti\\Tesseract-OCR" accanto ai programmi, cosi' la cartella
    Gestione Chiesa resta portabile.
    """
    candidati = [os.environ.get("TESSERACT_CMD", "")]
    for base in cartelle_extra:
        if base:
            candidati += [os.path.join(base, "strumenti", "Tesseract-OCR", "tesseract.exe"),
                          os.path.join(base, "Tesseract-OCR", "tesseract.exe")]
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        radice = os.environ.get(var, "")
        if radice:
            candidati += [os.path.join(radice, "Tesseract-OCR", "tesseract.exe"),
                          os.path.join(radice, "Programs", "Tesseract-OCR", "tesseract.exe")]
    trovato = shutil.which("tesseract")
    if trovato:
        candidati.append(trovato)
    for c in candidati:
        if c and os.path.isfile(c):
            return c
    return ""


def trova_tessdata(cartelle_extra=()):
    """Cartella con ita.traineddata scaricata dal build (se c'e')."""
    for base in cartelle_extra:
        if not base:
            continue
        for d in (os.path.join(base, "strumenti", "tessdata"), os.path.join(base, "tessdata")):
            if os.path.isfile(os.path.join(d, "ita.traineddata")):
                return d
    return ""


class LettoreOCR:
    def __init__(self, cartelle_extra=()):
        self.cmd = trova_tesseract(cartelle_extra) if pytesseract else ""
        self.tessdata = trova_tessdata(cartelle_extra)
        self.lingua = "eng"
        self.pronto = False
        if not self.cmd:
            return
        pytesseract.pytesseract.tesseract_cmd = self.cmd
        try:
            lingue = set(pytesseract.get_languages(config=self._cfg("")))
        except Exception:
            lingue = set()
        if "ita" in lingue:
            self.lingua = "ita"
        elif not lingue:
            return
        self.pronto = True

    def _cfg(self, extra):
        cfg = extra
        if self.tessdata:
            cfg += ' --tessdata-dir "%s"' % self.tessdata
        return cfg.strip()

    def parole(self, img, psm=3, grigio=False):
        """
        Elenco delle parole lette, con fiducia e dimensione.

        grigio=True passa l'immagine in scala di grigi col contrasto tirato:
        serve sulle copertine illustrate, dove a colori Tesseract non vede
        quasi niente (zero parole su "Il vero discepolo"). Sui retri invece
        fa danni (da 121 a 20 parole su "E se Dio ci fosse davvero"), per
        questo la lettura principale resta a colori.
        """
        if not self.pronto:
            return []
        if grigio:
            img = ImageOps.autocontrast(img.convert("L"), cutoff=1)
        try:
            d = pytesseract.image_to_data(img, lang=self.lingua, config=self._cfg("--psm %d" % psm),
                                          output_type=pytesseract.Output.DICT, timeout=60)
        except Exception:
            return []
        out = []
        for i, t in enumerate(d.get("text", [])):
            t = (t or "").strip()
            try:
                c = float(d["conf"][i])
            except (TypeError, ValueError):
                c = -1
            if not t or c < 0:
                continue
            out.append({"t": t, "c": c, "h": d["height"][i], "x": d["left"][i], "y": d["top"][i],
                        "w": d["width"][i], "b": d["block_num"][i], "p": d["par_num"][i],
                        "r": d["line_num"][i]})
        return out


def punteggio_lettura(parole):
    """Quanto e' leggibile: lettere delle parole sensate lette con fiducia."""
    tot = 0
    for p in parole:
        t = p["t"]
        if p["c"] < 70 or len(t) < 3:
            continue
        lettere = sum(ch.isalpha() for ch in t)
        if lettere / len(t) < 0.8:
            continue
        if not re.search(r"[aeiouàèéìòùAEIOU]", t):
            continue
        tot += lettere
    return tot


def righe(parole):
    """Raggruppa le parole in righe, nell'ordine di lettura."""
    gruppi = {}
    for p in parole:
        gruppi.setdefault((p["b"], p["p"], p["r"]), []).append(p)
    out = []
    for k in sorted(gruppi):
        ws = sorted(gruppi[k], key=lambda p: p["x"])
        testo = " ".join(w["t"] for w in ws)
        altezze = sorted(w["h"] for w in ws)
        out.append({"t": testo, "h": altezze[len(altezze) // 2],
                    "c": sum(w["c"] for w in ws) / len(ws),
                    "y": min(w["y"] for w in ws), "b": k[0], "p": k[1]})
    return out


def testo_da_parole(parole):
    """Testo a paragrafi, con le parole spezzate a fine riga ricucite."""
    pars = {}
    for r in righe(parole):
        pars.setdefault((r["b"], r["p"]), []).append(r)
    blocchi = []
    for k in sorted(pars):
        testo = ""
        for r in pars[k]:
            t = r["t"]
            if testo.endswith("-") and t[:1].islower():
                testo = testo[:-1] + t
            else:
                testo = (testo + " " + t).strip()
        blocchi.append(testo)
    return "\n\n".join(b for b in blocchi if b)


# ══════════════════════════════════════════════════════════════════════
#  Immagini
# ══════════════════════════════════════════════════════════════════════
def apri(percorso):
    img = Image.open(percorso)
    img = ImageOps.exif_transpose(img)          # il verso registrato dal telefono
    if img.mode not in ("RGB", "L"):
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            fondo = Image.new("RGB", img.size, (255, 255, 255))
            fondo.paste(img, mask=img.split()[-1])
            img = fondo
        else:
            img = img.convert("RGB")
    return img


def ruotata(img, gradi_orari):
    g = gradi_orari % 360
    if g == 90:
        return img.transpose(Image.ROTATE_270)
    if g == 180:
        return img.transpose(Image.ROTATE_180)
    if g == 270:
        return img.transpose(Image.ROTATE_90)
    return img


def ridotta(img, lato):
    img = img.copy()
    img.thumbnail((lato, lato), Image.LANCZOS)
    return img


def ha_exif_verso(percorso):
    try:
        with Image.open(percorso) as im:
            return im.getexif().get(274) not in (None, 0)
    except Exception:
        return False


def data_scatto(percorso):
    """Data dello scatto: EXIF, poi il nome WhatsApp, poi la data del file."""
    try:
        with Image.open(percorso) as im:
            ex = im.getexif()
            dt = ex.get_ifd(0x8769).get(36867) or ex.get(306)
            sub = ex.get_ifd(0x8769).get(37521) or "0"
        if dt:
            t = datetime.strptime(str(dt).strip()[:19], "%Y:%m:%d %H:%M:%S").timestamp()
            return t + float("0." + re.sub(r"\D", "", str(sub)) or 0)
    except Exception:
        pass
    nome = os.path.basename(percorso)
    m = re.search(r"(\d{4})-(\d\d)-(\d\d) at (\d\d)\.(\d\d)\.(\d\d)(?: \((\d+)\))?", nome)
    if m:
        t = datetime(*map(int, m.groups()[:6])).timestamp()
        return t + int(m.group(7) or 0) / 1000.0
    m = re.search(r"(20\d\d)(\d\d)(\d\d)[_-](\d\d)(\d\d)(\d\d)", nome)     # IMG_20260921_120304
    if m:
        try:
            return datetime(*map(int, m.groups())).timestamp()
        except ValueError:
            pass
    try:
        return os.path.getmtime(percorso)
    except OSError:
        return 0


def colore_medio(img):
    piccola = img.convert("RGB").resize((48, 64))
    return tuple(ImageStat.Stat(piccola).mean)


def quasi_vuota(img):
    """Pagina senza nulla sopra (tanti retri sono cosi')."""
    g = img.convert("L").resize((120, 160))
    return ImageStat.Stat(g).stddev[0] < 14


def codici_a_barre(img):
    """ISBN letti dal codice a barre, se c'e' la libreria per leggerlo."""
    if zxingcpp is None:
        return []
    trovati = []
    for prova in (img, ruotata(img, 90)):
        try:
            for r in zxingcpp.read_barcodes(prova.convert("L")):
                cod = re.sub(r"\D", "", r.text or "")
                if len(cod) == 13 and cod[:3] in ("978", "979") and isbn_valido(cod):
                    trovati.append(cod)
        except Exception:
            pass
        if trovati:
            break
    return trovati


# ══════════════════════════════════════════════════════════════════════
#  ISBN
# ══════════════════════════════════════════════════════════════════════
def isbn_valido(s):
    s = re.sub(r"[^0-9Xx]", "", s or "").upper()
    if len(s) == 10:
        if not re.fullmatch(r"\d{9}[\dX]", s):
            return False
        tot = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s))
        return tot % 11 == 0
    if len(s) == 13 and s.isdigit():
        tot = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(s[:12]))
        return (10 - tot % 10) % 10 == int(s[12])
    return False


def isbn13(s):
    s = re.sub(r"[^0-9Xx]", "", s or "").upper()
    if len(s) == 13:
        return s
    if len(s) != 10:
        return ""
    base = "978" + s[:9]
    tot = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(base))
    return base + str((10 - tot % 10) % 10)


def isbn_nel_testo(testo):
    """ISBN scritti in chiaro ("ISBN 88-85290-02-7") che tornano con la cifra di controllo."""
    trovati = []
    t = (testo or "").replace("O", "0").replace("o", "0") if "ISBN" in (testo or "").upper() else (testo or "")
    for m in re.finditer(r"(?:ISBN[\s:\-]*)?((?:97[89][\s\-]?)?\d{1,5}[\s\-]?\d{1,7}[\s\-]?\d{1,7}[\s\-]?[\dXx])", t):
        grezzo = m.group(1)
        cifre = re.sub(r"[^0-9Xx]", "", grezzo)
        if len(cifre) in (10, 13) and isbn_valido(cifre):
            trovati.append(re.sub(r"\s+", "", grezzo.strip()))
    return trovati


# ══════════════════════════════════════════════════════════════════════
#  Ricerche in rete (Google Books, Open Library)
# ══════════════════════════════════════════════════════════════════════
def _json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "GestioneChiesa-Libreria/1.0"})
    for tentativo in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and tentativo == 0:       # troppe richieste: si aspetta un attimo
                time.sleep(2.0)
                continue
            return None
        except Exception:
            return None
    return None


def _anno(s):
    m = re.search(r"(1[5-9]\d\d|20\d\d)", str(s or ""))
    return m.group(1) if m else ""


def da_google(vol):
    v = (vol or {}).get("volumeInfo", {}) or {}
    isbn = ""
    for ident in v.get("industryIdentifiers", []) or []:
        if ident.get("type") in ("ISBN_13", "ISBN_10"):
            isbn = ident.get("identifier", "")
            if ident.get("type") == "ISBN_13":
                break
    titolo = v.get("title", "") or ""
    if v.get("subtitle"):
        titolo += " — " + v["subtitle"]
    return {
        "titolo": titolo, "autore": ", ".join(v.get("authors", []) or []),
        "editore": v.get("publisher", "") or "", "anno": _anno(v.get("publishedDate")),
        "pagine": int(v.get("pageCount") or 0), "descrizione": v.get("description", "") or "",
        "categorie": v.get("categories", []) or [], "lingua": v.get("language", "") or "",
        "isbn": isbn, "fonte": "Google Books",
    }


def da_openlibrary(voce):
    v = voce or {}
    titolo = v.get("title", "") or ""
    if v.get("subtitle"):
        titolo += " — " + v["subtitle"]
    return {
        "titolo": titolo,
        "autore": ", ".join(a.get("name", "") for a in v.get("authors", []) or [] if a.get("name")),
        "editore": ", ".join(p.get("name", "") for p in v.get("publishers", []) or [] if p.get("name")),
        "anno": _anno(v.get("publish_date")), "pagine": int(v.get("number_of_pages") or 0),
        "descrizione": "", "categorie": [s.get("name", "") for s in v.get("subjects", []) or []][:6],
        "lingua": "", "isbn": "", "fonte": "Open Library",
    }


def unisci(primo, secondo):
    if not primo:
        return secondo
    if not secondo:
        return primo
    out = dict(primo)
    for k, v in secondo.items():
        if not out.get(k) and v:
            out[k] = v
    if primo.get("fonte") and secondo.get("fonte") and primo["fonte"] != secondo["fonte"]:
        out["fonte"] = primo["fonte"] + " + " + secondo["fonte"]
    return out


def cerca_isbn(isbn):
    cod = re.sub(r"[^0-9Xx]", "", isbn or "")
    if not cod:
        return None
    g = _json("https://www.googleapis.com/books/v1/volumes?q=isbn:" + cod)
    gb = da_google(g["items"][0]) if g and g.get("items") else None
    o = _json("https://openlibrary.org/api/books?bibkeys=ISBN:%s&format=json&jscmd=data" % cod)
    ol = da_openlibrary(o.get("ISBN:" + cod)) if o and o.get("ISBN:" + cod) else None
    ris = unisci(gb, ol)
    if ris and not ris.get("isbn"):
        ris["isbn"] = isbn
    return ris


def cerca_titolo(titolo, autore=""):
    """Candidati per titolo (e autore): servono solo come suggerimento."""
    if not titolo or len(chiave(titolo)) < 4:
        return []
    q = 'intitle:"%s"' % titolo
    if autore:
        q += ' inauthor:"%s"' % autore.split(",")[0]
    url = ("https://www.googleapis.com/books/v1/volumes?maxResults=6&printType=books&q="
           + urllib.parse.quote(q))
    g = _json(url)
    out = []
    for vol in (g or {}).get("items", []) or []:
        d = da_google(vol)
        d["somiglianza"] = round(somiglianza(titolo, d["titolo"].split(" — ")[0]), 2)
        out.append(d)
    if not out:
        u = "https://openlibrary.org/search.json?limit=6&title=" + urllib.parse.quote(titolo)
        if autore:
            u += "&author=" + urllib.parse.quote(autore.split(",")[0])
        o = _json(u)
        for doc in (o or {}).get("docs", []) or []:
            d = {"titolo": doc.get("title", ""), "autore": ", ".join(doc.get("author_name", [])[:3]),
                 "editore": (doc.get("publisher") or [""])[0], "anno": str(doc.get("first_publish_year") or ""),
                 "pagine": int(doc.get("number_of_pages_median") or 0), "descrizione": "",
                 "categorie": [], "lingua": "", "isbn": (doc.get("isbn") or [""])[0], "fonte": "Open Library"}
            d["somiglianza"] = round(somiglianza(titolo, d["titolo"]), 2)
            out.append(d)
    out.sort(key=lambda d: -d["somiglianza"])
    return out


# ══════════════════════════════════════════════════════════════════════
#  Dal testo alle schede
# ══════════════════════════════════════════════════════════════════════
# Solo nomi che non sono anche parole comuni: "Ancora" veniva riconosciuto
# in ogni quarta che conteneva la parola "ancora".
EDITORI_NOTI = [
    "Soli Deo Gloria", "Centro Biblico", "Edizioni Centro Biblico", "Edizioni GBU", "UCEB",
    "IFED", "Il Messaggero Cristiano", "Voce della Bibbia", "Casa Editrice Battista",
    "Edizioni Casa Biblica", "Casa Biblica", "Edizioni CLC", "Patmos", "Claudiana",
    "ADI-Media", "Uomini Nuovi", "Alfa & Omega", "Edizioni Passaggio", "BE Edizioni",
    "Coram Deo", "La Casa della Bibbia", "Istituto Biblico Evangelico", "Evangelical Press",
    "Edizioni Evangeliche", "Editrice Evangelica", "Hilfsbund", "Garzanti", "Mondadori",
    "Editrice Il Pellegrino", "Edizioni Dehoniane", "Elledici", "Elle Di Ci",
    "Edizioni Paoline", "Edizioni San Paolo", "Qiqajon", "Città Nuova Editrice", "Queriniana",
    "Àncora Editrice", "Libreria Editrice Vaticana",
]

# Il vostro adesivo sui retri ("PER INFORMAZIONI ... EVANGELICI MARANELLO"):
# non e' ne' l'autore ne' la sintesi.
ADESIVO = re.compile(r"per informazioni|evangelici\s*maranello|evangelicimaranello|"
                     r"libreria@|\bsito\s*:|\bemail\s*:|\bcell\b", re.I)

CATTOLICI = [  # (cosa cercare, perche')
    ("elledici", "editrice salesiana Elledici"), ("elle di ci", "editrice salesiana Elledici"),
    ("paoline", "Edizioni Paoline"), ("edizioni san paolo", "Edizioni San Paolo"),
    ("dehoniane", "Edizioni Dehoniane"), ("qiqajon", "Comunità di Bose"),
    ("comunita di bose", "Comunità di Bose"), ("citta nuova", "Città Nuova"),
    ("queriniana", "editrice Queriniana"), ("libreria editrice vaticana", "Libreria Editrice Vaticana"),
    ("messaggero di sant antonio", "Messaggero di Sant'Antonio"), ("ancora editrice", "editrice Àncora"),
    ("imprimatur", "porta l'imprimatur"), ("nihil obstat", "porta il nihil obstat"),
    ("santo rosario", "parla del rosario"), ("beata vergine", "devozione mariana"),
    ("madonna di", "devozione mariana"), ("santissima vergine", "devozione mariana"),
]

REGOLE_GENERE = [  # (parole chiave, genere): conta quante volte compaiono, col peso del campo
    (r"preghier|pregare|orazion", "Preghiera"),
    (r"creazion|evoluzion|genesi|darwin|origine della vita", "Creazione ed evoluzione"),
    (r"anzian|diacon|chiesa local|battesim|cena del signore|pastoral|ministero|corpo di cristo", "Chiesa e ministero"),
    (r"storia della chiesa|storia del cristianesimo|nei secoli|riforma protestante|valdes|risveglio", "Storia della chiesa"),
    (r"apologet|difesa della fede|scienza e fede|esiste dio|dio ci fosse|filosof|umanesimo|ateo|atei", "Apologetica"),
    (r"aborto|eutanasia|bioetic|divorzi|matrimonio|sessualit", "Etica cristiana"),
    (r"nascere di nuovo|unica via|vita eterna|salvezza|conversion|incontro con gesu", "Evangelizzazione"),
    (r"antico testamento|nuovo testamento|lettera ai|lettera di|vangelo di|sermone sul monte|salmi|"
     r"profet|apocalisse|studio bibl|introduzione alla|commentario", "Studio biblico"),
    (r"scrittura|ispirazion|autorita della bibbia|inerran|dottrin|teolog|predestinazion|grazia", "Teologia"),
    (r"meditazion|quotidian|riflessioni bibliche|devozional", "Meditazioni quotidiane"),
    (r"discepol|santita|vita cristiana|crescita spiritual|spiritualit|consacrazion|vittoria cristiana", "Vita cristiana"),
    (r"movimenti religiosi|testimoni di geova|mormon|sette\b|occult|new age", "Sette e religioni"),
    (r"testimonianz|missionar|biografi|la storia di|la sua storia|racconta", "Testimonianze"),
    (r"archeolog", "Archeologia biblica"),
    (r"calendari", "Calendario"),
]


def genere_da(testi, generi_esistenti):
    punti = {}
    for peso, t in testi:
        t = chiave(t)
        for regola, genere in REGOLE_GENERE:
            n = len(re.findall(regola, t))
            if n:
                punti[genere] = punti.get(genere, 0) + peso * n
    if not punti:
        return ""
    migliore = max(punti.items(), key=lambda kv: kv[1])[0]
    # se nel catalogo c'e' gia' un genere quasi uguale si usa quello, per non
    # avere due voci diverse nel filtro della pagina
    for g in generi_esistenti or []:
        if chiave(g) == chiave(migliore):
            return g
    return migliore


def editore_da(testo, editori_esistenti):
    t = " " + chiave(testo) + " "
    elenco = sorted(set((editori_esistenti or []) + EDITORI_NOTI), key=lambda s: -len(s))
    for e in elenco:
        k = chiave(e)
        if len(k) >= 3 and " " + k + " " in t:
            for g in editori_esistenti or []:        # la grafia gia' usata nel catalogo
                if chiave(g) == k:
                    return g
            return e
    m = re.search(r"((?:Edizioni|Editrice|Casa Editrice|Ed\.)\s+[A-Z][\w'’]+(?:\s+[A-Z][\w'’]+){0,3})", testo or "")
    return m.group(1).strip() if m else ""


PAROLE_NON_NOME = set("""di da del della dei degli delle il lo la i gli le un una uno e ed per con che
non su sul sulla nel nella al alla come cosa perche perché chi dio gesu gesù cristo bibbia vangelo
edizioni editrice edizione casa libro manuale nuovi credenti prefazione introduzione capitolo
fede vita chiesa signore spirito santo parola verita verità amore via monte sermone
aeterna vitae verba verbum domini dei deo gloria soli sola scriptura
""".split())


NON_AUTORI = {"aa vv", "evangelici maranello", "chiesa evangelica maranello", "gruppi biblici universitari",
              "assemblee dei fratelli"}


def senza_adesivo(testo):
    return "\n".join(r for r in (testo or "").splitlines() if not ADESIVO.search(r))


def autore_da(righe_fronte, testo_tutto, autori_esistenti, titolo):
    # 1) un autore gia' presente nel catalogo che compare nel testo
    t = " " + chiave(senza_adesivo(testo_tutto)) + " "
    for a in sorted(set(autori_esistenti or []), key=lambda s: -len(s)):
        k = chiave(a)
        if len(k) >= 6 and k not in NON_AUTORI and " " + k + " " in t:
            return a
    # 2) una riga della copertina che ha la forma di un nome
    kt = chiave(titolo)
    for r in righe_fronte:
        if ADESIVO.search(r["t"]):
            continue
        s = re.sub(r"^(?:di|a cura di|by)\s+", "", r["t"].strip(), flags=re.I)
        s = re.sub(r"[^\wÀ-ÿ.'\s-]", "", s).strip()
        parti = s.split()
        # "Juan Carlos Orti RS": gli ultimi pezzetti in maiuscolo sono rumore dell'OCR
        while parti and len(parti[-1]) <= 2 and parti[-1].isupper() and not parti[-1].endswith("."):
            parti.pop()
        s = " ".join(parti)
        if not 2 <= len(parti) <= 4 or r["c"] < 55:
            continue
        if chiave(s) and chiave(s) in kt:
            continue
        if any(chiave(p) in PAROLE_NON_NOME for p in parti):
            continue
        if not all(re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'.-]*", p) for p in parti):
            continue
        if not all(p[0].isupper() for p in parti) and not s.islower():
            continue
        if sum(len(p) for p in parti) < 7 or chiave(s) in NON_AUTORI:
            continue
        return nome_proprio(s)
    return ""


def nome_proprio(s):
    """"WILLIAM MACDONALD" / "ellero balzani" -> "William Macdonald" / "Ellero Balzani"."""
    if not (s.isupper() or s.islower()):
        return s                                   # gia' scritto bene: non si tocca
    out = []
    for p in s.split():
        if re.fullmatch(r"[A-Za-z]\.", p):         # iniziali: "g." -> "G."
            out.append(p.upper())
        else:
            out.append("-".join(x.capitalize() for x in p.split("-")))
    return " ".join(out)


BIO = re.compile(r"^([A-ZÀ-Ý][A-Za-zÀ-ÿ'.]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'.]+){1,3})[\s,]+"
                 r"(?:è|e'|ha |vive|nato|nata|insegna|lavora|laureat|pastore|dottore|scrittore|autore)")


def bio_da(paragrafi):
    """
    Il paragrafo della quarta che presenta l'autore ("VINCENT EZE AHANONU è
    membro della Chiesa...", "Helga Anton ha studiato musica...").
    Restituisce (nome, paragrafo) oppure ("", "").
    """
    for p in paragrafi:
        m = BIO.match(p.strip())
        if m and not ADESIVO.search(p):
            nome = m.group(1).strip()
            if chiave(nome) not in NON_AUTORI and not any(chiave(w) in PAROLE_NON_NOME for w in nome.split()):
                return nome_proprio(nome), p.strip()
    return "", ""


def titolo_da(righe_fronte):
    """Le righe col testo piu' grande della copertina."""
    buone = [r for r in righe_fronte if r["c"] >= 55 and sum(ch.isalpha() for ch in r["t"]) >= 3]
    if not buone:
        return ""
    hmax = max(r["h"] for r in buone)
    grandi = [r for r in buone if r["h"] >= 0.62 * hmax]
    grandi.sort(key=lambda r: r["y"])
    t = " ".join(r["t"] for r in grandi[:4])
    t = re.sub(r"[^\wÀ-ÿ'’,.!?:;\- ]", "", t)
    return titolo_leggibile(t)


RIGHE_DA_SCARTARE = re.compile(
    r"per informazioni|evangelicimaranello|www\.|http|@|tel\.?\s*\d|telefono|cell\.|"
    r"isbn|prezzo|lire|\bl\.\s*\d|€|euro\b|iva\b|copertina di|stampato|finito di stampare|"
    r"tutti i diritti|printed in|\bvia\s+\w+\s*,?\s*\d|\bc\.p\.|cap\s*\d{5}|\d{5}\s+[A-Z]",
    re.I)


def paragrafi_puliti(parole_retro, titolo=""):
    """
    I paragrafi della quarta di copertina, senza l'adesivo, i prezzi, gli
    indirizzi e le parole che l'OCR ha tirato a indovinare.
    """
    # parola per parola: via quelle lette con poca fiducia o fatte di simboli
    buone = []
    for p in parole_retro:
        t = p["t"]
        lettere = sum(ch.isalnum() for ch in t)
        if p["c"] < 30 or (lettere == 0 and t not in ("-", "–", "—")):
            continue
        if lettere / len(t) < 0.5 and len(t) > 2:
            continue
        buone.append(p)
    pars = {}
    for r in righe(buone):
        pars.setdefault((r["b"], r["p"]), []).append(r)
    kt = chiave(titolo)
    blocchi = []
    for k in sorted(pars):
        rs = [r for r in pars[k] if not RIGHE_DA_SCARTARE.search(r["t"]) and not ADESIVO.search(r["t"])
              and r["c"] >= 62]
        if not rs:
            continue
        testo = ""
        for r in rs:
            t = r["t"]
            if testo.endswith("-") and t[:1].islower():
                testo = testo[:-1] + t
            else:
                testo = (testo + " " + t).strip()
        testo = re.sub(r"^[\W_]+", "", testo)              # "» Avete...", "| Questa...", ": ..."
        testo = re.sub(r"\s+\|\s+", " ", testo)
        lettere = sum(ch.isalpha() for ch in testo)
        if len(testo) < 25 or lettere / max(1, len(testo)) < 0.72:
            continue
        if testo.isupper() and kt and somiglianza(testo, titolo) > 0.7:
            continue                                        # il titolo ripetuto in cima alla quarta
        blocchi.append(testo)
    return blocchi


def sintesi_da(paragrafi):
    """Unisce i paragrafi in una sintesi di lunghezza ragionevole."""
    testo = "\n\n".join(paragrafi)
    testo = re.sub(r"\s+([,.;:!?])", r"\1", testo)
    testo = re.sub(r"[ \t]{2,}", " ", testo).strip()
    if len(testo) > 1400:
        taglio = testo.rfind(".", 0, 1400)
        testo = testo[: taglio + 1 if taglio > 600 else 1400].strip()
    return testo


def anno_da(testo):
    anni = []
    ora = datetime.now().year
    for m in re.finditer(r"(?<![\d.,])(19[3-9]\d|20[0-4]\d)(?![\d.,])", testo or ""):
        a = int(m.group(1))
        if a <= ora:
            vicino = (testo[max(0, m.start() - 25):m.start()]).lower()
            peso = 2 if re.search(r"©|copyright|edizione|stampa|pubblicato", vicino) else 1
            anni.append((peso, a))
    if not anni:
        return ""
    anni.sort(reverse=True)
    if anni[0][0] == 2 or len({a for _, a in anni}) == 1:
        return str(anni[0][1])
    return ""            # piu' anni e nessun indizio: meglio lasciarlo vuoto


def avvisi_cattolici(testo):
    t = " " + chiave(testo) + " "
    motivi = []
    for cosa, perche in CATTOLICI:
        if " " + chiave(cosa) + " " in t and perche not in motivi:
            motivi.append(perche)
    return motivi


def leggi_quantita(cartella):
    """
    File di testo con "titolo   numero" per riga (per esempio quantita.py):
    restituisce {titolo: copie}. Le righe senza numero vengono ignorate.
    """
    out = {}
    for nome in os.listdir(cartella):
        p = os.path.join(cartella, nome)
        if not os.path.isfile(p) or nome.lower().endswith(ESTENSIONI):
            continue
        if os.path.getsize(p) > 200_000:
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                righe_file = f.read().splitlines()
        except OSError:
            continue
        for riga in righe_file:
            m = re.match(r"^\s*(.+?)[\s\t:;,=\-]+(\d{1,4})\s*$", riga)
            if m and len(chiave(m.group(1))) >= 3:
                out[m.group(1).strip()] = int(m.group(2))
    return out


def copie_per(titolo, quantita):
    migliore, punti = None, 0.0
    kt = chiave(titolo)
    for t, n in quantita.items():
        k = chiave(re.sub(r"\b(fronte|retro)\b", "", t, flags=re.I))
        s = 1.0 if k and (k == kt) else somiglianza(k, kt)
        if k and (kt.startswith(k) or k.startswith(kt)) and min(len(k), len(kt)) >= 8:
            s = max(s, 0.9)
        if s > punti:
            migliore, punti = n, s
    return migliore if punti >= 0.82 else None


# ══════════════════════════════════════════════════════════════════════
#  Nomi dei file: "Titolo fronte.jpg", "titolo retro.jpg", "Titolo_copertina.png"
# ══════════════════════════════════════════════════════════════════════
FACCE = [("fronte", r"fronte|front|copertina|cover|davanti|prima"),
         ("retro", r"retro|back|dietro|quarta|seconda")]


def faccia_dal_nome(nome):
    base = os.path.splitext(os.path.basename(nome))[0]
    for faccia, rx in FACCE:
        m = re.match(r"^(.*?)[\s_\-]*\b(?:%s)\b[\s_\-]*\d*$" % rx, base, re.I)
        if m:
            return faccia, m.group(1).strip(" _-")
    return "", ""


def e_nome_generico(titolo):
    """IMG_1234, WhatsApp Image ..., DSC0012: nomi che non dicono niente."""
    return bool(re.match(r"^(img|dsc|dcim|pxl|photo|foto|whatsapp|screenshot|image|scan)[\s_\-]*", titolo or "", re.I)) \
        or not re.search(r"[A-Za-zÀ-ÿ]{3}", titolo or "")


# ══════════════════════════════════════════════════════════════════════
#  Il catalogatore
# ══════════════════════════════════════════════════════════════════════
class Catalogatore:
    def __init__(self, cartelle_strumenti=()):
        self.cartelle_strumenti = [c for c in cartelle_strumenti if c]
        self._lock = threading.Lock()
        self._annulla = False
        self.foto = {}
        self.libri = []
        self.stato = {"fase": "pronto", "fatti": 0, "totale": 0, "messaggio": "", "finito": False}
        self._mini = {}

    # ── avanzamento ──────────────────────────────────────────────────
    def _avanza(self, fase=None, fatti=None, totale=None, messaggio=None):
        with self._lock:
            if fase is not None:
                self.stato["fase"] = fase
            if fatti is not None:
                self.stato["fatti"] = fatti
            if totale is not None:
                self.stato["totale"] = totale
            if messaggio is not None:
                self.stato["messaggio"] = messaggio

    def annulla(self):
        self._annulla = True

    def leggi_stato(self):
        with self._lock:
            return dict(self.stato)

    # ── analisi ──────────────────────────────────────────────────────
    def analizza(self, cartella, catalogo=None, in_rete=True):
        """Lavoro vero: da chiamare in un thread. Riempie self.libri."""
        self._annulla = False
        self.foto, self.libri, self._mini = {}, [], {}
        with self._lock:
            self.stato = {"fase": "lettura", "fatti": 0, "totale": 0, "messaggio": "Cerco le foto…",
                          "finito": False, "errore": "", "ocr": False, "avvisi": []}
        try:
            self._analizza(cartella, catalogo or [], in_rete)
            self._avanza(fase="fatto", messaggio="Analisi completata.")
        except Exception as e:                       # mai lasciare la pagina ad aspettare
            with self._lock:
                self.stato["errore"] = "%s: %s" % (type(e).__name__, e)
            self._avanza(fase="errore", messaggio="Qualcosa non ha funzionato: " + str(e))
        finally:
            with self._lock:
                self.stato["finito"] = True

    def _analizza(self, cartella, catalogo, in_rete):
        if Image is None:
            raise RuntimeError("manca la libreria Pillow (lancia build_exe.bat)")
        if not os.path.isdir(cartella):
            raise RuntimeError("cartella non trovata")

        file = [os.path.join(cartella, f) for f in os.listdir(cartella)
                if f.lower().endswith(ESTENSIONI) and not f.startswith(("_", "."))]
        if not file:
            raise RuntimeError("nella cartella non ci sono immagini")
        file.sort(key=lambda p: (data_scatto(p), os.path.basename(p).lower()))

        ocr = LettoreOCR(self.cartelle_strumenti)
        with self._lock:
            self.stato["ocr"] = ocr.pronto
            if not ocr.pronto:
                self.stato["avvisi"].append(
                    "Tesseract non è installato: niente lettura del testo. Accoppio e raddrizzo "
                    "comunque le foto, ma titolo, autore e sintesi andranno scritti a mano.")
            elif ocr.lingua != "ita":
                self.stato["avvisi"].append(
                    "Manca il dizionario italiano di Tesseract: il testo viene letto peggio.")
            if zxingcpp is None:
                self.stato["avvisi"].append("Lettore di codici a barre assente: cerco l'ISBN solo nel testo.")

        # ── 1. ogni foto: verso, testo, codice a barre ──
        self._avanza(fase="foto", totale=len(file), fatti=0, messaggio="Leggo le foto…")
        for i, p in enumerate(file):
            self.foto["f%d" % (i + 1)] = {"id": "f%d" % (i + 1), "file": p, "nome": os.path.basename(p),
                                          "ordine": i, "rot": 0, "incerta": False}

        fatti = [0]

        def lavora(f):
            if self._annulla:
                return
            self._studia_foto(f, ocr)
            with self._lock:
                fatti[0] += 1
                self.stato["fatti"] = fatti[0]
                self.stato["messaggio"] = "Leggo le foto… (%s)" % f["nome"]

        lavoratori = max(1, min(4, (os.cpu_count() or 2)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=lavoratori) as ex:
            list(ex.map(lavora, list(self.foto.values())))
        if self._annulla:
            raise RuntimeError("annullato")

        # ── 2. coppie fronte/retro ──
        self._avanza(fase="coppie", messaggio="Accoppio fronte e retro…")
        coppie = self._accoppia([self.foto[k] for k in sorted(self.foto, key=lambda k: self.foto[k]["ordine"])])

        # sulle copertine si rilegge in modalita' "testo sparso": trova titoli
        # e nomi sparsi per la pagina che la lettura a paragrafi salta
        if ocr.pronto:
            self._avanza(fase="copertine", messaggio="Rileggo le copertine…")

            def rileggi(fr):
                if self._annulla or fr.get("vuota"):
                    return
                img = ruotata(ridotta(apri(fr["file"]), LATO_OCR), fr["rot"])
                fr["parole_sparse"] = ocr.parole(img, psm=11, grigio=True)

            with concurrent.futures.ThreadPoolExecutor(max_workers=lavoratori) as ex:
                list(ex.map(rileggi, [fr for fr, _ in coppie]))

        # ── 3. schede ──
        esistenti_titoli = [(l.get("titolo", ""), re.sub(r"\D", "", l.get("isbn", "") or "")) for l in catalogo]
        autori = [l.get("autore", "") for l in catalogo if l.get("autore")]
        editori = [l.get("editore", "") for l in catalogo if l.get("editore")]
        generi = sorted({l.get("genere", "") for l in catalogo if l.get("genere")})
        quantita = leggi_quantita(cartella)

        self._avanza(fase="schede", totale=len(coppie), fatti=0, messaggio="Ricavo i dati dei libri…")
        for n, (fr, re_) in enumerate(coppie):
            if self._annulla:
                raise RuntimeError("annullato")
            libro = self._scheda(fr, re_, autori, editori, generi, in_rete)
            # doppioni gia' a catalogo
            for t, isbn in esistenti_titoli:
                if (libro["isbn"] and isbn and re.sub(r"\D", "", libro["isbn"])[-9:] == isbn[-9:]) \
                        or (libro["titolo"] and somiglianza(t, libro["titolo"]) >= 0.9):
                    libro["avvisi"].append({"tipo": "doppione", "testo": "Già a catalogo: «%s»" % t})
                    libro["includi"] = False
                    break
            c = copie_per(libro["titolo"] or libro["titolo_file"], quantita) if quantita else None
            if c is not None:
                libro["copie"] = c
                libro["copie_da_file"] = True
            libro["id"] = "b%d" % (n + 1)
            self.libri.append(libro)
            self._avanza(fatti=n + 1, messaggio="Ricavo i dati dei libri… (%d di %d)" % (n + 1, len(coppie)))

        with self._lock:
            self.stato["generi"] = generi

    def _studia_foto(self, f, ocr):
        img = apri(f["file"])
        f["dim"] = img.size
        f["exif"] = ha_exif_verso(f["file"])
        piccola = ridotta(img, LATO_OCR)
        f["vuota"] = quasi_vuota(piccola)
        f["colore"] = colore_medio(piccola)

        faccia, titolo = faccia_dal_nome(f["nome"])
        f["faccia_nome"], f["titolo_nome"] = faccia, ("" if e_nome_generico(titolo) else titolo)

        # Verso. I libri stanno in piedi: una foto verticale resta verticale
        # (si decide solo fra dritta e capovolta), una orizzontale e' quasi
        # sempre un libro fotografato di fianco. Si cambia idea solo se il
        # testo si legge nettamente meglio: sulle copertine illustrate Tesseract
        # legge poco, e prima girava di 90 gradi copertine gia' dritte.
        orizzontale = img.size[0] > img.size[1] * 1.08
        predefinita = 270 if (orizzontale and not f["exif"]) else 0
        if f["exif"] or not ocr.pronto or f["vuota"]:
            f["rot"] = predefinita
            f["incerta"] = orizzontale and not f["exif"] and not f["vuota"]
            f["parole"] = ocr.parole(ruotata(piccola, f["rot"])) if ocr.pronto and not f["vuota"] else []
        else:
            alternativa = (predefinita + 180) % 360
            prove = {predefinita: ocr.parole(ruotata(piccola, predefinita))}
            s0 = punteggio_lettura(prove[predefinita])
            scelta, incerta = predefinita, False
            if s0 < 120:                                   # se si legge benissimo e' gia' dritta
                prove[alternativa] = ocr.parole(ruotata(piccola, alternativa))
                s1 = punteggio_lettura(prove[alternativa])
                if s1 >= max(25, 2 * s0):
                    scelta = alternativa
                elif s1 >= 25 and s1 > s0:
                    incerta = True
                elif orizzontale and max(s0, s1) < 25:
                    incerta = True                         # di fianco e muta: il verso e' un'ipotesi
                # un orizzontale che si legge solo cosi' com'e' (un calendario)
                if orizzontale and max(s0, s1) < 80:
                    prove[0] = ocr.parole(piccola)
                    if punteggio_lettura(prove[0]) >= max(80, 2 * max(s0, s1)):
                        scelta, incerta = 0, False
            f["rot"] = scelta
            f["parole"] = prove[scelta]
            f["incerta"] = incerta

        f["testo"] = testo_da_parole(f.get("parole", []))
        f["leggibilita"] = punteggio_lettura(f.get("parole", []))
        f["isbn_barre"] = codici_a_barre(ruotata(piccola, f["rot"])) if not f["vuota"] else []
        f["isbn_testo"] = isbn_nel_testo(f["testo"])

        # indizi di retro: codice a barre, prezzo, tanto testo minuto
        t = f["testo"].lower()
        punti = 0.0
        if f["isbn_barre"]:
            punti += 3
        if f["isbn_testo"] or "isbn" in t:
            punti += 2
        if re.search(r"€|\blire\b|\bl\.\s*\d|prezzo|iva incl", t):
            punti += 2
        parole = f.get("parole", [])
        n_parole = sum(1 for p in parole if p["c"] >= 60 and len(p["t"]) >= 3)
        punti += min(3.0, n_parole / 40.0)
        if f["vuota"]:
            punti += 1.5
        if parole:
            h = sorted((p["h"] for p in parole if p["c"] >= 60), reverse=True)
            if h and h[0] / max(1, ridotta(img, LATO_OCR).size[1]) > 0.035:
                punti -= 1.5                               # titolone: aria da copertina
        f["punti_retro"] = round(punti, 2)
        f.pop("_img", None)

    # ── coppie ───────────────────────────────────────────────────────
    def _accoppia(self, foto):
        """Restituisce [(fronte, retro), ...]; retro puo' essere None."""
        coppie = []
        con_nome = [f for f in foto if f["faccia_nome"]]
        senza_nome = [f for f in foto if not f["faccia_nome"]]

        # 1) i nomi dei file dicono gia' tutto
        fronti = [f for f in con_nome if f["faccia_nome"] == "fronte"]
        retri = [f for f in con_nome if f["faccia_nome"] == "retro"]
        liberi = list(retri)
        for fr in fronti:
            kf = chiave(fr["titolo_nome"])
            migliore, punti = None, 0.0
            for r in liberi:
                kr = chiave(r["titolo_nome"])
                s = 1.0 if kf == kr else somiglianza(kf, kr)
                if kf and kr and (kf.startswith(kr) or kr.startswith(kf)) and min(len(kf), len(kr)) >= 6:
                    s = max(s, 0.88)
                if s > punti:
                    migliore, punti = r, s
            if migliore is not None and punti >= 0.75:
                liberi.remove(migliore)
                coppie.append((fr, migliore))
            else:
                coppie.append((fr, None))
        # retri rimasti senza fronte: tornano fra quelli da accoppiare per ordine
        senza_nome = sorted(senza_nome + liberi, key=lambda f: f["ordine"])

        # 2) le altre, nell'ordine di scatto, due a due
        i = 0
        while i < len(senza_nome):
            a = senza_nome[i]
            b = senza_nome[i + 1] if i + 1 < len(senza_nome) else None
            c = senza_nome[i + 2] if i + 2 < len(senza_nome) else None
            if b is None:
                coppie.append((a, None) if a["punti_retro"] < 2.5 else (a, None))
                i += 1
                continue
            # se b somiglia molto piu' a c che ad a, a e' rimasta sola
            if c is not None and self._vicinanza(b, c) > self._vicinanza(a, b) + 0.25 \
                    and self._vicinanza(b, c) > 0.8:
                coppie.append((a, None))
                i += 1
                continue
            fr, rt = (a, b) if a["punti_retro"] < b["punti_retro"] else (b, a)
            if abs(a["punti_retro"] - b["punti_retro"]) < 0.3:
                fr, rt = b, a            # a pari indizi: si fotografa prima il retro
            coppie.append((fr, rt))
            i += 2

        coppie.sort(key=lambda fr_rt: fr_rt[0]["ordine"])
        return coppie

    @staticmethod
    def _vicinanza(a, b):
        """Quanto si somigliano i colori di due foto (1 = identici)."""
        ca, cb = a.get("colore"), b.get("colore")
        if not ca or not cb:
            return 0.0
        d = sum((x - y) ** 2 for x, y in zip(ca, cb)) ** 0.5
        return max(0.0, 1.0 - d / 180.0)

    # ── una scheda ───────────────────────────────────────────────────
    def _scheda(self, fr, rt, autori, editori, generi, in_rete):
        avvisi = []
        sparse = fr.get("parole_sparse", [])
        testo_f = fr.get("testo", "") + "\n" + " ".join(p["t"] for p in sparse if p["c"] >= 60)
        testo_r = rt.get("testo", "") if rt else ""
        tutto = testo_f + "\n" + testo_r
        # righe della copertina: la lettura a paragrafi e quella sparsa insieme
        righe_f = righe(fr.get("parole", [])) + righe(sparse)

        titolo_file = fr.get("titolo_nome") or (rt.get("titolo_nome") if rt else "")
        titolo = titolo_leggibile(accenti_da(titolo_file, tutto)) if titolo_file else titolo_da(righe_f)
        fonte = "nome del file" if titolo_file else ("testo della copertina" if titolo else "")

        isbn = ""
        for f in (rt, fr):
            if f and (f.get("isbn_barre") or f.get("isbn_testo")):
                isbn = (f.get("isbn_barre") or f.get("isbn_testo"))[0]
                break

        online = None
        suggerimenti = []
        if in_rete and isbn:
            online = cerca_isbn(isbn)
            if online:
                fonte = "ISBN · " + online.get("fonte", "")
        if in_rete and not online and titolo:
            cand = cerca_titolo(titolo, autore_da(righe_f, tutto, autori, titolo))
            suggerimenti = [c for c in cand if c["somiglianza"] >= 0.6][:3]

        paragrafi = paragrafi_puliti(rt.get("parole", []), titolo) if rt else []
        nome_bio, bio = bio_da(paragrafi)
        # la presentazione dell'autore va nel suo campo, se resta altro testo per la sintesi
        if bio and sum(len(p) for p in paragrafi if p.strip() != bio) >= 150:
            paragrafi = [p for p in paragrafi if p.strip() != bio]
        else:
            bio = ""

        autore = ((online or {}).get("autore") or autore_da(righe_f, tutto, autori, titolo)
                  or nome_bio)
        editore = editore_da(senza_adesivo(tutto), editori) or (online or {}).get("editore", "")
        anno = (online or {}).get("anno") or anno_da(senza_adesivo(testo_r))
        pagine = int((online or {}).get("pagine") or 0)
        sintesi = sintesi_da(paragrafi)
        if len(sintesi) < 120 and (online or {}).get("descrizione"):
            sintesi = online["descrizione"]
        if online and online.get("titolo") and not titolo_file:
            titolo = online["titolo"]

        genere = genere_da([(3, titolo), (1, sintesi), (2, " ".join((online or {}).get("categorie", [])))], generi)

        for motivo in avvisi_cattolici(tutto + " " + editore):
            avvisi.append({"tipo": "cattolico", "testo": "Possibile libro cattolico: " + motivo})
        if rt is None:
            avvisi.append({"tipo": "retro", "testo": "Retro non trovato"})
        if not titolo:
            avvisi.append({"tipo": "titolo", "testo": "Titolo non letto: scrivilo tu"})
        if fr.get("incerta") or (rt and rt.get("incerta")):
            avvisi.append({"tipo": "verso", "testo": "Controlla che le foto siano dritte"})
        if not titolo_file and titolo and not online:
            avvisi.append({"tipo": "ocr", "testo": "Titolo letto dalla copertina: controllalo"})

        return {
            "fronte": fr["id"], "retro": rt["id"] if rt else "",
            "titolo": titolo, "titolo_file": titolo_file, "tipo": tipo_da(pagine, titolo),
            "autore": autore, "autore_bio": bio,
            "editore": editore, "anno": anno, "pagine": pagine, "genere": genere,
            "lingua": "Italiano", "isbn": isbn, "descrizione": sintesi, "note": "",
            "copie": 1, "fonte": fonte, "suggerimenti": suggerimenti,
            "avvisi": avvisi, "includi": not any(a["tipo"] == "cattolico" for a in avvisi),
        }

    # ── per la pagina ────────────────────────────────────────────────
    def risultato(self):
        foto = {}
        for k, f in self.foto.items():
            foto[k] = {"id": k, "nome": f["nome"], "rot": f["rot"], "incerta": f.get("incerta", False),
                       "vuota": f.get("vuota", False)}
        generi = sorted(set(self.stato.get("generi", [])) | {g for _, g in REGOLE_GENERE},
                        key=lambda g: senza_accenti(g).lower())
        return {"libri": self.libri, "foto": foto, "generi": generi, "tipi": TIPI_LIBRO,
                "avvisi": self.stato.get("avvisi", []), "ocr": self.stato.get("ocr", False)}

    def miniatura(self, fid):
        f = self.foto.get(fid)
        if not f:
            return ""
        chiave_mini = (fid, f["rot"])
        if chiave_mini not in self._mini:
            img = ruotata(ridotta(apri(f["file"]), LATO_MINI * 2), f["rot"])
            img.thumbnail((LATO_MINI, LATO_MINI), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, "JPEG", quality=80)
            self._mini[chiave_mini] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        return self._mini[chiave_mini]

    def ruota(self, fid, gradi):
        f = self.foto.get(fid)
        if not f:
            return ""
        f["rot"] = (f["rot"] + int(gradi)) % 360
        f["incerta"] = False
        return self.miniatura(fid)

    # ── pubblicazione: immagini nel sito, voci per dati.json ─────────
    def prepara(self, sito, libri):
        """
        Scrive le copertine in <sito>/libreria e restituisce le voci da
        aggiungere a dati.json. Un libro diverso con lo stesso titolo non
        sovrascrive mai i file di un altro: prende un suffisso -2, -3...
        """
        cartella = os.path.join(sito, "libreria")
        os.makedirs(cartella, exist_ok=True)
        voci = []
        for l in libri:
            titolo = (l.get("titolo") or "").strip()
            if not titolo or not l.get("fronte"):
                continue
            base = slug(titolo)
            n, nome = 1, base
            while os.path.exists(os.path.join(cartella, nome + "-fronte.webp")):
                n += 1
                nome = "%s-%d" % (base, n)
            percorsi = {}
            for faccia in ("fronte", "retro"):
                fid = l.get(faccia)
                f = self.foto.get(fid) if fid else None
                if not f:
                    continue
                img = ruotata(apri(f["file"]), f["rot"]).convert("RGB")
                img.thumbnail((LATO_SITO, LATO_SITO), Image.LANCZOS)
                dest = os.path.join(cartella, "%s-%s.webp" % (nome, faccia))
                img.save(dest, "WEBP", quality=82, method=6)
                percorsi[faccia] = "libreria/" + os.path.basename(dest)
            try:
                copie = max(0, int(l.get("copie", 1)))
            except (TypeError, ValueError):
                copie = 1
            try:
                pagine = max(0, int(l.get("pagine") or 0))
            except (TypeError, ValueError):
                pagine = 0
            voci.append({
                "titolo": titolo, "tipo": (l.get("tipo") or "Libro").strip(),
                "autore": (l.get("autore") or "").strip(),
                "autore_bio": (l.get("autore_bio") or "").strip(),
                "editore": (l.get("editore") or "").strip(), "anno": str(l.get("anno") or "").strip(),
                "pagine": pagine, "genere": (l.get("genere") or "").strip(),
                "lingua": (l.get("lingua") or "Italiano").strip(), "isbn": (l.get("isbn") or "").strip(),
                "descrizione": (l.get("descrizione") or "").strip(),
                "copertina": percorsi.get("fronte", ""), "retro": percorsi.get("retro", ""),
                "copie": copie, "note": (l.get("note") or "").strip(),
            })
        return voci


# ══════════════════════════════════════════════════════════════════════
#  Metodi per la pagina (window.pywebview.api.catalogo_*)
# ══════════════════════════════════════════════════════════════════════
class CatalogoAPI:
    """
    Da ereditare nella classe che il programma passa a pywebview come js_api.
    Il programma deve fornire:
        _catalogo_sito()        -> cartella del sito (quella con dati.json)
        _catalogo_finestra()    -> la finestra pywebview (per il dialogo cartella)
        _catalogo_strumenti()   -> cartelle dove cercare Tesseract (opzionale)
        _catalogo_salva(voci)   -> opzionale: salva le voci in dati.json e
                                   restituisce un dict; se manca, le voci
                                   tornano alla pagina che le aggiunge da se'
    Tutti i metodi restituiscono JSON (stringa), cosi' vanno bene per entrambi.
    """

    def _cat(self):
        if not hasattr(self, "_catalogatore_obj"):
            strumenti = []
            if hasattr(self, "_catalogo_strumenti"):
                strumenti = self._catalogo_strumenti() or []
            self._catalogatore_obj = Catalogatore(strumenti)
        return self._catalogatore_obj

    def catalogo_disponibile(self):
        ocr = LettoreOCR(self._catalogo_strumenti() if hasattr(self, "_catalogo_strumenti") else [])
        return json.dumps({"ok": Image is not None, "ocr": ocr.pronto, "lingua": ocr.lingua,
                           "tesseract": ocr.cmd, "barre": zxingcpp is not None})

    def catalogo_installa_ocr(self):
        """
        Scarica e installa Tesseract in Gestione Chiesa\\strumenti\\Tesseract-OCR
        (cartella portabile). Windows chiede il permesso dell'amministratore.
        """
        strumenti = [c for c in (self._catalogo_strumenti() if hasattr(self, "_catalogo_strumenti") else []) if c]
        if os.name != "nt" or not strumenti:
            return json.dumps({"ok": False, "errore": "Installazione automatica possibile solo su Windows."})
        dest = os.path.join(strumenti[0], "strumenti", "Tesseract-OCR")
        tmp = os.path.join(os.environ.get("TEMP", strumenti[0]), "tesseract-setup.exe")
        try:
            req = urllib.request.Request(TESSERACT_SETUP_URL, headers={"User-Agent": "GestioneChiesa/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            import subprocess
            ps = ("Start-Process -FilePath '%s' -ArgumentList '/S','/D=%s' -Verb RunAs -Wait"
                  % (tmp.replace("'", "''"), dest.replace("'", "''")))
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            return json.dumps({"ok": False, "errore": str(e)})
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if hasattr(self, "_catalogatore_obj"):
            del self._catalogatore_obj
        return self.catalogo_disponibile()

    def catalogo_scegli_cartella(self):
        try:
            import webview
            tipo = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
            if tipo is None:
                tipo = getattr(webview, "FOLDER_DIALOG", 20)
            scelta = self._catalogo_finestra().create_file_dialog(tipo)
        except Exception as e:
            return json.dumps({"ok": False, "errore": str(e)})
        if not scelta:
            return json.dumps({"ok": False, "annullato": True})
        percorso = scelta[0] if isinstance(scelta, (list, tuple)) else scelta
        n = len([f for f in os.listdir(percorso) if f.lower().endswith(ESTENSIONI)])
        return json.dumps({"ok": True, "cartella": percorso, "immagini": n})

    def catalogo_avvia(self, cartella, in_rete=True):
        cat = self._cat()
        catalogo = []
        try:
            with open(os.path.join(self._catalogo_sito(), "dati.json"), encoding="utf-8") as f:
                catalogo = json.load(f).get("libreria", []) or []
        except Exception:
            pass
        threading.Thread(target=cat.analizza, args=(cartella, catalogo, bool(in_rete)), daemon=True).start()
        return json.dumps({"ok": True})

    def catalogo_stato(self):
        return json.dumps(self._cat().leggi_stato())

    def catalogo_annulla(self):
        self._cat().annulla()
        return json.dumps({"ok": True})

    def catalogo_risultato(self):
        return json.dumps(self._cat().risultato(), ensure_ascii=False)

    def catalogo_miniatura(self, fid):
        try:
            return json.dumps({"ok": True, "src": self._cat().miniatura(fid)})
        except Exception as e:
            return json.dumps({"ok": False, "errore": str(e)})

    def catalogo_ruota(self, fid, gradi):
        try:
            return json.dumps({"ok": True, "src": self._cat().ruota(fid, gradi)})
        except Exception as e:
            return json.dumps({"ok": False, "errore": str(e)})

    def catalogo_cerca(self, titolo, autore="", isbn=""):
        try:
            if isbn and isbn_valido(isbn):
                r = cerca_isbn(isbn)
                return json.dumps({"ok": True, "risultati": [r] if r else []}, ensure_ascii=False)
            return json.dumps({"ok": True, "risultati": cerca_titolo(titolo, autore)[:5]}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "errore": str(e)})

    def catalogo_conferma(self, libri_json):
        try:
            libri = json.loads(libri_json) if isinstance(libri_json, str) else libri_json
            voci = self._cat().prepara(self._catalogo_sito(), libri)
        except Exception as e:
            return json.dumps({"ok": False, "errore": str(e)})
        if hasattr(self, "_catalogo_salva"):
            esito = self._catalogo_salva(voci) or {}
            esito.setdefault("ok", True)
            esito["voci"] = voci
            esito["salvato"] = esito.get("ok", False)
            return json.dumps(esito, ensure_ascii=False)
        return json.dumps({"ok": True, "salvato": False, "voci": voci}, ensure_ascii=False)
