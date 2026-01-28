import json
import datetime

from configurations.config_loader import creds
from agents.tweet_feed import fetch_recent_tweets


def call(acct: str):
    print(f"\n=== {datetime.datetime.utcnow().isoformat()}Z | Testing @{acct} ===")
    try:
        res = fetch_recent_tweets(acct, creds["twitter"]["x_bearer_token"])
        if isinstance(res, dict):
            print("status:", "error" if res.get("error") else "unknown")
            print("response:", json.dumps(res, ensure_ascii=False))
        elif isinstance(res, list):
            print("status:", "success")
            print("count:", len(res))
            print("sample:", json.dumps(res[:2], ensure_ascii=False))
        else:
            print("status:", "unknown_type")
            print("response:", str(res))
    except Exception as e:
        print("status:", "exception")
        print("response:", str(e))


if __name__ == "__main__":
    # Primary and fallback accounts
    call("HRSD_SA")
    call("SaudiGOSI")
