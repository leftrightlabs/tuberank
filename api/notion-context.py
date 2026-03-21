from http.server import BaseHTTPRequestHandler
import json, os, re, urllib.request, urllib.error, urllib.parse


def _normalize_page_id(page_id):
    if not page_id:
        return ""
    s = page_id.strip()
    m = re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        s, re.I,
    )
    if m:
        return m.group(1).lower()
    hex32 = re.sub(r"[^0-9a-f]", "", s, flags=re.I)
    if len(hex32) == 32:
        return f"{hex32[0:8]}-{hex32[8:12]}-{hex32[12:16]}-{hex32[16:20]}-{hex32[20:32]}"
    return s


def _http_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _text_from_rich(rich):
    return "".join([(x.get("plain_text") or "") for x in (rich or [])])


def _block_to_line(block):
    btype = block.get("type", "")
    data = block.get(btype, {}) if isinstance(block.get(btype, {}), dict) else {}
    txt = _text_from_rich(data.get("rich_text", []))
    if not txt and btype == "child_page":
        txt = block.get("child_page", {}).get("title", "")
    if not txt:
        return ""
    if btype == "callout":
        icon = (data.get("icon") or {}).get("emoji", "")
        return f"{icon} {txt}" if icon else txt
    if btype == "toggle":
        return f"▸ {txt}"
    if btype in ("heading_1", "heading_2", "heading_3"):
        return f"\n{txt}\n"
    if btype == "bulleted_list_item":
        return f"- {txt}"
    if btype == "numbered_list_item":
        return f"1. {txt}"
    if btype == "to_do":
        return f"[{'x' if data.get('checked') else ' '}] {txt}"
    if btype == "quote":
        return f"> {txt}"
    if btype == "code":
        return f"`{txt}`"
    return txt


def _collect_lines(block_id, headers, depth=0, max_depth=4):
    if depth > max_depth:
        return []
    lines = []
    cursor = None
    while True:
        q = {"page_size": 100}
        if cursor:
            q["start_cursor"] = cursor
        url = f"https://api.notion.com/v1/blocks/{block_id}/children?" + urllib.parse.urlencode(q)
        data = _http_json(url, headers=headers, timeout=25)
        for block in data.get("results", []):
            line = _block_to_line(block)
            if line:
                lines.append(line)
            if block.get("has_children"):
                lines.extend(_collect_lines(block["id"], headers, depth + 1, max_depth))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return lines


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        notion_key = os.environ.get("NOTION_TOKEN", "").strip()
        page_id = os.environ.get("NOTION_PAGE_ID", "").strip()

        if not notion_key:
            self._json(503, {"error": {"message": "Server missing NOTION_TOKEN"}})
            return
        if not page_id:
            self._json(400, {"error": {"message": "Missing Notion page: set NOTION_PAGE_ID"}})
            return

        page_id = _normalize_page_id(page_id)
        headers = {
            "Authorization": f"Bearer {notion_key}",
            "Notion-Version": "2022-06-28",
        }

        try:
            page = _http_json(f"https://api.notion.com/v1/pages/{page_id}", headers=headers)
            title = "Notion Context"
            for _, val in page.get("properties", {}).items():
                if val.get("type") == "title":
                    t = _text_from_rich(val.get("title", []))
                    if t:
                        title = t
                        break

            lines = _collect_lines(page_id, headers=headers)
            text = "\n".join([ln for ln in lines if ln]).strip()
            if not text:
                text = (
                    f'(No extractable text blocks on this page yet. Title: "{title}". '
                    "Add paragraphs, headings, or toggles on the page, or pick a different page.)"
                )
            self._json(200, {"title": title, "text": text, "charCount": len(text), "pageId": page_id})

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            msg = err_body
            try:
                err_json = json.loads(err_body)
                if err_json.get("object") == "error":
                    msg = err_json.get("message") or err_body
            except Exception:
                pass
            self._json(e.code, {"error": {"message": msg, "status": e.code}})
        except Exception as e:
            self._json(500, {"error": {"message": str(e)}})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt, *args):
        pass
