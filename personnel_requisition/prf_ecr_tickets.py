import pandas as pd
from google.cloud import firestore
import gspread
from google.oauth2.service_account import Credentials

# ==========================================================
# CONFIGURATION
# ==========================================================
SERVICE_ACCOUNT_FILE = 'service_account.json'  # Path to your JSON key file
FIRESTORE_COLLECTION = 'your_collection_name'   # Firestore collection name
SPREADSHEET_ID = 'YOUR_SPREADSHEET_ID_HERE'    # Found in sheet URL: /d/SPREADSHEET_ID/edit
WORKSHEET_NAME = 'Sheet1'                       # Sheet tab name

# Required API scopes
SCOPES = [
    'https://www.googleapis.com/auth/cloud-platform',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def export_firestore_to_sheets():
    print("1. Authenticating credentials...")
    # Load credentials with the required scopes
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, 
        scopes=SCOPES
    )

    # ==========================================================
    # 2. FETCH DATA FROM FIRESTORE
    # ==========================================================
    print(f"2. Fetching documents from Firestore collection: '{FIRESTORE_COLLECTION}'...")
    db = firestore.Client(credentials=creds)
    docs = db.collection(FIRESTORE_COLLECTION).stream()

    data = []
    for doc in docs:
        doc_dict = doc.to_dict()
        doc_dict['document_id'] = doc.id  # Include the document ID as a column
        data.append(doc_dict)

    if not data:
        print("⚠️ No documents found in the specified collection.")
        return

    # Convert data into a Pandas DataFrame for easy manipulation
    df = pd.DataFrame(data)

    # Clean / stringify data (Google Sheets API requires serializable formats)
    df = df.fillna('')  # Replace NaN values with empty strings
    
    # Optional: Convert nested dicts/objects or timestamps to string representation
    for col in df.columns:
        df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (dict, list)) else x)
        df[col] = df[col].astype(str)

    # ==========================================================
    # 3. WRITE DATA TO GOOGLE SHEETS
    # ==========================================================
    print("3. Connecting to Google Sheets...")
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(WORKSHEET_NAME)

    # Prepare headers and rows
    headers = df.columns.tolist()
    values = [headers] + df.values.tolist()

    print("4. Clearing existing sheet and writing new data...")
    worksheet.clear()  # Clear existing content (omit if appending)
    worksheet.update('A1', values)

    print("✅ Export completed successfully!")

if __name__ == '__main__':
    export_firestore_to_sheets()