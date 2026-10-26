import os
import json
import pandas as pd
from datetime import datetime
from google.cloud import firestore
import gspread
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# ==========================================================
# CONFIGURATION
# ==========================================================
CREDS_FILE = 'google_creds.json'
FIRESTORE_PROJECT_ID = 'ticketingtool-prod'
FIRESTORE_COLLECTION = 'serviceRequests'

# Shared Drive Target Folder ID
TARGET_FOLDER_ID = '12CHNWIQuqMbIHZrFRI2mYp7fF7eJ2kxH'

# Metadata Mapping Sheet ("Data Integration Form Fields")
MAPPING_SPREADSHEET_ID = '1Q2wFATBIC8CS-lEnEF2K4zzbWdHRiwwJbZS3QkU8YhU' # Replace with your mapping sheet ID
MAPPING_WORKSHEET_NAME = 'Sheet1'

SCOPES = [
    'https://www.googleapis.com/auth/cloud-platform',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_credentials():
    if os.path.exists(CREDS_FILE):
        return Credentials.from_authorized_user_file(CREDS_FILE, scopes=SCOPES)
    raise FileNotFoundError(f"Credential file '{CREDS_FILE}' not found.")

def export_firestore_weekly():
    print("1. Authenticating credentials...")
    creds = get_credentials()
    gc = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    db = firestore.Client(credentials=creds, project=FIRESTORE_PROJECT_ID)

    # ==========================================================
    # 2. FETCH FIELD MAPPING METADATA
    # ==========================================================
    print("2. Fetching field mappings...")
    mapping_sheet = gc.open_by_key(MAPPING_SPREADSHEET_ID).worksheet(MAPPING_WORKSHEET_NAME)
    mapping_records = mapping_sheet.get_all_records()
    
    # Map Firestore key (Field Name or Field ID) -> Field Label
    field_mapping = {}
    for row in mapping_records:
        # Check 'Field Name' first, fallback to 'Field ID'
        firestore_key = row.get('Field Name') or row.get('Field ID')
        label = row.get('Field Label')
        if firestore_key and label:
            field_mapping[str(firestore_key).strip()] = str(label).strip()

    if not field_mapping:
        print("❌ No valid mappings found in the mapping sheet!")
        return

    print(f"   -> Loaded {len(field_mapping)} target field mappings.")

    # ==========================================================
    # 3. FETCH & FILTER FIRESTORE DATA
    # ==========================================================
    print(f"3. Querying collection '{FIRESTORE_COLLECTION}' from Firestore...")
    docs = db.collection(FIRESTORE_COLLECTION).stream()

    extracted_rows = []
    for doc in docs:
        doc_dict = doc.to_dict()
        
        # Check for nested payload structures
        form_payload = doc_dict.get('formPayload', doc_dict.get('payload', {}))
        if isinstance(form_payload, str):
            try:
                form_payload = json.loads(form_payload)
            except Exception:
                form_payload = {}

        row_data = {'Document ID': doc.id}
        
        # Extract mapped fields (check root doc first, then nested payload)
        for firestore_key, label in field_mapping.items():
            val = doc_dict.get(firestore_key)
            if val is None and isinstance(form_payload, dict):
                val = form_payload.get(firestore_key, '')
            row_data[label] = val if val is not None else ''
            
        extracted_rows.append(row_data)

    if not extracted_rows:
        print("⚠️ No documents found in Firestore collection.")
        return

    # Process DataFrame
    df = pd.DataFrame(extracted_rows)
    df = df.fillna('')  
    for col in df.columns:
        df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (dict, list)) else x).astype(str)

    ordered_columns = ['Document ID'] + list(field_mapping.values())
    df = df.reindex(columns=ordered_columns)

    # ==========================================================
    # 4. CREATE WEEKLY SPREADSHEET IN SHARED DRIVE
    # ==========================================================
    weekly_filename = f"Firestore_Export_{datetime.now().strftime('%Y-%m-%d')}"
    print(f"4. Creating new spreadsheet '{weekly_filename}' in Shared Drive...")

    file_metadata = {
        'name': weekly_filename,
        'mimeType': 'application/vnd.google-apps.spreadsheet',
        'parents': [TARGET_FOLDER_ID]
    }

    new_file = drive_service.files().create(
        body=file_metadata,
        supportsAllDrives=True,
        fields='id'
    ).execute()

    new_sheet_id = new_file.get('id')
    print(f"   -> Created File ID: {new_sheet_id}")

    # ==========================================================
    # 5. WRITE DATA TO SHEET
    # ==========================================================
    print("5. Writing extracted rows to Google Sheet...")
    spreadsheet = gc.open_by_key(new_sheet_id)
    worksheet = spreadsheet.sheet1

    headers = df.columns.tolist()
    values = [headers] + df.values.tolist()

    worksheet.update('A1', values)
    print(f"🎉 SUCCESS! Weekly report created and saved to folder '{TARGET_FOLDER_ID}'.")

if __name__ == '__main__':
    export_firestore_weekly()