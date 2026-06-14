import os
import json
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from utils.github_helper import (
    fetch_pull_request,
    fetch_pull_request_diff,
    is_valid_signature,
)

# Load environment variables from a .env file if present
load_dotenv()

app = FastAPI(title="ai-pr-reviewer")

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    raise RuntimeError("GITHUB_WEBHOOK_SECRET is required in the environment.")


@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
):
    """Receive GitHub webhook events and process pull request openings."""
    payload_bytes = await request.body()

    if x_hub_signature_256 is None:
        raise HTTPException(status_code=400, detail="Missing X-Hub-Signature-256 header.")

    if not is_valid_signature(WEBHOOK_SECRET, payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    if x_github_event != "pull_request":
        return PlainTextResponse("Event ignored. Only pull_request events are supported.", status_code=200)

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    action = payload.get("action")
    if action != "opened":
        return PlainTextResponse(
            f"Pull request event ignored. Action '{action}' is not 'opened'.",
            status_code=200,
        )

    pull_request_payload = payload.get("pull_request")
    if not pull_request_payload:
        raise HTTPException(status_code=400, detail="Missing pull_request payload.")

    pr_number = pull_request_payload.get("number")
    repository = payload.get("repository", {})
    repo_full_name = repository.get("full_name")

    if not isinstance(pr_number, int) or not repo_full_name:
        raise HTTPException(status_code=400, detail="Missing PR number or repository name.")

    # Extract basic PR information from the webhook payload
    pr_title = pull_request_payload.get("title", "")
    pr_body = pull_request_payload.get("body", "")
    diff_url = pull_request_payload.get("diff_url", "")

    # Fetch the full PR diff from GitHub using PyGithub helper functions
    try:
        pr = fetch_pull_request(repo_full_name, pr_number)
        full_diff = fetch_pull_request_diff(pr)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch PR data: {exc}")

    # Print extracted data cleanly to the console for Phase 1 verification
    print("--- Received Pull Request Webhook ---")
    print(f"Repository: {repo_full_name}")
    print(f"PR Number: {pr_number}")
    print(f"Title: {pr_title}")
    print(f"Body: {pr_body}")
    print(f"Webhook diff_url: {diff_url}")
    print("--- Full PR Diff Start ---")
    print(full_diff)
    print("--- Full PR Diff End ---")

    return PlainTextResponse("Pull request opened event received and processed.", status_code=200)
