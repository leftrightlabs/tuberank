from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except Exception:
            self._json(400, {"error": {"message": "bad json"}})
            return

        yt_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
        endpoint = payload.get("endpoint", "")

        if not yt_key:
            self._json(503, {"error": {"message": "Server missing YOUTUBE_API_KEY"}})
            return
        if not endpoint:
            self._json(400, {"error": {"message": "missing endpoint"}})
            return

        is_api_key = yt_key.startswith("AIza")
        url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
        if is_api_key:
            sep = "&" if "?" in endpoint else "?"
            url = f"{url}{sep}key={yt_key}"

        headers = {}
        if not is_api_key:
            headers["Authorization"] = f"Bearer {yt_key}"

        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=15)
            data = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(err_body.encode())
        except Exception as e:
            self._json(500, {"error": str(e)})

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
