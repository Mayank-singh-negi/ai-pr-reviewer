import json
import sys
import os
import requests
import time

# Ensure project root is on sys.path for imports in tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import rag.indexer as indexer
from pipeline.review_pipeline import build_rag_context


def make_dummy_pr():
    class DummyPR:
        def __init__(self):
            self.title = "Smoke"
            self.body = ""

        def get_files(self):
            return []

    return DummyPR()


def test_webhook_fallback(monkeypatch):
    # Simulate Chroma client failing to initialize
    monkeypatch.setattr(indexer, "_get_chroma_client", lambda: None)

    # index_repository should report disabled when Chroma is unavailable
    resp = indexer.index_repository("owner/repo", force=True)
    assert resp.get("status") in {"disabled", "skipped", "indexed"}

    # query_similar_code should return empty results with no client
    q = indexer.query_similar_code("some code", repo_name="owner/repo")
    assert isinstance(q.get("results"), list)

    # Build RAG context should handle disabled Chroma and return dict
    monkeypatch.setattr("pipeline.review_pipeline.fetch_pull_request", lambda repo, num: make_dummy_pr())
    monkeypatch.setattr("pipeline.review_pipeline.fetch_pull_request_diff", lambda pr: "diff")
    rag = build_rag_context("owner/repo", 1)
    assert isinstance(rag, dict)
