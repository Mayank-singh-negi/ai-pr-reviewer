import os
import hmac
import hashlib
import json
import time
import requests
from github import Github

from dotenv import load_dotenv


def sign_payload(secret: str, payload_bytes: bytes) -> str:
    digest = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def main():
    load_dotenv(dotenv_path=".env")
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        print("GITHUB_WEBHOOK_SECRET not set in .env; aborting smoke test")
        return

    base = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000")
    print(f"Using base URL: {base}")

    # Health
    r = requests.get(f"{base}/health")
    print("GET /health ->", r.status_code, r.text)

    # Stats
    r = requests.get(f"{base}/stats")
    print("GET /stats ->", r.status_code)

    # Determine a repo to use for the smoke webhook. Prefer `SMOKE_REPO` from env.
    smoke_repo = os.getenv("SMOKE_REPO")
    github_token = os.getenv("GITHUB_TOKEN")

    if not github_token or not smoke_repo:
        print("Skipping POST /webhook: set GITHUB_TOKEN and SMOKE_REPO in .env for full webhook test")
        return

    # Verify token can access the repo
    gh = Github(github_token)
    try:
        repo = gh.get_repo(smoke_repo)
    except Exception as exc:
        print(f"GITHUB_TOKEN cannot access repo '{smoke_repo}': {exc}\nSkipping webhook POST")
        return

    # Prepare a minimal pull_request opened webhook payload referencing a non-destructive PR number
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 1,
            "title": "Smoke test PR",
            "body": "This is a smoke test",
            "diff_url": "",
        },
        "repository": {"full_name": smoke_repo},
    }

    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = sign_payload(secret, payload_bytes)

    headers = {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": "pull_request",
        "Content-Type": "application/json",
    }

    print("POST /webhook (signed) ...")
    r = requests.post(f"{base}/webhook", data=payload_bytes, headers=headers)
    print("POST /webhook ->", r.status_code)
    try:
        print(r.text)
    except Exception:
        pass


if __name__ == "__main__":
    main()
