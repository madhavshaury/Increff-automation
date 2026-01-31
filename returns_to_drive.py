import requests
import time
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Google Drive Libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# =========================
# LOAD ENV
# =========================
load_dotenv()

# =========================
# CONFIG
# =========================
BASE_URL = "https://agilitas.omni.increff.com"
GENERATE_URL = f"{BASE_URL}/reporting/api/standard/app-access/request-report"
STATUS_URL   = f"{BASE_URL}/reporting/api/standard/request-report"

DOWNLOAD_DIR = "./downloads"
POLL_INTERVAL = 2
MAX_WAIT_SECONDS = 600

# Increff Credentials
SESSION_COOKIE = os.getenv("INCREFF_SESSION")
AUTH_TOKEN     = os.getenv("INCREFF_AUTHTOKEN")

# Google Drive Config
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
CLIENT_SECRETS_FILE = os.getenv("GDRIVE_CLIENT_SECRETS_FILE")
TOKEN_FILE = "token.json"

if not SESSION_COOKIE or not AUTH_TOKEN:
    raise RuntimeError("❌ Missing INCREFF_SESSION or INCREFF_AUTHTOKEN")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# =========================
# GOOGLE DRIVE HELPERS
# =========================

def get_drive_service():
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                raise FileNotFoundError(f"❌ Error: {CLIENT_SECRETS_FILE} not found.")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def upload_to_drive(file_path, folder_id):
    print(f"📤 Uploading {os.path.basename(file_path)} to Google Drive...")
    try:
        service = get_drive_service()
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"✅ Successfully uploaded to Drive! File ID: {file.get('id')}")
    except Exception as e:
        print(f"❌ Google Drive Upload Failed: {str(e)}")

# =========================
# INCREFF HELPERS
# =========================

def assert_session_alive(resp):
    if resp.status_code in (401, 403):
        raise RuntimeError("🔒 Session expired or unauthorized")
    if "login" in resp.text.lower():
        raise RuntimeError("🔒 Redirected to login page")

# =========================
# MAIN LOGIC
# =========================

def main():
    # 1. SETUP SESSION
    session = requests.Session()
    session.cookies.set("SESSION", SESSION_COOKIE, domain="agilitas.omni.increff.com", path="/")
    session.cookies.set("authToken", AUTH_TOKEN, domain="agilitas.omni.increff.com", path="/")
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15",
    })

    # 2. CALCULATE DATES
    now = datetime.now()
    first_of_month = now.replace(day=1)
    start_utc = (first_of_month - timedelta(days=1)).strftime("%Y-%m-%d") + "T18:30:00.000Z"
    end_utc = now.strftime("%Y-%m-%d") + "T18:29:59.000Z"
    
    print(f"📅 Date Range: {start_utc} to {end_utc}")

    # 3. GENERATE REPORT (Returns - Detail)
    payload = {
        "paramMap": {
            "client": ["1101201064", "1101210390"],
            "fulfillmentLocations": ["1101210185", "1101214370", "1101205510"],
            "childSKU": ["1. Child+Standalone SKUs (ITEM LEVEL)"],
            "returnsWithoutFwd": ["ALL"],
            "expectedReturns": ["ALL"],
            "retOrdID": [],
            "returnCreatedFrom": [start_utc],
            "returnCreatedTo": [end_utc],
            "retOrdItemID": [],
            "returnProcessedFrom": [],
            "returnProcessedTo": [],
            "returnGateEntryId": [],
            "returnGateEntryCreatedFrom": [],
            "returnGateEntryCreatedTo": [],
            "returnGateEntryItemId": [],
            "outwardOrderId": [],
            "uploadedChOrdID": [],
            "roStatus": [],
            "salesChannel": [],
            "brand": [],
            "standardSkuAttributes": [],
            "customSkuAttributes": [],
            "customReturnOrderAttribute": [],
            "CustomReturnOrderItemAttributes": []
        },
        "timezone": "Asia/Calcutta",
        "reportId": 107071,
        "fileFormat": "XLSX"
    }

    print("🚀 Requesting Return Order Report...")
    resp = session.post(GENERATE_URL, json=payload)
    assert_session_alive(resp)

    request_id = None
    if resp.status_code in (200, 201, 204) and resp.text:
        try:
            request_id = resp.json().get("id")
        except: pass
    
    if not request_id:
        status_resp = session.get(STATUS_URL)
        reports = status_resp.json()
        if reports:
            request_id = reports[0].get("requestId")

    if not request_id:
        raise RuntimeError("❌ Could not determine requestId")

    # 4. POLL
    print(f"⏳ Waiting for report {request_id} to be ready...")
    download_url = None
    start_time = time.time()

    while time.time() - start_time < MAX_WAIT_SECONDS:
        r = session.get(STATUS_URL)
        reports = r.json()
        target = next((x for x in reports if x.get("requestId") == request_id), None)

        if target:
            status = target.get("status")
            if status == "COMPLETED":
                detail_resp = session.get(f"{STATUS_URL}/{request_id}")
                val = detail_resp.json()
                download_url = val.get("status") if isinstance(val, dict) else str(val)
                if download_url.startswith("http"):
                    break
        time.sleep(POLL_INTERVAL)

    # 5. DOWNLOAD
    filename = f"return_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    file_path = os.path.join(DOWNLOAD_DIR, filename)

    print("📥 Downloading file...")
    with requests.get(download_url, stream=True) as r:
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    abs_path = os.path.abspath(file_path)
    print(f"✅ Local download complete: {abs_path}")

    # 6. UPLOAD TO DRIVE
    if GDRIVE_FOLDER_ID:
        upload_to_drive(abs_path, GDRIVE_FOLDER_ID)

if __name__ == "__main__":
    main()
