import urllib.request
import urllib.parse
import json
import time

SLACK_BOT_TOKEN = input("Paste your SLACK_BOT_TOKEN: ").strip()
CHANNEL_ID = "C0BBD9ZQF8T"  # #prepayment-approvals

def slack_get(method, params):
    params["token"] = SLACK_BOT_TOKEN
    url = f"https://slack.com/api/{method}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as res:
        return json.loads(res.read())

def slack_delete(channel, ts):
    body = json.dumps({"channel": channel, "ts": ts}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.delete",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read())

print(f"\nFetching messages from channel {CHANNEL_ID}...")
deleted = 0
skipped = 0
cursor = None

while True:
    params = {"channel": CHANNEL_ID, "limit": 200}
    if cursor:
        params["cursor"] = cursor

    data = slack_get("conversations.history", params)

    if not data.get("ok"):
        print(f"Error fetching messages: {data.get('error')}")
        break

    messages = data.get("messages", [])
    if not messages:
        print("No more messages found.")
        break

    for msg in messages:
        ts = msg.get("ts")
        result = slack_delete(CHANNEL_ID, ts)
        if result.get("ok"):
            deleted += 1
            print(f"  Deleted message {ts}")
        else:
            skipped += 1
            print(f"  Skipped (can't delete): {result.get('error')} — ts={ts}")
        time.sleep(0.5)  # avoid rate limiting

    if data.get("response_metadata", {}).get("next_cursor"):
        cursor = data["response_metadata"]["next_cursor"]
    else:
        break

print(f"\nDone. Deleted: {deleted}  Skipped: {skipped}")
print("Skipped messages were posted by users (not the bot) and must be deleted manually.")
