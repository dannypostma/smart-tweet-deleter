import os
import json
import time
import tweepy
import argparse
import requests
import base64
from io import BytesIO
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from pymongo import MongoClient
from utils.storage_manager import CloudflareR2Storage, StorageUploadError

load_dotenv()

# API Credentials
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASEURL")

# Configuration
MAX_TWEETS_PER_RUN = 10  # Basic tier: 5 deletes per 15 mins, analyze more than we delete
DELAY_BETWEEN_DELETES = 2
PRE_2019_CUTOFF = datetime(2019, 1, 1, tzinfo=timezone.utc)
SKIP_RECENT_DAYS = 3  # Skip tweets newer than this many days

# MongoDB Setup
mongo_client = MongoClient(DATABASE_URL)
db = mongo_client.get_default_database()

# Use -dev suffix for collections in development to avoid interfering with live data
NODE_ENV = os.getenv("NODE_ENV", "production")
collection_suffix = "-dev" if NODE_ENV == "development" else ""
state_collection = db[f"state{collection_suffix}"]
decisions_collection = db[f"decisions{collection_suffix}"]

if NODE_ENV == "development":
    print("⚠️  Development mode: Using -dev collections")

# Initialize OpenAI
openai_client = OpenAI(api_key=OPENAI_API_KEY)


class ContentAnalyzer:
    """Analyzes tweet content using OpenAI GPT-4V"""

    def __init__(self):
        self.client = openai_client

    def analyze_tweet(self, tweet_text, image_urls=None):
        """
        Analyze tweet text and images to determine if it should be deleted
        Returns: {decision: DELETE/KEEP, confidence: float, reason: str, keywords: list}
        """

        prompt = f"""You are analyzing a tweet to determine if it should be deleted.

DELETE if the tweet:
- Mentions Bali, Indonesia, or any Indonesian cities/locations (Ubud, Canggu, Jakarta, etc.)
- Shows or mentions work activities: working, building, shipping, coding, developing,
  launching, crafting, presenting, posting updates, creating, designing, programming
- Contains images of: laptops, workspaces, coding screens, meetings, presentations,
  office setups, work equipment
- Combines any location with work activity
- Shows someone working or being productive
- Mentions HeadshotPro, course creation, or online business activities
- Mentions anything about my wealth, income, earnings, or financial status

KEEP if the tweet:
- Is purely personal (food, travel without work context, social activities)
- Mentions other locations (not Indonesia/Bali)
- Contains no work indicators
- Is about hobbies, entertainment, or leisure

Tweet text: "{tweet_text}"
Number of images: {len(image_urls) if image_urls else 0}

Analyze carefully and respond in JSON format:
{{
  "decision": "DELETE" or "KEEP",
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "detected_keywords": ["keyword1", "keyword2"]
}}"""

        try:
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

            # Add images if present
            if image_urls:
                for img_url in image_urls[:4]:  # Max 4 images
                    try:
                        # Download and encode image
                        response = requests.get(img_url, timeout=10)
                        if response.status_code == 200:
                            img = Image.open(BytesIO(response.content))
                            # Resize if too large (max 2000x2000)
                            if img.width > 2000 or img.height > 2000:
                                img.thumbnail((2000, 2000))

                            # Convert to base64
                            buffered = BytesIO()
                            img.save(buffered, format="PNG")
                            img_base64 = base64.b64encode(buffered.getvalue()).decode()

                            messages[0]["content"].append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_base64}"
                                }
                            })
                    except Exception as e:
                        print(f"⚠️  Failed to download image {img_url}: {e}")

            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Cost-effective model
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=500
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            print(f"❌ OpenAI API error: {e}")
            # Fallback to keyword-based detection
            return self._fallback_analysis(tweet_text)

    def _fallback_analysis(self, text):
        """Fallback keyword-based analysis if OpenAI fails"""
        text_lower = text.lower()

        # Check for Bali/Indonesia mentions
        location_keywords = ['bali', 'indonesia', 'ubud', 'canggu', 'jakarta', 'seminyak']
        has_location = any(kw in text_lower for kw in location_keywords)

        # Check for work mentions
        work_keywords = ['work', 'build', 'ship', 'code', 'develop', 'launch',
                         'craft', 'present', 'post', 'create', 'design', 'program']
        has_work = any(kw in text_lower for kw in work_keywords)

        if has_location or has_work:
            return {
                "decision": "DELETE",
                "confidence": 0.8,
                "reason": f"Keyword match: {'location' if has_location else 'work'}",
                "detected_keywords": [kw for kw in (location_keywords + work_keywords) if kw in text_lower]
            }

        return {
            "decision": "KEEP",
            "confidence": 0.6,
            "reason": "No obvious red flags (fallback analysis)",
            "detected_keywords": []
        }


