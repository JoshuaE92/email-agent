"""Run ONCE on your own computer to get a Gmail refresh token.

    python scripts/get_refresh_token.py

It reads your OAuth client ID/secret from either:
  * credentials.json in the repo root (downloaded from Google Cloud), or
  * GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET in your .env
then opens your browser so you can log in and approve READ-ONLY access.
It prints the refresh token; paste it into the GMAIL_REFRESH_TOKEN GitHub
Secret. Nothing is written to disk.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

import config


def client_config() -> dict:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "credentials.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    cid, secret = os.environ.get("GMAIL_CLIENT_ID"), os.environ.get("GMAIL_CLIENT_SECRET")
    if not (cid and secret):
        sys.exit("Put credentials.json in the repo root, or set GMAIL_CLIENT_ID and "
                 "GMAIL_CLIENT_SECRET in .env")
    return {"installed": {
        "client_id": cid, "client_secret": secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }}


def main():
    load_dotenv()
    flow = InstalledAppFlow.from_client_config(client_config(), scopes=config.GMAIL_SCOPES)
    # access_type=offline + prompt=consent make Google always return a refresh token.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent",
                                  open_browser=True)
    if not creds.refresh_token:
        sys.exit("No refresh token returned. Remove the app at "
                 "https://myaccount.google.com/permissions and run again.")
    info = flow.client_config
    print("\nSuccess! Add these as GitHub Secrets (and to .env for local runs):\n")
    print(f"GMAIL_CLIENT_ID={info['client_id']}")
    print(f"GMAIL_CLIENT_SECRET={info['client_secret']}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}\n")
    print("Keep these private. Anyone with all three can read your email.")


if __name__ == "__main__":
    main()
