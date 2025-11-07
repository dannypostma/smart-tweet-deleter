# Tweet Deleter for @dannypostmaa

A Python script that automatically deletes tweets from your Twitter account, designed to work within free tier API limits.

## Features

- Deletes 5 tweets per run to stay within rate limits
- Tracks progress with state file (resumes where it left off)
- Built-in rate limiting and error handling
- Safe for scheduled execution via cron jobs
- Works with Twitter API Basic tier (5 deletes per 15 mins)

## Setup

### 1. Get Twitter API Credentials

1. Go to [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Create a new app or use an existing one
3. Navigate to "Keys and tokens"
4. Generate/copy these credentials:
   - API Key
   - API Secret
   - Access Token
   - Access Token Secret

Make sure your app has **Read and Write** permissions.

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and add your Twitter API credentials:

```
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here
ACCESS_TOKEN=your_access_token_here
ACCESS_TOKEN_SECRET=your_access_token_secret_here
```

### 4. Run the Script

```bash
python app.py
```

The script will:
- Delete up to 5 tweets per run
- Save progress to `deletion_state.json`
- Display detailed output of what was deleted

## Running on Render.com as a Cron Job

Render.com offers free tier cron jobs that are perfect for this use case.

### Setup on Render

1. **Push your code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin YOUR_GITHUB_REPO_URL
   git push -u origin main
   ```

2. **Create a new Cron Job on Render**
   - Go to [Render Dashboard](https://dashboard.render.com/)
   - Click "New +" and select "Cron Job"
   - Connect your GitHub repository
   - Configure:
     - **Name**: tweet-deleter
     - **Environment**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Command**: `python app.py`
     - **Schedule**: `*/15 * * * *` (every 15 minutes)

3. **Add Environment Variables**
   In the Render dashboard, add these environment variables:
   - `API_KEY`
   - `API_SECRET`
   - `ACCESS_TOKEN`
   - `ACCESS_TOKEN_SECRET`

### Recommended Schedules

Twitter API Basic tier allows **5 deletions per 15 minutes**.

With 5 tweets per run:
- **Every 15 minutes**: 480 tweets/day (maximum throughput)
- **Every 30 minutes**: 240 tweets/day
- **Every hour**: 120 tweets/day
- **Every 6 hours**: 20 tweets/day

Recommended: **Every 15 minutes** (`*/15 * * * *`) for fastest deletion, or adjust based on your needs.

## Configuration

Edit these values in `app.py`:

```python
MAX_DELETES_PER_RUN = 5  # Number of tweets to delete per run (Basic tier: 5 per 15 mins)
DELAY_BETWEEN_DELETES = 2  # Seconds between each delete
```

## Progress Tracking

The script saves progress in `deletion_state.json`:

```json
{
  "total_deleted": 150,
  "last_run": "2025-01-07T10:30:00",
  "last_tweet_id": 1234567890
}
```

This allows the script to resume where it left off, even across multiple runs or server restarts.

## Important Notes

- **Basic Tier Limits**: Twitter API Basic tier allows 5 deletions per 15 minutes (480/day max)
- **Be Patient**: With 5 tweets per run every 15 mins, you can delete ~14,400 tweets per month
- **State Persistence**: On Render, use a persistent disk or external storage for `deletion_state.json` to survive deployments
- **Rate Limits**: The script includes automatic rate limit handling via tweepy

## Troubleshooting

**Error: "403 Forbidden"**
- Check that your app has Read and Write permissions
- Regenerate your Access Token after changing permissions

**Error: "401 Unauthorized"**
- Verify all credentials in `.env` are correct
- Make sure there are no extra spaces in the values

**Script finishes but tweets still visible**
- Twitter cache can take a few minutes to update
- Check your profile in a private/incognito window

## License

Personal use script for @dannypostmaa



Twitter API v2 Endpoints:

  1. GET /2/users/me (app.py:308)

  - Purpose: Get authenticated user's information
  - Used for: Getting your user ID and username
  - Called: Once at startup
  - Rate limit: 75 requests per 15 minutes

  2. GET /2/users/:id/tweets (app.py:334-340)

  - Purpose: Fetch user's tweets
  - Used for: Getting your recent tweets to analyze
  - Parameters:
    - max_results: 5-100 tweets per request
    - tweet_fields: created_at, text, attachments, referenced_tweets, in_reply_to_user_id
    - expansions: attachments.media_keys
    - media_fields: type, url, preview_image_url
  - Called: Every time the script runs
  - Rate limit: 1,500 requests per 15 minutes (Free tier: 10,000 tweets/month)

  Twitter API v1.1 Endpoint:

  3. POST /1.1/statuses/destroy/:id (app.py:382)

  - Purpose: Delete a tweet
  - Used for: Actually deleting tweets (only when --execute flag is used)
  - Called: For each tweet marked for deletion
  - Rate limit: No documented rate limit, but you have a 2-second delay between deletes
  - Note: V2 doesn't have a delete endpoint yet, so v1.1 is required