class StateManager:
    """Manages state and decision logging using MongoDB"""

    def __init__(self):
        self.state_collection = state_collection
        self.decisions_collection = decisions_collection
        self.state = self.load_state()

    def load_state(self):
        """Load state from MongoDB"""
        state_doc = self.state_collection.find_one({"_id": "app_state"})
        if state_doc:
            return state_doc
        return {
            "_id": "app_state",
            "total_deleted": 0,
            "total_kept": 0,
            "total_analyzed": 0,
            "last_run": None,
            "last_analyzed_tweet_id": None,
            "pagination_token": None
        }

    def save_state(self):
        """Save state to MongoDB"""
        self.state["last_run"] = datetime.now().isoformat()
        self.state_collection.replace_one(
            {"_id": "app_state"},
            self.state,
            upsert=True
        )

    def update_pagination_token(self, token):
        """Update pagination token in state"""
        self.state["pagination_token"] = token

    def log_decision(self, tweet, decision, reason, ai_analysis, deleted=False, media_uploads=None):
        """Log a decision to MongoDB"""
        decision_doc = {
            "tweet_id": str(tweet.id),
            "text": tweet.full_text[:200],  # Truncate long tweets
            "created_at": tweet.created_at.isoformat(),
            "decision": decision,
            "reason": reason,
            "ai_analysis": ai_analysis,
            "has_images": bool(hasattr(tweet, 'entities') and 'media' in tweet.entities),
            "has_video": self._has_video(tweet),
            "is_reply": bool(tweet.in_reply_to_status_id),
            "is_retweet": hasattr(tweet, 'retweeted_status'),
            "deleted": deleted,
            "deleted_at": datetime.now().isoformat() if deleted else None,
            "analyzed_at": datetime.now().isoformat(),
            "media_uploads": media_uploads or []
        }

        # Insert decision into MongoDB
        self.decisions_collection.insert_one(decision_doc)

        # Update stats in state
        self.state["total_analyzed"] += 1
        if deleted:
            self.state["total_deleted"] += 1
        elif decision == "KEEP":
            self.state["total_kept"] += 1

    def _has_video(self, tweet):
        """Check if tweet has video"""
        if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
            for media in tweet.extended_entities['media']:
                if media['type'] in ['video', 'animated_gif']:
                    return True
        return False

    def was_analyzed(self, tweet_id):
        """Check if tweet was already analyzed in MongoDB"""
        return self.decisions_collection.find_one({"tweet_id": str(tweet_id)}) is not None


class DeletionDecider:
    """Makes deletion decisions based on rules and AI analysis"""

    def __init__(self, analyzer, my_user_id):
        self.analyzer = analyzer
        self.my_user_id = my_user_id

    def should_delete(self, tweet):
        """
        Determine if tweet should be deleted
        Returns: (should_delete: bool, reason: str, ai_analysis: dict)
        """

        # Rule 1: Pre-2019 tweets - auto delete
        if tweet.created_at < PRE_2019_CUTOFF:
            return True, "Pre-2019 tweet (auto-delete)", {"decision": "DELETE", "confidence": 1.0}

        # Rule 2: Videos - auto delete
        if self._has_video(tweet):
            return True, "Contains video (auto-delete)", {"decision": "DELETE", "confidence": 1.0}

        # Rule 3: Replies to others - auto delete (keep only self-replies)
        if tweet.in_reply_to_status_id and tweet.in_reply_to_user_id != self.my_user_id:
            return True, "Reply to another user (auto-delete)", {"decision": "DELETE", "confidence": 1.0}

        # Rule 4: Retweets - auto delete
        if hasattr(tweet, 'retweeted_status'):
            return True, "Retweet (auto-delete)", {"decision": "DELETE", "confidence": 1.0}

        # Rule 5: AI Analysis for original tweets and self-replies
        image_urls = self._extract_image_urls(tweet)
        ai_analysis = self.analyzer.analyze_tweet(tweet.full_text, image_urls)

        # Delete if confidence >= 0.5 and decision is DELETE
        if ai_analysis['decision'] == 'DELETE' and ai_analysis['confidence'] >= 0.5:
            return True, f"AI: {ai_analysis['reason']}", ai_analysis

        return False, f"AI: {ai_analysis['reason']}", ai_analysis

    def _has_video(self, tweet):
        """Check if tweet has video"""
        if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
            for media in tweet.extended_entities['media']:
                if media['type'] in ['video', 'animated_gif']:
                    return True
        return False

    def _extract_image_urls(self, tweet):
        """Extract image URLs from tweet"""
        image_urls = []
        if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
            for media in tweet.extended_entities['media']:
                if media['type'] == 'photo':
                    image_urls.append(media['media_url_https'])
        return image_urls

    def _extract_video_urls(self, tweet):
        """Extract video URLs from tweet"""
        video_urls = []
        if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
            for media in tweet.extended_entities['media']:
                if media['type'] in ['video', 'animated_gif']:
                    # Get highest quality video variant
                    if 'video_info' in media and 'variants' in media['video_info']:
                        # Filter for mp4 variants and sort by bitrate
                        mp4_variants = [v for v in media['video_info']['variants'] if v.get('content_type') == 'video/mp4']
                        if mp4_variants:
                            # Sort by bitrate (highest first)
                            best_variant = max(mp4_variants, key=lambda v: v.get('bitrate', 0))
                            video_urls.append(best_variant['url'])
        return video_urls

    def _extract_all_media(self, tweet):
        """
        Extract all media (images and videos) from tweet
        Returns: list of dicts with {type: 'photo'|'video', url: str}
        """
        media_items = []
        if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
            for media in tweet.extended_entities['media']:
                if media['type'] == 'photo':
                    media_items.append({
                        'type': 'photo',
                        'url': media['media_url_https']
                    })
                elif media['type'] in ['video', 'animated_gif']:
                    if 'video_info' in media and 'variants' in media['video_info']:
                        mp4_variants = [v for v in media['video_info']['variants'] if v.get('content_type') == 'video/mp4']
                        if mp4_variants:
                            best_variant = max(mp4_variants, key=lambda v: v.get('bitrate', 0))
                            media_items.append({
                                'type': 'video',
                                'url': best_variant['url']
                            })
        return media_items


