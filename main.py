import os
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from dotenv import load_dotenv

from pipeline.review_pipeline import run_review_pipeline
from utils.github_helper import (
    fetch_pull_request,
    fetch_pull_request_diff,
    is_valid_signature,
    post_pr_summary,
)
from memory.feedback_memory import (
    save_feedback,
    get_memory_stats,
)

# Load environment variables from a .env file if present.
load_dotenv()

# Validate required deployment environment variables.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN is required in the environment.")

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    raise RuntimeError("GITHUB_WEBHOOK_SECRET is required in the environment.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is required in the environment.")

# Configure logging for the application.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="ai-pr-reviewer", version="1.0.0")

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    raise RuntimeError("GITHUB_WEBHOOK_SECRET is required in the environment.")

# Paths for stats and memory directories.
STATS_FILE = os.path.join(os.path.dirname(__file__), "stats.json")
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory")
CHROMA_DB_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")

# Ensure required directories exist.
os.makedirs(MEMORY_DIR, exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)

# In-memory rate limiting: track PR reviews to avoid duplicates.
REVIEWED_PRS: Dict[str, float] = {}
RATE_LIMIT_WINDOW = 300  # 5 minutes

# Track application uptime.
START_TIME = time.time()


def _ensure_stats_file() -> None:
    """Ensure stats file exists with default values."""
    if not os.path.exists(STATS_FILE):
        default_stats = {
            "total_prs_reviewed": 0,
            "total_comments_posted": 0,
            "total_tokens_used": 0,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat(),
        }
        with open(STATS_FILE, "w") as f:
            json.dump(default_stats, f, indent=2)


def _load_stats() -> Dict[str, Any]:
    """Load stats from JSON file and normalize missing fields."""
    _ensure_stats_file()
    with open(STATS_FILE, "r") as f:
        stats = json.load(f)

    stats.setdefault("total_prs_reviewed", 0)
    stats.setdefault("total_comments_posted", 0)
    stats.setdefault("total_tokens_used", 0)
    stats.setdefault("created_at", datetime.utcnow().isoformat())
    stats.setdefault("last_updated", datetime.utcnow().isoformat())
    return stats


def _save_stats(stats: Dict[str, Any]) -> None:
    """Save stats to JSON file."""
    stats["last_updated"] = datetime.utcnow().isoformat()
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def _is_rate_limited(repo_name: str, pr_number: int) -> bool:
    """Check if a PR has been recently reviewed (rate limiting)."""
    key = f"{repo_name}#{pr_number}"
    current_time = time.time()

    if key in REVIEWED_PRS:
        last_review = REVIEWED_PRS[key]
        if current_time - last_review < RATE_LIMIT_WINDOW:
            logger.warning(f"Rate limit hit for {key}. Already reviewed within {RATE_LIMIT_WINDOW}s.")
            return True

    REVIEWED_PRS[key] = current_time
    return False


def _record_pr_review(tokens_used: int = 0, comments_posted: int = 0) -> None:
    """Increment PR review stats."""
    stats = _load_stats()
    stats["total_prs_reviewed"] += 1
    stats["total_tokens_used"] += tokens_used
    stats["total_comments_posted"] += comments_posted
    _save_stats(stats)
    logger.info(
        "Recorded PR review. Total: %s, Tokens: %s, Comments posted: %s",
        stats["total_prs_reviewed"],
        stats["total_tokens_used"],
        stats["total_comments_posted"],
    )


