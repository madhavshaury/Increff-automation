# Increff Automation Suite

A comprehensive automation toolkit designed to streamline report generation from **Increff Omni**, download them locally, upload them to **Google Drive**, and optionally distribute them via **SendGrid**.

---

## Key Features

- **Automated Report Generation**: Seamlessly triggers standard reports across multiple categories:
  - **Inventory**: Current stock levels and QC status (Daily).
  - **Orders**: Monthly order status details (OMS).
  - **Returns**: Detailed return order tracking (Monthly).
  - **SKU Master**: Global SKU and style mapping.
- **Google Drive Integration**: Automatically uploads every generated report to a designated Google Drive folder for centralized access.
- **Email Distribution**: Built-in SendGrid support to email inventory reports directly to stakeholders.
- **Smart Polling**: Intelligent retry logic that waits for Increff to process large reports before attempting download.
- **Session Persistence**: Automated login via Playwright to-capture and refresh session cookies.

---

## Project Structure

```text
increff_automation/
├── inventory_to_drive.py    # Inventory report automation (includes Email)
├── orders_to_drive.py       # Order report automation (OMS)
├── returns_to_drive.py      # Returns report automation
├── sku_master_to_drive.py   # SKU Master report automation
├── downloads/               # Temporary local storage for reports
├── .env                     # Configuration and credentials
├── increff_auth.json        # Persistent session storage (generated)
├── token.json               # Google OAuth token (generated)
└── README.md                # This file
```

---

## Getting Started

### 1. Prerequisites
Ensure you have Python 3.8+ installed.

### 2. Installation
Install the required Python packages:

```bash
pip install requests google-auth google-auth-oauthlib google-api-python-client python-dotenv playwright
playwright install chromium
```

### 3. Configuration
Create a `.env` file in the root directory based on the following template:

```ini
# Increff Credentials (Extracted from increff_auth.json)
export INCREFF_SESSION="your_session_cookie"
export INCREFF_AUTHTOKEN="your_auth_token"

# Google Drive Configuration
GDRIVE_FOLDER_ID="your_google_drive_folder_id"
GDRIVE_CLIENT_SECRETS_FILE="client_secret_xxxx.json"

# SendGrid Email Configuration (Optional)
SENDGRID_API_KEY="your_sendgrid_api_key"
SENDGRID_SENDER_EMAIL="sender@yourdomain.com"
SENDGRID_RECIPIENTS="user1@example.com,user2@example.com"
```

---

## Authentication Setup

### Increff Session
Since Increff uses session-based authentication, you must first capture a valid session:
1. Run the session saver: `python save_session.py` (located in the parent directory or move it here).
2. A browser window will open. Complete the login, solve any CAPTCHAs, and wait until the dashboard loads.
3. The script will save `increff_auth.json`.
4. Extract the `SESSION` and `authToken` values and update your `.env` file.

### Google Drive API
1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Drive API**.
3. Create **OAuth 2.0 Client IDs** and download the JSON file.
4. Rename it or point `GDRIVE_CLIENT_SECRETS_FILE` in `.env` to this file.
5. On the first run of any `*_to_drive.py` script, a browser will open for one-time authorization.

---

## Usage

Run the desired automation script based on the report you need:

| Report Type | Command | Features |
| :--- | :--- | :--- |
| **Inventory** | `python inventory_to_drive.py` | Drive Upload + Email |
| **Orders** | `python orders_to_drive.py` | Drive Upload |
| **Returns** | `python returns_to_drive.py` | Drive Upload |
| **SKU Master** | `python sku_master_to_drive.py` | Drive Upload |

---

## Disclaimer
This tool is intended for internal automation purposes. Ensure you comply with Increff's Terms of Service regarding API usage and automated access.
