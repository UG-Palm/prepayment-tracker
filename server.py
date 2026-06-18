import http.server
import json
import urllib.request
import urllib.error
import os

SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK", "")
PORT = int(os.environ.get("PORT", 3500))
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_POST(self):
        if self.path == "/notify":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                req = urllib.request.Request(
                    SLACK_WEBHOOK,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=5)
                self._respond(200, {"ok": True})
            except urllib.error.HTTPError as e:
                self._respond(502, {"ok": False, "error": str(e)})
            except Exception as e:
                self._respond(502, {"ok": False, "error": str(e)})
        else:
            self._respond(404, {"ok": False})

    def _respond(self, code, data):
        payload = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(payload))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[server] {self.address_string()} - {fmt % args}")

if __name__ == "__main__":
    print(f"Prepayment Tracker running at http://localhost:{PORT}")
    with http.server.HTTPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()
