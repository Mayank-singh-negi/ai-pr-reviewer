import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from github import Github
from github.GithubException import GithubException

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Configure logging for the RAG indexer module.
logger = logging.getLogger(__name__)

# The directory where ChromaDB will persist its local database files.
PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")

# Supported code file extensions for repository indexing.
SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
}

# Sentence Transformer model used to create embeddings for code chunks.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


def _get_embedding_model() -> SentenceTransformer:
    """Load the sentence-transformers model used for code embeddings."""
    logger.debug(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def _get_chroma_client() -> chromadb.Client:
    """Create a persistent ChromaDB client for the local index."""
    os.makedirs(PERSIST_DIR, exist_ok=True)
    logger.debug(f"Creating ChromaDB client with persist_dir: {PERSIST_DIR}")
    settings = Settings(
        chroma_db_impl="duckdb+parquet",
        persist_directory=PERSIST_DIR,
    )
    return chromadb.Client(settings=settings)


def _sanitize_collection_name(repo_name: str) -> str:
    """Create a valid ChromaDB collection name from the GitHub repo full name."""
    return repo_name.replace("/", "__")


def _is_supported_file(file_path: str) -> bool:
    """Return True when the file extension is supported for indexing."""
    _, ext = os.path.splitext(file_path.lower())
    return ext in SUPPORTED_EXTENSIONS


def _language_for_path(file_path: str) -> str:
    """Guess a programming language from the file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
    }.get(ext, "text")


def _split_code_into_chunks(code: str, file_path: str) -> List[Dict[str, Any]]:
    """Split a source file into logical chunks by functions and classes."""
    language = _language_for_path(file_path)
    lines = code.splitlines()
    logger.debug(f"Splitting {file_path} ({language}) into chunks: {len(lines)} lines")

    if language == "python":
        pattern = re.compile(r"^(async\s+def|def|class)\s+\w+")
    elif language in {"javascript", "typescript"}:
        pattern = re.compile(
            r"^(export\s+)?(async\s+)?(function\s+\w+|const\s+\w+\s*=\s*(async\s+)?\(?|class\s+\w+|let\s+\w+\s*=\s*(async\s+)?\(?|var\s+\w+\s*=\s*(async\s+)?\(?).*$"
        )
    elif language == "java":
        pattern = re.compile(r"^(public|private|protected|static|class)\s+")
    elif language == "go":
        pattern = re.compile(r"^func\s+")
    else:
        pattern = re.compile(r"^$")

    chunks: List[Dict[str, Any]] = []
    current_lines: List[str] = []
    current_start = 1

    def _flush_chunk(end_line: int) -> None:
        if not current_lines:
            return
        chunks.append(
            {
                "file_path": file_path,
                "language": language,
                "start_line": current_start,
                "end_line": end_line,
                "text": "\n".join(current_lines).strip(),
            }
        )

    for line_number, line in enumerate(lines, start=1):
        if pattern.match(line) and current_lines:
            _flush_chunk(line_number - 1)
            current_lines = [line]
            current_start = line_number
        else:
            current_lines.append(line)

    if current_lines:
        _flush_chunk(len(lines))

    if not chunks:
        return [
            {
                "file_path": file_path,
                "language": language,
                "start_line": 1,
                "end_line": len(lines),
                "text": code.strip(),
            }
        ]

    logger.debug(f"Created {len(chunks)} chunks for {file_path}")
    return chunks


def _fetch_code_files(repo_name: str) -> List[Tuple[str, str]]:
    """Fetch repository files recursively from GitHub using PyGithub."""
    logger.info(f"Fetching code files from repository: {repo_name}")
    
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN is not set")
        raise RuntimeError("GITHUB_TOKEN is required to index a repository.")

    client = Github(github_token)
    repo = client.get_repo(repo_name)
    files: List[Tuple[str, str]] = []
    queue = [""]

    while queue:
        path = queue.pop()
        contents = repo.get_contents(path)
        for item in contents:
            if item.type == "dir":
                queue.append(item.path)
                continue
            if item.type != "file":
                continue
            if not _is_supported_file(item.path):
                continue
            code = item.decoded_content.decode("utf-8", errors="replace")
            files.append((item.path, code))

    logger.info(f"Fetched {len(files)} code files from {repo_name}")
    return files


def index_repository(repo_name: str, force: bool = False) -> Dict[str, Any]:
    """Index repository source files into ChromaDB by logical code chunks."""
    logger.info(f"Indexing repository: {repo_name} (force={force})")
    
    collection_name = _sanitize_collection_name(repo_name)
    client = _get_chroma_client()

    existing_collections = [collection.name for collection in client.list_collections()]
    if collection_name in existing_collections and not force:
        logger.info(f"Repository {repo_name} already indexed, skipping")
        return {
            "repo_name": repo_name,
            "collection_name": collection_name,
            "status": "skipped",
            "message": "Repository already indexed. Use force=True to rebuild.",
        }

    if collection_name in existing_collections and force:
        logger.info(f"Force reindexing: deleting existing collection {collection_name}")
        client.delete_collection(name=collection_name)

    collection = client.create_collection(name=collection_name)
    embedder = _get_embedding_model()

    try:
        files = _fetch_code_files(repo_name)
    except GithubException as exc:
        logger.error(f"GitHub API error while indexing {repo_name}: {exc}")
        return {"error": f"GitHub API error while indexing repository: {exc}"}
    except Exception as exc:
        logger.error(f"Unexpected error while indexing {repo_name}: {exc}")
        return {"error": f"Unexpected error while indexing repository: {exc}"}

    ids = []
    metadatas = []
    documents = []
    embeddings = []

    for file_path, code in files:
        chunks = _split_code_into_chunks(code, file_path)
        for chunk in chunks:
            if not chunk["text"]:
                continue
            doc_id = f"{collection_name}::{file_path}::{chunk['start_line']}"
            ids.append(doc_id)
            metadatas.append(
                {
                    "repo_name": repo_name,
                    "file_path": file_path,
                    "language": chunk["language"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                }
            )
            documents.append(chunk["text"])
            embeddings.append(embedder.encode(chunk["text"], convert_to_numpy=True).tolist())

    if ids:
        collection.add(
            ids=ids,
            metadatas=metadatas,
            documents=documents,
            embeddings=embeddings,
        )
        logger.info(f"Indexed {len(ids)} code chunks for {repo_name}")

    return {
        "repo_name": repo_name,
        "collection_name": collection_name,
        "indexed_chunks": len(ids),
        "status": "indexed",
    }


def query_similar_code(
    code_snippet: str,
    n_results: int = 5,
    repo_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Query the ChromaDB index for similar code patterns.

    Args:
        code_snippet: The code text to search for.
        n_results: Number of similar results to return.
        repo_name: Repository name whose index should be searched.
    """
    logger.info(f"Querying similar code for {repo_name} (n_results={n_results})")
    
    if not code_snippet.strip():
        logger.warning("Empty code snippet provided")
        return {"results": []}

    client = _get_chroma_client()
    if repo_name:
        collection_name = _sanitize_collection_name(repo_name)
    else:
        logger.error("repo_name is required to query the index")
        return {"error": "repo_name is required to query the index."}

    try:
        collection = client.get_collection(name=collection_name)
    except Exception as exc:
        logger.error(f"Collection not found for {repo_name}: {exc}")
        return {"error": f"No index found for repository '{repo_name}'."}

    embedder = _get_embedding_model()
    query_embedding = embedder.encode(code_snippet, convert_to_numpy=True).tolist()

    query_result = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    results: List[Dict[str, Any]] = []
    for i, doc_id in enumerate(query_result.get("ids", [[]])[0]):
        results.append(
            {
                "id": doc_id,
                "document": query_result.get("documents", [[]])[0][i],
                "metadata": query_result.get("metadatas", [[]])[0][i],
                "distance": query_result.get("distances", [[]])[0][i],
            }
        )

    logger.info(f"Query returned {len(results)} similar code results")
    return {"repo_name": repo_name, "results": results}


def clear_index(repo_name: str) -> Dict[str, Any]:
    """Remove an existing ChromaDB index for a repository."""
    logger.info(f"Clearing index for repository: {repo_name}")
    
    collection_name = _sanitize_collection_name(repo_name)
    client = _get_chroma_client()
    existing_collections = [collection.name for collection in client.list_collections()]

    if collection_name not in existing_collections:
        logger.warning(f"No index found to clear for {repo_name}")
        return {
            "repo_name": repo_name,
            "status": "missing",
            "message": "No existing index was found to clear.",
        }

    client.delete_collection(name=collection_name)
    logger.info(f"Cleared index for {repo_name}")
    return {
        "repo_name": repo_name,
        "status": "cleared",
    }
