import requests
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Google Drive Libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Email Libraries (Resend API)
import base64

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

# SendGrid Config
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_SENDER_EMAIL = os.getenv("SENDGRID_SENDER_EMAIL")
SENDGRID_SENDER_NAME = os.getenv("SENDGRID_SENDER_NAME", "Increff Automation")
SENDGRID_RECIPIENTS = os.getenv("SENDGRID_RECIPIENTS", "").split(",")

if not SESSION_COOKIE or not AUTH_TOKEN:
    raise RuntimeError("❌ Missing INCREFF_SESSION or INCREFF_AUTHTOKEN")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# =========================
# GOOGLE DRIVE HELPERS
# =========================

def get_drive_service():
    """Gets valid user credentials from storage or opens browser to log in."""
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    creds = None
    
    # 1. Try loading existing token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # 2. If no valid token, log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                raise FileNotFoundError(f"❌ Error: {CLIENT_SECRETS_FILE} not found. Please download it from Google Cloud Console.")
            
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # 3. Save token for next time
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
        
        media = MediaFileUpload(
            file_path, 
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"✅ Successfully uploaded to Drive! File ID: {file.get('id')}")
    except Exception as e:
        print(f"❌ Google Drive Upload Failed: {str(e)}")

# =========================
# EMAIL HELPERS (SENDGRID)
# =========================

def send_email_with_sendgrid(file_path):
    if not SENDGRID_API_KEY or not SENDGRID_RECIPIENTS[0] or not SENDGRID_SENDER_EMAIL:
        print("⚠️ SendGrid credentials not fully configured. Skipping email.")
        return

    print(f"📧 Sending email via SendGrid to {', '.join(SENDGRID_RECIPIENTS)}...")
    
    try:
        # 1. Read and encode the file
        with open(file_path, "rb") as f:
            file_content = base64.b64encode(f.read()).decode()

        # 2. Format recipients for SendGrid
        personalizations = []
        for email in SENDGRID_RECIPIENTS:
            if email.strip():
                personalizations.append({"to": [{"email": email.strip()}]})

        # 3. Create Payload
        payload = {
            "personalizations": personalizations,
            "from": {"email": SENDGRID_SENDER_EMAIL, "name": SENDGRID_SENDER_NAME},
            "subject": f"Increff Inventory Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": [
                {
                    "type": "text/html",
                    "value": f"<p>Please find the attached Increff Inventory Report for <strong>{datetime.now().strftime('%Y-%m-%d')}</strong>.</p>"
                }
            ],
            "attachments": [
                {
                    "content": file_content,
                    "filename": os.path.basename(file_path),
                    "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "disposition": "attachment"
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        }

        # 4. API Request
        response = requests.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers)
        
        if response.status_code in (200, 201, 202):
            print(f"✅ Email sent successfully via SendGrid!")
        else:
            print(f"❌ Failed to send email: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"❌ SendGrid API Error: {str(e)}")

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

    # 2. GENERATE REPORT
    payload = {
        "paramMap": {
            "fulfillmentLocations": ["1101210185", "1101214370", "1101205510"],
            "client": ["1101201064", "1101210390"],
            "brand": [], "QCStatus": [], "GlobalSKUId": [],
            "Style": [], "EAN": [], "VirtualSKU": [],
            "ReservationPool": [], "customSkuAttributes": []
        },
        "timezone": "Asia/Calcutta",
        "reportId": 106899,
        "fileFormat": "XLSX"
    }

    print("🚀 Requesting Increff report...")
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

    # 3. POLL
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

    # 4. DOWNLOAD
    filename = f"inventory_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    file_path = os.path.join(DOWNLOAD_DIR, filename)

    print("📥 Downloading file...")
    with requests.get(download_url, stream=True) as r:
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    abs_path = os.path.abspath(file_path)
    print(f"✅ Local download complete: {abs_path}")

    # 5. UPLOAD TO DRIVE
    if GDRIVE_FOLDER_ID:
        upload_to_drive(abs_path, GDRIVE_FOLDER_ID)

    # 6. SEND EMAIL
    if SENDGRID_API_KEY:
        send_email_with_sendgrid(abs_path)

if __name__ == "__main__":
    main()
