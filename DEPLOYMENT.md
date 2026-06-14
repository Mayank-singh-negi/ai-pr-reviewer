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
