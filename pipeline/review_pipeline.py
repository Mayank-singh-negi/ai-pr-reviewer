import re
import os
import logging
import openai
from typing import Any, Dict, List

from github.GithubException import GithubException

from rag.indexer import index_repository, query_similar_code
from utils.github_helper import fetch_pull_request, fetch_pull_request_diff
from memory.feedback_memory import should_skip_suggestion

# Configure logging for the pipeline module.
logger = logging.getLogger(__name__)

# Initialize OpenAI API key (optional). If not set, the placeholder is used.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
    logger.info("OpenAI API key loaded for review pipeline")
else:
    logger.info("OPENAI_API_KEY not set — pipeline will use placeholder reviews")


def extract_changed_files_from_pr(pr) -> List[Dict[str, str]]:
    """Extract changed files and patch text from a GitHub pull request."""
    logger.debug(f"Extracting changed files from PR")
    changed_files = []
    for changed_file in pr.get_files():
        changed_files.append(
            {
                "filename": changed_file.filename,
                "patch": changed_file.patch or "",
            }
        )
    logger.info(f"Extracted {len(changed_files)} changed files")
    return changed_files


def build_rag_context(repo_name: str, pr_number: int, n_results: int = 5) -> Dict[str, Any]:
    """Query ChromaDB for similar code examples for changed PR files."""
    logger.info(f"Building RAG context for {repo_name}#{pr_number}")
    
    index_response = index_repository(repo_name)
    if index_response.get("status") not in {"indexed", "skipped"}:
        logger.error(f"Failed to index repository: {index_response.get('error')}")
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
        logger.debug(f"RAG query for {changed_file['filename']}: {len(query_response.get('results', []))} results")

    logger.info(f"RAG context built with {len(rag_results['files'])} files")
    return rag_results


def summarize_rag_context(rag_context: Dict[str, Any]) -> str:
    """Create a short summary of retrieved RAG context for inclusion in prompts."""
    summary_lines = [f"RAG context for repo {rag_context.get('repo_name')}:"]
    
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
    logger.debug(f"Building review prompt for {repo_name}#{pr_number}")
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


def filter_suggestions_by_memory(suggestions: List[Dict[str, Any]], repo_name: str, file_path: str) -> List[Dict[str, Any]]:
    """Filter out suggestions that have been frequently dismissed in the past.
    
    Checks memory before posting a suggestion — skips if pattern is often ignored.
    """
    logger.info(f"Filtering suggestions for {file_path} using memory")
    filtered = []
    
    for suggestion in suggestions:
        suggestion_type = suggestion.get("type", "general")
        
        # Check if this suggestion pattern should be skipped based on feedback memory.
        if should_skip_suggestion(suggestion_type, file_path):
            logger.info(f"Skipping suggestion (type={suggestion_type}, file={file_path}) — frequently dismissed")
            continue
        
        filtered.append(suggestion)
    
    logger.info(f"Kept {len(filtered)}/{len(suggestions)} suggestions after memory filtering")
    return filtered


def call_claude_review(prompt: str) -> str:
    """Use OpenAI ChatCompletion as the review engine when `OPENAI_API_KEY` is set.

    This keeps the function name (`call_claude_review`) so the rest of the
    pipeline does not need to be changed. If `OPENAI_API_KEY` is missing, a
    readable placeholder string is returned.
    """
    logger.info("Invoking review model for prompt (length=%d)", len(prompt))

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not configured — returning placeholder review")
        return (
            "[OpenAI placeholder review]\n"
            "OpenAI API key not configured. Set OPENAI_API_KEY to enable real reviews."
        )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert code reviewer."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.0,
        )
        review_text = response.choices[0].message.content
        logger.info("OpenAI review received (tokens=%s)", getattr(response, 'usage', {}))
        return review_text
    except Exception as exc:
        logger.error(f"OpenAI review call failed: {exc}")
        return (
            "[OpenAI review error]\n"
            f"OpenAI call failed: {exc}\n"
            "Falling back to placeholder summary."
        )


def run_review_pipeline(repo_name: str, pr_number: int) -> Dict[str, Any]:
    """Execute the review pipeline with RAG context for a pull request."""
    logger.info(f"Starting review pipeline for {repo_name}#{pr_number}")
    
    pr = fetch_pull_request(repo_name, pr_number)
    full_diff = fetch_pull_request_diff(pr)
    logger.debug(f"PR diff fetched: {len(full_diff)} characters")

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
    logger.info(f"Review completed for {repo_name}#{pr_number}")

    return {
        "repo_name": repo_name,
        "pr_number": pr_number,
        "prompt": prompt,
        "review_text": review_text,
        "rag_context": rag_context,
    }


def get_changed_filenames_from_diff(diff: str) -> List[str]:
    """Parse a diff string and return a list of changed filenames."""
    logger.debug("Parsing filenames from diff")
    filenames = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            filenames.append(line.replace("+++ b/", ""))
    logger.debug(f"Found {len(filenames)} changed files in diff")
    return filenames
