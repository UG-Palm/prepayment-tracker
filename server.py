import http.server
import json
import urllib.request
import urllib.error
import os

SLACK_WEBHOOK  = os.environ.get("SLACK_WEBHOOK", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SUPABASE_URL   = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY", "")
PORT           = int(os.environ.get("PORT", 3500))
STATIC_DIR     = os.path.dirname(os.path.abspath(__file__))

def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

def supabase_get_orders():
    url = f"{SUPABASE_URL}/rest/v1/orders?select=id,data,created_at&order=created_at.desc"
    req = urllib.request.Request(url, headers=supabase_headers())
    with urllib.request.urlopen(req, timeout=10) as res:
        rows = json.loads(res.read())
    return [row["data"] for row in rows]

def supabase_save_order(order):
    url  = f"{SUPABASE_URL}/rest/v1/orders"
    body = json.dumps({"id": order["id"], "data": order}).encode()
    headers = {**supabase_headers(), "Prefer": "resolution=merge-duplicates"}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    urllib.request.urlopen(req, timeout=10)

def supabase_update_order(order):
    url  = f"{SUPABASE_URL}/rest/v1/orders?id=eq.{order['id']}"
    body = json.dumps({"data": order}).encode()
    headers = {**supabase_headers(), "Prefer": "return=minimal"}
    req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    urllib.request.urlopen(req, timeout=10)

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/orders":
            try:
                orders = supabase_get_orders()
                self._respond(200, orders)
            except Exception as e:
                self._respond(500, {"error": str(e)})
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        if self.path == "/api/orders":
            try:
                order = json.loads(body)
                supabase_save_order(order)
                self._respond(200, {"ok": True})
            except Exception as e:
                self._respond(500, {"ok": False, "error": str(e)})

        elif self.path == "/api/orders/update":
            try:
                order = json.loads(body)
                supabase_update_order(order)
                self._respond(200, {"ok": True})
            except Exception as e:
                self._respond(500, {"ok": False, "error": str(e)})

        elif self.path == "/api/orders/delete":
            try:
                payload = json.loads(body)
                order_id = payload["id"]
                url = f"{SUPABASE_URL}/rest/v1/orders?id=eq.{order_id}"
                headers = {**supabase_headers(), "Prefer": "return=minimal"}
                req = urllib.request.Request(url, headers=headers, method="DELETE")
                urllib.request.urlopen(req, timeout=10)
                self._respond(200, {"ok": True})
            except Exception as e:
                self._respond(500, {"ok": False, "error": str(e)})

        elif self.path == "/notify":
            try:
                req = urllib.request.Request(
                    SLACK_WEBHOOK, data=body,
                    headers={"Content-Type": "application/json"}, method="POST"
                )
                urllib.request.urlopen(req, timeout=5)
                self._respond(200, {"ok": True})
            except Exception as e:
                self._respond(502, {"ok": False, "error": str(e)})

        elif self.path == "/notify-dm":
            if not SLACK_BOT_TOKEN:
                self._respond(503, {"ok": False, "error": "SLACK_BOT_TOKEN not configured"})
                return
            try:
                payload = json.loads(body)
                dm_body = json.dumps({
                    "channel": payload.get("channel"),
                    "text":    payload.get("text", ""),
                    "blocks":  payload.get("blocks", []),
                }).encode()
                req = urllib.request.Request(
                    "https://slack.com/api/chat.postMessage",
                    data=dm_body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as res:
                    result = json.loads(res.read())
                self._respond(200, result)
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[server] {self.address_string()} - {fmt % args}")

if __name__ == "__main__":
    print(f"Prepayment Tracker running at http://localhost:{PORT}")
    with http.server.HTTPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()
