# Project Plan: Selective Tweet Deletion with AI Analysis

## Overview

Modify the tweet deletion script to selectively delete tweets that mention Bali, Indonesia, or any work-related activities, using OpenAI's GPT-4 Vision API to analyze both text and images.

## Objectives

1. Fetch tweets from @dannypostmaa timeline
2. Analyze each tweet (text + images) using OpenAI
3. If video, delete the tweet always
4. Delete tweets that match deletion criteria
5. Keep safe tweets untouched
6. Track all decisions for review

## Deletion Criteria

Delete tweets that contain:
- Mentions of "Bali" or "Indonesia"
- Work-related activities: working, shipping, building, crafting, presenting, posting, coding, developing, launching
- Images showing work (laptop, office, coding, meetings, presentations)
- Location indicators suggesting work in Bali/Indonesia
- Any combination of location + work activity

## Architecture Changes

### 1. Core Components

```
app.py (main script)
├── TweetFetcher: Get tweets with text + images
├── ContentAnalyzer: OpenAI GPT-4V analysis
├── DeletionDecider: Apply deletion rules
├── StateManager: Track all decisions
└── TweetDeleter: Execute deletions
```

### 2. New Dependencies

```
openai>=1.0.0
Pillow>=10.0.0
requests>=2.31.0
```

### 3. Data Structures

**Decision Log** (`deletion_decisions.json`):
```json
{
  "decisions": [
    {
      "tweet_id": "123456",
      "text": "Working on a new project...",
      "created_at": "2024-01-15T10:30:00",
      "decision": "DELETE",
      "reason": "Work activity mentioned",
      "ai_analysis": "Tweet mentions 'working' which indicates work activity",
      "has_images": true,
      "deleted": true,
      "deleted_at": "2025-01-07T14:30:00"
    },
    {
      "tweet_id": "123457",
      "text": "Beautiful sunset today",
      "created_at": "2024-01-16T18:00:00",
      "decision": "KEEP",
      "reason": "No work or location indicators",
      "ai_analysis": "Personal observation, no work context",
      "has_images": false,
      "deleted": false
    }
  ],
  "stats": {
    "total_analyzed": 100,
    "marked_for_deletion": 35,
    "actually_deleted": 35,
    "kept": 65,
    "last_run": "2025-01-07T14:30:00"
  }
}
```

**State File** (`deletion_state.json`):
```json
{
  "total_deleted": 35,
  "total_kept": 65,
  "last_run": "2025-01-07T14:30:00",
  "last_analyzed_tweet_id": "123500",
  "oldest_tweet_date": "2024-01-01T00:00:00"
}
```

## Implementation Plan

### Phase 1: OpenAI Integration (2-3 hours)

**Files to create/modify:**
- `app.py` - Add OpenAI client setup
- `requirements.txt` - Add new dependencies

**Tasks:**
1. ✅ Load `OPENAI_API_KEY` from .env
2. ✅ Create `ContentAnalyzer` class
3. ✅ Implement GPT-4V prompt for analysis
4. ✅ Handle text-only tweets
5. ✅ Handle tweets with images
6. ✅ Parse AI response into DELETE/KEEP decision

**OpenAI Prompt Design:**
```
You are analyzing a tweet to determine if it should be deleted.

DELETE if the tweet:
- Mentions Bali or Indonesia (any cities, regions, or locations)
- Shows or mentions work activities: working, building, shipping, coding,
  developing, launching, crafting, presenting, posting updates
- Contains images of: laptops, workspaces, coding, meetings, presentations
- Combines location (Bali/Indonesia) with ANY activity

KEEP if the tweet:
- Is purely personal (food, travel, social activities)
- Mentions other locations
- Contains no work indicators

Tweet: {text}
Images: {image_count}

Respond in JSON:
{
  "decision": "DELETE" or "KEEP",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "detected_keywords": ["keyword1", "keyword2"]
}
```

### Phase 2: Tweet Fetching with Media (1-2 hours)

**Tasks:**
1. ✅ Modify `user_timeline()` to include media entities
2. ✅ Download tweet images to temporary storage
3. ✅ Encode images for OpenAI Vision API
4. ✅ Handle multiple images per tweet
5. ✅ Clean up temp files after analysis

**Considerations:**
- Twitter API returns media URLs
- Need to download images for OpenAI analysis
- Handle rate limits on image downloads
- Max 4 images per tweet for OpenAI

### Phase 3: Decision Engine (2 hours)

**Files to modify:**
- `app.py` - Add decision logic

**Tasks:**
1. ✅ Create `DeletionDecider` class
2. ✅ Combine AI analysis with rule-based checks
3. ✅ Implement confidence threshold (0.7+)
4. ✅ Log all decisions with reasoning
5. ✅ Handle edge cases (retweets, replies, quotes)

**Decision Logic:**
```python
if ai_confidence >= 0.7 and ai_decision == "DELETE":
    return DELETE
elif ai_confidence < 0.5:
    # Manual review needed - be conservative
    return KEEP
else:
    # Medium confidence - apply strict keyword check
    if strict_keyword_match(text):
        return DELETE
    return KEEP
```

