import re
from typing import Any, Dict, List

from github.GithubException import GithubException

from rag.indexer import index_repository, query_similar_code
from utils.github_helper import fetch_pull_request, fetch_pull_request_diff


def extract_changed_files_from_pr(pr) -> List[Dict[str, str]]:
    """Extract changed files and patch text from a GitHub pull request."""
    changed_files = []
    for changed_file in pr.get_files():
        changed_files.append(
            {
                "filename": changed_file.filename,
                "patch": changed_file.patch or "",
            }
        )
    return changed_files


def build_rag_context(repo_name: str, pr_number: int, n_results: int = 5) -> Dict[str, Any]:
    """Query ChromaDB for similar code examples for changed PR files."""
    index_response = index_repository(repo_name)
    if index_response.get("status") not in {"indexed", "skipped"}:
        return {
            "repo_name": repo_name,
            "error": index_response.get("error", "Failed to index repository."),
        }

    pr = fetch_pull_request(repo_name, pr_number)
    changed_files = extract_changed_files_from_pr(pr)
    rag_results: Dict[str, Any] = {"repo_name": repo_name, "files": []}

    for changed_file in changed_files:
        snippet = changed_file["patch"].strip()
        if not snippet:
            snippet = f"Changes in {changed_file['filename']}"

        query_response = query_similar_code(snippet, n_results=n_results, repo_name=repo_name)
        file_context = {
            "filename": changed_file["filename"],
            "patch": changed_file["patch"],
            "similar_code": query_response.get("results", []),
        }
        rag_results["files"].append(file_context)

    return rag_results


def summarize_rag_context(rag_context: Dict[str, Any]) -> str:
    """Create a short summary of retrieved RAG context for inclusion in prompts."""
    summary_lines = [f"RAG context for repo {rag_context.get('repo_name')}:"
                    ]
    for file_entry in rag_context.get("files", []):
        source = file_entry["filename"]
        similar = file_entry.get("similar_code", [])
        if not similar:
            summary_lines.append(f"- {source}: no similar patterns found.")
            continue

        summary_lines.append(f"- {source}: {len(similar)} similar code chunks found.")
        for match in similar[:2]:
            metadata = match.get("metadata", {})
            summary_lines.append(
                f"  * {metadata.get('file_path')} lines {metadata.get('start_line')}-{metadata.get('end_line')}"
            )
    return "\n".join(summary_lines)


def build_review_prompt(
    repo_name: str,
    pr_number: int,
    pr_title: str,
    pr_body: str,
    full_diff: str,
    rag_summary: str,
) -> str:
    """Assemble the review prompt to send to Claude with RAG context included."""
    return (
        "You are an expert code reviewer.\n"
        f"Repository: {repo_name}\n"
        f"PR Number: {pr_number}\n"
        f"Title: {pr_title}\n"
        f"Body: {pr_body}\n"
        "\nReview the changed code and provide findings for correctness, security, and conventions.\n"
        "Use the retrieved RAG context when relevant.\n\n"
        "RAG Context:\n"
        f"{rag_summary}\n\n"
        "Diff:\n"
        f"{full_diff}\n"
    )


def call_claude_review(prompt: str) -> str:
    """Placeholder for the Claude call used in the review node.

    Replace this function with the actual Anthropic/Claude integration in Phase 5.
    """
    # TODO: Replace this stub with an actual call to Claude API
    return (
        "[Claude review placeholder]\n" "The review prompt was built successfully, and RAG context was included."
    )


def run_review_pipeline(repo_name: str, pr_number: int) -> Dict[str, Any]:
    """Execute the review pipeline with RAG context for a pull request."""
    pr = fetch_pull_request(repo_name, pr_number)
    full_diff = fetch_pull_request_diff(pr)

    rag_context = build_rag_context(repo_name, pr_number)
    rag_summary = summarize_rag_context(rag_context)

    prompt = build_review_prompt(
        repo_name=repo_name,
        pr_number=pr_number,
        pr_title=pr.title,
        pr_body=pr.body or "",
        full_diff=full_diff,
        rag_summary=rag_summary,
    )

    review_text = call_claude_review(prompt)

    return {
        "repo_name": repo_name,
        "pr_number": pr_number,
        "prompt": prompt,
        "review_text": review_text,
        "rag_context": rag_context,
    }


def get_changed_filenames_from_diff(diff: str) -> List[str]:
    """Parse a diff string and return a list of changed filenames."""
    filenames = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            filenames.append(line.replace("+++ b/", ""))
    return filenames
