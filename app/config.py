import os
from pathlib import Path

E = os.getenv
DEBUG = E("DEBUG", "0") == "1"
DATABASE_URL = E("DATABASE_URL", "sqlite:///./local.db")
SECRET_KEY = E("SECRET_KEY", "change-me")
BASE_URL = E("BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_USERNAME = E("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = E("ADMIN_PASSWORD", "")
ADMIN_EMAIL = E("ADMIN_EMAIL", "")
ADMIN_WHATSAPP = E("ADMIN_WHATSAPP", "923368149077")
SMTP_HOST, SMTP_PORT = E("SMTP_HOST", ""), int(E("SMTP_PORT", "587"))
SMTP_USER, SMTP_PASS = E("SMTP_USER", ""), E("SMTP_PASS", "")
SMTP_FROM = E("SMTP_FROM", "") or SMTP_USER
WA_TOKEN, WA_PHONE_ID = E("WA_TOKEN", ""), E("WA_PHONE_ID", "")
COMPANY = E("COMPANY_NAME", "Immaculate Crest")
COMPANY_LINES = E("COMPANY_ADDRESS", "Karachi, Pakistan|WhatsApp +92 336 8149077|Instagram 8immaculatecrest").split("|")
UPLOAD_DIR = Path(E("UPLOAD_DIR", "./data/uploads"))
PUBLIC_DIR, PRIVATE_DIR, DOCS_DIR = UPLOAD_DIR / "public", UPLOAD_DIR / "private", UPLOAD_DIR / "docs"
MAX_FILE_MB, MAX_VIDEO_MB, MAX_FILES = int(E("MAX_FILE_MB", "25")), int(E("MAX_VIDEO_MB", "200")), 10
STATUSES = ["New Inquiry", "Quotation Sent", "Awaiting Confirmation", "Confirmed", "In Production", "Dispatched", "Completed"]
