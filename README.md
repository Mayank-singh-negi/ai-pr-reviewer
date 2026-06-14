# AI PR Reviewer

An autonomous GitHub Pull Request reviewer powered by Google Gemini API, MCP, and RAG. Automatically reviews every PR for bugs, security vulnerabilities, and performance issues — then posts structured comments directly on GitHub.

## Features

- Auto-triggers on every new pull request via GitHub webhook
- Reviews code for bugs, security issues, and performance anti-patterns
- Posts line-by-line review comments directly on GitHub PR
- Cross-references changes against existing codebase patterns using RAG
- Generates a summary comment with overall quality score and top 3 concerns
- Learns from dismissed suggestions for future PRs

## Tech Stack

| Tool | Role |
|------|------|
| Google Gemini API | Primary reasoning model for code analysis |
| MCP (Model Context Protocol) | Custom server connecting GitHub to the agent |
| In-house review pipeline | Stateful workflow managing the review pipeline |
| ChromaDB | Vector database for RAG over codebase |
| GitHub API + PyGithub | Read PRs, post comments, manage webhooks |
| FastAPI | Webhook listener and API service layer |
| Railway | Cloud deployment |

## Architecture

```
GitHub PR Opened
      ↓
Webhook → FastAPI Listener
      ↓
Review pipeline
      ↓
MCP Server → GitHub API (fetch diff)
      ↓
ChromaDB RAG (codebase context)
      ↓
Google Gemini API (analyze + generate review)
      ↓
MCP Server → GitHub API (post comments)
```

## Getting Started

### Prerequisites

- Python 3.12+
- GitHub account
- Google Gemini API key

### Installation

1. Clone the repo
```bash
git clone https://github.com/yourusername/ai-pr-reviewer.git
cd ai-pr-reviewer
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

This project uses `google-genai==2.8.0` for Google Gemini integration.

3. Set up environment variables
```bash
cp .env.example .env
```

Fill in your `.env`:
```
GEMINI_API_KEY=your_gemini_api_key
GITHUB_TOKEN=your_github_token
GITHUB_WEBHOOK_SECRET=your_webhook_secret
```

4. Run the server
```bash
uvicorn main:app --reload
```

5. Expose local server for webhook (dev)
```bash
ngrok http 8000
```

6. Add the ngrok URL as a webhook in your GitHub repo settings

## Project Structure

```
ai-pr-reviewer/
├── main.py              # FastAPI webhook listener
├── mcp_server/          # Custom MCP server for GitHub
├── pipeline/            # Review workflow and AI integration
├── rag/                 # ChromaDB codebase indexing
├── requirements.txt
├── .env.example
└── README.md
```

## Demo

> Add demo video or screenshot here after build

## Roadmap

- [x] Webhook listener
- [x] MCP server
- [x] Review pipeline
- [x] RAG over codebase
- [ ] Slack notifications
- [ ] Support for multiple repos

## License

MIT
Testing Gemini AI Review Integration
