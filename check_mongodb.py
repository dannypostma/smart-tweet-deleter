"""
Check what's stored in MongoDB after the dry run
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

DATABASE_URL = os.getenv("DATABASEURL")

try:
    # Connect to MongoDB
    client = MongoClient(DATABASE_URL)
    db = client.get_default_database()

    state_collection = db["state"]
    decisions_collection = db["decisions"]

    # Check state
    print("="*60)
    print("📊 APP STATE:")
    print("="*60)
    state = state_collection.find_one({"_id": "app_state"})
    if state:
        print(f"Total analyzed: {state.get('total_analyzed', 0)}")
        print(f"Total deleted: {state.get('total_deleted', 0)}")
        print(f"Total kept: {state.get('total_kept', 0)}")
        print(f"Last run: {state.get('last_run', 'Never')}")
    else:
        print("No state found")

    # Check decisions
    print("\n" + "="*60)
    print("📋 RECENT DECISIONS:")
    print("="*60)
    decisions = list(decisions_collection.find().sort("analyzed_at", -1).limit(5))
    print(f"Total decisions in DB: {decisions_collection.count_documents({})}")
    print(f"\nShowing last 5 decisions:\n")

    for i, decision in enumerate(decisions, 1):
        print(f"{i}. [{decision['decision']}] {decision['text'][:50]}...")
        print(f"   Reason: {decision['reason'][:80]}...")
        print(f"   Deleted: {decision['deleted']}")
        print(f"   Analyzed at: {decision['analyzed_at']}")
        print()

    print("="*60)
    print("✅ MongoDB check complete!")
    print("="*60)

except Exception as e:
    print(f"❌ Error: {e}")
