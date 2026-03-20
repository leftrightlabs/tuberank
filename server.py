#!/usr/bin/env python3
"""
TubeRank local server — proxies YouTube & Anthropic API calls.
Run: python3 server.py
Then open: http://localhost:8765

Secrets: set environment variables (optional: create .env next to this file — see .env.example).
"""
import http.server, urllib.request, urllib.parse, json, os, sys, re

PORT = 8765
DIR  = os.path.dirname(os.path.abspath(__file__))

# Load .env from project directory if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(DIR, ".env"))
except ImportError:
    pass


def _env(name, default=""):
    return (os.environ.get(name) or default).strip()


ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
YOUTUBE_API_KEY = _env("YOUTUBE_API_KEY")
YOUTUBE_CHANNEL_ID = _env("YOUTUBE_CHANNEL_ID")
NOTION_TOKEN = _env("NOTION_TOKEN")
NOTION_PAGE_ID = _env("NOTION_PAGE_ID")
TUBERANK_PASSWORD = _env("TUBERANK_PASSWORD")


def notion_normalize_page_id(page_id):
    """Notion API expects a UUID; accept dashed, undashed, or full notion.so URLs."""
    if not page_id:
        return ""
    s = page_id.strip()
    # Full URL: ...notion.so/Page-Title-abc123... or ...?p=...
    m = re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        s,
        re.I,
    )
    if m:
        return m.group(1).lower()
    hex32 = re.sub(r"[^0-9a-f]", "", s, flags=re.I)
    if len(hex32) == 32:
        return f"{hex32[0:8]}-{hex32[8:12]}-{hex32[12:16]}-{hex32[16:20]}-{hex32[20:32]}"
    return s


