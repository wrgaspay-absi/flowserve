"""
Extract form submissions for 'Personnel Requisition Form 2.0', filter by Target Company ID, 
and output to a BRAND NEW Google Sheet inside the Shared Drive folder.
Naming convention: Personnel Requisition Form 2.0_MMDDYYYY
"""

import os
import json
from datetime import datetime
import gspread
from google.cloud import firestore
from google.oauth2.service_account import Credentials as SACredentials

# ==============================================================================
# ⚙️ CONFIGURATION
# ==============================================================================

TARGET_FORM = "Personnel Requisition Form 2.0"
FIRESTORE_PROJECT_ID = "ticketingtool-prod"
CREDS_FILE = "service_account.json"  # Automatically checked in current and parent directory
TARGET_COMPANY_ID = "1EMo1zoZuqqDNINR678H"
FIELD_DEF_SHEET_ID = "1xaYPnEbx9s4Ho7uXgNJTiAnhEHA3utF7BDIYJZaCXDg"
SHARED_DRIVE_FOLDER_ID = "12CHNWIQuqMbIHZrFRI2mYp7fF7eJ2kxH"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/cloud-platform"
]

# ==============================================================================


def get_service_account_credentials(creds_filename):
    """Locates and loads the Service Account JSON credentials."""
    search_paths = [
        creds_filename,
        os.path.join("..", creds_filename),
        os.path.join("C:\\flowserve", creds_filename)
    ]
    
    resolved_path = None
    for path in search_paths:
        if os.path.exists(path):
            resolved_path = path
            break
            
    if not resolved_path:
        raise FileNotFoundError(f"Could not locate '{creds_filename}' in search paths: {search_paths}")

    return SACredentials.from_service_account_file(resolved_path, scopes=SCOPES)


def find_col(header, name):
    for i, h in enumerate(header):
        if h.strip().lower() == name.lower():
            return i
    return None


def get_value_from_doc(doc_dict, fid, fname):
    payload_sources = [doc_dict.get("formPayload"), doc_dict, doc_dict.get("formData"), doc_dict.get("answers")]
    for source in payload_sources:
        if not isinstance(source, dict):
            continue
        if fname and fname in source and source[fname] is not None:
            return source[fname]
        if fid and fid in source and source[fid] is not None:
            return source[fid]
    return None


def format_cell_value(val, subsidiary_map=None):
    if val is None:
        return ""
    if isinstance(val, str) and subsidiary_map and val.strip() in subsidiary_map:
        return subsidiary_map[val.strip()]
    if isinstance(val, list):
        if not val:
            return ""
        if all(isinstance(x, dict) for x in val):
            names = [x.get("name") or x.get("url") or str(x) for x in val]
            return ", ".join(names)
        return json.dumps(val)
    if isinstance(val, dict):
        return json.dumps(val)
    return str(val).strip()


def main():
    print(f"🚀 Starting extraction script for: {TARGET_FORM}")
    print("🔑 Loading Service Account credentials...")
    creds = get_service_account_credentials(CREDS_FILE)
    gc = gspread.authorize(creds)
    db = firestore.Client(credentials=creds, project=FIRESTORE_PROJECT_ID)

    # 1. Fetch Definition Headers
    print("📊 Opening definition spreadsheet...")
    def_spreadsheet = gc.open_by_key(FIELD_DEF_SHEET_ID)
    try:
        ws = def_spreadsheet.worksheet(TARGET_FORM)
    except gspread.WorksheetNotFound:
        print(f"❌ Error: Tab '{TARGET_FORM}' not found in definition sheet.")
        return

    values = ws.get_all_values()
    header = values[0] if values else []
    label_idx = find_col(header, "Field Label")
    name_idx = find_col(header, "Field Name")
    id_idx = find_col(header, "Field ID")

    field_definitions = []
    for row in values[1:]:
        fid = row[id_idx].strip() if (id_idx is not None and id_idx < len(row)) else ""
        fname = row[name_idx].strip() if (name_idx is not None and name_idx < len(row)) else ""
        flabel = row[label_idx].strip() if (label_idx is not None and label_idx < len(row)) else ""
        
        display_header = flabel if flabel else (fname if fname else fid)
        if fid or fname:
            field_definitions.append((fid, fname, display_header))

    if not field_definitions:
        print(f"⚠️ No fields defined for '{TARGET_FORM}'. Exiting.")
        return

    # 2. Fetch Reference Collections
    print("🏢 Fetching reference collections...")
    subsidiary_map = {sub.id: (sub.to_dict().get("name") or sub.to_dict().get("subsidiaryName") or sub.id) for sub in db.collection("subsidiaries").stream()}
    workflow_map = {wf.id: wf.to_dict().get("service", "") for wf in db.collection("approvalWorkflows").stream()}
    ticket_map = {}
    for tk in db.collection("tickets").stream():
        data = tk.to_dict()
        req_id = data.get("requestId")
        if req_id:
            ticket_map[req_id] = {"ticket_id": data.get("id", ""), "created_at": data.get("createdAt", "")}

    # 3. Fetch and Filter serviceRequests
    print(f"🔍 Fetching and filtering 'serviceRequests' for '{TARGET_FORM}'...")
    raw_docs = []
    for doc in db.collection("serviceRequests").stream():
        d = doc.to_dict()
        d["__doc_id__"] = doc.id
        
        service_name = workflow_map.get(d.get("workflowId"), "").strip()
        
        if service_name.lower() == TARGET_FORM.lower():
            company_val = get_value_from_doc(d, "company", "company")
            if company_val and str(company_val).strip() == TARGET_COMPANY_ID:
                tk_info = ticket_map.get(doc.id, {})
                d["__ticket_id__"] = tk_info.get("ticket_id", "No Ticket ID")
                d["__ticket_created_at__"] = tk_info.get("created_at", "")
                d["__service__"] = service_name
                raw_docs.append(d)

    print(f"🎯 Found {len(raw_docs)} matching tickets.")

    # 4. Extract Data Rows
    headers = ["Ticket ID", "Ticket Created At", "Service", "Document ID"] + [h for _, _, h in field_definitions]
    rows = []
    for doc in raw_docs:
        row = [doc["__ticket_id__"], doc["__ticket_created_at__"], doc["__service__"], doc["__doc_id__"]]
        has_any_value = False
        for fid, fname, _ in field_definitions:
            raw_val = get_value_from_doc(doc, fid, fname)
            formatted_val = format_cell_value(raw_val, subsidiary_map)
            if formatted_val != "":
                has_any_value = True
            row.append(formatted_val)
        
        if has_any_value:
            rows.append(row)

    # 5. Create Brand New Google Sheet in Shared Drive Folder
    today_str = datetime.now().strftime("%m%d%Y")
    safe_form_name = TARGET_FORM.replace("/", "-")
    sheet_title = f"{safe_form_name}_{today_str}"
    
    print(f"➕ Creating Google Sheet: '{sheet_title}' inside Shared Drive...")
    target_spreadsheet = gc.create(sheet_title, folder_id=SHARED_DRIVE_FOLDER_ID)
    ws_target = target_spreadsheet.sheet1
    ws_target.update_title("Form Data")
    
    data_to_write = [headers] + (rows if rows else [["No matching submissions found"]])
    ws_target.update("A1", data_to_write)
    print(f"✅ Created successfully: https://docs.google.com/spreadsheets/d/{target_spreadsheet.id}")


if __name__ == "__main__":
    main()