### Phase 4: State Management (1 hour)

**Tasks:**
1. ✅ Load/save `deletion_decisions.json`
2. ✅ Track analyzed tweets (don't re-analyze)
3. ✅ Update statistics
4. ✅ Add manual review flags
5. ✅ Create CSV export for review

### Phase 5: Execution & Safety (1 hour)

**Tasks:**
1. ✅ Add dry-run mode (analyze without deleting)
2. ✅ Add manual review before batch deletion
3. ✅ Implement batch deletion with progress tracking
4. ✅ Add rollback protection (can't undelete)
5. ✅ Add extensive logging

**Safety Features:**
```python
# Dry run first
python app.py --dry-run

# Review decisions
cat deletion_decisions.json | jq '.decisions[] | select(.decision=="DELETE")'

# Execute deletions (manual confirm)
python app.py --execute

# Export for review
python app.py --export-csv
```

### Phase 6: Testing & Validation (2 hours)

**Test Cases:**
1. ✅ Text-only tweet mentioning "Bali" → DELETE
2. ✅ Tweet with "working on project" → DELETE
3. ✅ Tweet "shipping new feature from Bali" → DELETE
4. ✅ Tweet "enjoying sunset" with beach photo → KEEP
5. ✅ Tweet mentioning "work" but in different context → Review carefully
6. ✅ Tweet with laptop in Bali coffee shop → DELETE
7. ✅ Retweet of someone else's work → KEEP (not your work)

## Cost Estimation

**OpenAI API Costs (GPT-4 Vision):**
- Text analysis: ~$0.01 per 1K tokens
- Image analysis: ~$0.01 per image
- Estimated: $0.02-0.05 per tweet with images

**For 10,000 tweets:**
- ~5,000 with images
- Cost: ~$250-500 total
- Can reduce by using GPT-4o-mini: ~$50-100

**Optimization:**
- Use GPT-4o-mini for initial pass ($)
- Use GPT-4V only for image-heavy tweets ($$$)
- Cache common patterns

## Timeline

**Total: 9-11 hours**

1. **Day 1 (4 hours)**: OpenAI integration + Tweet fetching
2. **Day 2 (3 hours)**: Decision engine + State management
3. **Day 3 (3 hours)**: Safety features + Testing
4. **Day 4 (1 hour)**: Dry run on real data + adjustments

## Deployment Strategy

### Local Testing
```bash
# Dry run on 50 tweets
python app.py --dry-run --limit 50

# Review decisions
python app.py --review

# Execute if satisfied
python app.py --execute --limit 50
```

### Production on Render.com
```bash
# Run every 30 mins, analyze 10 tweets per run
cron: */30 * * * *
command: python app.py --execute --limit 10
```

**Rate Limits:**
- Twitter: 5 deletions per 15 mins (Basic tier)
- OpenAI: 500 requests per minute (Tier 1)
- Safe: 5 tweets per run = 5 OpenAI calls

## Risk Mitigation

### False Positives (Deleting safe tweets)
- ✅ Dry-run mode mandatory
- ✅ Manual review of first 100 decisions
- ✅ Confidence threshold tuning
- ✅ Export decisions to CSV for review

### False Negatives (Missing problematic tweets)
- ✅ Multi-pass analysis with different prompts
- ✅ Keyword fallback detection
- ✅ Manual review of KEEP decisions with high confidence

### API Failures
- ✅ Retry logic with exponential backoff
- ✅ Save state after each batch
- ✅ Resume from last analyzed tweet
- ✅ Graceful degradation (skip analysis if OpenAI down)

### Cost Overruns
- ✅ Set max budget per run
- ✅ Use GPT-4o-mini by default
- ✅ Batch similar tweets
- ✅ Cache common analyses

## File Structure

```
tweet-deleter/
├── app.py                      # Main script (refactored)
├── requirements.txt            # Updated dependencies
├── .env                        # API keys (OPENAI_API_KEY added)
├── .env.example               # Updated template
├── .gitignore                 # Ignore decision logs
├── README.md                  # Updated usage docs
├── PROJECT_PLAN.md           # This file
├── deletion_state.json        # State tracking
├── deletion_decisions.json    # All analysis results
└── temp_images/              # Temporary image storage (gitignored)
```

## Success Metrics

1. **Accuracy**: >95% correct DELETE/KEEP decisions
2. **Coverage**: Analyze 100% of tweets
3. **Safety**: 0 accidental deletions of safe tweets
4. **Cost**: <$200 for full archive cleanup
5. **Speed**: Process 480 tweets/day (within API limits)

## Next Steps

1. Get approval for plan
2. Implement Phase 1 (OpenAI integration)
3. Run dry-run on 100 sample tweets
4. Review accuracy with user
5. Adjust prompt/thresholds
6. Execute full cleanup
7. Deploy to Render.com for ongoing monitoring

## Questions to Address

1. Should we analyze replies and retweets differently?
2. What date range to analyze? (All time vs. specific dates)
3. Should we keep a local backup of tweets before deletion?
4. Manual review required before each batch or trust AI after validation?
5. What to do with borderline cases (0.5-0.7 confidence)?
