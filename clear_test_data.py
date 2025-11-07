"""
Clear test data from MongoDB to test pagination from scratch
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

DATABASE_URL = os.getenv("DATABASEURL")

try:
    client = MongoClient(DATABASE_URL)
    db = client.get_default_database()

    state_collection = db["state"]
    decisions_collection = db["decisions"]

    # Clear all data
    decisions_collection.delete_many({})
    state_collection.delete_many({})

    print("✅ Cleared all test data from MongoDB")
    print("   Ready to test pagination from scratch")

except Exception as e:
    print(f"❌ Error: {e}")