class Handler(http.server.BaseHTTPRequestHandler):
    def _http_json(self, url, headers=None, timeout=20):
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))

    def _notion_text_from_rich(self, rich):
        return "".join([(x.get("plain_text") or "") for x in (rich or [])])

    def _notion_block_to_line(self, block):
        btype = block.get("type", "")
        data = block.get(btype, {}) if isinstance(block.get(btype, {}), dict) else {}
        txt = self._notion_text_from_rich(data.get("rich_text", []))
        if not txt:
            if btype == "child_page":
                txt = block.get("child_page", {}).get("title", "")
            elif btype == "to_do":
                txt = self._notion_text_from_rich(data.get("rich_text", []))
        if not txt:
            return ""
        if btype == "callout":
            icon = (data.get("icon") or {}).get("emoji", "")
            prefix = f"{icon} " if icon else ""
            return f"{prefix}{txt}"
        if btype == "toggle":
            return f"▸ {txt}"
        if btype in ("heading_1", "heading_2", "heading_3"):
            return f"\n{txt}\n"
        if btype == "bulleted_list_item":
            return f"- {txt}"
        if btype == "numbered_list_item":
            return f"1. {txt}"
        if btype == "to_do":
            checked = data.get("checked", False)
            return f"[{'x' if checked else ' '}] {txt}"
        if btype == "quote":
            return f"> {txt}"
        if btype == "code":
            return f"`{txt}`"
        return txt

    def _notion_collect_lines(self, block_id, headers, depth=0, max_depth=4):
        if depth > max_depth:
            return []
        lines = []
        cursor = None
        while True:
            q = {"page_size": 100}
            if cursor:
                q["start_cursor"] = cursor
            url = f"https://api.notion.com/v1/blocks/{block_id}/children?" + urllib.parse.urlencode(q)
            data = self._http_json(url, headers=headers, timeout=25)
            for block in data.get("results", []):
                line = self._notion_block_to_line(block)
                if line:
                    lines.append(line)
                if block.get("has_children"):
                    child_lines = self._notion_collect_lines(block["id"], headers, depth + 1, max_depth)
                    lines.extend(child_lines)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return lines

    def log_message(self, fmt, *args):
        print(f"  {args[0]} {args[1]}")   # tidy log

    def send_cors(self, code=200, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_cors()

    # ── GET: serve static files ──────────────────────────────────────────────
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/proxy/health":
            body = json.dumps({
                "youtube": bool(YOUTUBE_API_KEY),
                "claude": bool(ANTHROPIC_API_KEY),
                "notionToken": bool(NOTION_TOKEN),
                "notionPageFromEnv": bool(NOTION_PAGE_ID),
                "youtubeChannel": bool(YOUTUBE_CHANNEL_ID),
                "passwordGate": bool(TUBERANK_PASSWORD),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/" or path == "":
            path = "/tuberank.html"
        filepath = os.path.join(DIR, path.lstrip("/"))
        if os.path.isfile(filepath):
            ext = filepath.rsplit(".", 1)[-1]
            ct  = {"html":"text/html","js":"application/javascript","css":"text/css"}.get(ext,"text/plain")
            with open(filepath, "rb") as f:
                data = f.read()
            self.send_cors(200, ct)
            self.wfile.write(data)
        else:
            self.send_cors(404, "text/plain")
            self.wfile.write(b"Not found")

    # ── POST: proxy API calls ────────────────────────────────────────────────
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        try:
            payload = json.loads(body)
        except Exception:
            self.send_cors(400)
            self.wfile.write(json.dumps({"error":"bad json"}).encode())
            return

        path = urllib.parse.urlparse(self.path).path

        # ── /proxy/login  ────────────────────────────────────────────────────
        if path == "/proxy/login":
            if not TUBERANK_PASSWORD:
                self.send_cors(503)
                self.wfile.write(json.dumps({
                    "error": {"message": "Server missing TUBERANK_PASSWORD in .env"}
                }).encode())
                return
            if not YOUTUBE_CHANNEL_ID:
                self.send_cors(503)
                self.wfile.write(json.dumps({
                    "error": {"message": "Server missing YOUTUBE_CHANNEL_ID in .env"}
                }).encode())
                return
            got = (payload.get("password") or "")
            if got != TUBERANK_PASSWORD:
                self.send_cors(401)
                self.wfile.write(json.dumps({"error": {"message": "Invalid password"}}).encode())
                return
            self.send_cors()
            self.wfile.write(json.dumps({"ok": True, "channelId": YOUTUBE_CHANNEL_ID}).encode())
            return

        # ── /proxy/youtube  ──────────────────────────────────────────────────
        if path == "/proxy/youtube":
            yt_key = YOUTUBE_API_KEY
            endpoint = payload.get("endpoint", "")
            if not yt_key:
                self.send_cors(503)
                self.wfile.write(json.dumps({
                    "error": {"message": "Server missing YOUTUBE_API_KEY. Set it in .env or the environment."}
                }).encode())
                return
            if not endpoint:
                self.send_cors(400)
                self.wfile.write(json.dumps({"error": {"message": "missing endpoint"}}).encode())
                return

            # Support either API key (AIza...) or OAuth access token.
            # If it does not look like an API key, send it as Bearer token.
            is_api_key = yt_key.startswith("AIza")
            url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
            if is_api_key:
                sep = "&" if "?" in endpoint else "?"
                url = f"{url}{sep}key={yt_key}"
            try:
                headers = {}
                if not is_api_key:
                    headers["Authorization"] = f"Bearer {yt_key}"
                req  = urllib.request.Request(url, headers=headers)
                resp = urllib.request.urlopen(req, timeout=15)
                data = resp.read()
                self.send_cors()
                self.wfile.write(data)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                self.send_cors(e.code)
                # Forward YouTube's error message so the UI can show it
                self.wfile.write(err_body.encode())
            except Exception as e:
                self.send_cors(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        # ── /proxy/claude  ───────────────────────────────────────────────────
        elif path == "/proxy/claude":
            claude_key = ANTHROPIC_API_KEY
            messages   = payload.get("messages", [])
            model      = payload.get("model", "claude-sonnet-4-20250514")
            max_tokens = payload.get("max_tokens", 1000)
            if not claude_key:
                self.send_cors(503)
                self.wfile.write(json.dumps({
                    "error": {"message": "Server missing ANTHROPIC_API_KEY. Set it in .env or the environment."}
                }).encode())
                return
            claude_payload = json.dumps({
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=claude_payload,
                headers={
                    "Content-Type":       "application/json",
                    "x-api-key":          claude_key,
                    "anthropic-version":  "2023-06-01",
                }
            )
            try:
                resp = urllib.request.urlopen(req, timeout=60)
                data = resp.read()
                self.send_cors()
                self.wfile.write(data)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                self.send_cors(e.code)
                self.wfile.write(err_body.encode())
            except Exception as e:
                self.send_cors(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        # ── /proxy/notion-context  ───────────────────────────────────────────
        elif path == "/proxy/notion-context":
            notion_key = NOTION_TOKEN
            page_id = NOTION_PAGE_ID
            if not notion_key:
                self.send_cors(503)
                self.wfile.write(json.dumps({
                    "error": {"message": "Server missing NOTION_TOKEN. Set it in .env or the environment."}
                }).encode())
                return
            if not page_id:
                self.send_cors(400)
                self.wfile.write(json.dumps({
                    "error": {"message": "Missing Notion page: set NOTION_PAGE_ID in .env."}
                }).encode())
                return
            page_id = notion_normalize_page_id(page_id)
            headers = {
                "Authorization": f"Bearer {notion_key}",
                "Notion-Version": "2022-06-28",
            }
            try:
                page_url = f"https://api.notion.com/v1/pages/{page_id}"
                page = self._http_json(page_url, headers=headers, timeout=20)
                title = "Notion Context"
                props = page.get("properties", {})
                for _, val in props.items():
                    if val.get("type") == "title":
                        t = self._notion_text_from_rich(val.get("title", []))
                        if t:
                            title = t
                            break
                lines = self._notion_collect_lines(page_id, headers=headers, depth=0, max_depth=4)
                text = "\n".join([ln for ln in lines if ln]).strip()
                if not text:
                    text = (
                        f"(No extractable text blocks on this page yet. Title: \"{title}\". "
                        "Add paragraphs, headings, or toggles on the page, or pick a different page.)"
                    )
                self.send_cors()
                self.wfile.write(json.dumps({
                    "title": title,
                    "text": text,
                    "charCount": len(text),
                    "pageId": page_id,
                }).encode())
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                msg = err_body
                try:
                    err_json = json.loads(err_body)
                    if err_json.get("object") == "error":
                        msg = err_json.get("message") or err_body
                except Exception:
                    pass
                self.send_cors(e.code)
                self.wfile.write(json.dumps({"error": {"message": msg, "status": e.code}}).encode())
            except Exception as e:
                self.send_cors(500)
                self.wfile.write(json.dumps({"error": {"message": str(e)}}).encode())

        else:
            self.send_cors(404)
            self.wfile.write(json.dumps({"error":"unknown route"}).encode())


if __name__ == "__main__":
    os.chdir(DIR)
    print(f"\n  ✅  TubeRank server running!")
    print(f"  👉  Open in your browser: http://localhost:{PORT}\n")
    print(f"  Env: YouTube={'✓' if YOUTUBE_API_KEY else '✗'}  Channel ID={'✓' if YOUTUBE_CHANNEL_ID else '✗'}  Claude={'✓' if ANTHROPIC_API_KEY else '✗'}  Login={'✓' if TUBERANK_PASSWORD else '✗'}  Notion={'✓' if NOTION_TOKEN else '✗'}  Notion page={'✓' if NOTION_PAGE_ID else '—'}\n")
    if not YOUTUBE_API_KEY or not ANTHROPIC_API_KEY or not YOUTUBE_CHANNEL_ID or not TUBERANK_PASSWORD:
        print(f"  ⚠  Copy .env.example → .env and set missing keys.\n")
    print(f"  (Press Ctrl+C to stop)\n")
    httpd = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        sys.exit(0)
