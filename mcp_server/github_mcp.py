"""MCP server exposing GitHub operations to Claude via stdio transport."""

import os
from typing import Any, Dict, List

import anyio
import requests
from dotenv import load_dotenv
from github import Github
from github.GithubException import GithubException
from mcp.server import FastMCP

# Load environment variables from a .env file if present.
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN is required to run the GitHub MCP server.")


def create_github_client() -> Github:
    """Create a PyGithub client from the configured GitHub token."""
    return Github(GITHUB_TOKEN)


def fetch_repository(repo_name: str):
    """Load a GitHub repository object by its full name."""
    client = create_github_client()
    return client.get_repo(repo_name)


def fetch_pull_request(repo_name: str, pr_number: int):
    """Fetch a pull request object from the repository."""
    repo = fetch_repository(repo_name)
    return repo.get_pull(pr_number)


def make_error(message: str) -> Dict[str, Any]:
    """Standardize error responses for MCP tools."""
    return {"error": message}


def get_pr_diff(repo_name: str, pr_number: int) -> Dict[str, Any]:
    """Fetch the full diff text for a pull request.

    Args:
        repo_name: Full repository name, e.g. "owner/repo".
        pr_number: Pull request number.

    Returns:
        A dictionary containing the PR diff or an error message.
    """
    try:
        pr = fetch_pull_request(repo_name, pr_number)
        diff_url = pr.diff_url
        if not diff_url:
            return make_error("Pull request diff URL is unavailable.")

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3.diff",
        }
        response = requests.get(diff_url, headers=headers, timeout=30)
        response.raise_for_status()

        return {
            "repo_name": repo_name,
            "pr_number": pr_number,
            "diff": response.text,
        }
    except GithubException as exc:
        return make_error(f"GitHub API error while fetching PR diff: {exc}")
    except requests.RequestException as exc:
        return make_error(f"HTTP error while fetching PR diff: {exc}")
    except Exception as exc:
        return make_error(f"Unexpected error while fetching PR diff: {exc}")


def get_pr_files(repo_name: str, pr_number: int) -> Dict[str, Any]:
    """List all changed files in a pull request."""
    try:
        pr = fetch_pull_request(repo_name, pr_number)
        files = [file.filename for file in pr.get_files()]
        return {
            "repo_name": repo_name,
            "pr_number": pr_number,
            "files": files,
        }
    except GithubException as exc:
        return make_error(f"GitHub API error while listing PR files: {exc}")
    except Exception as exc:
        return make_error(f"Unexpected error while listing PR files: {exc}")


def get_file_content(repo_name: str, file_path: str, ref: str) -> Dict[str, Any]:
    """Retrieve the content of a specific file at a Git ref."""
    try:
        repo = fetch_repository(repo_name)
        content_file = repo.get_contents(file_path, ref=ref)
        decoded_content = content_file.decoded_content
        if isinstance(decoded_content, bytes):
            decoded_content = decoded_content.decode("utf-8", errors="replace")

        return {
            "repo_name": repo_name,
            "file_path": file_path,
            "ref": ref,
            "content": decoded_content,
        }
    except GithubException as exc:
        return make_error(f"GitHub API error while fetching file content: {exc}")
    except Exception as exc:
        return make_error(f"Unexpected error while fetching file content: {exc}")


def post_review_comment(
    repo_name: str,
    pr_number: int,
    commit_id: str,
    path: str,
    line: int,
    body: str,
) -> Dict[str, Any]:
    """Post a line-level review comment on a pull request.

    Note: GitHub expects the comment position in the diff rather than the absolute
    source line number. Provide the diff position for reliable placement.
    """
    try:
        pr = fetch_pull_request(repo_name, pr_number)
        comment = pr.create_review_comment(body, commit_id, path, line)
        return {
            "repo_name": repo_name,
            "pr_number": pr_number,
            "comment_url": comment.html_url,
            "comment_id": getattr(comment, "id", None),
        }
    except GithubException as exc:
        return make_error(f"GitHub API error while posting review comment: {exc}")
    except Exception as exc:
        return make_error(f"Unexpected error while posting review comment: {exc}")


def post_pr_summary(repo_name: str, pr_number: int, body: str) -> Dict[str, Any]:
    """Post a general summary comment on the pull request."""
    try:
        pr = fetch_pull_request(repo_name, pr_number)
        comment = pr.create_issue_comment(body)
        return {
            "repo_name": repo_name,
            "pr_number": pr_number,
            "comment_url": comment.html_url,
            "comment_id": getattr(comment, "id", None),
        }
    except GithubException as exc:
        return make_error(f"GitHub API error while posting PR summary: {exc}")
    except Exception as exc:
        return make_error(f"Unexpected error while posting PR summary: {exc}")


def get_repo_structure(repo_name: str) -> Dict[str, Any]:
    """Return the top-level repository structure: files and folders in the root."""
    try:
        repo = fetch_repository(repo_name)
        contents = repo.get_contents("")
        structure = [
            {"path": item.path, "type": item.type, "name": item.name}
            for item in contents
        ]
        return {
            "repo_name": repo_name,
            "structure": structure,
        }
    except GithubException as exc:
        return make_error(f"GitHub API error while fetching repository structure: {exc}")
    except Exception as exc:
        return make_error(f"Unexpected error while fetching repository structure: {exc}")


def build_server() -> FastMCP:
    """Register GitHub tools and return the configured MCP server."""
    server = FastMCP(
        name="github_mcp",
        instructions="GitHub helper MCP server exposing repository and pull request tools.",
    )

    server.add_tool(
        get_pr_diff,
        description="Fetch the full diff text for a GitHub pull request.",
        structured_output=True,
    )
    server.add_tool(
        get_pr_files,
        description="List all files changed in a GitHub pull request.",
        structured_output=True,
    )
    server.add_tool(
        get_file_content,
        description="Get the content of a file from a repository at a specific ref.",
        structured_output=True,
    )
    server.add_tool(
        post_review_comment,
        description="Post a line-level review comment on a GitHub pull request.",
        structured_output=True,
    )
    server.add_tool(
        post_pr_summary,
        description="Post a general summary comment on a GitHub pull request.",
        structured_output=True,
    )
    server.add_tool(
        get_repo_structure,
        description="Get the top-level file and folder structure of a GitHub repository.",
        structured_output=True,
    )

    return server


async def main() -> None:
    """Start the MCP server using stdio transport."""
    server = build_server()
    await server.run_stdio_async()


if __name__ == "__main__":
    anyio.run(main)
