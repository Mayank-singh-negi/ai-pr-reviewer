# Deployment Guide — ai-pr-reviewer on Railway

## Overview
This guide explains how to deploy the ai-pr-reviewer to Railway.

## Prerequisites
- A GitHub repository with the ai-pr-reviewer code
- A Railway account (https://railway.app)
- Google Gemini API key
- GitHub personal access token

## Step 1: Deploy to Railway

### Option A: Using Railway CLI
```bash
npm i -g @railway/cli
railway login
railway init
railway up
```

### Option B: Using Railway Dashboard
1. Go to https://railway.app/dashboard
2. Click "New Project" → "Deploy from GitHub"
3. Select the ai-pr-reviewer repository
4. Railway automatically detects the `Procfile` and `railway.json`
5. Wait for deployment to complete

## Step 2: Set Environment Variables on Railway

In the Railway dashboard, go to your project → Variables and add:

```
GEMINI_API_KEY=your_gemini_api_key
GITHUB_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
```

Click "Save" and Railway will restart the service.

## Step 3: Register GitHub Webhook

1. Go to your repository → Settings → Webhooks
2. Click "Add webhook"
3. **Payload URL**: `https://<your-railway-domain>/webhook`
   - Your Railway domain is shown in the deployment URL
   - Example: `https://ai-pr-reviewer-production.railway.app/webhook`
4. **Content type**: Select "application/json"
5. **Secret**: Use the same value as `GITHUB_WEBHOOK_SECRET`
6. **Events**: Select "Pull requests"
7. Click "Add webhook"

## Step 4: Test the Deployment

### Health Check
```bash
curl https://<your-railway-domain>/health
```

### Expected Response
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 123.45
}
```

### Create a Test PR
- Push a new branch to your repository
- Open a pull request
- The webhook will trigger the review pipeline
- Check the PR comments for Gemini's review

## Monitoring

### View Logs
In Railway dashboard → Deployments → View logs

### Check Stats
```bash
curl https://<your-railway-domain>/stats
```

### Health Endpoint
The `/health` endpoint is available at:
```
https://<your-railway-domain>/health
```

## Troubleshooting

### Webhook Not Triggering
1. Verify `GITHUB_WEBHOOK_SECRET` matches on GitHub and Railway
2. Check Railway logs for errors
3. Manually test webhook by creating a PR
4. Verify the webhook delivery in GitHub → Settings → Webhooks → Recent Deliveries

### Gemini API Errors
1. Verify `GEMINI_API_KEY` is valid
2. Check Google Gemini model availability and rate limits
3. Review logs for token count and error messages

### Permission Errors
1. Verify `GITHUB_TOKEN` has `repo` and `write:repo_hook` scopes
2. Generate a new token if needed

## Directory Structure on Railway

Railway automatically creates these directories:
- `./chroma_db/` — ChromaDB vector database (persisted across restarts)
- `./memory/` — Feedback memory and stats JSON files

## Scaling Tips

1. **Database Persistence**: Railway provides persistent storage at `/tmp` — make sure `chroma_db/` is there
2. **Memory Optimization**: The RAG indexer caches embeddings in ChromaDB
3. **Rate Limiting**: The service is configured with 1 review per PR to avoid duplicate triggers
4. **Token Usage**: Monitor Gemini token usage via `/stats` endpoint

## Rollback

To rollback to a previous deployment:
1. Go to Railway dashboard → Deployments
2. Click on an earlier deployment
3. Click "Redeploy"

## Support

For issues:
- Check Railway docs: https://docs.railway.app
- Check Google Gemini docs: https://developers.generativeai.google
- Review GitHub webhook docs: https://docs.github.com/webhooks


## ChromaDB compatibility and recovery

If you see runtime errors mentioning "migrate your data to the new Chroma architecture" or failures creating a Chroma client,
there are two safe options depending on whether your stored vector data is critical:

- Quick recreate (data non-critical):
  - Set the environment variable `CHROMA_ALLOW_RECREATE=true` in Railway or your `.env` file. The service will attempt
    to remove and recreate the local `chroma_db/` persistence directory when the Chroma client fails to initialize.
  - This ensures the service becomes available immediately but will discard existing vector data.

- Preserve and migrate (data critical):
  - Install the Chroma migration tool locally on an admin machine:

```bash
pip install chroma-migrate
```

  - Follow the migration tool instructions printed by the Chroma error logs, or run the migration command suggested by the tool.
  - After migration, redeploy the service.

Notes:
- By default the service will not auto-delete your Chroma persistence. `CHROMA_ALLOW_RECREATE` is opt-in.
- For production scaling, consider using an external managed vector DB instead of local filesystem persistence.

### Railway environment setup (CLI)

You can set environment variables on Railway using the CLI:

```bash
railway login
railway variables set GITHUB_TOKEN=ghp_xxx --project <project_id>
railway variables set GITHUB_WEBHOOK_SECRET=your_secret --project <project_id>
railway variables set GEMINI_API_KEY=your_key --project <project_id>
railway variables set CHROMA_ALLOW_RECREATE=true --project <project_id>
railway variables set SENTRY_DSN=your_sentry_dsn --project <project_id>
```

Replace `<project_id>` with your Railway project identifier (or omit `--project` to set for the current project).

### Backing up local Chroma data

Before running migrations or recreation, create a backup copy of `chroma_db/`:

```bash
python scripts/backup_chroma.py
```

The script creates a timestamped `.zip` file under `backups/`.

## Local smoke test

After deploying or running locally, verify the service with the included smoke test:

1. Copy `.env.example` to `.env` and fill in `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, and `GEMINI_API_KEY`.
2. Start the app:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

3. Run the smoke test (from repository root):

```bash
python -m tests.smoke_test
```

The smoke test will check `/health`, `/stats`, and post a synthetic, signed `/webhook` event.

