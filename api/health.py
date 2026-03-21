from http.server import BaseHTTPRequestHandler
import json, os


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = {
            "youtube":          bool(os.environ.get("YOUTUBE_API_KEY", "").strip()),
            "claude":           bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
            "notionToken":      bool(os.environ.get("NOTION_TOKEN", "").strip()),
            "notionPageFromEnv":bool(os.environ.get("NOTION_PAGE_ID", "").strip()),
            "youtubeChannel":   bool(os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()),
            "passwordGate":     bool(os.environ.get("TUBERANK_PASSWORD", "").strip()),
        }
        self._json(200, data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt, *args):
        pass
