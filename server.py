#!/usr/bin/env python3
"""
Local gallery server for a Vulpea notes directory.
Read/arrange-only canvas: browses your Vulpea notes+media spatially,
saves only x/y/size positions back to disk (never touches your notes).

Notes, tags, and the link graph come from the vulpea database
(vulpea-db-autosync-mode keeps it fresh); note files are read only for
card snippets, and media files are picked up by a directory scan.

Usage:
    python3 server.py /path/to/your/notes/dir [port] [/path/to/vulpea.db]

Then open http://localhost:PORT
"""
import http.server
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
VID_EXT = {".mp4", ".webm", ".mov"}
PDF_EXT = {".pdf"}


HERE = Path(__file__).parent.resolve()
LAYOUT_FILE = HERE / "layout.json"
CONFIG_FILE = HERE / ".config.json"
DEFAULT_DB = "~/.config/emacs/vulpea.db"


def _j(value, default=None):
    """Vulpea stores every db value JSON-encoded; decode with a default.
    Collection columns (tags, ...) are encoded twice - a JSON string
    holding JSON - so decode again when a string decodes to more JSON."""
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            break
    return default if value is None else value


def query_notes(db: Path, root: Path):
    """Read note cards, the id link graph, and the id->card map from vulpea.db.

    A card is a file-level (level 0) note under ROOT.  Heading-level
    notes map to their file's card, so links to and from headings
    resolve at the card level.
    """
    prefix = json.dumps(str(root) + "/")[:-1]  # quoted path prefix for LIKE
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT id, path, level, title, tags FROM notes WHERE path LIKE ?",
            (prefix + "%",),
        ).fetchall()
        link_rows = con.execute(
            "SELECT source, dest FROM links WHERE type = ?", (json.dumps("id"),)
        ).fetchall()
    finally:
        con.close()

    items = []
    path_to_card = {}  # note file path -> its file-level note id
    for note_id, path, level, title, tags in rows:
        if level != 0:
            continue
        path_to_card[_j(path)] = _j(note_id)
        items.append({
            "id": _j(note_id),
            "title": _j(title, ""),
            "tags": _j(tags, []),
            "path": _j(path),
        })

    id_to_card = {}  # any note id (headings included) -> its file's card id
    for note_id, path, level, title, tags in rows:
        card = path_to_card.get(_j(path))
        if card:
            id_to_card[_j(note_id)] = card

    links = set()
    for source, dest in link_rows:
        src_card = id_to_card.get(_j(source))
        dst_card = id_to_card.get(_j(dest))
        if src_card and dst_card and src_card != dst_card:
            links.add(tuple(sorted([src_card, dst_card])))
    return items, sorted(links), id_to_card


def parse_media_name(stem):
    """Best-effort title/tags for a media file (no metadata inside)."""
    m = re.match(r"^(?:\d{8}T\d{6}--)?([^_]+)(?:__(.+))?$", stem)
    if not m:
        return {"title": stem.replace("-", " "), "tags": []}
    title_slug, tags = m.groups()
    return {
        "title": title_slug.replace("-", " "),
        "tags": tags.split("_") if tags else [],
    }


def text_snippet(text, n=400):
    # strip org keywords, property drawers, and drawer-ish lines
    lines = [
        l
        for l in text.splitlines()
        if not l.strip().startswith(("#+", "---", ":"))
    ]
    body = "\n".join(lines).strip()
    return body[:n]


