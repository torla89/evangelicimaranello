#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gestore_sito.py — App desktop per gestire dati.json e pubblicare su GitHub.
Usa pywebview per mostrare gestore.html come finestra nativa.

Setup (una volta sola):
    pip install pywebview

Avvio:
    python gestore_sito.py
    oppure doppio click su "Apri Gestore Sito.bat"
"""

import webview
import json, os, shutil, subprocess, threading, queue
from datetime import datetime

# ── PERCORSI ──────────────────────────────────────────────────
SITE_DIR   = r"C:\Users\torla\OneDrive\Documenti\Chiesa\sito web evangelicimaranello"
JSON_FILE  = os.path.join(SITE_DIR, "dati.json")
BACKUP_DIR = os.path.join(SITE_DIR, "backup")
HTML_FILE  = os.path.join(SITE_DIR, "gestore.html")
# ──────────────────────────────────────────────────────────────


class PythonBridge:

    def __init__(self):
        self._log_q   = queue.Queue()
        self._running = False

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
        with open(os.path.join(dest_dir, "playlist.json"), "w", encoding="utf-8") as fp:
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
        with open(os.path.join(dest_dir, "playlist.json"), "w", encoding="utf-8") as fp:
            json.dump(playlist, fp, ensure_ascii=False, indent=2)

    # ──────────────────────────────────────────────────────────

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
            with open(JSON_FILE, "w", encoding="utf-8") as f:
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
            log("📡 git add...")
            if run("git add dati.json predicazioni/ musica-player/ basi-inni/ *.html") != 0:
                log("❌ git add fallito"); log("__ERROR__"); return

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

    def on_loaded():
        try:
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
