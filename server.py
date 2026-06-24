import http.server
import json
import urllib.request
import urllib.parse
import urllib.error
import os

SLACK_WEBHOOK       = os.environ.get("SLACK_WEBHOOK", "")
SLACK_BOT_TOKEN     = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CLIENT_ID     = os.environ.get("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET", "")
SLACK_REDIRECT_URI  = os.environ.get("SLACK_REDIRECT_URI", "https://prepayment-tracker.onrender.com/auth/callback")
SUPABASE_URL        = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY        = os.environ.get("SUPABASE_KEY", "")
PORT                = int(os.environ.get("PORT", 3500))
STATIC_DIR          = os.path.dirname(os.path.abspath(__file__))

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
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/orders":
            try:
                orders = supabase_get_orders()
                self._respond(200, orders)
            except Exception as e:
                self._respond(500, {"error": str(e)})

        elif parsed.path == "/auth/slack":
            # Redirect user to Slack OAuth
            params = urllib.parse.urlencode({
                "client_id":    SLACK_CLIENT_ID,
                "user_scope":   "identity.basic",
                "redirect_uri": SLACK_REDIRECT_URI,
            })
            self.send_response(302)
            self.send_header("Location", f"https://slack.com/oauth/v2/authorize?{params}")
            self.end_headers()

        elif parsed.path == "/auth/callback":
            qs = urllib.parse.parse_qs(parsed.query)
            code = qs.get("code", [None])[0]
            error = qs.get("error", [None])[0]

            if error or not code:
                self._redirect_with_error("Slack sign-in was cancelled.")
                return

            try:
                # Exchange code for token
                token_body = urllib.parse.urlencode({
                    "client_id":     SLACK_CLIENT_ID,
                    "client_secret": SLACK_CLIENT_SECRET,
                    "code":          code,
                    "redirect_uri":  SLACK_REDIRECT_URI,
                }).encode()
                req = urllib.request.Request(
                    "https://slack.com/api/oauth.v2.access",
                    data=token_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as res:
                    token_data = json.loads(res.read())

                if not token_data.get("ok"):
                    self._redirect_with_error("Slack OAuth failed: " + token_data.get("error", "unknown"))
                    return

                user_token = token_data.get("authed_user", {}).get("access_token")
                if not user_token:
                    self._redirect_with_error("Could not get user token from Slack.")
                    return

                # Get user identity
                req2 = urllib.request.Request(
                    "https://slack.com/api/users.identity",
                    headers={"Authorization": f"Bearer {user_token}"},
                    method="GET"
                )
                with urllib.request.urlopen(req2, timeout=10) as res2:
                    identity = json.loads(res2.read())

                if not identity.get("ok"):
                    self._redirect_with_error("Could not fetch Slack identity.")
                    return

                slack_id   = identity["user"]["id"]
                slack_name = identity["user"]["name"]
                display_name = identity["user"].get("name", slack_name)

                # Redirect back to app with identity in query params
                redirect_params = urllib.parse.urlencode({
                    "slackId":   slack_id,
                    "slackName": display_name,
                })
                self.send_response(302)
                self.send_header("Location", f"/?{redirect_params}")
                self.end_headers()

            except Exception as e:
                self._redirect_with_error(str(e))

        else:
            super().do_GET()

    def _redirect_with_error(self, msg):
        params = urllib.parse.urlencode({"authError": msg})
        self.send_response(302)
        self.send_header("Location", f"/?{params}")
        self.end_headers()

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
                payload  = json.loads(body)
                order_id = payload["id"]
                url      = f"{SUPABASE_URL}/rest/v1/orders?id=eq.{order_id}"
                headers  = {**supabase_headers(), "Prefer": "return=minimal"}
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
                user_id = payload.get("channel")

                # Open a DM channel with the user first
                open_body = json.dumps({"users": user_id}).encode()
                open_req = urllib.request.Request(
                    "https://slack.com/api/conversations.open",
                    data=open_body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                    },
                    method="POST"
                )
                with urllib.request.urlopen(open_req, timeout=5) as open_res:
                    open_result = json.loads(open_res.read())

                if not open_result.get("ok"):
                    self._respond(502, {"ok": False, "error": "conversations.open failed: " + open_result.get("error", "unknown")})
                    return

                dm_channel = open_result["channel"]["id"]

                dm_body = json.dumps({
                    "channel": dm_channel,
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[server] {self.address_string()} - {fmt % args}")

if __name__ == "__main__":
    print(f"Prepayment Tracker running at http://localhost:{PORT}")
    with http.server.HTTPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()
