import os
from google.cloud import firestore
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account

# ==========================================
# CONFIGURATION
# ==========================================
FIRESTORE_PROJECT_ID = "ticketingtool-prod"
COLLECTION_NAME = "serviceRequests"

def test_firestore_connection():
    print("🔍 Testing Firestore Connection...")
    db = None

    # 1. Try google_creds.json (OAuth Credentials)
    if os.path.exists("google_creds.json"):
        print("✅ Found 'google_creds.json'. Authenticating...")
        try:
            creds = Credentials.from_authorized_user_file("google_creds.json")
            db = firestore.Client(credentials=creds, project=FIRESTORE_PROJECT_ID)
        except Exception as e:
            print(f"⚠️ Could not load google_creds.json: {e}")

    # 2. Try service_account.json (Service Account Key)
    if not db and os.path.exists("service_account.json"):
        print("✅ Found 'service_account.json'. Authenticating...")
        try:
            creds = service_account.Credentials.from_service_account_file("service_account.json")
            db = firestore.Client(credentials=creds, project=FIRESTORE_PROJECT_ID)
        except Exception as e:
            print(f"⚠️ Could not load service_account.json: {e}")

    # 3. Fallback to ADC
    if not db:
        print("⚠️ No local credential files loaded. Falling back to Application Default Credentials (ADC)...")
        db = firestore.Client(project=FIRESTORE_PROJECT_ID)

    # Test Firestore Query
    try:
        print(f"📡 Querying collection '{COLLECTION_NAME}' (Limit: 3 documents)...")
        docs = list(db.collection(COLLECTION_NAME).limit(3).stream())

        if docs:
            print(f"\n🎉 SUCCESS! Connected to Firestore and fetched {len(docs)} test record(s):\n")
            for i, doc in enumerate(docs, 1):
                data = doc.to_dict()
                keys_sample = list(data.keys())[:5]  # Show sample field names
                print(f"  [{i}] Document ID: {doc.id}")
                print(f"      Sample Fields: {keys_sample}")
        else:
            print(f"✅ Connected successfully to Firestore, but collection '{COLLECTION_NAME}' is empty.")

    except Exception as e:
        print(f"\n❌ Firestore Connection FAILED: {e}")

if __name__ == '__main__':
    test_firestore_connection()