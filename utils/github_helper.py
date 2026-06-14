import os
import hmac
import hashlib
from typing import Any
from github import Github
from github.PullRequest import PullRequest
import requests


def get_github_client() -> Github:
    """Create and return a PyGithub client using the GITHUB_TOKEN environment variable."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise EnvironmentError("GITHUB_TOKEN is not set in the environment.")
    return Github(github_token)


def fetch_pull_request(repo_full_name: str, pr_number: int) -> PullRequest:
    """Fetch the pull request object from GitHub using PyGithub."""
    client = get_github_client()
    repo = client.get_repo(repo_full_name)
    return repo.get_pull(pr_number)


def fetch_pull_request_diff(pr: PullRequest) -> str:
    """Fetch the full PR diff text from GitHub using the PR object and diff URL."""
    diff_url = pr.diff_url
    if not diff_url:
        raise ValueError("Could not determine diff URL for the pull request.")

    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff",
    }
    response = requests.get(diff_url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def is_valid_signature(secret: str, body: bytes, signature_header: str) -> bool:
    """Validate the GitHub webhook signature using HMAC SHA256."""
    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header.split("=", 1)[1]
    mac = hmac.new(secret.encode(), msg=body, digestmod=hashlib.sha256)
    computed_signature = mac.hexdigest()
    return hmac.compare_digest(computed_signature, expected_signature)