class TweetDeleter:
    """Main orchestrator for tweet deletion"""

    def __init__(self, dry_run=True):
        self.dry_run = dry_run

        # Authenticate with Twitter v1.1 (for delete operations)
        auth = tweepy.OAuth1UserHandler(
            API_KEY, API_SECRET,
            ACCESS_TOKEN, ACCESS_TOKEN_SECRET
        )
        self.api = tweepy.API(auth, wait_on_rate_limit=True)

        # Authenticate with Twitter v2 (for fetching tweets)
        self.client = tweepy.Client(
            bearer_token=BEARER_TOKEN,
            consumer_key=API_KEY,
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET,
            wait_on_rate_limit=True
        )

        # Get user info
        me_v2 = self.client.get_me()
        self.my_user_id = me_v2.data.id
        self.username = me_v2.data.username

        # Initialize components
        self.analyzer = ContentAnalyzer()
        self.decider = DeletionDecider(self.analyzer, self.my_user_id)
        self.state_manager = StateManager()

        # Initialize Cloudflare R2 storage (optional - only if credentials are set)
        self.storage = None
        try:
            self.storage = CloudflareR2Storage()
            print(f"✅ Cloudflare R2 storage initialized")
        except (ValueError, Exception) as e:
            print(f"⚠️  Cloudflare R2 not configured: {e}")
            print(f"   Media will not be uploaded. Set CLOUDFLARE_* env vars to enable.")

    def run(self, limit=MAX_TWEETS_PER_RUN):
        """Main execution loop"""
        print("="*60)
        print(f"🧹 Selective Tweet Deleter for @{self.username}")
        print(f"   Mode: {'DRY RUN (no deletions)' if self.dry_run else 'EXECUTE (will delete)'}")
        print("="*60)
        print(f"\n📊 Stats so far:")
        print(f"   Analyzed: {self.state_manager.state['total_analyzed']}")
        print(f"   Deleted: {self.state_manager.state['total_deleted']}")
        print(f"   Kept: {self.state_manager.state['total_kept']}")

        # Get pagination token from state
        pagination_token = self.state_manager.state.get("pagination_token")

        if pagination_token:
            print(f"\n📥 Fetching up to {limit} tweets (continuing from previous run)...")
        else:
            print(f"\n📥 Fetching up to {limit} tweets (starting from newest)...")

        try:
            # Fetch tweets using v2 API with pagination
            # v2 API requires min 5, max 100 results per request
            max_results = max(5, min(limit, 100))

            # Build request parameters
            request_params = {
                "id": self.my_user_id,
                "max_results": max_results,
                "tweet_fields": ['created_at', 'text', 'attachments', 'referenced_tweets', 'in_reply_to_user_id'],
                "expansions": ['attachments.media_keys'],
                "media_fields": ['type', 'url', 'preview_image_url']
            }

            # Add pagination token if we have one
            if pagination_token:
                request_params["pagination_token"] = pagination_token

            response = self.client.get_users_tweets(**request_params)

            if not response.data:
                print("✅ No more tweets to process!")
                # Reset pagination token since we've reached the end
                self.state_manager.update_pagination_token(None)
                self.state_manager.save_state()
                return

            tweets = response.data
            media_dict = {}
            if response.includes and 'media' in response.includes:
                media_dict = {m.media_key: m for m in response.includes['media']}

            print(f"📋 Found {len(tweets)} tweets to analyze\n")

            analyzed_count = 0
            deleted_count = 0
            kept_count = 0

            for tweet in tweets:
                # Skip if already analyzed
                if self.state_manager.was_analyzed(tweet.id):
                    print(f"⏭️  Skipping already analyzed tweet {tweet.id}")
                    continue

                # Skip tweets that are too recent
                tweet_age = datetime.now(timezone.utc) - tweet.created_at
                if tweet_age.days < SKIP_RECENT_DAYS:
                    print(f"⏭️  Skipping recent tweet {tweet.id} ({tweet_age.days} days old, waiting {SKIP_RECENT_DAYS} days)")
                    continue

                analyzed_count += 1

                # Adapt v2 tweet to v1-like structure for compatibility
                tweet_adapted = self._adapt_v2_tweet(tweet, media_dict)

                # Extract and upload media (skip replies to other people)
                uploaded_media = []
                is_reply_to_other = tweet_adapted.in_reply_to_status_id and tweet_adapted.in_reply_to_user_id != self.my_user_id

                if not is_reply_to_other:
                    media_items = self.decider._extract_all_media(tweet_adapted)
                    if media_items:
                        print(f"📸 Found {len(media_items)} media item(s) in tweet {tweet.id}")
                        uploaded_media = self._upload_tweet_media(tweet_adapted, media_items)
                    else:
                        print(f"⏭️  No media found in tweet {tweet.id} - skipping backup")

                # Make decision
                should_delete, reason, ai_analysis = self.decider.should_delete(tweet_adapted)

                tweet_preview = tweet.text[:60].replace('\n', ' ')
                date_str = tweet.created_at.strftime("%Y-%m-%d")

                if should_delete:
                    deleted_count += 1
                    decision_emoji = "🗑️ "

                    # Actually delete if not dry run
                    actually_deleted = False
                    if not self.dry_run:
                        try:
                            self.api.destroy_status(tweet.id)
                            actually_deleted = True
                            print(f"{decision_emoji} DELETED [{date_str}]: {tweet_preview}...")
                            print(f"   Reason: {reason}")
                            time.sleep(DELAY_BETWEEN_DELETES)
                        except tweepy.errors.TweepyException as e:
                            print(f"❌ Failed to delete: {e}")
                    else:
                        print(f"{decision_emoji} WOULD DELETE [{date_str}]: {tweet_preview}...")
                        print(f"   Reason: {reason}")

                    self.state_manager.log_decision(
                        tweet_adapted, "DELETE", reason, ai_analysis, actually_deleted, uploaded_media
                    )
                else:
                    kept_count += 1
                    print(f"✅ KEEPING [{date_str}]: {tweet_preview}...")
                    print(f"   Reason: {reason}")

                    self.state_manager.log_decision(
                        tweet_adapted, "KEEP", reason, ai_analysis, False, uploaded_media
                    )

                print()  # Blank line between tweets

            # Summary
            print("="*60)
            print(f"✨ Summary for this run:")
            print(f"   Analyzed: {analyzed_count}")
            print(f"   Would delete: {deleted_count}")
            print(f"   Keeping: {kept_count}")
            if not self.dry_run:
                print(f"   Actually deleted: {deleted_count}")
            print("="*60)

            # Update pagination token for next run
            if response.meta and 'next_token' in response.meta:
                next_token = response.meta['next_token']
                self.state_manager.update_pagination_token(next_token)
                print(f"\n📄 Pagination token saved - will continue from here next run")
            else:
                # No more pages, reset token
                self.state_manager.update_pagination_token(None)
                print(f"\n🏁 Reached end of tweets - will start from newest on next run")

        except tweepy.errors.TweepyException as e:
            print(f"❌ Twitter API Error: {e}")
        finally:
            # Save state to MongoDB
            self.state_manager.save_state()
            print(f"\n💾 Progress saved to MongoDB")

    def _adapt_v2_tweet(self, tweet_v2, media_dict):
        """Convert v2 tweet format to v1-like structure for compatibility"""
        class AdaptedTweet:
            def __init__(self, v2_tweet, media_dict):
                self.id = v2_tweet.id
                self.full_text = v2_tweet.text
                self.created_at = v2_tweet.created_at
                self.in_reply_to_status_id = None
                self.in_reply_to_user_id = getattr(v2_tweet, 'in_reply_to_user_id', None)

                # Check for retweet
                if hasattr(v2_tweet, 'referenced_tweets') and v2_tweet.referenced_tweets:
                    for ref in v2_tweet.referenced_tweets:
                        if ref.type == 'retweeted':
                            self.retweeted_status = True
                            break
                        elif ref.type == 'replied_to':
                            self.in_reply_to_status_id = ref.id

                # Handle media
                self.extended_entities = {}
                if hasattr(v2_tweet, 'attachments') and v2_tweet.attachments and 'media_keys' in v2_tweet.attachments:
                    media_list = []
                    for media_key in v2_tweet.attachments['media_keys']:
                        if media_key in media_dict:
                            media_obj = media_dict[media_key]
                            media_list.append({
                                'type': media_obj.type,
                                'media_url_https': getattr(media_obj, 'url', None)
                            })
                    if media_list:
                        self.extended_entities['media'] = media_list

        return AdaptedTweet(tweet_v2, media_dict)

    def _download_media(self, url, timeout=30):
        """
        Download media from URL
        Returns: bytes or None if failed
        """
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return response.content
            else:
                print(f"⚠️  Failed to download media: HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"⚠️  Failed to download media from {url}: {e}")
            return None

    def _upload_tweet_media(self, tweet, media_items):
        """
        Upload all media from a tweet to Cloudflare R2
        Returns: list of dicts with upload metadata
        """
        if not self.storage:
            return []

        uploaded_media = []
        tweet_id = tweet.id

        for idx, media_item in enumerate(media_items):
            media_type = media_item['type']
            media_url = media_item['url']

            # Download media
            print(f"📥 Downloading {media_type} {idx+1}/{len(media_items)} from tweet {tweet_id}...")
            media_bytes = self._download_media(media_url)

            if not media_bytes:
                print(f"⚠️  Skipping upload - download failed")
                continue

            # Determine file extension and content type
            if media_type == 'photo':
                extension = 'jpg'
                content_type = 'image/jpeg'
            else:  # video
                extension = 'mp4'
                content_type = 'video/mp4'

            # Generate object key with username/tweets/tweet_id/filename structure
            filename = f"{media_type}_{idx}.{extension}"
            object_key = f"{self.username}/tweets/{tweet_id}/{filename}"

            # Upload to R2
            try:
                upload_result = self.storage.upload_bytes(
                    media_bytes,
                    object_key,
                    content_type=content_type
                )

                uploaded_media.append({
                    'type': media_type,
                    'object_path': upload_result['object_path'],
                    'deeplink': upload_result['deeplink'],
                    'content_type': upload_result['content_type'],
                    'file_size': upload_result['file_size']
                })

                print(f"✅ Uploaded {media_type} to: {upload_result['object_path']}")

            except StorageUploadError as e:
                print(f"❌ Failed to upload {media_type}: {e}")
                continue

        return uploaded_media


def main():
    parser = argparse.ArgumentParser(description='Selective Tweet Deleter')
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute deletions (default is dry-run)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=MAX_TWEETS_PER_RUN,
        help=f'Number of tweets to process (default: {MAX_TWEETS_PER_RUN})'
    )
    parser.add_argument(
        '--reset-pagination',
        action='store_true',
        help='Reset pagination and start from newest tweets'
    )

    args = parser.parse_args()

    if not OPENAI_API_KEY:
        print("❌ Error: OPENAI_API_KEY not found in .env file")
        return

    # Reset pagination if requested
    if args.reset_pagination:
        state_collection.update_one(
            {"_id": "app_state"},
            {"$set": {"pagination_token": None}},
            upsert=True
        )
        print("✅ Pagination reset - will start from newest tweets\n")

    if not args.execute:
        print("\n⚠️  DRY RUN MODE - No tweets will be deleted")
        print("   Use --execute to actually delete tweets\n")

    deleter = TweetDeleter(dry_run=not args.execute)
    deleter.run(limit=args.limit)

    print("\n" + "="*60)
    if args.execute:
        print("✨ Done! Run again to process more tweets.")
    else:
        print("✨ Dry run complete! Review decisions in MongoDB")
        print("   Run with --execute to actually delete tweets")
    print("="*60)


if __name__ == "__main__":
    main()
