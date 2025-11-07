import os
import tweepy
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")

print("Testing Twitter API credentials...")
print(f"API_KEY: {API_KEY[:10]}..." if API_KEY else "API_KEY: NOT SET")
print(f"API_SECRET: {API_SECRET[:10]}..." if API_SECRET else "API_SECRET: NOT SET")
print(f"ACCESS_TOKEN: {ACCESS_TOKEN[:10]}..." if ACCESS_TOKEN else "ACCESS_TOKEN: NOT SET")
print(f"ACCESS_TOKEN_SECRET: {ACCESS_TOKEN_SECRET[:10]}..." if ACCESS_TOKEN_SECRET else "ACCESS_TOKEN_SECRET: NOT SET")

print("\nTrying to authenticate with v2 API...")
try:
    client = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )

    me = client.get_me()
    print(f"✅ Success! Authenticated as @{me.data.username}")
    print(f"   User ID: {me.data.id}")

except Exception as e:
    print(f"❌ Authentication failed: {e}")
    print("\nPlease check:")
    print("1. Your .env file has all four credentials")
    print("2. Your Twitter app has Read and Write permissions")
    print("3. You regenerated the Access Token after changing permissions")
