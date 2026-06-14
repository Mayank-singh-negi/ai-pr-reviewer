import os
import hmac
import hashlib
import logging
from typing import Any
from github import Github
from github.PullRequest import PullRequest
import requests

# Configure logging for the helper module.
logger = logging.getLogger(__name__)


def get_github_client() -> Github:
    """Create and return a PyGithub client using the GITHUB_TOKEN environment variable."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN is not set in the environment")
        raise EnvironmentError("GITHUB_TOKEN is not set in the environment.")
    logger.debug("GitHub client created")
    return Github(github_token)


def fetch_pull_request(repo_full_name: str, pr_number: int) -> PullRequest:
    """Fetch the pull request object from GitHub using PyGithub."""
    logger.info(f"Fetching PR {repo_full_name}#{pr_number}")
    try:
        client = get_github_client()
        repo = client.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        logger.info(f"PR fetched successfully: {pr.title}")
        return pr
    except Exception as exc:
        logger.error(f"Failed to fetch PR {repo_full_name}#{pr_number}: {exc}")
        raise


def fetch_pull_request_diff(pr: PullRequest) -> str:
    """Fetch the full PR diff text from GitHub using the PR object and diff URL."""
    logger.info(f"Fetching diff for PR {pr.number}")
    
    diff_url = pr.diff_url
    if not diff_url:
        logger.error(f"Could not determine diff URL for PR {pr.number}")
        raise ValueError("Could not determine diff URL for the pull request.")

    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff",
    }
    
    try:
        response = requests.get(diff_url, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info(f"Diff fetched successfully: {len(response.text)} characters")
        return response.text
    except Exception as exc:
        logger.error(f"Failed to fetch diff from {diff_url}: {exc}")
        raise


def is_valid_signature(secret: str, body: bytes, signature_header: str) -> bool:
    """Validate the GitHub webhook signature using HMAC SHA256."""
    logger.debug("Validating webhook signature")
    
    if not signature_header.startswith("sha256="):
        logger.warning("Invalid signature header format")
        return False

    expected_signature = signature_header.split("=", 1)[1]
    mac = hmac.new(secret.encode(), msg=body, digestmod=hashlib.sha256)
    computed_signature = mac.hexdigest()
    
    is_valid = hmac.compare_digest(computed_signature, expected_signature)
    if is_valid:
        logger.debug("Webhook signature validated successfully")
    else:
        logger.warning("Webhook signature validation failed")
    
    return is_valid
