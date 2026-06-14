# AI PR Reviewer

An autonomous GitHub Pull Request reviewer powered by Claude API, MCP, and LangGraph. Automatically reviews every PR for bugs, security vulnerabilities, and performance issues — then posts structured comments directly on GitHub.

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
| Claude API | Primary reasoning model for code analysis |
| MCP (Model Context Protocol) | Custom server connecting Claude to GitHub |
| LangGraph | Stateful workflow managing the review pipeline |
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
LangGraph Pipeline
      ↓
MCP Server → GitHub API (fetch diff)
      ↓
ChromaDB RAG (codebase context)
      ↓
Claude API (analyze + generate review)
      ↓
MCP Server → GitHub API (post comments)
```

## Getting Started

### Prerequisites

- Python 3.12+
- GitHub account
- Claude API key ([get one here](https://console.anthropic.com))

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

3. Set up environment variables
```bash
cp .env.example .env
```

Fill in your `.env`:
```
ANTHROPIC_API_KEY=your_claude_api_key
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
├── pipeline/            # LangGraph review workflow
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
- [x] LangGraph pipeline
- [x] RAG over codebase
- [ ] Slack notifications
- [ ] Support for multiple repos

## License

MIT