def build_index(root: Path, db: Path):
    notes, links, id_to_card = query_notes(db, root)

    items = []
    for note in notes:
        p = Path(note.pop("path"))
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        try:
            full = p.read_text(errors="ignore")
        except Exception:
            full = ""
        items.append({
            **note,
            "type": "text",
            "snippet": text_snippet(full),
            "src": "/media/" + urllib.parse.quote(rel),
        })

    for p in sorted(root.rglob("*")):
        if p.is_dir() or p.name.startswith("."):
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        ext = p.suffix.lower()
        rel = p.relative_to(root).as_posix()
        src = "/media/" + urllib.parse.quote(rel)
        if ext in IMG_EXT:
            items.append({"id": rel, **parse_media_name(p.stem), "type": "image", "src": src})
        elif ext in VID_EXT:
            items.append({"id": rel, **parse_media_name(p.stem), "type": "video", "src": src})
        elif ext in PDF_EXT:
            items.append({"id": rel, **parse_media_name(p.stem), "type": "pdf", "src": src, "snippet": "[PDF Document]"})
    return items, links, id_to_card


_index_cache = {"mtime": None, "data": None}


def current_mtime():
    """Freshness marker: the database changes on any note edit, the
    directory on media add/remove."""
    return max(DB_FILE.stat().st_mtime, NOTES_DIR.stat().st_mtime)


def get_index_cached():
    """Rebuild the index only when the notes have actually changed."""
    mtime = current_mtime()
    if _index_cache["mtime"] != mtime or _index_cache["data"] is None:
        items, links, idmap = build_index(NOTES_DIR, DB_FILE)
        _index_cache["data"] = {"items": items, "links": links, "idmap": idmap}
        _index_cache["mtime"] = mtime
    return _index_cache["data"]


class Handler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            html = (HERE / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif parsed.path == "/api/index":
            self._send_json(get_index_cached())
        elif parsed.path == "/api/stat":
            self._send_json({"mtime": current_mtime()})
        elif parsed.path == "/api/layout":
            if LAYOUT_FILE.exists():
                self._send_json(json.loads(LAYOUT_FILE.read_text()))
            else:
                self._send_json({})
        elif parsed.path.startswith("/media/"):
            rel = urllib.parse.unquote(parsed.path[len("/media/"):])
            fp = (NOTES_DIR / rel).resolve()
            if not str(fp).startswith(str(NOTES_DIR.resolve())) or not fp.exists():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", guess_type(fp))
            self.end_headers()
            self.wfile.write(fp.read_bytes())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/layout":
            length = int(self.headers.get("Content-Length", 0))
            data = self.rfile.read(length)
            LAYOUT_FILE.write_bytes(data)
            self._send_json({"ok": True})
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        pass  # quiet


def guess_type(fp: Path):
    ext = fp.suffix.lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
        ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
        ".pdf": "application/pdf",
        ".org": "text/plain",
    }.get(ext, "application/octet-stream")


if __name__ == "__main__":
    notes_dir = sys.argv[1] if len(sys.argv) > 1 else None
    port = int(sys.argv[2]) if len(sys.argv) > 2 else None
    db = sys.argv[3] if len(sys.argv) > 3 else None

    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
        except Exception:
            cfg = {}

    if notes_dir is None:
        notes_dir = cfg.get("notes_dir")
        if notes_dir is None:
            notes_dir = input("Path to your notes folder: ").strip()
    if port is None:
        port = cfg.get("port", 8420)
    if db is None:
        db = cfg.get("db", DEFAULT_DB)

    NOTES_DIR = Path(notes_dir).expanduser().resolve()
    if not NOTES_DIR.is_dir():
        print(f"Not a directory: {NOTES_DIR}")
        sys.exit(1)

    DB_FILE = Path(db).expanduser().resolve()
    if not DB_FILE.is_file():
        print(f"vulpea database not found: {DB_FILE}")
        sys.exit(1)

    CONFIG_FILE.write_text(json.dumps(
        {"notes_dir": str(NOTES_DIR), "port": port, "db": str(DB_FILE)}))

    url = f"http://localhost:{port}"
    print(f"Serving {NOTES_DIR} at {url}")
    print("(local only — not reachable from other machines)")
    if not os.environ.get("VULPEA_SPATIAL_NO_OPEN"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    http.server.HTTPServer(("localhost", port), Handler).serve_forever()
