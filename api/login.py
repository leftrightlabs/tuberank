from http.server import BaseHTTPRequestHandler
import json, os


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except Exception:
            self._json(400, {"error": {"message": "bad json"}})
            return

        password = os.environ.get("TUBERANK_PASSWORD", "").strip()
        channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()

        if not password:
            self._json(503, {"error": {"message": "Server missing TUBERANK_PASSWORD"}})
            return
        if not channel_id:
            self._json(503, {"error": {"message": "Server missing YOUTUBE_CHANNEL_ID"}})
            return
        if payload.get("password", "") != password:
            self._json(401, {"error": {"message": "Invalid password"}})
            return

        self._json(200, {"ok": True, "channelId": channel_id})

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
