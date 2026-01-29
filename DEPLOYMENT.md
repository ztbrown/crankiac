# Railway Deployment Guide

This guide covers deploying Crankiac to [Railway](https://railway.app).

## Prerequisites

- Railway account (sign up at railway.app)
- Git repository with your code
- Patreon session ID for episode syncing (optional)

## Step 1: Install Railway CLI

```bash
# macOS (Homebrew)
brew install railway

# npm (cross-platform)
npm install -g @railway/cli

# Shell script (Linux/macOS)
curl -fsSL https://railway.app/install.sh | sh
```

Verify installation:

```bash
railway --version
```

## Step 2: Authenticate

```bash
railway login
```

This opens a browser window to authenticate with your Railway account.

## Step 3: Initialize Project

Navigate to your project directory and initialize:

```bash
cd crankiac
railway init
```

Select "Create new project" when prompted, then give it a name (e.g., "crankiac").

## Step 4: Add PostgreSQL

Add a PostgreSQL database to your project:

```bash
railway add
```

Select "PostgreSQL" from the list. Railway provisions a managed Postgres instance with the `pg_trgm` extension available.

Alternatively, add via the Railway dashboard:
1. Open your project at railway.app
2. Click "New" → "Database" → "PostgreSQL"

## Step 5: Configure Environment Variables

Set required environment variables:

```bash
# Database URL is auto-injected by Railway when you link services
# But you can verify it's set:
railway variables

# Set Patreon session ID (required for episode syncing)
railway variables set PATREON_SESSION_ID=your_session_id_here

# Optional: YouTube API key for video duration fetching
railway variables set YOUTUBE_API_KEY=your_api_key_here

# Optional: Server configuration (Railway sets PORT automatically)
railway variables set HOST=0.0.0.0
railway variables set DEBUG=false
```

### Required Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Auto-set by Railway |
| `PATREON_SESSION_ID` | Patreon authentication cookie | Yes (for syncing) |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `YOUTUBE_API_KEY` | YouTube Data API key | - |
| `HOST` | Server bind address | `0.0.0.0` |
| `DEBUG` | Enable debug mode | `false` |

**Note:** Railway automatically sets `PORT` - do not override it.

## Step 6: Deploy

Deploy your application:

```bash
railway up
```

This builds and deploys your application. First deploy may take a few minutes.

To get your deployment URL:

```bash
railway domain
```

Or add a custom domain via the Railway dashboard.

## Step 7: Run Migrations

After first deploy, run database migrations:

```bash
railway run python manage.py migrate
```

## Post-Deployment

### Verify Deployment

Check the health endpoint:

```bash
curl https://your-app.railway.app/api/health
# Should return: {"status": "ok"}
```

### View Logs

```bash
railway logs
```

Or view in the Railway dashboard under "Deployments" → select deployment → "Logs".

### Sync Episodes

Run episode sync manually:

```bash
railway run python manage.py process --limit 10
```

---

## Rollback

### Via CLI

List recent deployments:

```bash
railway deployments
```

Rollback to a previous deployment:

```bash
railway rollback <deployment-id>
```

### Via Dashboard

1. Go to your project on railway.app
2. Click "Deployments" tab
3. Find the previous working deployment
4. Click the three dots menu → "Rollback"

### Database Rollback

Railway doesn't have built-in database rollback. For database issues:

1. **Point-in-time recovery** - Contact Railway support for database restore
2. **Manual rollback** - If you have migration down scripts, run them:
   ```bash
   railway run python manage.py migrate --down
   ```

---

## Debugging

### Common Issues

#### Application won't start

Check logs for errors:

```bash
railway logs --tail 100
```

Common causes:
- Missing environment variables
- Database connection issues
- Port binding (ensure `HOST=0.0.0.0`)

#### Database connection errors

Verify DATABASE_URL is set:

```bash
railway variables | grep DATABASE_URL
```

Test connection:

```bash
railway run python -c "from app.db.connection import get_connection; print(get_connection())"
```

#### Migrations fail

Check migration status:

```bash
railway run python manage.py migrate --status
```

Run with verbose output:

```bash
railway run python manage.py migrate --verbose
```

#### High memory usage

The Whisper transcription model uses significant memory. Consider:
- Using a smaller model: `railway variables set WHISPER_MODEL=tiny`
- Running transcription jobs locally instead of on Railway

### Useful Commands

```bash
# Open Railway dashboard for project
railway open

# Open a shell in the container
railway shell

# Check service status
railway status

# View all variables
railway variables

# Stream logs in real-time
railway logs -f
```

### Health Monitoring

Set up health checks in Railway dashboard:
1. Go to Service Settings
2. Under "Health Check", set path to `/api/health`
3. Railway will restart unhealthy instances automatically

---

## Cost Optimization

Railway charges based on resource usage. To minimize costs:

1. **Use sleep mode** - Enable in Settings to pause when idle
2. **Right-size resources** - Start with defaults, scale as needed
3. **Monitor usage** - Check the Usage tab regularly
4. **Clean up old deployments** - Railway keeps deployment history

---

## Additional Resources

- [Railway Documentation](https://docs.railway.app)
- [Railway CLI Reference](https://docs.railway.app/reference/cli-api)
- [Railway Discord](https://discord.gg/railway) - Community support