@app.get("/health", response_class=JSONResponse)
async def health() -> Dict[str, Any]:
    """Health check endpoint for deployment monitoring."""
    uptime = time.time() - START_TIME
    logger.info("Health check requested.")
    return {
        "status": "healthy",
        "version": "1.0.0",
        "uptime_seconds": round(uptime, 2),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/stats", response_class=JSONResponse)
async def stats() -> Dict[str, Any]:
    """Endpoint to view review statistics and memory stats."""
    logger.info("Stats endpoint requested.")
    review_stats = _load_stats()
    memory_stats = get_memory_stats()
    return {
        "review_stats": review_stats,
        "memory_stats": memory_stats,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/feedback", response_class=JSONResponse)
async def feedback(request: Request) -> Dict[str, Any]:
    """Endpoint to record feedback about dismissed suggestions.

    Expected payload:
    {
        "suggestion_type": "security",
        "file_pattern": "utils/helper.py",
        "dismissed": true
    }
    """
    try:
        payload = await request.json()
    except Exception as exc:
        logger.error(f"Invalid JSON in /feedback: {exc}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    suggestion_type = payload.get("suggestion_type", "").strip()
    file_pattern = payload.get("file_pattern", "").strip()
    dismissed = payload.get("dismissed", False)

    if not suggestion_type or not file_pattern:
        logger.warning("Missing suggestion_type or file_pattern in /feedback request.")
        raise HTTPException(
            status_code=400,
            detail="suggestion_type and file_pattern are required.",
        )

    result = save_feedback(suggestion_type, file_pattern, dismissed)
    logger.info(f"Feedback recorded: {suggestion_type} :: {file_pattern} (dismissed={dismissed})")
    return {
        "status": "recorded",
        "record": result,
    }


@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
) -> str:
    """Receive GitHub webhook events and process pull request openings.

    Validates webhook signature, filters for PR opened events, and queues review.
    """
    payload_bytes = await request.body()
    logger.info("Webhook received.")

    if x_hub_signature_256 is None:
        logger.warning("Missing X-Hub-Signature-256 header.")
        raise HTTPException(status_code=400, detail="Missing X-Hub-Signature-256 header.")

    if not is_valid_signature(WEBHOOK_SECRET, payload_bytes, x_hub_signature_256):
        logger.warning("Invalid webhook signature.")
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    if x_github_event != "pull_request":
        logger.debug(f"Event type '{x_github_event}' ignored. Only 'pull_request' events supported.")
        return PlainTextResponse("Event ignored. Only pull_request events are supported.", status_code=200)

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse JSON payload: {exc}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    action = payload.get("action")
    if action != "opened":
        logger.debug(f"PR action '{action}' ignored. Only 'opened' actions are processed.")
        return PlainTextResponse(
            f"Pull request event ignored. Action '{action}' is not 'opened'.",
            status_code=200,
        )

    pull_request_payload = payload.get("pull_request")
    if not pull_request_payload:
        logger.error("Missing pull_request payload in webhook.")
        raise HTTPException(status_code=400, detail="Missing pull_request payload.")

    pr_number = pull_request_payload.get("number")
    repository = payload.get("repository", {})
    repo_full_name = repository.get("full_name")

    if not isinstance(pr_number, int) or not repo_full_name:
        logger.error(f"Invalid PR number or repo name: {pr_number}, {repo_full_name}")
        raise HTTPException(status_code=400, detail="Missing PR number or repository name.")

    # Rate limiting — avoid reviewing the same PR multiple times.
    if _is_rate_limited(repo_full_name, pr_number):
        logger.info(f"Skipping review for {repo_full_name}#{pr_number} (already reviewed recently).")
        return PlainTextResponse(
            "PR review skipped (already reviewed recently).",
            status_code=200,
        )

    # Extract basic PR information from the webhook payload.
    pr_title = pull_request_payload.get("title", "")
    pr_body = pull_request_payload.get("body", "")
    diff_url = pull_request_payload.get("diff_url", "")

    logger.info(f"Processing PR: {repo_full_name}#{pr_number} ({pr_title})")

    # Fetch the full PR diff from GitHub using PyGithub helper functions.
    try:
        pr = fetch_pull_request(repo_full_name, pr_number)
        full_diff = fetch_pull_request_diff(pr)
    except Exception as exc:
        logger.error(f"Failed to fetch PR data for {repo_full_name}#{pr_number}: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch PR data: {exc}")

    # Log extracted data for debugging.
    logger.info(f"PR data extracted: title='{pr_title}', diff_lines={len(full_diff.splitlines())}")
    logger.debug(f"PR body: {pr_body[:200] if pr_body else '(empty)'}")

    # Run the AI review pipeline and post the summary back to GitHub.
    try:
        review_result = run_review_pipeline(repo_full_name, pr_number)
        review_text = review_result.get("review_text", "").strip()
        tokens_used = int(review_result.get("tokens_used", 0) or 0)

        if not review_text:
            logger.warning("Gemini generated an empty review for %s#%s", repo_full_name, pr_number)
            raise RuntimeError("Gemini returned an empty review response.")

        post_result = post_pr_summary(repo_full_name, pr_number, review_text)
        if post_result.get("error"):
            raise RuntimeError(post_result["error"])

        logger.info(
            "Review comment posted for %s#%s: %s",
            repo_full_name,
            pr_number,
            post_result.get("comment_url"),
        )
        _record_pr_review(tokens_used=tokens_used, comments_posted=1)
    except Exception as exc:
        logger.error(
            "Failed to complete AI review for %s#%s: %s",
            repo_full_name,
            pr_number,
            exc,
        )
        raise HTTPException(status_code=500, detail=f"AI review failed: {exc}")

    return PlainTextResponse("Pull request review generated and posted.", status_code=200)


@app.on_event("startup")
async def startup() -> None:
    """Initialize application on startup."""
    logger.info("=" * 60)
    logger.info("ai-pr-reviewer starting up")
    logger.info(f"Webhook secret loaded: {'*' * 10}")
    _ensure_stats_file()
    logger.info(f"Stats file initialized at {STATS_FILE}")
    logger.info(f"Memory directory: {MEMORY_DIR}")
    logger.info(f"ChromaDB directory: {CHROMA_DB_DIR}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown() -> None:
    """Log application shutdown."""
    logger.info("ai-pr-reviewer shutting down.")
