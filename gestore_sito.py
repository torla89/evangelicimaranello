#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gestore_sito.py — App desktop per gestire dati.json e pubblicare su GitHub.
Usa pywebview per mostrare gestore.html come finestra nativa.

Setup (una volta sola):
    pip install pywebview requests mutagen

Avvio:
    python gestore_sito.py
    oppure doppio click su "Apri Gestore Sito.bat" / "Gestore Sito.exe"
"""

import webview
import json, os, shutil, subprocess, threading, queue, sys
from datetime import datetime

# ── CONFIGURAZIONE REPOSITORY ─────────────────────────────────
REPO_URL  = "https://github.com/torla89/evangelicimaranello.git"
GIT_INSTALLER_URL = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe"
# ──────────────────────────────────────────────────────────────


def _msg(titolo, testo):
    """Mostra un messaggio nativo Windows."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, testo, titolo, 0x40)
    except Exception:
        print(f"{titolo}: {testo}")


def _chiedi(titolo, testo):
    """Chiede conferma Sì/No. Ritorna True se Sì."""
    try:
        import ctypes
        r = ctypes.windll.user32.MessageBoxW(0, testo, titolo, 0x24)  # Yes/No + question
        return r == 6
    except Exception:
        return True


def git_disponibile() -> bool:
    try:
        r = subprocess.run("git --version", capture_output=True, shell=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def installa_git() -> bool:
    """Scarica e installa Git for Windows in modo silenzioso."""
    try:
        import urllib.request, tempfile
        _msg("Gestore Sito", "Git non è installato.\n\nVerrà scaricato e installato automaticamente.\nPotrebbe richiedere qualche minuto.")
        tmp = os.path.join(tempfile.gettempdir(), "GitInstaller.exe")
        urllib.request.urlretrieve(GIT_INSTALLER_URL, tmp)
        # Installazione silenziosa
        r = subprocess.run(
            f'"{tmp}" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS',
            shell=True, timeout=900
        )
        try:
            os.remove(tmp)
        except Exception:
            pass
        # Aggiorna il PATH della sessione corrente
        for p in (r"C:\Program Files\Git\cmd", r"C:\Program Files (x86)\Git\cmd"):
            if os.path.isdir(p):
                os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
        return git_disponibile()
    except Exception as e:
        _msg("Errore installazione Git", f"Non è stato possibile installare Git automaticamente.\n\n{e}\n\nScaricalo manualmente da:\nhttps://git-scm.com/download/win")
        return False


def _base_dir() -> str:
    """Cartella dove si trova l'eseguibile/script."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def prepara_cartella_sito() -> str:
    """
    Determina la cartella del sito. Se lo script è già dentro il repo la usa,
    altrimenti clona il repository in una sottocartella.
    """
    base = _base_dir()

    # Caso 1: siamo già dentro il repo (c'è gestore.html accanto)
    if os.path.exists(os.path.join(base, "gestore.html")):
        return base

    # Caso 2: c'è già una sottocartella clonata
    sub = os.path.join(base, "evangelicimaranello")
    if os.path.exists(os.path.join(sub, "gestore.html")):
        return sub

    # Caso 3: bisogna clonare
    if not _chiedi("Gestore Sito",
                   "Il sito non è ancora presente su questo computer.\n\n"
                   "Vuoi scaricarlo ora da GitHub?"):
        sys.exit(0)

    r = subprocess.run(f'git clone "{REPO_URL}" "{sub}"',
                       shell=True, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(os.path.join(sub, "gestore.html")):
        _msg("Errore", f"Clone del repository fallito.\n\n{(r.stderr or '')[:400]}")
        sys.exit(1)
    _msg("Gestore Sito", "Sito scaricato correttamente!")
    return sub


# ── SETUP INIZIALE ────────────────────────────────────────────
if not git_disponibile():
    if not installa_git():
        sys.exit(1)

SITE_DIR   = prepara_cartella_sito()
JSON_FILE  = os.path.join(SITE_DIR, "dati.json")
BACKUP_DIR = os.path.join(SITE_DIR, "backup")
HTML_FILE  = os.path.join(SITE_DIR, "gestore.html")
# ──────────────────────────────────────────────────────────────


class PythonBridge:

    def __init__(self):
        self._log_q      = queue.Queue()
        self._running    = False
        self._window     = None
        self._upload_stato = {"status": "idle", "pct": 0, "speed": "", "message": ""}

    def _estrai_copertina(self, mp3_path: str, filename: str) -> str:
        try:
            from mutagen.id3 import ID3
            tags = ID3(mp3_path)
            for tag in tags.values():
                if tag.__class__.__name__ == 'APIC':
                    ext = 'jpg' if 'jpeg' in tag.mime else 'png'
                    cover_name = os.path.splitext(filename)[0] + '_cover.' + ext
                    cover_path = os.path.join(SITE_DIR, "musica-player", cover_name)
                    with open(cover_path, 'wb') as f:
                        f.write(tag.data)
                    from urllib.parse import quote
                    return f"musica-player/{quote(cover_name, safe='')}"
        except Exception:
            pass
        return "cover_gioia.jpg"

    def _aggiorna_playlist_json(self):
        import json
        from urllib.parse import quote
        dest_dir = os.path.join(SITE_DIR, "musica-player")
        os.makedirs(dest_dir, exist_ok=True)
        files = sorted([f for f in os.listdir(dest_dir) if f.lower().endswith('.mp3')])
        playlist = []
        for f in files:
            encoded = quote(f, safe='')
            base = os.path.splitext(f)[0]
            cover = "cover_gioia.jpg"
            for ext in ['jpg', 'jpeg', 'png']:
                cover_file = f"{base}_cover.{ext}"
                if os.path.exists(os.path.join(dest_dir, cover_file)):
                    cover = f"musica-player/{quote(cover_file, safe='')}"
                    break
            playlist.append({"src": f"musica-player/{encoded}", "title": base,
                              "artist": "Chiesa Evangelica Maranello", "cover": cover})
        with open(os.path.join(dest_dir, "playlist.json"), "w", encoding="utf-8", newline='\n') as fp:
            json.dump(playlist, fp, ensure_ascii=False, indent=2)

    def salva_musica(self, filename: str, base64_data: str) -> str:
        try:
            import base64 as b64mod
            data = b64mod.b64decode(base64_data)
            dest_dir = os.path.join(SITE_DIR, "musica-player")
            os.makedirs(dest_dir, exist_ok=True)
            mp3_path = os.path.join(dest_dir, filename)
            with open(mp3_path, 'wb') as f:
                f.write(data)
            self._estrai_copertina(mp3_path, filename)
            self._aggiorna_playlist_json()
            return "ok"
        except Exception as e:
            return str(e)

    def lista_musica(self) -> str:
        try:
            import json
            dest_dir = os.path.join(SITE_DIR, "musica-player")
            os.makedirs(dest_dir, exist_ok=True)
            files = sorted([f for f in os.listdir(dest_dir) if f.lower().endswith('.mp3')])
            return json.dumps(files)
        except Exception:
            return "[]"

    def elimina_musica(self, filename: str) -> str:
        try:
            mp3_path = os.path.join(SITE_DIR, "musica-player", filename)
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
            base = os.path.splitext(filename)[0]
            for ext in ['jpg', 'jpeg', 'png']:
                cover_path = os.path.join(SITE_DIR, "musica-player", f"{base}_cover.{ext}")
                if os.path.exists(cover_path):
                    os.remove(cover_path)
            self._aggiorna_playlist_json()
            return "ok"
        except Exception as e:
            return str(e)

    # ── BASI INNI ─────────────────────────────────────────────
    def salva_base(self, filename: str, base64_data: str) -> str:
        """Salva un MP3 nella cartella basi-inni/ e aggiorna playlist.json."""
        try:
            import base64 as b64mod
            data = b64mod.b64decode(base64_data)
            dest_dir = os.path.join(SITE_DIR, "basi-inni")
            os.makedirs(dest_dir, exist_ok=True)
            with open(os.path.join(dest_dir, filename), 'wb') as f:
                f.write(data)
            self._aggiorna_basi_json()
            return "ok"
        except Exception as e:
            return str(e)

    def lista_basi(self) -> str:
        """Restituisce la lista dei file MP3 in basi-inni/."""
        try:
            import json
            dest_dir = os.path.join(SITE_DIR, "basi-inni")
            os.makedirs(dest_dir, exist_ok=True)
            files = sorted([f for f in os.listdir(dest_dir) if f.lower().endswith('.mp3')])
            return json.dumps(files)
        except Exception:
            return "[]"

    def elimina_base(self, filename: str) -> str:
        """Elimina un MP3 da basi-inni/ e aggiorna playlist.json."""
        try:
            path = os.path.join(SITE_DIR, "basi-inni", filename)
            if os.path.exists(path):
                os.remove(path)
            self._aggiorna_basi_json()
            return "ok"
        except Exception as e:
            return str(e)

    def _aggiorna_basi_json(self):
        """Rigenera basi-inni/playlist.json ordinato numericamente."""
        import json, re
        from urllib.parse import quote
        dest_dir = os.path.join(SITE_DIR, "basi-inni")
        os.makedirs(dest_dir, exist_ok=True)
        files = os.listdir(dest_dir)
        files = [f for f in files if f.lower().endswith('.mp3')]
        # Ordina numericamente estraendo il numero iniziale dal nome file
        def sort_key(f):
            m = re.match(r'^(\d+)', f)
            return (int(m.group(1)) if m else 9999, f)
        files = sorted(files, key=sort_key)
        playlist = [{"src": f"basi-inni/{quote(f, safe='')}", "title": os.path.splitext(f)[0], "cover": ""} for f in files]
        with open(os.path.join(dest_dir, "playlist.json"), "w", encoding="utf-8", newline='\n') as fp:
            json.dump(playlist, fp, ensure_ascii=False, indent=2)

    # ──────────────────────────────────────────────────────────

    def avvia_upload(self, filepath: str, collezione: str,
                      access_key: str, secret_key: str, tipo: str = 'musica') -> str:
        """Avvia upload in background e aggiorna lo stato."""
        self._upload_stato = {"status": "uploading", "pct": 0, "speed": "", "message": ""}
        threading.Thread(
            target=self._upload_thread,
            args=(filepath, collezione, access_key, secret_key, tipo),
            daemon=True
        ).start()
        return "started"

    def stato_upload(self) -> str:
        """Restituisce lo stato corrente dell'upload come JSON."""
        import json
        return json.dumps(getattr(self, '_upload_stato', {"status": "idle", "pct": 0}))

    # ── IMMAGINI (copertine libreria) ─────────────────────────
    def salva_copertina(self, filepath: str, titolo: str, faccia: str) -> str:
        """
        Mette una copertina nella cartella "libreria" del sito e restituisce
        il percorso da scrivere in dati.json (es. "libreria/sii-forte-fronte.webp").

        Le copertine stanno dentro al sito e non piu' su Archive.org: cosi' la
        pagina non dipende da un servizio esterno, si carica piu' in fretta e
        le immagini viaggiano con il repository.
        """
        import json, re, unicodedata
        try:
            from PIL import Image
        except ImportError:
            return json.dumps({"ok": False, "errore":
                "Manca la libreria Pillow: lancia build_exe.bat per installarla."})
        try:
            base = titolo.strip() or os.path.splitext(os.path.basename(filepath))[0]
            # gli apostrofi diventano trattini, altrimenti "Cos'e" si saldera' in "Cose"
            base = re.sub(r"['\u2019\u02bc`]", "-", base)
            nome = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
            nome = re.sub(r"[^a-zA-Z0-9]+", "-", nome).strip("-").lower()
            nome = re.sub(r"-{2,}", "-", nome) or "copertina"
            faccia = "retro" if faccia == "retro" else "fronte"

            dest_dir = os.path.join(SITE_DIR, "libreria")
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, f"{nome}-{faccia}.webp")

            img = Image.open(filepath)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            img.thumbnail((900, 900), Image.LANCZOS)
            img.save(dest, "WEBP", quality=82, method=6)

            return json.dumps({"ok": True,
                               "percorso": "libreria/" + os.path.basename(dest),
                               "kb": os.path.getsize(dest) // 1024})
        except Exception as e:
            return json.dumps({"ok": False, "errore": str(e)})

    def _ottimizza_immagine(self, filepath: str):
        """
        Ridimensiona e comprime una copertina per il web.
        Ritorna (bytes, nome_file, content_type). Se Pillow non è installato
        restituisce il file originale senza modifiche.
        """
        import mimetypes
        base = os.path.splitext(os.path.basename(filepath))[0]
        try:
            from PIL import Image
            import io as _io
            img = Image.open(filepath)
            has_alpha = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)
            img = img.convert('RGBA' if has_alpha else 'RGB')
            img.thumbnail((1000, 1000), Image.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, format='WEBP', quality=85, method=6)
            return buf.getvalue(), base + '.webp', 'image/webp'
        except Exception:
            with open(filepath, 'rb') as f:
                data = f.read()
            nome = os.path.basename(filepath)
            ctype = mimetypes.guess_type(nome)[0] or 'application/octet-stream'
            return data, nome, ctype

    def seleziona_file_immagine(self) -> list:
        """Dialogo nativo per selezionare immagini (copertine libri)."""
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Immagini (*.png;*.jpg;*.jpeg;*.webp)', 'Tutti i file (*.*)')
            )
            if result:
                return list(result)
            return []
        except Exception:
            return []

    def _upload_thread(self, filepath: str, collezione: str,
                        access_key: str, secret_key: str, tipo: str):
        import re, time, io
        from urllib.parse import quote
        try:
            if tipo == 'immagine':
                data, filename, content_type = self._ottimizza_immagine(filepath)
                mediatype = 'image'
            else:
                with open(filepath, 'rb') as f:
                    data = f.read()
                filename = os.path.basename(filepath)
                content_type = 'audio/mpeg'
                mediatype = 'audio'
            total = len(data)
            filename_encoded = quote(filename, safe='')
            url = f"https://s3.us.archive.org/{collezione}/{filename_encoded}"

            # Upload con tracking progresso
            import requests
            uploaded = [0]
            start_time = [time.time()]
            chunk_size = 256 * 1024  # 256KB chunks

            class ProgressReader(io.RawIOBase):
                def __init__(self, data):
                    self._data = data
                    self._pos = 0
                # Questi due servono a far sapere a requests quanto e' lungo
                # il file. Senza, lo manda "a pezzi" (chunked) e Archive.org
                # rifiuta gli invii di cui non conosce la lunghezza: HTTP 411.
                def __len__(self):
                    return len(self._data)
                def tell(self):
                    return self._pos
                def read(self, n=-1):
                    chunk = self._data[self._pos:self._pos+n] if n > 0 else self._data[self._pos:]
                    self._pos += len(chunk)
                    uploaded[0] = self._pos
                    elapsed = time.time() - start_time[0]
                    pct = int(self._pos / total * 100)
                    if elapsed > 0:
                        speed_bps = self._pos / elapsed
                        if speed_bps > 1024*1024:
                            speed_str = f"{speed_bps/1024/1024:.1f} MB/s"
                        else:
                            speed_str = f"{speed_bps/1024:.0f} KB/s"
                    else:
                        speed_str = ""
                    self._outer._upload_stato = {
                        "status": "uploading", "pct": pct, "speed": speed_str, "message": ""
                    }
                    return chunk
                def readable(self): return True

            reader = ProgressReader(data)
            reader._outer = self

            headers = {
                'Authorization': f'LOW {access_key}:{secret_key}',
                'x-archive-auto-make-bucket': '1',
                'x-archive-meta-mediatype': mediatype,
                'Content-Type': content_type,
                'Content-Length': str(total),
            }
            r = requests.put(url, data=reader, headers=headers, timeout=600)

            if r.status_code in (200, 201):
                file_url = f"https://archive.org/download/{collezione}/{filename_encoded}"
                if tipo == 'immagine':
                    pass  # nessuna playlist da aggiornare: l'URL torna all'interfaccia
                elif tipo == 'basi':
                    title = filename.replace('.mp3','').replace('.MP3','').strip()
                    self._aggiungi_a_playlist_basi(file_url, title)
                else:
                    title = re.sub(r'^\d+\s*-\s*', '', filename.replace('.mp3','').replace('.MP3','')).strip()
                    self._aggiungi_a_playlist_musica(file_url, title)
                self._upload_stato = {"status": "done", "pct": 100, "speed": "",
                                      "message": "", "url": file_url}
            else:
                self._upload_stato = {"status": "error", "pct": 0, "speed": "", "message": f"HTTP {r.status_code}"}
        except Exception as e:
            self._upload_stato = {"status": "error", "pct": 0, "speed": "", "message": str(e)}

    def seleziona_file_mp3(self) -> list:
        """Apre il dialogo nativo di pywebview per selezionare file MP3."""
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=('File audio (*.mp3;*.wav;*.MP3)', 'Tutti i file (*.*)')
            )
            if result:
                return list(result)
            return []
        except Exception as e:
            return []

    def carica_file_su_archive(self, filepath: str, collezione: str,
                                access_key: str, secret_key: str,
                                tipo: str = 'musica') -> str:
        """Carica un file direttamente dal path locale su Archive.org."""
        try:
            import re, requests, io
            from urllib.parse import quote

            filename = os.path.basename(filepath)
            with open(filepath, 'rb') as f:
                data = f.read()

            if not data:
                return "Errore: file vuoto"

            filename_encoded = quote(filename, safe='')
            url = f"https://s3.us.archive.org/{collezione}/{filename_encoded}"

            headers = {
                'Authorization': f'LOW {access_key}:{secret_key}',
                'x-archive-auto-make-bucket': '1',
                'x-archive-meta-mediatype': 'audio',
                'Content-Type': 'audio/mpeg',
                'Content-Length': str(len(data)),
            }
            r = requests.put(url, data=io.BytesIO(data), headers=headers, timeout=600)
            if r.status_code not in (200, 201):
                return f"Errore HTTP {r.status_code}: {r.text[:200]}"

            file_url = f"https://archive.org/download/{collezione}/{filename_encoded}"
            if tipo == 'basi':
                title = filename.replace('.mp3','').replace('.MP3','').replace('.wav','').replace('.WAV','').strip()
                self._aggiungi_a_playlist_basi(file_url, title)
            else:
                title = re.sub(r'^\d+\s*-\s*', '', filename.replace('.mp3','').replace('.MP3','')).strip()
                self._aggiungi_a_playlist_musica(file_url, title)

            return "ok"
        except Exception as e:
            return str(e)

    def salva_chiavi_s3(self, access: str, secret: str) -> str:
        """Salva le chiavi S3 in un file locale."""
        try:
            import json
            path = os.path.join(SITE_DIR, ".s3keys")
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump({"access": access, "secret": secret}, f)
            return "ok"
        except Exception as e:
            return str(e)

    def leggi_chiavi_s3(self) -> str:
        """Legge le chiavi S3 dal file locale."""
        try:
            import json
            path = os.path.join(SITE_DIR, ".s3keys")
            if os.path.exists(path):
                with open(path) as f:
                    return f.read()
            return "{}"
        except Exception as e:
            return "{}"

    def carica_su_archive(self, filename: str, base64_data: str,
                           collezione: str, access_key: str, secret_key: str,
                           tipo: str = 'musica') -> str:
        """Carica un file su Archive.org via S3 e aggiorna il playlist.json locale."""
        try:
            import base64 as b64mod, re, io
            from urllib.parse import quote
            data = b64mod.b64decode(base64_data)
            if not data:
                return "Errore: file vuoto"

            filename_encoded = quote(filename, safe='')
            url = f"https://s3.us.archive.org/{collezione}/{filename_encoded}"

            try:
                import requests
                headers = {
                    'Authorization': f'LOW {access_key}:{secret_key}',
                    'x-archive-auto-make-bucket': '1',
                    'x-archive-meta-mediatype': 'audio',
                    'Content-Type': 'audio/mpeg',
                    'Content-Length': str(len(data)),
                }
                r = requests.put(url, data=io.BytesIO(data), headers=headers, timeout=600)
                if r.status_code not in (200, 201):
                    return f"Errore HTTP {r.status_code}: {r.text[:200]}"
            except ImportError:
                # Fallback a urllib se requests non è installato
                import urllib.request, urllib.error
                req = urllib.request.Request(url, data=data, method='PUT')
                req.add_header('Authorization', f'LOW {access_key}:{secret_key}')
                req.add_header('x-archive-auto-make-bucket', '1')
                req.add_header('x-archive-meta-mediatype', 'audio')
                req.add_header('Content-Type', 'audio/mpeg')
                req.add_header('Content-Length', str(len(data)))
                try:
                    with urllib.request.urlopen(req, timeout=600) as r:
                        if r.status not in (200, 201):
                            return f"Errore HTTP {r.status}"
                except urllib.error.HTTPError as e:
                    return f"Errore HTTP {e.code}: {e.reason}"

            # Aggiorna playlist.json locale
            file_url = f"https://archive.org/download/{collezione}/{filename_encoded}"
            if tipo == 'basi':
                title = filename.replace('.mp3','').replace('.MP3','').strip()
                self._aggiungi_a_playlist_basi(file_url, title)
            else:
                title = re.sub(r'^\d+\s*-\s*', '', filename.replace('.mp3','').replace('.MP3','')).strip()
                self._aggiungi_a_playlist_musica(file_url, title)

            return "ok"
        except Exception as e:
            return str(e)

    def _aggiungi_a_playlist_musica(self, url: str, titolo: str):
        import json
        path = os.path.join(SITE_DIR, "musica-player", "playlist.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        playlist = []
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                playlist = json.load(f)
        # Evita duplicati
        if not any(p['src'] == url for p in playlist):
            playlist.append({"src": url, "title": titolo, "artist": "Chiesa Evangelica Maranello", "cover": ""})
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(playlist, f, ensure_ascii=False, indent=2)

    def _aggiungi_a_playlist_basi(self, url: str, titolo: str):
        import json, re, shutil
        path = os.path.join(SITE_DIR, "basi-inni", "playlist.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        playlist = []
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    content = f.read().strip()
                if content:
                    playlist = json.loads(content)
                # Backup prima di modificare
                shutil.copy2(path, path + '.bak')
            except Exception:
                # File corrotto — ripristina dal backup se esiste
                bak = path + '.bak'
                if os.path.exists(bak):
                    shutil.copy2(bak, path)
                    with open(path, encoding='utf-8') as f:
                        playlist = json.load(f)
                else:
                    playlist = []
        if not any(p['src'] == url for p in playlist):
            playlist.append({"src": url, "title": titolo, "cover": ""})
            def sort_key(item):
                t = item.get('title', '')
                m = re.match(r'^(\d+)', t)
                if not m:
                    fname = item.get('src', '').split('/')[-1]
                    from urllib.parse import unquote
                    fname = unquote(fname)
                    m = re.match(r'^(\d+)', fname)
                return int(m.group(1)) if m else 9999
            playlist.sort(key=sort_key)
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(playlist, f, ensure_ascii=False, indent=2)

    def aggiungi_musica_url(self, url: str, titolo: str, cover: str = '') -> str:
        """Aggiunge un brano alla playlist musica-player/playlist.json tramite URL Archive.org."""
        try:
            import json
            playlist_path = os.path.join(SITE_DIR, "musica-player", "playlist.json")
            os.makedirs(os.path.dirname(playlist_path), exist_ok=True)
            playlist = []
            if os.path.exists(playlist_path):
                with open(playlist_path, encoding='utf-8') as f:
                    playlist = json.load(f)
            playlist.append({"src": url, "title": titolo, "artist": "Chiesa Evangelica Maranello", "cover": cover})
            with open(playlist_path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(playlist, f, ensure_ascii=False, indent=2)
            return "ok"
        except Exception as e:
            return str(e)

    def lista_musica_url(self) -> str:
        """Restituisce la playlist musica-player/playlist.json."""
        try:
            import json
            playlist_path = os.path.join(SITE_DIR, "musica-player", "playlist.json")
            if os.path.exists(playlist_path):
                with open(playlist_path, encoding='utf-8') as f:
                    return f.read()
            return "[]"
        except Exception as e:
            return "[]"

    def elimina_musica_url(self, idx: int) -> str:
        """Rimuove un brano dalla playlist musica-player/playlist.json per indice."""
        try:
            import json
            playlist_path = os.path.join(SITE_DIR, "musica-player", "playlist.json")
            with open(playlist_path, encoding='utf-8') as f:
                playlist = json.load(f)
            if 0 <= idx < len(playlist):
                playlist.pop(idx)
            with open(playlist_path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(playlist, f, ensure_ascii=False, indent=2)
            return "ok"
        except Exception as e:
            return str(e)

    def aggiungi_base_url(self, url: str, titolo: str) -> str:
        """Aggiunge una base a basi-inni/playlist.json tramite URL Archive.org."""
        try:
            self._aggiungi_a_playlist_basi(url, titolo)
            return "ok"
        except Exception as e:
            return str(e)

    def lista_basi_url(self) -> str:
        """Restituisce la playlist basi-inni/playlist.json."""
        try:
            playlist_path = os.path.join(SITE_DIR, "basi-inni", "playlist.json")
            if os.path.exists(playlist_path):
                with open(playlist_path, encoding='utf-8') as f:
                    return f.read()
            return "[]"
        except Exception as e:
            return "[]"

    def elimina_base_url(self, idx: int) -> str:
        """Rimuove una base da basi-inni/playlist.json per indice."""
        try:
            import json
            playlist_path = os.path.join(SITE_DIR, "basi-inni", "playlist.json")
            with open(playlist_path, encoding='utf-8') as f:
                playlist = json.load(f)
            if 0 <= idx < len(playlist):
                playlist.pop(idx)
            with open(playlist_path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(playlist, f, ensure_ascii=False, indent=2)
            return "ok"
        except Exception as e:
            return str(e)

    def aggiungi_predicazione_vecchia(self, predicatore: str, titolo: str, mp3_url: str) -> str:
        """Aggiunge un messaggio a predicazioni_vecchie.json raggruppato per predicatore."""
        try:
            import json
            path = os.path.join(SITE_DIR, "predicazioni_vecchie.json")
            data = {}
            if os.path.exists(path):
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            if predicatore not in data:
                data[predicatore] = []
            data[predicatore].append({"titolo": titolo, "src": mp3_url})
            # Riordina predicatori alfabeticamente
            data = dict(sorted(data.items()))
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return "ok"
        except Exception as e:
            return str(e)

    def salva_pdf(self, filename: str, base64_data: str) -> str:
        try:
            import base64 as b64mod
            data = b64mod.b64decode(base64_data)
            subdir = "predicazioni"
            dest_dir = os.path.join(SITE_DIR, subdir)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, filename)
            with open(dest, 'wb') as f:
                f.write(data)
            return "ok"
        except Exception as e:
            return str(e)

    def sincronizza_da_github(self) -> str:
        """
        Scarica le ultime modifiche da GitHub prima di caricare i dati.
        Ritorna JSON con esito: {"ok": true/false, "message": "..."}
        """
        import json as _json
        try:
            # Controlla se ci sono modifiche locali non committate
            status = subprocess.run(
                "git status --porcelain", cwd=SITE_DIR,
                capture_output=True, text=True, shell=True, timeout=30
            )
            modifiche_locali = bool(status.stdout.strip())

            if modifiche_locali:
                # Stash temporaneo per non perdere modifiche
                subprocess.run("git stash", cwd=SITE_DIR,
                              capture_output=True, text=True, shell=True, timeout=30)

            # Pull
            r = subprocess.run(
                "git pull --rebase", cwd=SITE_DIR,
                capture_output=True, text=True, shell=True, timeout=60,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
            )

            if modifiche_locali:
                # Ripristina le modifiche locali
                subprocess.run("git stash pop", cwd=SITE_DIR,
                              capture_output=True, text=True, shell=True, timeout=30)

            out = (r.stdout or "").strip() + (" " + r.stderr.strip() if r.stderr.strip() else "")
            if r.returncode == 0:
                if "up to date" in out.lower() or "aggiornato" in out.lower():
                    return _json.dumps({"ok": True, "message": "Già aggiornato"})
                return _json.dumps({"ok": True, "message": "Sincronizzato con GitHub"})
            return _json.dumps({"ok": False, "message": out[:200] or "Errore git pull"})
        except subprocess.TimeoutExpired:
            return _json.dumps({"ok": False, "message": "Timeout — connessione lenta o assente"})
        except Exception as e:
            return _json.dumps({"ok": False, "message": str(e)[:200]})

    def carica_auto(self) -> str:
        try:
            if os.path.exists(JSON_FILE):
                with open(JSON_FILE, encoding="utf-8") as f:
                    return f.read()
            return "__NOT_FOUND__"
        except Exception as e:
            return f"__ERROR__:{e}"

    def salva_json(self, json_str: str) -> str:
        try:
            dati = json.loads(json_str)
            os.makedirs(BACKUP_DIR, exist_ok=True)
            if os.path.exists(JSON_FILE):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                dst = os.path.join(BACKUP_DIR, f"dati_backup_{ts}.json")
                shutil.copy2(JSON_FILE, dst)
            with open(JSON_FILE, "w", encoding="utf-8", newline='\n') as f:
                json.dump(dati, f, ensure_ascii=False, indent=2)
            return "ok"
        except Exception as e:
            return str(e)

    def git_push_start(self) -> str:
        if self._running:
            return "busy"
        self._running = True
        while not self._log_q.empty():
            self._log_q.get_nowait()
        threading.Thread(target=self._push_thread, daemon=True).start()
        return "started"

    def git_push_poll(self) -> str:
        try:
            return self._log_q.get(timeout=2.0)
        except queue.Empty:
            return ""

    def _push_thread(self):
        def log(msg): self._log_q.put(msg)

        def run(cmd):
            r = subprocess.run(cmd, cwd=SITE_DIR,
                               capture_output=True, text=True, shell=True,
                               env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
            if r.stdout.strip(): log(r.stdout.strip())
            if r.stderr.strip(): log(r.stderr.strip())
            return r.returncode

        try:
            log(f"📁 {SITE_DIR}")
            log("")

            # Configura credential helper per non chiedere password
            run("git config credential.helper manager-core")

            log("📡 git add...")
            # Aggiungi solo ciò che esiste
            run("git add dati.json")
            run("git add predicazioni_vecchie.json")
            run("git add musica-player/playlist.json")
            run("git add basi-inni/playlist.json")
            run("git add canti/playlist.json")
            run("git add *.html")
            # Cartella predicazioni solo se esiste
            import os as _os
            if _os.path.exists(_os.path.join(SITE_DIR, "predicazioni")):
                run("git add predicazioni/")

            # Verifica che ci sia qualcosa da committare
            status = subprocess.run("git status --porcelain", cwd=SITE_DIR,
                                   capture_output=True, text=True, shell=True)
            if not status.stdout.strip():
                log("⚠  Nessuna modifica da pubblicare"); log("__DONE__"); return

            msg = f"aggiorna dati.json - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            log(f"📝 commit: {msg}")
            rc = run(f'git commit -m "{msg}"')
            if rc != 0:
                log("⚠  Nessuna modifica (file identico)"); log("__DONE__"); return

            log("🚀 git push...")
            if run("git push") != 0:
                log("❌ Push fallito — controlla credenziali"); log("__ERROR__"); return

            log(""); log("✅ Pubblicato su GitHub!"); log("__DONE__")

        except Exception as e:
            log(f"❌ {e}"); log("__ERROR__")
        finally:
            self._running = False


def main():
    bridge = PythonBridge()

    url = "file:///" + HTML_FILE.replace("\\", "/")

    window = webview.create_window(
        title      = "Gestione Sito — Chiesa Evangelica Maranello",
        url        = url,
        js_api     = bridge,
        width      = 920,
        height     = 700,
        min_size   = (720, 520),
        background_color = "#0a0704",
        confirm_close    = True,
    )

    # Passa la finestra al bridge così può aprire dialoghi nativi
    bridge._window = window

    def on_loaded():
        try:
            # 1. Sincronizza da GitHub
            window.evaluate_js("setSyncStatus('loading', 'Sincronizzazione...')")
            esito = bridge.sincronizza_da_github()
            esito_esc = esito.replace("\\", "\\\\").replace("`", "\\`")
            window.evaluate_js(f"applicaSyncEsito(`{esito_esc}`)")

            # 2. Carica dati.json aggiornato
            if os.path.exists(JSON_FILE):
                with open(JSON_FILE, encoding="utf-8") as f:
                    content = f.read()
                content_escaped = content.replace("\\", "\\\\").replace("`", "\\`")
                window.evaluate_js(f"parsaECarica(`{content_escaped}`, 'dati.json')")
            else:
                window.evaluate_js(
                    "setStatus('warn', 'dati.json non trovato — selezionalo manualmente')"
                )
        except Exception as e:
            window.evaluate_js(f"setStatus('warn', 'Errore: {e}')")

    webview.start(on_loaded, debug=False)


if __name__ == "__main__":
    main()
