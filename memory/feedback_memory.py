import json
import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# Configure logging for the memory module.
logger = logging.getLogger(__name__)

FEEDBACK_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "memory", "feedback_store.json"
)


def _ensure_feedback_store() -> None:
    """Ensure feedback store directory and file exist."""
    os.makedirs(os.path.dirname(FEEDBACK_STORE_PATH), exist_ok=True)
    if not os.path.exists(FEEDBACK_STORE_PATH):
        logger.info(f"Creating feedback store at {FEEDBACK_STORE_PATH}")
        with open(FEEDBACK_STORE_PATH, "w") as f:
            json.dump({"ignored_patterns": {}}, f, indent=2)


def _load_feedback_store() -> Dict[str, Any]:
    """Load the feedback store from JSON file."""
    _ensure_feedback_store()
    logger.debug(f"Loading feedback store from {FEEDBACK_STORE_PATH}")
    with open(FEEDBACK_STORE_PATH, "r") as f:
        return json.load(f)


def _save_feedback_store(data: Dict[str, Any]) -> None:
    """Save the feedback store to JSON file."""
    _ensure_feedback_store()
    logger.debug(f"Saving feedback store to {FEEDBACK_STORE_PATH}")
    with open(FEEDBACK_STORE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def save_feedback(suggestion_type: str, file_pattern: str, dismissed: bool) -> Dict[str, Any]:
    """Record feedback about a suggestion (dismissed or acted upon).

    Args:
        suggestion_type: Category of suggestion, e.g., 'security', 'performance', 'style'.
        file_pattern: File path or pattern where suggestion was made.
        dismissed: True if the suggestion was dismissed/ignored.

    Returns:
        Updated feedback record.
    """
    logger.info(f"Saving feedback: type={suggestion_type}, file={file_pattern}, dismissed={dismissed}")
    
    store = _load_feedback_store()
    key = f"{suggestion_type}::{file_pattern}"

    if key not in store["ignored_patterns"]:
        logger.debug(f"Creating new feedback record for {key}")
        store["ignored_patterns"][key] = {
            "suggestion_type": suggestion_type,
            "file_pattern": file_pattern,
            "dismissed_count": 0,
            "total_count": 0,
            "last_seen": None,
        }

    record = store["ignored_patterns"][key]
    record["total_count"] += 1
    if dismissed:
        record["dismissed_count"] += 1
    record["last_seen"] = datetime.utcnow().isoformat()

    _save_feedback_store(store)
    logger.debug(f"Feedback record updated: {record}")
    return record


def get_ignored_patterns(min_dismissal_rate: float = 0.7) -> List[Dict[str, Any]]:
    """Return list of commonly dismissed suggestion patterns.

    Args:
        min_dismissal_rate: Return patterns dismissed >= this fraction.

    Returns:
        List of ignored pattern records.
    """
    logger.info(f"Fetching ignored patterns (min_dismissal_rate={min_dismissal_rate})")
    
    store = _load_feedback_store()
    ignored = []

    for key, record in store["ignored_patterns"].items():
        if record["total_count"] == 0:
            continue
        dismissal_rate = record["dismissed_count"] / record["total_count"]
        if dismissal_rate >= min_dismissal_rate:
            ignored.append(record)

    logger.info(f"Found {len(ignored)} ignored patterns")
    return ignored


def should_skip_suggestion(suggestion_type: str, file_pattern: str) -> bool:
    """Check if a suggestion type and file pattern should be skipped.

    Args:
        suggestion_type: Category of suggestion.
        file_pattern: File path or pattern.

    Returns:
        True if this suggestion pattern is frequently dismissed.
    """
    logger.debug(f"Checking if suggestion should be skipped: type={suggestion_type}, file={file_pattern}")
    
    store = _load_feedback_store()
    key = f"{suggestion_type}::{file_pattern}"

    if key not in store["ignored_patterns"]:
        logger.debug(f"No record found for {key}")
        return False

    record = store["ignored_patterns"][key]
    if record["total_count"] < 3:
        logger.debug(f"Not enough attempts for {key} (total={record['total_count']})")
        return False

    dismissal_rate = record["dismissed_count"] / record["total_count"]
    should_skip = dismissal_rate >= 0.7
    logger.info(f"Should skip {key}: {should_skip} (dismissal_rate={dismissal_rate:.2%})")
    return should_skip


def clear_memory() -> Dict[str, str]:
    """Clear all feedback memory."""
    logger.warning("Clearing all feedback memory")
    _ensure_feedback_store()
    _save_feedback_store({"ignored_patterns": {}})
    return {"status": "cleared", "message": "All feedback memory has been cleared."}


def get_memory_stats() -> Dict[str, Any]:
    """Get statistics about the feedback memory."""
    logger.info("Retrieving memory statistics")
    
    store = _load_feedback_store()
    patterns = store["ignored_patterns"]

    total_records = len(patterns)
    total_dismissals = sum(r.get("dismissed_count", 0) for r in patterns.values())
    total_suggestions = sum(r.get("total_count", 0) for r in patterns.values())

    stats = {
        "total_patterns_tracked": total_records,
        "total_suggestions_made": total_suggestions,
        "total_dismissals": total_dismissals,
        "dismissal_rate": total_dismissals / total_suggestions if total_suggestions > 0 else 0,
    }
    logger.debug(f"Memory stats: {stats}")
    return stats
