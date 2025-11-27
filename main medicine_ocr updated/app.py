from flask import Flask, request, render_template, jsonify, redirect, url_for, session, flash
from google.cloud import vision
import re, os
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import io
from google.cloud.vision_v1 import types
import logging
import base64
import json

# Set up logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Key Configuration
# Set your Gemini API key as environment variable: 
# Windows CMD: set GEMINI_API_KEY=your-api-key-here
# Windows PowerShell: $env:GEMINI_API_KEY="your-api-key-here"
# Linux/Mac: export GEMINI_API_KEY="your-api-key-here"
# 
# Get a FREE API key from: https://aistudio.google.com/app/apikey
GEMINI_API_KEY_FALLBACK = ""  # Leave empty - set via environment variable

# Try to import AI libraries
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not available. Install with: pip install google-generativeai")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai not available. Install with: pip install openai")

# Try to import Tesseract OCR (FREE - no API key needed!)
TESSERACT_AVAILABLE = False
TESSERACT_PATH = None
try:
    import pytesseract
    from PIL import Image as PILImage
    # Set Tesseract path for Windows - check multiple locations
    tesseract_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Tesseract-OCR\tesseract.exe',
        r'C:\Users\Public\Tesseract-OCR\tesseract.exe',
        os.path.expanduser(r'~\AppData\Local\Tesseract-OCR\tesseract.exe'),
        os.path.expanduser(r'~\Tesseract-OCR\tesseract.exe'),
        # Linux/Mac paths
        '/usr/bin/tesseract',
        '/usr/local/bin/tesseract',
        '/opt/homebrew/bin/tesseract',
    ]
    for path in tesseract_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            TESSERACT_PATH = path
            TESSERACT_AVAILABLE = True
            print(f"[STARTUP] ✅ Tesseract found at: {path}")
            logger.info(f"Tesseract OCR found at: {path}")
            break
    
    # Also try without explicit path (if tesseract is in PATH)
    if not TESSERACT_AVAILABLE:
        try:
            # Test if tesseract works without explicit path
            pytesseract.get_tesseract_version()
            TESSERACT_AVAILABLE = True
            TESSERACT_PATH = "tesseract (in PATH)"
            print("[STARTUP] ✅ Tesseract found in system PATH")
            logger.info("Tesseract OCR found in system PATH")
        except Exception:
            pass
    
    if not TESSERACT_AVAILABLE:
        print("[STARTUP] ❌ Tesseract NOT found!")
        print("[STARTUP] Please install Tesseract OCR (FREE):")
        print("[STARTUP] Download from: https://github.com/UB-Mannheim/tesseract/wiki")
        logger.warning("pytesseract imported but tesseract.exe not found")
except ImportError as e:
    print(f"[STARTUP] ❌ pytesseract import failed: {e}")
    print("[STARTUP] Run: pip install pytesseract")
    logger.warning(f"pytesseract not available: {e}")

# ─── App & DB Setup ───────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medicine.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'supersecretkey'  # Needed for session management

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# Initialize Google Vision client with error handling
try:
    credentials_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vision-key.json')
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
    logger.info(f"Setting GOOGLE_APPLICATION_CREDENTIALS to: {credentials_path}")
    
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"Credentials file not found at: {credentials_path}")
        
    global_vision_client = vision.ImageAnnotatorClient()
    logger.info("Successfully initialized Google Cloud Vision client")
except Exception as e:
    logger.error(f"Failed to initialize Google Cloud Vision client: {str(e)}")
    raise

class Medicine(db.Model):
    batch_id = db.Column(db.Integer, primary_key=True)
    medicine_name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    batch_number = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)
    manufacture_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)

class MedicineEnquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    medicine_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    enquiry_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_name = db.Column(db.String(100), nullable=False)

# Initial medicine data
initial_medicine_data = [
    {"batch_id": 1, "medicine_name": "Augmentin", "brand": "GSK", "category": "Tablet", "batch_number": "AUG-GSK-2026", "quantity": 120, "price_per_unit": 32.00, "manufacture_date": "2024-02-15", "expiry_date": "2026-02-15"},
    {"batch_id": 2, "medicine_name": "Avil", "brand": "Sanofi", "category": "Tablet", "batch_number": "AVIL-SAN-2026", "quantity": 90, "price_per_unit": 5.00, "manufacture_date": "2023-12-10", "expiry_date": "2026-12-10"},
    {"batch_id": 3, "medicine_name": "Benadryl", "brand": "J&J", "category": "Syrup", "batch_number": "BENA-JJ-2026", "quantity": 60, "price_per_unit": 75.00, "manufacture_date": "2024-04-20", "expiry_date": "2026-04-20"},
    {"batch_id": 4, "medicine_name": "Brufen", "brand": "Abbott", "category": "Tablet", "batch_number": "BRUF-ABB-2026", "quantity": 85, "price_per_unit": 20.00, "manufacture_date": "2024-03-12", "expiry_date": "2026-03-12"},
    {"batch_id": 5, "medicine_name": "Brufen", "brand": "Abbott", "category": "Tablet", "batch_number": "BRUF-ABB-2028", "quantity": 60, "price_per_unit": 20.00, "manufacture_date": "2025-06-18", "expiry_date": "2028-06-18"},
    {"batch_id": 6, "medicine_name": "Calpol", "brand": "GSK", "category": "Tablet", "batch_number": "CALP-GSK-2026", "quantity": 100, "price_per_unit": 18.00, "manufacture_date": "2024-06-15", "expiry_date": "2026-06-15"},
    {"batch_id": 7, "medicine_name": "Calpol", "brand": "GSK", "category": "Tablet", "batch_number": "CALP-GSK-2027", "quantity": 80, "price_per_unit": 18.00, "manufacture_date": "2025-03-01", "expiry_date": "2027-03-01"},
    {"batch_id": 8, "medicine_name": "Cetrizine", "brand": "Cipla", "category": "Tablet", "batch_number": "CET-CIP-2026", "quantity": 110, "price_per_unit": 3.00, "manufacture_date": "2024-01-22", "expiry_date": "2026-01-22"},
    {"batch_id": 9, "medicine_name": "Combiflam", "brand": "Sanofi", "category": "Tablet", "batch_number": "COMB-SAN-2026", "quantity": 150, "price_per_unit": 10.00, "manufacture_date": "2023-03-22", "expiry_date": "2026-03-22"},
    {"batch_id": 10, "medicine_name": "Combiflam", "brand": "Sanofi", "category": "Tablet", "batch_number": "COMB-SAN-2027", "quantity": 120, "price_per_unit": 10.00, "manufacture_date": "2024-02-10", "expiry_date": "2027-02-10"},
    {"batch_id": 11, "medicine_name": "Dolo 650", "brand": "Micro Labs", "category": "Tablet", "batch_number": "DL650-2038", "quantity": 100, "price_per_unit": 25.00, "manufacture_date": "2023-06-27", "expiry_date": "2038-06-27"},
    {"batch_id": 12, "medicine_name": "Dolo 650", "brand": "Micro Labs", "category": "Tablet", "batch_number": "DL650-2027", "quantity": 75, "price_per_unit": 25.00, "manufacture_date": "2022-07-23", "expiry_date": "2027-07-23"},
    {"batch_id": 13, "medicine_name": "Domstal", "brand": "Torrent", "category": "Tablet", "batch_number": "DOMS-TOR-2027", "quantity": 130, "price_per_unit": 17.00, "manufacture_date": "2024-01-10", "expiry_date": "2027-01-10"},
    {"batch_id": 14, "medicine_name": "Domstal", "brand": "Torrent", "category": "Tablet", "batch_number": "DOMS-TOR-2026", "quantity": 110, "price_per_unit": 17.00, "manufacture_date": "2023-06-20", "expiry_date": "2026-06-20"},
    {"batch_id": 15, "medicine_name": "Electral", "brand": "FDC", "category": "Powder", "batch_number": "ELEC-FDC-2025", "quantity": 50, "price_per_unit": 12.00, "manufacture_date": "2023-12-01", "expiry_date": "2025-12-01"},
    {"batch_id": 16, "medicine_name": "Electral", "brand": "FDC", "category": "Powder", "batch_number": "ELEC-FDC-2026", "quantity": 70, "price_per_unit": 12.00, "manufacture_date": "2024-04-14", "expiry_date": "2026-04-14"},
    {"batch_id": 17, "medicine_name": "Eno", "brand": "GSK", "category": "Powder", "batch_number": "ENO-GSK-2025", "quantity": 100, "price_per_unit": 7.00, "manufacture_date": "2023-09-01", "expiry_date": "2025-09-01"},
    {"batch_id": 18, "medicine_name": "Fepanil", "brand": "Sun Pharma", "category": "Tablet", "batch_number": "FEP-SUN-2026", "quantity": 120, "price_per_unit": 9.00, "manufacture_date": "2024-03-15", "expiry_date": "2026-03-15"},
    {"batch_id": 19, "medicine_name": "Flexon", "brand": "Aristo", "category": "Tablet", "batch_number": "FLEX-ARI-2026", "quantity": 100, "price_per_unit": 11.00, "manufacture_date": "2024-02-10", "expiry_date": "2026-02-10"},
    {"batch_id": 20, "medicine_name": "Gaviscon", "brand": "Reckitt", "category": "Suspension", "batch_number": "GAVI-REC-2026", "quantity": 70, "price_per_unit": 30.00, "manufacture_date": "2024-05-05", "expiry_date": "2026-05-05"},
    {"batch_id": 21, "medicine_name": "Gelusil", "brand": "Pfizer", "category": "Suspension", "batch_number": "GELU-PFZ-2026", "quantity": 75, "price_per_unit": 30.00, "manufacture_date": "2023-06-20", "expiry_date": "2026-06-20"},
    {"batch_id": 22, "medicine_name": "Gelusil", "brand": "Pfizer", "category": "Suspension", "batch_number": "GELU-PFZ-2027", "quantity": 55, "price_per_unit": 30.00, "manufacture_date": "2024-05-10", "expiry_date": "2027-05-10"},
    {"batch_id": 23, "medicine_name": "Honitus", "brand": "Dabur", "category": "Syrup", "batch_number": "HONI-DAB-2026", "quantity": 80, "price_per_unit": 90.00, "manufacture_date": "2024-02-25", "expiry_date": "2026-02-25"},
    {"batch_id": 24, "medicine_name": "Hifenac", "brand": "Intas", "category": "Tablet", "batch_number": "HIFE-INT-2026", "quantity": 90, "price_per_unit": 18.00, "manufacture_date": "2024-01-30", "expiry_date": "2026-01-30"},
    {"batch_id": 25, "medicine_name": "Ibugesic", "brand": "Cipla", "category": "Tablet", "batch_number": "IBU-CIP-2026", "quantity": 100, "price_per_unit": 10.00, "manufacture_date": "2024-06-10", "expiry_date": "2026-06-10"},
    {"batch_id": 26, "medicine_name": "Iodex", "brand": "GSK", "category": "Ointment", "batch_number": "IOD-GSK-2026", "quantity": 60, "price_per_unit": 40.00, "manufacture_date": "2024-03-12", "expiry_date": "2026-03-12"},
    {"batch_id": 27, "medicine_name": "Jiffy", "brand": "Cadila", "category": "Tablet", "batch_number": "JIFF-CAD-2026", "quantity": 70, "price_per_unit": 8.00, "manufacture_date": "2024-04-06", "expiry_date": "2026-04-06"},
    {"batch_id": 28, "medicine_name": "Junior Lanzol", "brand": "Cipla", "category": "Tablet", "batch_number": "JLAN-CIP-2026", "quantity": 60, "price_per_unit": 14.00, "manufacture_date": "2024-02-12", "expiry_date": "2026-02-12"},
    {"batch_id": 29, "medicine_name": "Ketanov", "brand": "Sun Pharma", "category": "Tablet", "batch_number": "KETA-SUN-2026", "quantity": 85, "price_per_unit": 22.00, "manufacture_date": "2024-01-18", "expiry_date": "2026-01-18"},
    {"batch_id": 30, "medicine_name": "Ketorol", "brand": "Dr. Reddy's", "category": "Tablet", "batch_number": "KETO-DRD-2026", "quantity": 90, "price_per_unit": 25.00, "manufacture_date": "2024-03-08", "expiry_date": "2026-03-08"},
    {"batch_id": 31, "medicine_name": "Limcee", "brand": "Abbott", "category": "Tablet", "batch_number": "LIM-ABB-2026", "quantity": 100, "price_per_unit": 7.00, "manufacture_date": "2024-02-22", "expiry_date": "2026-02-22"},
    {"batch_id": 32, "medicine_name": "Liv52", "brand": "Himalaya", "category": "Syrup", "batch_number": "LIV52-HIM-2027", "quantity": 60, "price_per_unit": 85.00, "manufacture_date": "2024-02-01", "expiry_date": "2027-02-01"},
    {"batch_id": 33, "medicine_name": "Liv52", "brand": "Himalaya", "category": "Syrup", "batch_number": "LIV52-HIM-2026", "quantity": 50, "price_per_unit": 85.00, "manufacture_date": "2023-01-18", "expiry_date": "2026-01-18"},
    {"batch_id": 34, "medicine_name": "Meftal Spas", "brand": "Blue Cross", "category": "Tablet", "batch_number": "MEF-BC-2026", "quantity": 120, "price_per_unit": 15.00, "manufacture_date": "2024-04-11", "expiry_date": "2026-04-11"},
    {"batch_id": 35, "medicine_name": "Metrogyl", "brand": "JB Chem", "category": "Tablet", "batch_number": "MET-JB-2026", "quantity": 110, "price_per_unit": 12.00, "manufacture_date": "2024-03-05", "expiry_date": "2026-03-20"},
    {"batch_id": 36, "medicine_name": "Nasivion", "brand": "Bayer", "category": "Drops", "batch_number": "NAS-BAY-2026", "quantity": 75, "price_per_unit": 65.00, "manufacture_date": "2024-05-20", "expiry_date": "2026-05-20"},
    {"batch_id": 37, "medicine_name": "Norflox", "brand": "Cipla", "category": "Tablet", "batch_number": "NOR-CIP-2026", "quantity": 90, "price_per_unit": 12.00, "manufacture_date": "2024-02-28", "expiry_date": "2026-02-28"},
    {"batch_id": 38, "medicine_name": "Omez", "brand": "Dr. Reddy's", "category": "Capsule", "batch_number": "OMEZ-DRD-2025", "quantity": 120, "price_per_unit": 12.50, "manufacture_date": "2023-11-15", "expiry_date": "2025-11-15"},
    {"batch_id": 39, "medicine_name": "Omez", "brand": "Dr. Reddy's", "category": "Capsule", "batch_number": "OMEZ-DRD-2026", "quantity": 90, "price_per_unit": 12.50, "manufacture_date": "2024-01-05", "expiry_date": "2026-01-05"},
    {"batch_id": 40, "medicine_name": "Ondem", "brand": "Alkem", "category": "Tablet", "batch_number": "OND-ALK-2026", "quantity": 95, "price_per_unit": 14.00, "manufacture_date": "2023-08-18", "expiry_date": "2026-08-18"},
    {"batch_id": 41, "medicine_name": "Ondem", "brand": "Alkem", "category": "Tablet", "batch_number": "OND-ALK-2027", "quantity": 100, "price_per_unit": 14.00, "manufacture_date": "2024-03-22", "expiry_date": "2027-03-22"},
    {"batch_id": 42, "medicine_name": "Pantoprazole", "brand": "Zydus", "category": "Tablet", "batch_number": "PANTO-ZYD-2026", "quantity": 110, "price_per_unit": 22.00, "manufacture_date": "2023-10-10", "expiry_date": "2026-10-10"},
    {"batch_id": 43, "medicine_name": "Pantoprazole", "brand": "Zydus", "category": "Tablet", "batch_number": "PANTO-ZYD-2027", "quantity": 95, "price_per_unit": 22.00, "manufacture_date": "2024-06-06", "expiry_date": "2027-06-06"},
    {"batch_id": 44, "medicine_name": "Paracetamol", "brand": "Cipla", "category": "Tablet", "batch_number": "PARA-CIPLA-2026", "quantity": 200, "price_per_unit": 15.00, "manufacture_date": "2024-05-12", "expiry_date": "2026-05-12"},
    {"batch_id": 45, "medicine_name": "Paracetamol", "brand": "Cipla", "category": "Tablet", "batch_number": "PARA-CIPLA-2027", "quantity": 160, "price_per_unit": 15.00, "manufacture_date": "2025-01-20", "expiry_date": "2027-01-20"},
    {"batch_id": 46, "medicine_name": "Quadriderm", "brand": "MSD", "category": "Cream", "batch_number": "QUAD-MSD-2026", "quantity": 50, "price_per_unit": 60.00, "manufacture_date": "2024-03-25", "expiry_date": "2026-03-25"},
    {"batch_id": 47, "medicine_name": "Quinidine", "brand": "Sandoz", "category": "Tablet", "batch_number": "QUIN-SAN-2026", "quantity": 40, "price_per_unit": 28.00, "manufacture_date": "2024-04-18", "expiry_date": "2026-04-18"},
    {"batch_id": 48, "medicine_name": "Rantac", "brand": "JB Chem", "category": "Tablet", "batch_number": "RANT-JB-2026", "quantity": 100, "price_per_unit": 9.00, "manufacture_date": "2024-01-07", "expiry_date": "2026-01-07"},
    {"batch_id": 49, "medicine_name": "Revital", "brand": "Sun Pharma", "category": "Capsule", "batch_number": "REVI-SUN-2027", "quantity": 80, "price_per_unit": 120.00, "manufacture_date": "2024-04-01", "expiry_date": "2027-04-01"},
    {"batch_id": 50, "medicine_name": "Revital", "brand": "Sun Pharma", "category": "Capsule", "batch_number": "REVI-SUN-2025", "quantity": 60, "price_per_unit": 120.00, "manufacture_date": "2023-02-01", "expiry_date": "2025-02-01"},
    {"batch_id": 51, "medicine_name": "Sinarest", "brand": "Centaur", "category": "Tablet", "batch_number": "SINA-CEN-2025", "quantity": 90, "price_per_unit": 8.00, "manufacture_date": "2023-09-05", "expiry_date": "2025-09-05"},
    {"batch_id": 52, "medicine_name": "Sinarest", "brand": "Centaur", "category": "Tablet", "batch_number": "SINA-CEN-2026", "quantity": 100, "price_per_unit": 8.00, "manufacture_date": "2024-07-01", "expiry_date": "2026-07-01"},
    {"batch_id": 53, "medicine_name": "Soframycin", "brand": "Sanofi", "category": "Cream", "batch_number": "SOFR-SAN-2026", "quantity": 70, "price_per_unit": 32.00, "manufacture_date": "2023-04-21", "expiry_date": "2026-04-21"},
    {"batch_id": 54, "medicine_name": "Soframycin", "brand": "Sanofi", "category": "Cream", "batch_number": "SOFR-SAN-2027", "quantity": 50, "price_per_unit": 32.00, "manufacture_date": "2024-05-01", "expiry_date": "2027-05-01"},
    {"batch_id": 55, "medicine_name": "Strepsils", "brand": "Reckitt", "category": "Lozenges", "batch_number": "STRE-REC-2025", "quantity": 100, "price_per_unit": 5.00, "manufacture_date": "2023-01-01", "expiry_date": "2025-01-01"},
    {"batch_id": 56, "medicine_name": "Strepsils", "brand": "Reckitt", "category": "Lozenges", "batch_number": "STRE-REC-2027", "quantity": 120, "price_per_unit": 5.00, "manufacture_date": "2024-08-09", "expiry_date": "2027-08-09"},
    {"batch_id": 57, "medicine_name": "Taxim-O", "brand": "Alkem", "category": "Tablet", "batch_number": "TAX-ALK-2026", "quantity": 85, "price_per_unit": 45.00, "manufacture_date": "2024-05-02", "expiry_date": "2026-05-02"},
    {"batch_id": 58, "medicine_name": "Thyronorm", "brand": "Abbott", "category": "Tablet", "batch_number": "THYR-ABB-2027", "quantity": 110, "price_per_unit": 18.00, "manufacture_date": "2024-02-19", "expiry_date": "2027-02-19"},
    {"batch_id": 59, "medicine_name": "Thyronorm", "brand": "Abbott", "category": "Tablet", "batch_number": "THYR-ABB-2026", "quantity": 90, "price_per_unit": 18.00, "manufacture_date": "2023-03-14", "expiry_date": "2026-03-14"},
    {"batch_id": 60, "medicine_name": "Ulgel", "brand": "Zydus", "category": "Suspension", "batch_number": "ULG-ZYD-2026", "quantity": 70, "price_per_unit": 25.00, "manufacture_date": "2024-04-01", "expiry_date": "2026-04-01"},
    {"batch_id": 61, "medicine_name": "Unienzyme", "brand": "Torrent", "category": "Tablet", "batch_number": "UNI-TOR-2026", "quantity": 95, "price_per_unit": 13.00, "manufacture_date": "2024-02-18", "expiry_date": "2026-02-18"},
    {"batch_id": 62, "medicine_name": "Vicks", "brand": "P&G", "category": "Ointment", "batch_number": "VICK-PG-2026", "quantity": 80, "price_per_unit": 56.00, "manufacture_date": "2024-03-14", "expiry_date": "2026-03-14"},
    {"batch_id": 63, "medicine_name": "Volini", "brand": "Sun Pharma", "category": "Gel", "batch_number": "VOLI-SUN-2025", "quantity": 60, "price_per_unit": 65.00, "manufacture_date": "2023-05-10", "expiry_date": "2025-05-10"},
    {"batch_id": 64, "medicine_name": "Volini", "brand": "Sun Pharma", "category": "Gel", "batch_number": "VOLI-SUN-2026", "quantity": 50, "price_per_unit": 65.00, "manufacture_date": "2024-06-20", "expiry_date": "2026-06-20"},
    {"batch_id": 65, "medicine_name": "Wikoryl", "brand": "Alembic", "category": "Tablet", "batch_number": "WIK-ALE-2026", "quantity": 100, "price_per_unit": 8.00, "manufacture_date": "2024-02-28", "expiry_date": "2026-02-28"},
    {"batch_id": 66, "medicine_name": "Wysolone", "brand": "Pfizer", "category": "Tablet", "batch_number": "WYS-PFZ-2026", "quantity": 90, "price_per_unit": 20.00, "manufacture_date": "2024-01-25", "expiry_date": "2026-01-25"},
    {"batch_id": 67, "medicine_name": "Xarelto", "brand": "Bayer", "category": "Tablet", "batch_number": "XAR-BAY-2026", "quantity": 60, "price_per_unit": 150.00, "manufacture_date": "2024-01-30", "expiry_date": "2026-01-30"},
    {"batch_id": 68, "medicine_name": "Xone", "brand": "Alkem", "category": "Injection", "batch_number": "XON-ALK-2026", "quantity": 40, "price_per_unit": 90.00, "manufacture_date": "2024-05-12", "expiry_date": "2026-05-12"},
    {"batch_id": 69, "medicine_name": "Yogurt Sachets", "brand": "Abbott", "category": "Powder", "batch_number": "YOG-ABB-2026", "quantity": 70, "price_per_unit": 35.00, "manufacture_date": "2024-02-07", "expiry_date": "2026-02-07"},
    {"batch_id": 70, "medicine_name": "Yondelis", "brand": "Janssen", "category": "Injection", "batch_number": "YON-JAN-2026", "quantity": 30, "price_per_unit": 1200.00, "manufacture_date": "2024-03-20", "expiry_date": "2026-03-20"},
    {"batch_id": 71, "medicine_name": "Zincovit", "brand": "Apex", "category": "Tablet", "batch_number": "ZINC-APX-2026", "quantity": 110, "price_per_unit": 10.00, "manufacture_date": "2024-06-02", "expiry_date": "2026-06-02"},
    {"batch_id": 72, "medicine_name": "Zyrtec", "brand": "Dr. Reddy's", "category": "Tablet", "batch_number": "ZYRC-DRD-2025", "quantity": 90, "price_per_unit": 22.00, "manufacture_date": "2023-07-09", "expiry_date": "2025-07-09"},
    {"batch_id": 73, "medicine_name": "Zyrtec", "brand": "Dr. Reddy's", "category": "Tablet", "batch_number": "ZYRC-DRD-2027", "quantity": 75, "price_per_unit": 22.00, "manufacture_date": "2024-04-15", "expiry_date": "2027-04-15"}
]

with app.app_context():
    db.create_all()
    # Check if the database is empty before populating
    if not Medicine.query.first():
        for data in initial_medicine_data:
            data['manufacture_date'] = datetime.strptime(data['manufacture_date'], '%Y-%m-%d').date()
            data['expiry_date'] = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
            medicine = Medicine(**data)
            db.session.add(medicine)
        db.session.commit()

# ─── Medicine Database ────────────────────────────────────────────────────────
MEDICINE_DB = {
    'A': ['Augmentin', 'Avil'],
    'B': ['Benadryl', 'Brufen', 'Bifilac', 'BIFILAC'],
    'C': ['Cetrizine', 'Combiflam'],
    'D': ['Dolo 650', 'Dolo-650', 'Domstal', 'Domperidone'],
    'E': ['Eno', 'Electral'],
    'F': ['Flexon', 'Fepanil'],
    'G': ['Gelusil', 'Gaviscon'],
    'H': ['Honitus', 'Hifenac'],
    'I': ['Ibugesic', 'Iodex'],
    'J': ['Junior Lanzol', 'Jiffy'],
    'K': ['Ketorol', 'Ketanov'],
    'L': ['Liv52', 'Limcee'],
    'M': ['Meftal Spas', 'Metrogyl'],
    'N': ['Norflox', 'Nasivion'],
    'O': ['Omez', 'Ondem', 'O2', 'Ofloxacin', 'Ornidazole'],
    'P': ['Paracetamol', 'Pantoprazole'],
    'Q': ['Quadriderm', 'Quinidine'],
    'R': ['Rantac', 'Revital', 'Rabemi-DSR', 'RABEMI-DSR', 'Rabeprazole'],
    'S': ['Sinarest', 'Soframycin'],
    'T': ['Thyronorm', 'Taxim-O'],
    'U': ['Ulgel', 'Unienzyme'],
    'V': ['Volini', 'Vicks'],
    'W': ['Wikoryl', 'Wysolone'],
    'X': ['Xarelto', 'Xone'],
    'Y': ['Yondelis', 'Yogurt Sachets'],
    'Z': ['Zyrtec', 'Zincovit']
}

# Medicine information database
MEDICINE_INFO = {
    "Augmentin": {
        "uses": "Bacterial infections",
        "side_effects": "Diarrhea, Rash",
        "dosage": "As directed by physician"
    },
    "Avil": {
        "uses": "Allergy, Cold",
        "side_effects": "Drowsiness, Dry mouth",
        "dosage": "1 tablet twice daily"
    },
    "Benadryl": {
        "uses": "Cough, Allergy",
        "side_effects": "Drowsiness, Dizziness",
        "dosage": "2 tsp thrice daily"
    },
    "Brufen": {
        "uses": "Pain relief, Fever",
        "side_effects": "Nausea, Stomach pain",
        "dosage": "1 tablet every 8 hours"
    },
    "Cetrizine": {
        "uses": "Allergies, Runny nose",
        "side_effects": "Drowsiness, Dry mouth",
        "dosage": "1 tablet once daily"
    },
    "Combiflam": {
        "uses": "Pain, Fever",
        "side_effects": "Stomach upset, Nausea",
        "dosage": "1 tablet twice daily"
    },
    "Dolo 650": {
        "uses": "Fever, Headache",
        "side_effects": "Liver damage (overdose)",
        "dosage": "1 tablet every 6 hours"
    },
    "Domstal": {
        "uses": "Nausea, Vomiting",
        "side_effects": "Dry mouth, Drowsiness",
        "dosage": "1 tablet before meals"
    },
    "Eno": {
        "uses": "Acidity, Indigestion",
        "side_effects": "None common",
        "dosage": "1 tsp in water as needed"
    },
    "Electral": {
        "uses": "Dehydration, Electrolyte imbalance",
        "side_effects": "None common",
        "dosage": "Dissolve 1 packet in 1L water"
    },
    "Flexon": {
        "uses": "Pain relief, Fever",
        "side_effects": "Nausea, Stomach pain",
        "dosage": "1 tablet twice daily"
    },
    "Fepanil": {
        "uses": "Fever, Cold",
        "side_effects": "Liver effects (overdose)",
        "dosage": "1 tablet every 6 hours"
    },
    "Gelusil": {
        "uses": "Acidity, Gas",
        "side_effects": "Constipation",
        "dosage": "2 tsp after meals"
    },
    "Gaviscon": {
        "uses": "Heartburn, Indigestion",
        "side_effects": "Constipation",
        "dosage": "2 tsp after meals"
    },
    "Honitus": {
        "uses": "Cough, Cold",
        "side_effects": "Drowsiness (rare)",
        "dosage": "2 tsp thrice daily"
    },
    "Hifenac": {
        "uses": "Pain, Inflammation",
        "side_effects": "Acidity, Nausea",
        "dosage": "1 tablet after food"
    },
    "Ibugesic": {
        "uses": "Fever, Pain",
        "side_effects": "Stomach pain, Nausea",
        "dosage": "1 tablet every 6–8 hours"
    },
    "Iodex": {
        "uses": "Muscle pain",
        "side_effects": "Skin irritation",
        "dosage": "Apply externally on affected area"
    },
    "Junior Lanzol": {
        "uses": "Acidity in kids",
        "side_effects": "Abdominal pain, Diarrhea",
        "dosage": "As prescribed by pediatrician"
    },
    "Jiffy": {
        "uses": "Fever, Cold",
        "side_effects": "Drowsiness, Dry mouth",
        "dosage": "As prescribed"
    },
    "Ketorol": {
        "uses": "Severe pain",
        "side_effects": "Stomach pain, Drowsiness",
        "dosage": "As prescribed"
    },
    "Ketanov": {
        "uses": "Post-operative pain",
        "side_effects": "Nausea, Dizziness",
        "dosage": "As directed"
    },
    "Liv52": {
        "uses": "Liver health",
        "side_effects": "None significant",
        "dosage": "2 tablets daily"
    },
    "Limcee": {
        "uses": "Vitamin C supplement",
        "side_effects": "None common",
        "dosage": "1 tablet daily"
    },
    "Meftal Spas": {
        "uses": "Menstrual pain, Spasms",
        "side_effects": "Dizziness, Nausea",
        "dosage": "1 tablet as needed"
    },
    "Metrogyl": {
        "uses": "Bacterial infections",
        "side_effects": "Metallic taste, Nausea",
        "dosage": "1 tablet twice daily"
    },
    "Norflox": {
        "uses": "UTI, Diarrhea",
        "side_effects": "Nausea, Headache",
        "dosage": "1 tablet twice daily"
    },
    "Nasivion": {
        "uses": "Nasal congestion",
        "side_effects": "Burning sensation",
        "dosage": "2 drops per nostril"
    },
    "Omez": {
        "uses": "Acidity, Ulcer",
        "side_effects": "Headache, Nausea",
        "dosage": "1 capsule before food"
    },
    "Ondem": {
        "uses": "Nausea, Vomiting",
        "side_effects": "Headache, Constipation",
        "dosage": "As directed by physician"
    },
    "Paracetamol": {
        "uses": "Fever, Mild pain",
        "side_effects": "Liver toxicity (overuse)",
        "dosage": "1 tablet every 6 hours"
    },
    "Pantoprazole": {
        "uses": "GERD, Acidity",
        "side_effects": "Abdominal pain",
        "dosage": "1 tablet before breakfast"
    },
    "Quadriderm": {
        "uses": "Skin infections",
        "side_effects": "Skin irritation",
        "dosage": "Apply thin layer twice daily"
    },
    "Quinidine": {
        "uses": "Irregular heartbeat",
        "side_effects": "Dizziness, Nausea",
        "dosage": "As directed"
    },
    "Rantac": {
        "uses": "Acidity, Ulcers",
        "side_effects": "Constipation",
        "dosage": "1 tablet before meals"
    },
    "Revital": {
        "uses": "Energy supplement",
        "side_effects": "None significant",
        "dosage": "1 capsule daily"
    },
    "Sinarest": {
        "uses": "Cold, Allergy",
        "side_effects": "Drowsiness",
        "dosage": "1 tablet twice daily"
    },
    "Soframycin": {
        "uses": "Wound healing",
        "side_effects": "Skin irritation",
        "dosage": "Apply externally"
    },
    "Thyronorm": {
        "uses": "Thyroid hormone deficiency",
        "side_effects": "Weight loss, Palpitations",
        "dosage": "1 tablet before breakfast"
    },
    "Taxim-O": {
        "uses": "Bacterial infections",
        "side_effects": "Nausea, Diarrhea",
        "dosage": "1 tablet twice daily"
    },
    "Ulgel": {
        "uses": "Acidity, Gas",
        "side_effects": "Constipation",
        "dosage": "2 tsp after meals"
    },
    "Unienzyme": {
        "uses": "Indigestion",
        "side_effects": "None common",
        "dosage": "1 tablet after meals"
    },
    "Volini": {
        "uses": "Sprains, Back pain",
        "side_effects": "Skin redness",
        "dosage": "Apply gently on affected area"
    },
    "Vicks": {
        "uses": "Cough, Congestion",
        "side_effects": "Skin irritation",
        "dosage": "Rub on chest/throat"
    },
    "Wikoryl": {
        "uses": "Cold, Cough",
        "side_effects": "Drowsiness",
        "dosage": "1 tablet twice daily"
    },
    "Wysolone": {
        "uses": "Inflammation, Allergies",
        "side_effects": "Weight gain, Mood swings",
        "dosage": "As directed by doctor"
    },
    "Xarelto": {
        "uses": "Blood thinner",
        "side_effects": "Bleeding",
        "dosage": "As prescribed"
    },
    "Xone": {
        "uses": "Bacterial infections",
        "side_effects": "Diarrhea, Nausea",
        "dosage": "As prescribed"
    },
    "Yondelis": {
        "uses": "Cancer treatment",
        "side_effects": "Fatigue, Vomiting",
        "dosage": "IV under supervision"
    },
    "Yogurt Sachets": {
        "uses": "Probiotic, Digestion",
        "side_effects": "None common",
        "dosage": "1 sachet daily"
    },
    "Zyrtec": {
        "uses": "Allergy, Sneezing",
        "side_effects": "Drowsiness",
        "dosage": "1 tablet at bedtime"
    },
    "Zincovit": {
        "uses": "Immunity booster",
        "side_effects": "Mild stomach upset",
        "dosage": "1 tablet daily"
    },
    "Bifilac": {
        "uses": "Probiotic, Diarrhea, Gut health, Antibiotic-associated diarrhea",
        "side_effects": "Bloating, Gas (rare)",
        "dosage": "1 capsule twice daily"
    },
    "BIFILAC": {
        "uses": "Probiotic, Diarrhea, Gut health, Antibiotic-associated diarrhea",
        "side_effects": "Bloating, Gas (rare)",
        "dosage": "1 capsule twice daily"
    },
    "O2": {
        "uses": "Bacterial infections (Ofloxacin + Ornidazole combination)",
        "side_effects": "Nausea, Headache, Dizziness",
        "dosage": "1 tablet twice daily after meals"
    },
    "Dolo-650": {
        "uses": "Fever, Headache, Body pain",
        "side_effects": "Liver damage (overdose)",
        "dosage": "1 tablet every 6 hours"
    },
    "Rabemi-DSR": {
        "uses": "Acidity, GERD, Gastric ulcers (Rabeprazole + Domperidone)",
        "side_effects": "Headache, Diarrhea, Dry mouth",
        "dosage": "1 capsule before breakfast"
    },
    "RABEMI-DSR": {
        "uses": "Acidity, GERD, Gastric ulcers (Rabeprazole + Domperidone)",
        "side_effects": "Headache, Diarrhea, Dry mouth",
        "dosage": "1 capsule before breakfast"
    },
    "Ofloxacin": {
        "uses": "Bacterial infections, UTI, Respiratory infections",
        "side_effects": "Nausea, Diarrhea, Headache",
        "dosage": "As prescribed by physician"
    },
    "Ornidazole": {
        "uses": "Protozoal infections, Amoebiasis, Giardiasis",
        "side_effects": "Nausea, Metallic taste, Dizziness",
        "dosage": "As prescribed by physician"
    },
    "Rabeprazole": {
        "uses": "GERD, Peptic ulcer, Acidity",
        "side_effects": "Headache, Diarrhea",
        "dosage": "1 tablet before meals"
    },
    "Domperidone": {
        "uses": "Nausea, Vomiting, Bloating",
        "side_effects": "Dry mouth, Headache",
        "dosage": "1 tablet before meals"
    }
}

# Health conditions and suggested medicines
HEALTH_CONDITIONS = {
    'stomach pain': ['Pantoprazole', 'Omez', 'Gelusil', 'Brufen', 'Flexon', 'Ibugesic', 'Meftal Spas'],
    'fever': ['Paracetamol', 'Dolo 650', 'Brufen', 'Flexon', 'Ibugesic', 'Fepanil', 'Jiffy'],
    'cold': ['Sinarest', 'Cetrizine', 'Benadryl', 'Honitus', 'Jiffy', 'Wikoryl', 'Vicks'],
    'headache': ['Paracetamol', 'Combiflam'],
    'allergy': ['Cetrizine', 'Zyrtec', 'Avil', 'Benadryl', 'Sinarest', 'Wysolone'],
    'acidity': ['Pantoprazole', 'Omez', 'Gelusil', 'Eno', 'Gaviscon', 'Junior Lanzol', 'Rantac', 'Ulgel'],
    'cough': ['Honitus', 'Benadryl', 'Sinarest', 'Wikoryl', 'Vicks'],
    'vomiting': ['Domstal', 'Ondem', 'Metrogyl', 'Taxim-O', 'Yondelis'],
    'skin irritation': ['Iodex', 'Soframycin', 'Quadriderm', 'Vicks', 'Wysolone']
}

# Regex patterns for extracting information from medicine strips
PATTERNS = {
    'brand_name': [
        # Specific medicine brands from sample images
        r"(?i)\b(BIFILAC|Bifilac)\b",
        r"(?i)\b(O2|O\s*2)\b",  # O2 tablets
        r"(?i)\b(Dolo[\s\-]*650|DOLO[\s\-]*650)\b",
        r"(?i)\b(RABEMI[\s\-]*DSR|Rabemi[\s\-]*DSR)\b",
        # Common Indian medicine brand patterns
        r"(?i)\b(Dolo\s*\d+|Crocin|Pan\s*\d+|Azee\s*\d+|Calpol|Combiflam|Allegra|Montair|Augmentin|Zifi\s*\d+|Shelcal|Becosules|Limcee|Revital|Liv\s*52|Digene|Gelusil|Eno|Hajmola|Pudin\s*Hara)\b",
        r"(?i)\b(Ofloxacin|Ornidazole|Paracetamol|Rabeprazole|Domperidone)\s*(?:Tablets?|Capsules?)?\s*(?:I\.?P\.?)?\b",
        r"(?i)^([A-Z][A-Za-z0-9\-]+(?:\s*\d+)?)\b",  # Brand at start with optional number
        r"(?i)\b([A-Z][a-z]+[\s\-]*\d{2,4})\b",  # Brand with number like "Dolo 650"
        r"(?i)\b([A-Z][a-z]+(?:\s*[&+]\s*[A-Za-z]+)?)\s*(?:Tablet|Capsule|Syrup|Tab|Cap)\b",
    ],
    'generic_name': [
        r"(?i)\b(?:contains|each)\s+(.+?)(?:IP|BP|USP|Ph\.?Eur\.|\)|\n)",
        r"(?i)\b(Paracetamol|Ibuprofen|Amoxicillin|Ciprofloxacin|Metronidazole|Azithromycin|Ofloxacin|Ornidazole|Pantoprazole|Omeprazole|Ranitidine|Cetirizine|Levocetirizine|Montelukast|Atorvastatin|Metformin|Rabeprazole|Domperidone)\b",
    ],
    'dosage': [
        r"(?i)(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|IU)(?:\s*[+/&]\s*\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|IU))?)",
        r"(?i)\b(\d+\s*mg)\b",
        r"(?i)\b(\d+\s*mcg)\b",
        r"(?i)(\d+\s*mg\s*[+/&]\s*\d+\s*mg)",  # Combined dosages like "200mg + 500mg"
    ],
    'batch_number': [
        # Various batch number formats on Indian medicine strips
        r"(?i)B\.?\s*No\.?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-]{3,})",
        r"(?i)Batch\s*(?:No\.?|Number|#)?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-]{3,})",
        r"(?i)Lot\s*(?:No\.?|Number|#)?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-]{3,})",
        r"(?i)B\.N\.?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-]{3,})",
        r"(?i)L\.?\s*No\.?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-]{3,})",
        r"\b([A-Z]{2,3}[\-]?[A-Z0-9]{3,})\b",  # Pattern like ALA306, RC-071022
        r"\b([A-Z]\d{5,})\b",  # Pattern like E40001
        r"\b([A-Z]{1,3}\d{4,})\b",  # Pattern like BN12345
    ],
    'mfd': [
        # Manufacturing date patterns - various Indian formats
        r"(?i)MFG\.?\s*(?:DT\.?|DATE|D)?\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2,4})",  # MFG. DT. JAN.24
        r"(?i)MFD\.?\s*(?:DT\.?|DATE|D)?\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2,4})",  # MFD JAN 24
        r"(?i)M\.?D\.?\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2,4})",  # M.D. JAN.24
        r"(?i)MFG\.?\s*(?:DT\.?|DATE)?\s*[:#.\-]?\s*(\d{1,2}[./-]\d{2,4})",  # MFG 01/24
        r"(?i)MFD\.?\s*(?:DT\.?|DATE)?\s*[:#.\-]?\s*(\d{1,2}[./-]\d{2,4})",  # MFD 01/2024
        r"(?i)(?:Mfg|Mfd|Manufactured)\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2,4}|\d{1,2}[./-]\d{2,4})",
        r"(?i)MFG\.?\s*[:#.\-]?\s*(\d{2}[./-]\d{4})",  # MFG. 10/2023
        r"(?i)(\d{2}/\d{4})\s*(?=.*EXP)",  # Date before EXP mention
    ],
    'expiry': [
        # Expiry date patterns - various Indian formats
        r"(?i)EXP\.?\s*(?:DT\.?|DATE|D)?\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2,4})",  # EXP. DT. DEC.26
        r"(?i)E\.?D\.?\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2,4})",  # E.D. DEC.26
        r"(?i)EXP\.?\s*(?:DT\.?|DATE)?\s*[:#.\-]?\s*(\d{1,2}[./-]\d{2,4})",  # EXP 12/26
        r"(?i)(?:Expiry|Exp|Use\s*Before|Best\s*Before)\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2,4}|\d{1,2}[./-]\d{2,4})",
        r"(?i)(?:Use|Best)\s*(?:Before|By)\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2,4}|\d{1,2}[./-]\d{2,4})",
        r"(?i)EXP\.?\s*[:#.\-]?\s*(\d{2}[./-]\d{4})",  # EXP. 09/2025
        r"(?i)EXP\.?\s*[:#.\-]?\s*([A-Z]{3}\.?\s*\d{2})",  # EXP. DEC.26
        r"(?i)(?:JUL|AUG|SEP|OCT|NOV|DEC|JAN|FEB|MAR|APR|MAY|JUN)\.?\s*\d{4}\s*$",  # Month Year at end
    ],
    'manufacturer': [
        # Indian pharmaceutical companies
        r"(?i)(?:Mfd\.?\s*by|Mfg\.?\s*by|Manufactured\s*by|Marketed\s*by|Mkt\.?\s*by)\s*[:#]?\s*([A-Za-z][A-Za-z\s&\.\-]+?)(?:\s*(?:Ltd|Pvt|Private|Limited|Pharma|Pharmaceuticals|Healthcare|Laboratories|Labs))",
        r"(?i)\b(Mankind|Cipla|Sun\s*Pharma|Dr\.?\s*Reddy'?s?|Lupin|Abbott|GSK|Pfizer|Zydus|Torrent|Alkem|Intas|Glenmark|Cadila|Micro\s*Labs|Macleods|Ranbaxy|Biocon|Wockhardt|Ipca|USV|Alembic|FDC|Ajanta|Eris|Natco|Hetero|Aurobindo|Emcure|Aristo|Blue\s*Cross|Sanofi|Bayer|Novartis|Merck|AstraZeneca|Meyer|Franco\s*Indian|JB\s*Chemicals?|Medy|Medley|TOA|TOAPHARMA|Paalmi|Renewed\s*Life|Meyer\s*Organics)\b",
        r"(?i)TABLETS?\s*\(INDIA\)\s*(LIMITED|LTD)",
    ],
    'mrp': [
        # MRP patterns - improved for various formats
        r"(?i)M\.?R\.?P\.?\s*[:#]?\s*(?:Rs\.?|₹|INR)?\s*(\d+(?:[.,]\d{1,2})?)",
        r"(?i)(?:Price|MRP)\s*[:#]?\s*(?:Rs\.?|₹|INR)?\s*(\d+(?:[.,]\d{1,2})?)",
        r"(?i)Rs\.?\s*(\d+(?:[.,]\d{1,2})?)",
        r"₹\s*(\d+(?:[.,]\d{1,2})?)",
        r"(?i)M\.R\.P\.Rs\.?\s*(\d+(?:[.,]\d{1,2})?)",  # M.R.P.Rs.140.00
        r"(?i)FOR\s*\d+\s*(?:TABS?|CAPS?)\s*.*?Rs\.?\s*(\d+(?:[.,]\d{1,2})?)",  # FOR 10 TABS Rs.35
    ],
    'category': [
        r"(?i)\b(?:antibiotic|analgesic|antipyretic|anti-inflammatory|antihistamine|antacid|laxative|antifungal|antiviral|diuretic|hypnotic|sedative|antidepressant|anticoagulant|beta-blocker|statin|insulin|vaccine|hormone|vitamin|probiotic|capsule|tablet)\b"
    ],
    'form': [
        r"(?i)\b(?:tablet|capsule|syrup|suspension|injection|cream|gel|ointment|lotion|powder|drops|tab|cap|caps)\b"
    ]
}

# ─── Helper Functions ─────────────────────────────────────────────────────────
def get_medicine_suggestions(query):
    query = query.lower()
    suggestions = []
    # Iterate through all medicines in MEDICINE_INFO for partial matches
    for medicine_name, info in MEDICINE_INFO.items():
        if query in medicine_name.lower():
            suggestions.append({
                'name': medicine_name,
                'uses': info.get('uses', 'Information not available'),
                'side_effects': info.get('side_effects', 'Information not available')
            })
    return suggestions[:5]  # Return top 5 suggestions

def get_health_suggestions(condition):
    condition = condition.lower()
    suggested_medicines = []
    # Iterate through the conditions to find a match
    for key, medicines in HEALTH_CONDITIONS.items():
        if condition in key or key in condition:
            # If a match is found, retrieve detailed info for each suggested medicine
            for med_name in medicines:
                medicine_details = MEDICINE_INFO.get(med_name, {
                    'uses': 'Information not available',
                    'side_effects': 'Information not available',
                    'dosage': 'Please consult your doctor'
                })
                suggested_medicines.append({'name': med_name, **medicine_details})
    return suggested_medicines

# ─── Helper: Normalize vertical text ──────────────────────────────────────────
def normalize_vertical(text):
    lines = text.splitlines()
    normalized = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if len(line) == 1 and line.isalnum():
            run = [line]
            i += 1
            while i < len(lines) and len(lines[i].strip()) == 1 and lines[i].strip().isalnum():
                run.append(lines[i].strip())
                i += 1
            normalized.append("".join(run))
        else:
            normalized.append(line)
            i += 1
    return "\n".join(normalized)

# ─── Helper: Match from list of patterns ──────────────────────────────────────
def find_first_match(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            if len(match.groups()) > 0:
                return match.group(1).strip()
    return "Information not available"

def clean_extracted_value(value, field_type="text"):
    """Clean and validate extracted values"""
    if not value or value == "Information not available":
        return None
    
    value = str(value).strip()
    
    # Remove common noise
    value = re.sub(r'^[:\-\.\s]+', '', value)  # Remove leading punctuation
    value = re.sub(r'[:\-\.\s]+$', '', value)  # Remove trailing punctuation
    
    if field_type == "brand":
        # Filter out invalid brand names
        invalid_starts = ['each', 'film', 'coated', 'tablet', 'capsule', 'contains', 
                         'information', 'store', 'keep', 'protect', 'the', 'this', 'for', 'use']
        if value.lower().split()[0] if value.split() else '' in invalid_starts:
            return None
        # Remove trailing generic terms
        value = re.sub(r'\s*(tablets?|capsules?|I\.?P\.?|B\.?P\.?)$', '', value, flags=re.IGNORECASE)
    
    elif field_type == "batch":
        # Batch should be alphanumeric
        if not re.search(r'[A-Z0-9]', value, re.IGNORECASE):
            return None
        # Clean batch number
        value = re.sub(r'^[:\-\.\s]+', '', value)
    
    elif field_type == "mrp":
        # Extract just the number
        match = re.search(r'(\d+(?:[.,]\d{1,2})?)', value)
        if match:
            value = match.group(1).replace(',', '.')
        else:
            return None
    
    elif field_type == "date":
        # Keep date as-is for parsing later
        pass
    
    return value if value else None

def parse_date_flexible(date_str):
    """Parse various date formats commonly found on Indian medicine labels. Return date or None."""
    if not date_str:
        return None
    s = str(date_str).strip()
    
    # Fast reject placeholders
    if s.lower() in {"n/a", "na", "information not available", "unknown", ""}:
        return None
    
    logger.info(f"Parsing date: '{s}'")
    
    # Month name mapping
    month_map = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
    # Helper to convert 2-digit year to 4-digit
    def fix_year(y):
        if y < 100:
            return 2000 + y if y < 50 else 1900 + y
        return y
    
    # Helper to validate year range
    def valid_year(y):
        return 1990 <= y <= datetime.utcnow().year + 20
    
    # Pattern 1: "JAN.24", "DEC.26", "JAN 24", "DEC 26", "JAN-24"
    m = re.search(r"(?i)\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[.\-/\s]*(\d{2,4})\b", s)
    if m:
        try:
            month_str = m.group(1).lower()[:3]
            year_str = m.group(2)
            mm = month_map.get(month_str, 1)
            yyyy = fix_year(int(year_str))
            if valid_year(yyyy):
                logger.info(f"Parsed date (pattern 1): {mm}/{yyyy}")
                return datetime(yyyy, mm, 1).date()
        except Exception as e:
            logger.warning(f"Date parse error (pattern 1): {e}")
    
    # Pattern 2: "01/24", "12/26", "01/2024", "12/2026" (MM/YY or MM/YYYY)
    m = re.search(r"\b(\d{1,2})[./-](\d{2,4})\b", s)
    if m:
        try:
            mm = int(m.group(1))
            yyyy = fix_year(int(m.group(2)))
            if 1 <= mm <= 12 and valid_year(yyyy):
                logger.info(f"Parsed date (pattern 2): {mm}/{yyyy}")
                return datetime(yyyy, mm, 1).date()
        except Exception as e:
            logger.warning(f"Date parse error (pattern 2): {e}")
    
    # Pattern 3: "2024", "2026" (year only)
    m = re.search(r"\b(20\d{2})\b", s)
    if m:
        try:
            yyyy = int(m.group(1))
            if valid_year(yyyy):
                logger.info(f"Parsed date (pattern 3 - year only): 1/{yyyy}")
                return datetime(yyyy, 1, 1).date()
        except Exception as e:
            logger.warning(f"Date parse error (pattern 3): {e}")
    
    # Pattern 4: "24", "26" (2-digit year only, assume current decade)
    m = re.search(r"\b(\d{2})\b", s)
    if m:
        try:
            yyyy = fix_year(int(m.group(1)))
            if valid_year(yyyy):
                logger.info(f"Parsed date (pattern 4 - 2-digit year): 1/{yyyy}")
                return datetime(yyyy, 1, 1).date()
        except Exception as e:
            logger.warning(f"Date parse error (pattern 4): {e}")
    
    # Try standard datetime formats as fallback
    fmts = [
        "%m/%Y", "%m-%Y", "%m.%Y", "%m/%y", "%m-%y",
        "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%b %Y", "%B %Y", "%b %y", "%B %y",
        "%b. %Y", "%b. %y", "%Y",
    ]
    
    # Normalize: JAN.24 -> JAN 24
    s_normalized = re.sub(r'\.(\d)', r' \1', s)
    s_normalized = re.sub(r'\s+', ' ', s_normalized).strip()
    
    for fmt in fmts:
        try:
            dt = datetime.strptime(s_normalized, fmt)
            year = dt.year
            if year < 100:
                year = fix_year(year)
                dt = dt.replace(year=year)
            if valid_year(year):
                logger.info(f"Parsed date (strptime {fmt}): {dt.month}/{dt.year}")
                return dt.date()
        except Exception:
            continue
    
    logger.warning(f"Could not parse date: '{date_str}'")
    return None

def parse_date_from_gemini(date_str):
    """Parse date string from Gemini response - handles exact formats like JAN.24, DEC.26"""
    if not date_str:
        return None
    s = str(date_str).strip()
    if not s or s.lower() in {"n/a", "na", "", "information not available"}:
        return None
    
    # Try the flexible parser first
    result = parse_date_flexible(s)
    if result:
        return result
    
    # Additional patterns specific to Gemini output
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    # Try to find any month name and any number
    m = re.search(r"(?i)(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)", s)
    if m:
        month = month_map.get(m.group(1).lower()[:3], 1)
        # Find year number
        y = re.search(r"(\d{2,4})", s)
        if y:
            year = int(y.group(1))
            if year < 100:
                year = 2000 + year if year < 50 else 1900 + year
            if 1990 <= year <= datetime.utcnow().year + 20:
                return datetime(year, month, 1).date()
    
    return None

# Collect all plausible dates from text for heuristic reconciliation
def find_date_candidates(text):
    candidates = []
    if not text:
        return candidates
    # Patterns: Month YYYY, MM/YYYY, MM-YYYY, and standalone valid years
    patterns = [
        r"(?i)\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
        r"\b\d{1,2}[./-]\d{2,4}\b",
        r"\b(?:19|20)\d{2}\b",
    ]
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            raw = m.group(0).strip()
            if raw in seen:
                continue
            seen.add(raw)
            dt = parse_date_flexible(raw)
            if dt:
                candidates.append(dt)
    # Sort and dedupe
    candidates = sorted(set(candidates))
    return candidates

def add_months(d, months):
    if not d:
        return None
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, 28)
    try:
        return datetime(y, m, day).date()
    except Exception:
        return datetime(y, m, 1).date()

def shelf_life_months(text):
    if not text:
        return None
    m = re.search(r"(?i)\b(best\s*before|use\s*before|shelf\s*life)\s*(\d{1,2})\s*months?\b", text)
    if m:
        try:
            return int(m.group(2))
        except Exception:
            return None
    m = re.search(r"(?i)\b(\d{1,2})\s*months?\s*(?:from|after)\s*(?:mfg|manufacture|manufacturing)\b", text)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None

def reconcile_dates_from_text(full_text, mfd_dt, exp_dt):
    candidates = find_date_candidates(full_text)
    life = shelf_life_months(full_text)
    now = datetime.utcnow().date()
    if mfd_dt and exp_dt and exp_dt < mfd_dt:
        if len(candidates) >= 2:
            return min(candidates), max(candidates)
        return exp_dt, mfd_dt
    if mfd_dt and not exp_dt:
        if life:
            return mfd_dt, add_months(mfd_dt, life)
        later = [d for d in candidates if d > mfd_dt]
        if later:
            return mfd_dt, min(later)
        return mfd_dt, add_months(mfd_dt, 24)
    if exp_dt and not mfd_dt:
        earlier = [d for d in candidates if d < exp_dt]
        if earlier:
            return max(earlier), exp_dt
        if life:
            return add_months(exp_dt, -life), exp_dt
        return add_months(exp_dt, -24), exp_dt
    if not mfd_dt and not exp_dt:
        if len(candidates) >= 2:
            return min(candidates), max(candidates)
        if len(candidates) == 1:
            d = candidates[0]
            return d, add_months(d, 24)
        return now, add_months(now, 12)
    return mfd_dt, exp_dt

def _compile_date_regex():
    # Month name + year OR MM[/.-]YYYY or MM[/.-]YY (case-insensitive via flag)
    month = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}"
    mmYY = r"\d{1,2}[./-]\d{2,4}"
    year = r"(?:19|20)\d{2}"
    return re.compile(rf"\b({month}|{mmYY}|{year})\b", re.IGNORECASE)

DATE_TOKEN_RE = _compile_date_regex()

def find_labeled_date_dt(text, keywords):
    """Find a date token near any of the given keywords within the same or next line.
    Returns a parsed date or None. Keeps changes local and robust for medicine strips."""
    if not text:
        return None
    lines = text.splitlines()
    # Build a case-insensitive search set
    kws = [k.lower() for k in keywords]
    for i, line in enumerate(lines):
        low = line.lower()
        if any(k in low for k in kws):
            # Avoid picking dates from license numbers like "Mfg Lic No: ... 2012"
            if "lic" in low or "license" in low:
                continue
            scope = line
            if i + 1 < len(lines):
                scope = scope + " " + lines[i + 1]
            # Try to find date token near the keyword
            m = DATE_TOKEN_RE.search(scope)
            if m:
                dt = parse_date_flexible(m.group(0))
                if dt:
                    return dt
            # If not found, try to combine month token and year token within a small window
            mon_re = re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\b", re.IGNORECASE)
            yr_re = re.compile(r"\b(?:19|20)\d{2}\b")
            mons = list(mon_re.finditer(scope))
            yrs = list(yr_re.finditer(scope))
            if mons and yrs:
                # pick closest year after a month within 12 chars
                for mon in mons:
                    for yr in yrs:
                        if yr.start() >= mon.end() and (yr.start() - mon.end()) <= 12:
                            candidate = scope[mon.start():yr.end()]
                            dt = parse_date_flexible(candidate)
                            if dt:
                                return dt
    # Fallback: window search after keyword anywhere in text
    low_text = text.lower()
    for k in kws:
        idx = low_text.find(k)
        if idx != -1:
            window = text[idx: idx + 120]
            m = DATE_TOKEN_RE.search(window)
            if m:
                dt = parse_date_flexible(m.group(0))
                if dt:
                    return dt
            # Combine month/year as above if needed
            mon_re = re.compile(r"(?i)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\b")
            yr_re = re.compile(r"\b(?:19|20)\d{2}\b")
            mons = list(mon_re.finditer(window))
            yrs = list(yr_re.finditer(window))
            if mons and yrs:
                for mon in mons:
                    for yr in yrs:
                        if yr.start() >= mon.end() and (yr.start() - mon.end()) <= 12:
                            candidate = window[mon.start():yr.end()]
                            dt = parse_date_flexible(candidate)
                            if dt:
                                return dt
    return None

# ─── OCR Helpers (Vision with Gemini fallback) ───────────────────────────────
def is_billing_disabled_error(e):
    try:
        msg = str(e)
        return ("BILLING_DISABLED" in msg) or ("requires billing" in msg.lower())
    except Exception:
        return False

def gemini_extract_text(image_content):
    try:
        if not GEMINI_AVAILABLE:
            logger.warning("Gemini not available for OCR fallback")
            return None

        gemini_api_key = os.environ.get('GEMINI_API_KEY') or GEMINI_API_KEY_FALLBACK
        if not gemini_api_key:
            logger.warning("No GEMINI_API_KEY set for OCR fallback")
            return None

        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)

        # Open image
        from io import BytesIO
        import PIL.Image
        try:
            image_pil = PIL.Image.open(BytesIO(image_content))
        except Exception as img_err:
            logger.error(f"Gemini OCR: failed to open image: {img_err}")
            return None

        # Try preferred models
        preferred = ['models/gemini-2.0-flash', 'models/gemini-2.5-flash']
        model = None
        for name in preferred:
            try:
                model = genai.GenerativeModel(name)
                break
            except Exception as me:
                logger.warning(f"Gemini OCR: could not init {name}: {me}")
                continue
        if model is None:
            logger.error("Gemini OCR: no model initialized")
            return None

        prompt = (
            "Transcribe ALL visible text from this medicine package/strip label image. "
            "Include: product name, generic name, batch number (B.No.), MFG date, EXP date, MRP, manufacturer name. "
            "Return plain text only, preserve the original format and numbers exactly as shown."
        )
        try:
            resp = model.generate_content([prompt, image_pil])
            text = (resp.text or '').strip()
            return text if text else None
        except Exception as api_err:
            logger.error(f"Gemini OCR: API error: {api_err}")
            return None
    except Exception as e:
        logger.error(f"Gemini OCR unexpected error: {e}")
        return None

def gemini_extract_fields_from_image(image_content):
    """Use Gemini to directly extract structured fields from medicine image. Returns dict or None."""
    try:
        if not GEMINI_AVAILABLE:
            return None
        gemini_api_key = os.environ.get('GEMINI_API_KEY') or GEMINI_API_KEY_FALLBACK
        if not gemini_api_key:
            return None
        
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        
        from io import BytesIO
        import PIL.Image
        try:
            image_pil = PIL.Image.open(BytesIO(image_content))
        except Exception as img_err:
            logger.error(f"Gemini field extraction: failed to open image: {img_err}")
            return None
        
        # Initialize model
        model = None
        for name in ['models/gemini-2.0-flash', 'models/gemini-2.5-flash']:
            try:
                model = genai.GenerativeModel(name)
                break
            except Exception:
                continue
        if model is None:
            return None
        
        prompt = """You are an expert pharmacist analyzing Indian medicine strip/blister pack images.

TASK: Extract medicine information from this image with HIGH ACCURACY.

CRITICAL READING INSTRUCTIONS:
1. Medicine strips have text in MULTIPLE ORIENTATIONS - read ALL directions (horizontal, vertical, upside down)
2. The BRAND NAME is the LARGEST, most prominent text (usually in RED or BOLD)
3. Look for the BOTTOM SECTION which typically contains: B.No., MFD., EXP., MRP
4. Reflective/metallic surfaces may make text harder to read - look carefully

FIELDS TO EXTRACT:

1. brand: The MAIN PRODUCT NAME (biggest text on strip)
   - Examples: "BIFILAC", "O2", "Dolo-650", "RABEMI-DSR", "Crocin", "Pan 40"
   - Look for the RED or BOLD prominent name
   - Include any numbers that are part of the name (like "650" in "Dolo-650")
   - DO NOT use generic drug names like "Paracetamol Tablets IP" or "Ofloxacin & Ornidazole"

2. dosage: The strength/composition (numbers with mg/mcg/g/ml)
   - Examples: "650 mg", "200 mg + 500 mg", "20 mg + 30 mg"
   - For combination drugs, include both strengths

3. batch_number: The batch/lot code (alphanumeric)
   - Look after: "B.No.", "B.N.", "Batch No.", "Lot No."
   - Examples: "ALA306", "E40001", "RC-071022", "D0983759"
   - Usually 5-10 characters, mix of letters and numbers

4. manufacture_date: Manufacturing date (COPY EXACTLY as printed)
   - Look after: "MFG.", "MFD.", "MFG.DT.", "Mfg Date"
   - Common formats: "10/2023", "JAN.24", "AUG.2024", "01/24"
   - Return EXACTLY what you see

5. expiry_date: Expiry date (COPY EXACTLY as printed)
   - Look after: "EXP.", "EXP.DT.", "Expiry", "Use Before"
   - Common formats: "09/2025", "DEC.26", "JUL.2028", "12/26"
   - Return EXACTLY what you see

6. manufacturer: Company name
   - Look after: "Mfd.by", "Manufactured by", "Marketed by"
   - Examples: "Micro Labs", "Meyer Organics", "TOA Pharmaceuticals", "Paalmi Pharmaceuticals", "Renewed Life Sciences"

7. mrp: Price (numbers only)
   - Look after: "MRP", "M.R.P.", "Rs.", "₹"
   - Examples: "140.00", "189.00", "35.70"
   - Return ONLY the number without Rs/₹

SPECIFIC MEDICINE PATTERNS TO RECOGNIZE:
- BIFILAC: Probiotic capsules, red/white packaging, TOA Pharmaceuticals
- O2: Ofloxacin + Ornidazole tablets, red "O2" logo, Meyer Organics
- Dolo-650: Paracetamol 650mg, blue packaging, Micro Labs
- RABEMI-DSR: Rabeprazole + Domperidone capsules, blue/white, Paalmi/Renewed Life

OUTPUT FORMAT - Return ONLY this JSON (no other text):
{"brand": "", "dosage": "", "batch_number": "", "manufacture_date": "", "expiry_date": "", "manufacturer": "", "mrp": ""}

REAL EXAMPLES:
{"brand": "BIFILAC", "dosage": "", "batch_number": "ALA306", "manufacture_date": "10/2023", "expiry_date": "09/2025", "manufacturer": "TOA Pharmaceuticals", "mrp": "140.00"}
{"brand": "O2", "dosage": "200 mg + 500 mg", "batch_number": "E40001", "manufacture_date": "JAN.24", "expiry_date": "DEC.26", "manufacturer": "Meyer Organics", "mrp": "189.00"}
{"brand": "Dolo-650", "dosage": "650 mg", "batch_number": "D0983759", "manufacture_date": "AUG.2024", "expiry_date": "JUL.2028", "manufacturer": "Micro Labs", "mrp": "35.70"}
{"brand": "RABEMI-DSR", "dosage": "20 mg + 30 mg", "batch_number": "RC-071022", "manufacture_date": "10/2022", "expiry_date": "09/2024", "manufacturer": "Renewed Life Sciences", "mrp": ""}

Use "" for fields you cannot find. Return ONLY the JSON."""

        try:
            resp = model.generate_content([prompt, image_pil])
            text = (resp.text or '').strip()
            logger.info(f"Gemini direct extraction response: {text[:500]}")
            
            # Clean and parse JSON
            text = text.replace('```json', '').replace('```', '').strip()
            import json as _json
            try:
                data = _json.loads(text)
                if isinstance(data, dict):
                    logger.info(f"Gemini extracted fields: {data}")
                    return data
            except Exception:
                # Try to find JSON in response
                import re as _re
                m = _re.search(r"\{[\s\S]*\}", text)
                if m:
                    try:
                        data = _json.loads(m.group(0))
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass
            return None
        except Exception as api_err:
            logger.error(f"Gemini field extraction API error: {api_err}")
            return None
    except Exception as e:
        logger.error(f"Gemini field extraction error: {e}")
        return None

def preprocess_medicine_strip_image(image_pil):
    """
    Advanced image preprocessing for medicine strip/blister pack images.
    Handles reflective surfaces, multiple text orientations, and small print.
    Uses OpenCV for better preprocessing when available.
    """
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    import numpy as np
    
    try:
        # Try to use OpenCV for better preprocessing
        try:
            import cv2
            return preprocess_with_opencv(image_pil)
        except ImportError:
            logger.info("OpenCV not available, using PIL preprocessing")
        
        # Fallback to PIL-based preprocessing
        # Convert to RGB if needed
        if image_pil.mode != 'RGB':
            image_pil = image_pil.convert('RGB')
        
        # Get image dimensions
        width, height = image_pil.size
        logger.info(f"Preprocessing image: {width}x{height}")
        
        # 1. Resize if too small (Tesseract works better with larger images)
        min_dimension = 1500
        if width < min_dimension or height < min_dimension:
            scale = max(min_dimension / width, min_dimension / height)
            new_size = (int(width * scale), int(height * scale))
            image_pil = image_pil.resize(new_size, Image.LANCZOS)
            logger.info(f"Resized to: {new_size}")
        
        # 2. Convert to grayscale
        gray = image_pil.convert('L')
        
        # 3. Enhance contrast (helps with reflective surfaces)
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(2.0)
        
        # 4. Enhance sharpness (helps with small text)
        enhancer = ImageEnhance.Sharpness(gray)
        gray = enhancer.enhance(2.0)
        
        # 5. Apply adaptive thresholding using numpy
        img_array = np.array(gray)
        
        # Simple adaptive threshold: compare each pixel to local mean
        from PIL import ImageFilter
        blurred = gray.filter(ImageFilter.GaussianBlur(radius=11))
        blurred_array = np.array(blurred)
        
        # Threshold: pixel is white if brighter than local average - offset
        offset = 10
        binary_array = np.where(img_array > blurred_array - offset, 255, 0).astype(np.uint8)
        binary_img = Image.fromarray(binary_array, mode='L')
        
        # 6. Denoise with median filter
        binary_img = binary_img.filter(ImageFilter.MedianFilter(size=3))
        
        # 7. Slight dilation to connect broken characters
        binary_img = binary_img.filter(ImageFilter.MaxFilter(size=3))
        
        return binary_img
        
    except Exception as e:
        logger.warning(f"Image preprocessing failed: {e}, using original")
        return image_pil.convert('L') if image_pil.mode != 'L' else image_pil


def preprocess_with_opencv(image_pil):
    """
    OpenCV-based preprocessing for medicine strip images.
    Provides better results for reflective/metallic surfaces.
    """
    import cv2
    import numpy as np
    from PIL import Image
    
    # Convert PIL to OpenCV format
    if image_pil.mode != 'RGB':
        image_pil = image_pil.convert('RGB')
    
    img = np.array(image_pil)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    
    height, width = img.shape[:2]
    logger.info(f"OpenCV preprocessing: {width}x{height}")
    
    # 1. Resize if too small
    min_dimension = 1500
    if width < min_dimension or height < min_dimension:
        scale = max(min_dimension / width, min_dimension / height)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        logger.info(f"Resized to: {img.shape[1]}x{img.shape[0]}")
    
    # 2. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 3. Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    # This is excellent for handling reflective surfaces and uneven lighting
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # 4. Denoise while preserving edges
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # 5. Sharpen the image
    kernel_sharpen = np.array([[-1, -1, -1],
                               [-1,  9, -1],
                               [-1, -1, -1]])
    gray = cv2.filter2D(gray, -1, kernel_sharpen)
    
    # 6. Apply adaptive thresholding (better for varying lighting on medicine strips)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 31, 10
    )
    
    # 7. Morphological operations to clean up
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    # 8. Remove small noise
    binary = cv2.medianBlur(binary, 3)
    
    # Convert back to PIL
    result = Image.fromarray(binary)
    logger.info("OpenCV preprocessing complete")
    
    return result


def preprocess_for_rotated_text(image_pil):
    """
    Special preprocessing for detecting rotated/vertical text on medicine strips.
    """
    import numpy as np
    from PIL import Image, ImageEnhance
    
    try:
        import cv2
        
        # Convert to OpenCV format
        if image_pil.mode != 'RGB':
            image_pil = image_pil.convert('RGB')
        
        img = np.array(image_pil)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply edge detection to find text regions
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # Detect lines using Hough transform
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, 
                                minLineLength=50, maxLineGap=10)
        
        if lines is not None:
            # Calculate dominant angle
            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
                angles.append(angle)
            
            if angles:
                # Find the most common angle
                median_angle = np.median(angles)
                
                # If text is significantly rotated, correct it
                if abs(median_angle) > 5 and abs(median_angle) < 85:
                    logger.info(f"Detected rotation angle: {median_angle:.1f}°")
                    
                    # Rotate image to correct
                    center = (img.shape[1] // 2, img.shape[0] // 2)
                    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                    rotated = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]),
                                            flags=cv2.INTER_CUBIC,
                                            borderMode=cv2.BORDER_REPLICATE)
                    
                    return Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))
        
        return image_pil
        
    except ImportError:
        return image_pil
    except Exception as e:
        logger.warning(f"Rotation detection failed: {e}")
        return image_pil


def tesseract_extract_text(image_content):
    """Extract text using Tesseract OCR with advanced preprocessing for medicine strips"""
    try:
        if not TESSERACT_AVAILABLE:
            logger.warning(f"Tesseract not available (TESSERACT_AVAILABLE={TESSERACT_AVAILABLE})")
            return None
        
        from io import BytesIO
        from PIL import Image
        
        logger.info(f"Using Tesseract at: {TESSERACT_PATH}")
        
        # Open image from bytes
        try:
            image_pil = Image.open(BytesIO(image_content))
            logger.info(f"Image opened: {image_pil.size}, mode: {image_pil.mode}")
        except Exception as img_err:
            logger.error(f"Tesseract OCR: failed to open image: {img_err}")
            return None
        
        all_texts = []
        
        # Strategy 1: Preprocessed image with custom config for medicine strips
        logger.info("Running Tesseract OCR with preprocessing...")
        try:
            preprocessed = preprocess_medicine_strip_image(image_pil)
            
            # Custom Tesseract config for medicine strips
            # PSM 6: Assume a single uniform block of text
            # PSM 11: Sparse text - find as much text as possible
            # PSM 3: Fully automatic page segmentation (default)
            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789./-:₹Rs '
            
            text1 = pytesseract.image_to_string(preprocessed, config=custom_config)
            if text1.strip():
                all_texts.append(text1.strip())
                logger.info(f"Preprocessed OCR: {len(text1)} chars")
        except Exception as e:
            logger.warning(f"Preprocessed OCR failed: {e}")
        
        # Strategy 2: Original image with sparse text mode (catches rotated text)
        logger.info("Running Tesseract OCR on original (sparse mode)...")
        try:
            if image_pil.mode != 'RGB':
                image_rgb = image_pil.convert('RGB')
            else:
                image_rgb = image_pil
            
            # PSM 11: Sparse text - good for medicine strips with scattered text
            sparse_config = r'--oem 3 --psm 11'
            text2 = pytesseract.image_to_string(image_rgb, config=sparse_config)
            if text2.strip():
                all_texts.append(text2.strip())
                logger.info(f"Sparse mode OCR: {len(text2)} chars")
        except Exception as e:
            logger.warning(f"Sparse mode OCR failed: {e}")
        
        # Strategy 3: Try with different orientations (medicine strips often have vertical text)
        logger.info("Running Tesseract OCR with rotation detection...")
        try:
            from PIL import Image
            
            # First try automatic rotation detection
            try:
                auto_rotated = preprocess_for_rotated_text(image_pil)
                if auto_rotated != image_pil:
                    text_auto = pytesseract.image_to_string(auto_rotated, config='--oem 3 --psm 6')
                    if text_auto.strip() and len(text_auto.strip()) > 20:
                        all_texts.append(text_auto.strip())
                        logger.info(f"Auto-rotated OCR: {len(text_auto)} chars")
            except Exception as e:
                logger.warning(f"Auto rotation failed: {e}")
            
            # Try 90-degree rotations for vertical text
            for angle in [90, 270]:
                rotated = image_pil.rotate(angle, expand=True)
                if rotated.mode != 'RGB':
                    rotated = rotated.convert('RGB')
                
                text_rot = pytesseract.image_to_string(rotated, config='--oem 3 --psm 6')
                if text_rot.strip() and len(text_rot.strip()) > 20:
                    all_texts.append(text_rot.strip())
                    logger.info(f"Rotated {angle}° OCR: {len(text_rot)} chars")
        except Exception as e:
            logger.warning(f"Rotation OCR failed: {e}")
        
        # Strategy 4: High contrast grayscale
        logger.info("Running Tesseract OCR with high contrast...")
        try:
            from PIL import ImageEnhance
            
            gray = image_pil.convert('L')
            enhancer = ImageEnhance.Contrast(gray)
            high_contrast = enhancer.enhance(3.0)
            
            text3 = pytesseract.image_to_string(high_contrast, config='--oem 3 --psm 3')
            if text3.strip():
                all_texts.append(text3.strip())
                logger.info(f"High contrast OCR: {len(text3)} chars")
        except Exception as e:
            logger.warning(f"High contrast OCR failed: {e}")
        
        # Combine all extracted texts, removing duplicates
        if all_texts:
            # Merge texts, keeping unique lines
            seen_lines = set()
            merged_lines = []
            for text in all_texts:
                for line in text.split('\n'):
                    line_clean = line.strip()
                    if line_clean and line_clean.lower() not in seen_lines:
                        seen_lines.add(line_clean.lower())
                        merged_lines.append(line_clean)
            
            combined_text = '\n'.join(merged_lines)
            logger.info(f"Tesseract OCR extracted {len(combined_text)} total characters from {len(merged_lines)} unique lines")
            return combined_text
        else:
            logger.warning("Tesseract OCR returned empty text from all strategies")
            return None
            
    except Exception as e:
        logger.error(f"Tesseract OCR error: {e}")
        return None

def ocr_extract_text(image_content):
    """Try OCR methods in order: Tesseract (free) -> Gemini -> Google Vision"""
    logger.info(f"=== OCR START === Tesseract={TESSERACT_AVAILABLE}, Gemini={GEMINI_AVAILABLE}")
    
    # 1. Try Tesseract first (free, offline, no API key needed)
    if TESSERACT_AVAILABLE:
        logger.info("Attempting OCR with Tesseract (free, offline)...")
        text = tesseract_extract_text(image_content)
        if text:
            logger.info("Tesseract OCR successful")
            return text
        logger.warning("Tesseract OCR failed, trying other methods...")
    
    # 2. Try Gemini if available
    try:
        gemini_key_present = bool(os.environ.get('GEMINI_API_KEY') or GEMINI_API_KEY_FALLBACK)
    except Exception:
        gemini_key_present = False

    if GEMINI_AVAILABLE and gemini_key_present:
        logger.info("Attempting OCR with Gemini...")
        text = gemini_extract_text(image_content)
        if text:
            logger.info("Gemini OCR successful")
            return text
        logger.warning("Gemini OCR failed, trying Google Vision...")

    # 3. Try Google Vision as last resort
    try:
        logger.info("Attempting OCR with Google Vision...")
        image = vision.Image(content=image_content)
        response = global_vision_client.text_detection(image=image)
        texts = response.text_annotations
        if texts:
            logger.info("Google Vision OCR successful")
            return texts[0].description
        logger.warning("Vision OCR returned no text")
    except Exception as e:
        if is_billing_disabled_error(e):
            logger.error("Vision OCR billing disabled.")
        else:
            logger.error(f"Vision OCR error: {e}")

    # 4. Final fallback to Gemini again (in case it wasn't tried)
    if GEMINI_AVAILABLE and gemini_key_present:
        text = gemini_extract_text(image_content)
        if text:
            return text
    
    logger.error("All OCR methods failed")
    return None

def extract_fields_with_gemini_from_text(full_text):
    """Use Gemini to extract structured fields from OCR text. Returns dict or None."""
    try:
        if not GEMINI_AVAILABLE:
            return None
        gemini_api_key = os.environ.get('GEMINI_API_KEY') or GEMINI_API_KEY_FALLBACK
        if not gemini_api_key:
            return None
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        # Initialize a fast model
        model = None
        for name in ['models/gemini-2.0-flash', 'models/gemini-2.5-flash']:
            try:
                model = genai.GenerativeModel(name)
                break
            except Exception:
                continue
        if model is None:
            return None
        prompt = """You are analyzing OCR text from an Indian medicine strip/blister pack.

Extract these fields from the text:

1. brand: The PRODUCT/BRAND NAME (the prominent name, NOT generic drug names)
   - Look for: BIFILAC, O2, Dolo-650, RABEMI-DSR, Crocin, Pan 40, etc.
   - IGNORE generic names like "Paracetamol Tablets IP", "Ofloxacin & Ornidazole"

2. dosage: Medicine strength (numbers with mg/mcg/g)
   - Examples: "650 mg", "200 mg + 500 mg", "20 mg + 30 mg"

3. batch_number: Alphanumeric code after "B.No.", "Batch No.", "L.No."
   - Examples: "ALA306", "E40001", "RC-071022", "D0983759"

4. manufacture_date: Date after "MFG.", "MFD.", "Mfg.Dt."
   - Return EXACTLY as found: "10/2023", "JAN.24", "AUG.2024"

5. expiry_date: Date after "EXP.", "Exp.Dt.", "Use Before"
   - Return EXACTLY as found: "09/2025", "DEC.26", "JUL.2028"

6. manufacturer: Company name after "Mfd.by", "Manufactured by"
   - Examples: "Micro Labs", "Meyer Organics", "TOA Pharmaceuticals"

7. mrp: Price number after "MRP", "M.R.P.", "Rs."
   - Return ONLY the number: "140.00", "189.00", "35.70"

OCR TEXT TO ANALYZE:
\"\"\"
""" + full_text + """
\"\"\"

Return ONLY this JSON (no other text):
{"brand": "", "dosage": "", "batch_number": "", "manufacture_date": "", "expiry_date": "", "manufacturer": "", "mrp": ""}

Use "" for fields not found."""
        resp = model.generate_content(prompt)
        text = (resp.text or '').strip()
        text = text.replace('```json', '').replace('```', '').strip()
        logger.info(f"Gemini text extraction response: {text[:300]}")
        import json as _json
        try:
            data = _json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    data = _json.loads(m.group(0))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    return None
        return None
    except Exception as e:
        logger.error(f"Gemini text extraction error: {e}")
        return None

# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET'])
def landing_page():
    if 'user_type' in session:
        return redirect(url_for('index'))
    return render_template('landing.html')

@app.route('/login/owner', methods=['GET', 'POST'])
def login_owner():
    error = None
    if request.method == 'POST':
        name = request.form.get('name')
        secret = request.form.get('secret')
        if secret == '1111':
            session['logged_in'] = True
            session['user_type'] = 'owner'
            session['user_name'] = name
            return redirect(url_for('index'))
        else:
            error = 'Invalid secret code.'
    return render_template('login.html', error=error)

@app.route('/login/user', methods=['GET', 'POST'])
def login_user():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Allow any username and password for user login
        if username and password:
            session['logged_in'] = True
            session['user_type'] = 'user'
            session['user_name'] = username
            return redirect(url_for('index'))
        else:
            error = 'Please enter both username and password.'
    return render_template('user_login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing_page'))

@app.route('/chatbot', methods=['GET'])
def chatbot():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('chatbot.html')

@app.route('/bmi', methods=['GET', 'POST'])
def bmi_calculator():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))

    bmi_result = None
    error_message = None
    gender = None
    weight = None
    height = None

    if request.method == 'POST':
        try:
            gender = request.form.get('gender')
            weight = float(request.form.get('weight'))
            height = float(request.form.get('height'))

            if weight <= 0 or height <= 0:
                error_message = "Weight and height must be positive numbers."
            else:
                height_m = height / 100  # Convert cm to meters
                bmi = weight / (height_m ** 2)
                
                category = ""
                if bmi < 18.5:
                    category = "Underweight"
                elif 18.5 <= bmi < 25:
                    category = "Normal weight"
                elif 25 <= bmi < 30:
                    category = "Overweight"
                elif 30 <= bmi < 35:
                    category = "Obesity (Class I)"
                elif 35 <= bmi < 40:
                    category = "Obesity (Class II)"
                else:
                    category = "Extreme Obesity (Class III)"
                
                bmi_result = {
                    'bmi': f"{bmi:.2f}",
                    'category': category
                }

        except ValueError:
            error_message = "Invalid input. Please enter numeric values for weight and height."
        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"

    return render_template('bmi_calculator.html', bmi_result=bmi_result, error_message=error_message, weight=weight, height=height, gender=gender)

@app.route('/health_tips', methods=['GET'])
def health_tips():
    if not session.get('logged_in'):
        return redirect(url_for('landing_page'))
    return render_template('health_tips.html')

# ─── User Feature Pages (no chatbot) ──────────────────────────────────────────
@app.route('/user/health-advice', methods=['GET'])
def health_advice_page():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('health_advice.html')

@app.route('/user/medicine-info', methods=['GET'])
def medicine_info_page():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('medicine_info_page.html')

@app.route('/user/availability-check', methods=['GET'])
def availability_check_page():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('availability_check_page.html')

@app.route('/user/upload-prescription', methods=['GET'])
def upload_prescription_page():
    if not session.get('logged_in') or session.get('user_type') == 'owner':
        return redirect(url_for('landing_page'))
    return render_template('upload_prescription_page.html')

@app.route('/api/suggest', methods=['POST'])
def suggest():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    query = request.json.get('query', '').strip()
    if not query:
        return jsonify({'suggestions': []})
    
    suggestions = get_medicine_suggestions(query)
    return jsonify({'suggestions': suggestions})

@app.route('/api/health', methods=['POST'])
def health_advice():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        condition = request.json.get('query', '').strip()
        if not condition:
            return jsonify({'response': 'Please provide a health condition.'}), 400

        suggested_medicines = get_health_suggestions(condition)

        response_message = ""
        if suggested_medicines:
            # Ensure full HTML formatting with inline styles for ul and li for guaranteed rendering
            response_message = f"For <strong>{condition}</strong>, you might consider:<br><ul style=\"list-style: disc; margin-left: 20px; padding-left: 0; margin-top: 10px; text-align: left;\">"
            for med in suggested_medicines:
                response_message += f"<li style=\"margin-bottom: 5px; padding-left: 5px;\"><strong>{med['name']}</strong><br>Uses: {med['uses']}<br>Side Effects: {med['side_effects']}</li>"
            response_message += "</ul>"
        else:
            response_message = f"I don't have specific medicine suggestions for \"{condition}\" at the moment. Please consult a doctor."

        return jsonify({'response': response_message})

    except Exception as e:
        print(f"Error in /api/health: {e}")
        # traceback.print_exc() # Uncomment for debugging
        return jsonify({'response': 'Sorry, I encountered an error. Please try again.'}), 500

@app.route('/api/medicine-info', methods=['POST'])
def medicine_info():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        medicine_name = request.json.get('query', '').strip()
        if not medicine_name:
            return jsonify({'response': 'Please provide a medicine name.'}), 400

        # Search for medicine info case-insensitively
        found_medicine = None
        for name, info in MEDICINE_INFO.items():
            if name.lower() == medicine_name.lower():
                found_medicine = info
                found_medicine['name'] = name  # Store original name for display
                break

        response_message = ""
        if found_medicine:
            response_message = f"Information for <strong>{found_medicine['name']}</strong>:<br>"
            response_message += f"<div class=\"medicine-details\">"
            response_message += f"<p class=\"detail-item\"><strong>Uses:</strong> {found_medicine['uses']}</p>"
            response_message += f"<p class=\"detail-item\"><strong>Side Effects:</strong> {found_medicine['side_effects']}</p>"
            response_message += f"<p class=\"detail-item\"><strong>Dosage:</strong> {found_medicine['dosage']}</p>"
            response_message += "</div>"
        else:
            response_message = f"Sorry, I could not find information for \"{medicine_name}\". Please check the spelling or try another medicine."

        return jsonify({'response': response_message})

    except Exception as e:
        print(f"Error in /api/medicine-info: {e}")
        # traceback.print_exc() # Uncomment for debugging
        return jsonify({'response': 'Sorry, I encountered an error. Please try again.'}), 500

@app.route('/api/get_medicine_names')
def get_medicine_names():
    medicine_names = [med.medicine_name for med in Medicine.query.with_entities(Medicine.medicine_name).distinct().all()]
    return jsonify({'medicine_names': medicine_names})

@app.route('/api/check_medicine_availability', methods=['POST'])
def check_medicine_availability():
    data = request.json
    medicine_name = data.get('medicine_name', '')
    requested_quantity = data.get('quantity', 0)

    medicine = Medicine.query.filter(Medicine.medicine_name.ilike(medicine_name)).first()
    
    # Store the enquiry in database
    if session.get('user_type') == 'user':
        enquiry = MedicineEnquiry(
            medicine_name=medicine_name,
            quantity=requested_quantity,
            user_name=session.get('user_name', 'Anonymous')
        )
        db.session.add(enquiry)
        db.session.commit()
    
    response_message = ""
    if medicine:
        if medicine.quantity >= requested_quantity:
            total_price = medicine.price_per_unit * requested_quantity
            response_message = f"Yes, {medicine.medicine_name} is available. Price for {requested_quantity} units: ₹{{:.2f}}."
            response_message = response_message.format(total_price)
        else:
            response_message = f"Sorry, only {medicine.quantity} units of {medicine.medicine_name} are available in stock."
    else:
        response_message = f"Sorry, {medicine_name} is not found in our database."

    return jsonify({'response': response_message})

def check_medicine_availability_in_db(medicine_name):
    """Helper function to check medicine availability in database"""
    # Clean the medicine name
    clean_name = medicine_name.strip()
    
    # Try exact match first (case-insensitive)
    medicine = Medicine.query.filter(Medicine.medicine_name.ilike(clean_name)).first()
    
    # If not found, try partial match
    if not medicine:
        medicines = Medicine.query.filter(Medicine.medicine_name.ilike(f'%{clean_name}%')).all()
        if medicines:
            medicine = medicines[0]  # Take the first match
    
    # If still not found, try matching without numbers/dosage
    if not medicine:
        # Remove numbers and common suffixes
        base_name = re.sub(r'[\s\-]*\d+.*$', '', clean_name).strip()
        if base_name and base_name != clean_name:
            medicine = Medicine.query.filter(Medicine.medicine_name.ilike(f'%{base_name}%')).first()
    
    # Try common name mappings
    if not medicine:
        name_mappings = {
            'paracetamol': 'Paracetamol',
            'ondem': 'Ondem',
            'ondansetron': 'Ondem',
            'dolo': 'Dolo 650',
            'dolo-650': 'Dolo 650',
            'dolo 650': 'Dolo 650',
            'crocin': 'Paracetamol',
            'calpol': 'Calpol',
            'pan': 'Pantoprazole',
            'pan-40': 'Pantoprazole',
            'pan 40': 'Pantoprazole',
        }
        mapped_name = name_mappings.get(clean_name.lower())
        if mapped_name:
            medicine = Medicine.query.filter(Medicine.medicine_name.ilike(mapped_name)).first()
    
    if medicine:
        return {
            'available': True,
            'name': medicine.medicine_name,
            'quantity': medicine.quantity,
            'price': medicine.price_per_unit
        }
    return {
        'available': False,
        'name': medicine_name,
        'quantity': 0,
        'price': 0.0
    }

def extract_medicines_with_gemini(image_content):
    """Extract medicine names from prescription image using Gemini API"""
    try:
        if not GEMINI_AVAILABLE:
            logger.error("Gemini API not available. Please install google-generativeai")
            return None
        
        # Initialize Gemini API - try environment variable first, then fallback
        gemini_api_key = os.environ.get('GEMINI_API_KEY') or GEMINI_API_KEY_FALLBACK
        if not gemini_api_key:
            logger.warning("GEMINI_API_KEY not found in environment or fallback. Please set it.")
            return None
        
        logger.info(f"Using Gemini API key (starts with: {gemini_api_key[:10]}...)")
        
        genai.configure(api_key=gemini_api_key)
        # Try to find available models - prioritize newer models
        model = None
        
        # First, try to see what models are available
        try:
            available_models = [m.name for m in genai.list_models()]
            logger.info(f"Available models: {available_models[:10]}")
            
            # Prioritize flash models (faster) and stable versions
            preferred_models = [
                'models/gemini-2.0-flash',
                'models/gemini-2.5-flash',
                'models/gemini-2.5-pro',
                'models/gemini-2.0-flash-001',
            ]
            
            # Try preferred models first
            for preferred in preferred_models:
                if preferred in available_models:
                    try:
                        model = genai.GenerativeModel(preferred)
                        logger.info(f"Successfully initialized preferred model: {preferred}")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to initialize {preferred}: {str(e)}")
                        continue
            
            # If preferred didn't work, try any gemini model
            if model is None:
                for available_model in available_models:
                    if 'gemini' in available_model.lower() and 'embedding' not in available_model.lower():
                        try:
                            model = genai.GenerativeModel(available_model)
                            logger.info(f"Successfully initialized model: {available_model}")
                            break
                        except Exception as e:
                            logger.warning(f"Failed to initialize {available_model}: {str(e)}")
                            continue
        except Exception as list_error:
            logger.warning(f"Could not list models: {str(list_error)}")
            # Fallback to known working models
            fallback_models = ['models/gemini-2.0-flash', 'models/gemini-2.5-flash']
            for fallback in fallback_models:
                try:
                    model = genai.GenerativeModel(fallback)
                    logger.info(f"Successfully initialized fallback model: {fallback}")
                    break
                except Exception:
                    continue
        
        if model is None:
            raise Exception("Could not initialize any Gemini model. Please check your API key has access to Gemini models.")
        
        # Use Gemini to directly analyze the image (no need for Vision API - it requires billing)
        # Gemini can process images directly
        import PIL.Image
        from io import BytesIO
        
        try:
            # Convert image content to PIL Image
            image_pil = PIL.Image.open(BytesIO(image_content))
            logger.info(f"Image opened successfully: {image_pil.size}, mode: {image_pil.mode}")
        except Exception as img_error:
            logger.error(f"Failed to open image: {str(img_error)}")
            raise Exception(f"Could not process image: {str(img_error)}")
        
        # Use Gemini to extract medicine names directly from the image
        extraction_prompt = """You are analyzing a doctor's prescription image. Your task is to extract ALL medicine names from this prescription.

LOOK FOR:
- Medicine names written after "Rx:" 
- Medicine names in CAPITAL LETTERS like PARACETAMOL, ONDEM, DOLO
- Medicine names with dosages like "Paracetamol 650mg", "Ondem 4mg"
- Brand names like Dolo-650, Calpol, Crocin, Combiflam

COMMON MEDICINES TO LOOK FOR:
Paracetamol, Ondem, Dolo, Crocin, Combiflam, Brufen, Pantoprazole, Omez, Cetrizine, Amoxicillin, Azithromycin, Metformin, etc.

INSTRUCTIONS:
1. Read ALL text in the image carefully
2. Identify medicine names (ignore dosage like mg, ml)
3. Return ONLY the medicine names as a JSON array

OUTPUT FORMAT - Return ONLY this JSON array (no other text):
["Medicine1", "Medicine2"]

Example outputs:
["Paracetamol", "Ondem"]
["Dolo-650", "Pantoprazole", "Cetrizine"]

If you see PARACETAMOL and ONDEM in the image, return: ["Paracetamol", "Ondem"]"""
        
        logger.info("Sending image directly to Gemini for analysis...")
        try:
            gemini_response = model.generate_content([extraction_prompt, image_pil])
            response_text = gemini_response.text.strip()
            logger.info(f"Gemini API response received (length: {len(response_text)})")
        except Exception as api_error:
            logger.error(f"Gemini API call failed: {str(api_error)}", exc_info=True)
            raise  # Re-raise to be caught by outer exception handler
        
        # Clean the response to extract JSON
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        # Parse JSON
        try:
            medicines = json.loads(response_text)
            if isinstance(medicines, list):
                return medicines
            else:
                return []
        except json.JSONDecodeError:
            # Try to extract array from text
            match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if match:
                try:
                    medicines = json.loads(match.group(0))
                    return medicines if isinstance(medicines, list) else []
                except:
                    pass
            logger.error(f"Failed to parse Gemini response: {response_text}")
            return []
            
    except Exception as e:
        error_details = str(e)
        logger.error(f"Error extracting medicines with Gemini: {error_details}", exc_info=True)
        import traceback
        full_traceback = traceback.format_exc()
        logger.error(f"Full traceback:\n{full_traceback}")
        
        # Check for common errors
        if "API key" in error_details or "authentication" in error_details.lower():
            logger.error("Possible API key authentication issue")
        elif "quota" in error_details.lower() or "limit" in error_details.lower():
            logger.error("Possible API quota/limit exceeded")
        elif "network" in error_details.lower() or "connection" in error_details.lower():
            logger.error("Possible network/connection issue")
        
        return None

def extract_medicines_with_chatgpt(image_content):
    """Extract medicine names from prescription image using ChatGPT API"""
    try:
        if not OPENAI_AVAILABLE:
            logger.error("OpenAI API not available. Please install openai")
            return None
        
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        if not openai_api_key:
            logger.warning("OPENAI_API_KEY not found in environment. Please set it.")
            return None
        
        openai.api_key = openai_api_key
        
        # Convert image to base64
        image_base64 = base64.b64encode(image_content).decode('utf-8')
        
        # First, use Google Vision API to extract text (as fallback)
        image = vision.Image(content=image_content)
        response = global_vision_client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts:
            logger.warning("No text detected in prescription image")
            return []
        
        prescription_text = texts[0].description
        
        # Use ChatGPT to extract medicine names
        client = openai.OpenAI(api_key=openai_api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Using cheaper model, can switch to gpt-4o for better accuracy
            messages=[
                {
                    "role": "system",
                    "content": "You are a medical assistant. Extract medicine names from prescription text. Return ONLY a JSON array of medicine names."
                },
                {
                    "role": "user",
                    "content": f"""From the following prescription text, extract all medicine names. 
                    Return ONLY a JSON array of medicine names. Format: ["Medicine Name 1", "Medicine Name 2", ...]
                    If no medicines are found, return an empty array [].
                    Do not include any other text, only the JSON array.
                    
                    Prescription text:
                    {prescription_text}
                    """
                }
            ]
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Clean the response to extract JSON
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        
        # Parse JSON
        try:
            # Try to parse as direct array first
            medicines = json.loads(response_text)
            if isinstance(medicines, list):
                return medicines
            
            # If it's a dict, try to extract array
            if isinstance(medicines, dict):
                medicines = medicines.get('medicines', medicines.get('medicine_names', []))
                if isinstance(medicines, list):
                    return medicines
            
            return []
        except json.JSONDecodeError:
            # Try to extract array from text using regex
            match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if match:
                try:
                    medicines = json.loads(match.group(0))
                    return medicines if isinstance(medicines, list) else []
                except:
                    pass
            logger.error(f"Failed to parse ChatGPT response: {response_text}")
            return []
            
    except Exception as e:
        logger.error(f"Error extracting medicines with ChatGPT: {str(e)}")
        return None

def extract_medicines_with_tesseract(image_content):
    """Extract medicine names from prescription using FREE Tesseract OCR"""
    try:
        if not TESSERACT_AVAILABLE:
            logger.error("Tesseract OCR not available")
            return None
        
        from io import BytesIO
        from PIL import Image, ImageEnhance, ImageFilter
        
        # Open image
        try:
            image_pil = Image.open(BytesIO(image_content))
            logger.info(f"Prescription image opened: {image_pil.size}")
        except Exception as e:
            logger.error(f"Failed to open prescription image: {e}")
            return None
        
        # Preprocess image for better OCR
        if image_pil.mode != 'RGB':
            image_pil = image_pil.convert('RGB')
        
        # Resize if too small
        width, height = image_pil.size
        if width < 1500:
            scale = 1500 / width
            image_pil = image_pil.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
            logger.info(f"Resized image to: {image_pil.size}")
        
        all_texts = []
        
        # Strategy 1: High contrast grayscale
        logger.info("Running Tesseract OCR Strategy 1: High contrast...")
        gray = image_pil.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(2.5)
        enhancer = ImageEnhance.Sharpness(gray)
        gray = enhancer.enhance(2.0)
        
        text1 = pytesseract.image_to_string(gray, config='--oem 3 --psm 6')
        if text1.strip():
            all_texts.append(text1)
            logger.info(f"Strategy 1 extracted: {len(text1)} chars")
        
        # Strategy 2: Different PSM mode (sparse text)
        logger.info("Running Tesseract OCR Strategy 2: Sparse text mode...")
        text2 = pytesseract.image_to_string(gray, config='--oem 3 --psm 11')
        if text2.strip():
            all_texts.append(text2)
            logger.info(f"Strategy 2 extracted: {len(text2)} chars")
        
        # Strategy 3: Auto page segmentation
        logger.info("Running Tesseract OCR Strategy 3: Auto segmentation...")
        text3 = pytesseract.image_to_string(gray, config='--oem 3 --psm 3')
        if text3.strip():
            all_texts.append(text3)
            logger.info(f"Strategy 3 extracted: {len(text3)} chars")
        
        # Strategy 4: Original image (sometimes works better)
        logger.info("Running Tesseract OCR Strategy 4: Original image...")
        text4 = pytesseract.image_to_string(image_pil, config='--oem 3 --psm 6')
        if text4.strip():
            all_texts.append(text4)
            logger.info(f"Strategy 4 extracted: {len(text4)} chars")
        
        # Combine all extracted texts
        combined_text = '\n'.join(all_texts)
        
        if not combined_text.strip():
            logger.warning("Tesseract returned empty text from all strategies")
            return []
        
        logger.info(f"Tesseract combined text ({len(combined_text)} chars): {combined_text[:800]}...")
        
        # Extract medicine names from text using patterns
        medicines = extract_medicine_names_from_text(combined_text)
        logger.info(f"Extracted {len(medicines)} medicines from prescription: {medicines}")
        return medicines
        
    except Exception as e:
        logger.error(f"Tesseract prescription extraction error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def extract_medicine_names_from_text(text):
    """Extract medicine names from OCR text using pattern matching"""
    medicines = []
    
    # Common medicine name patterns
    # Pattern 1: Words starting with capital letter followed by numbers (like Dolo 650, Pan 40)
    pattern1 = r'\b([A-Z][a-z]+(?:\s*[-]?\s*\d+)?)\b'
    
    # Pattern 2: All caps words (like BIFILAC, RABEMI-DSR, PARACETAMOL, ONDEM)
    pattern2 = r'\b([A-Z]{3,}(?:\s*[-]?\s*[A-Z0-9]+)?)\b'
    
    # Pattern 3: Common medicine suffixes
    medicine_suffixes = ['mg', 'mcg', 'ml', 'tab', 'cap', 'syrup', 'tablet', 'capsule', 'injection']
    
    # Known medicine database for matching - comprehensive list including all from MEDICINE_DB and MEDICINE_INFO
    known_medicines = [
        # From MEDICINE_DB and MEDICINE_INFO
        'Augmentin', 'Avil', 'Benadryl', 'Brufen', 'Bifilac', 'BIFILAC',
        'Cetrizine', 'Cetirizine', 'Combiflam', 'Calpol',
        'Dolo 650', 'Dolo-650', 'Domstal', 'Domperidone',
        'Eno', 'Electral',
        'Flexon', 'Fepanil',
        'Gelusil', 'Gaviscon',
        'Honitus', 'Hifenac',
        'Ibugesic', 'Iodex', 'Ibuprofen',
        'Junior Lanzol', 'Jiffy',
        'Ketorol', 'Ketanov',
        'Liv52', 'Limcee',
        'Meftal Spas', 'Metrogyl', 'Metronidazole',
        'Norflox', 'Nasivion',
        'Omez', 'Ondem', 'ONDEM', 'O2', 'Ofloxacin', 'Ornidazole', 'Ondansetron',
        'Paracetamol', 'PARACETAMOL', 'Pantoprazole',
        'Quadriderm', 'Quinidine',
        'Rantac', 'Revital', 'Rabemi-DSR', 'RABEMI-DSR', 'Rabeprazole',
        'Sinarest', 'Soframycin', 'Strepsils',
        'Thyronorm', 'Taxim-O',
        'Ulgel', 'Unienzyme',
        'Volini', 'Vicks',
        'Wikoryl', 'Wysolone',
        'Xarelto', 'Xone',
        'Yondelis', 'Yogurt Sachets',
        'Zyrtec', 'Zincovit',
        # Additional common medicines
        'Dolo', 'Crocin', 'Azithromycin', 'Azee', 'Zithromax', 'Amoxicillin', 'Mox',
        'Ciprofloxacin', 'Ciplox', 'Pan', 'Omeprazole', 'Rabemi',
        'Allegra', 'Montair', 'Montelukast',
        'Metformin', 'Glycomet', 'Glimepiride', 'Amaryl',
        'Atorvastatin', 'Atorva', 'Rosuvastatin', 'Crestor',
        'Amlodipine', 'Amlong', 'Telmisartan', 'Telma',
        'Flagyl', 'Ranitidine', 'Famotidine', 'Pepcid',
        'Diclofenac', 'Voveran', 'Aceclofenac', 'Zerodol',
        'Tramadol', 'Ultracet', 'Gabapentin', 'Gabapin',
        'Pregabalin', 'Lyrica', 'Pregalin',
        'Levothyroxine', 'Eltroxin',
        'Vitamin', 'Calcium', 'Iron', 'Folic', 'B12', 'D3',
        'Aspirin', 'Ecosprin', 'Clopidogrel', 'Plavix',
        'Atenolol', 'Metoprolol', 'Propranolol',
        'Losartan', 'Valsartan', 'Olmesartan',
        'Hydrochlorothiazide', 'Furosemide', 'Lasix',
        'Prednisolone', 'Dexamethasone',
        'Levofloxacin', 'Levoflox', 'Moxifloxacin',
        'Cefixime', 'Zifi', 'Cefpodoxime', 'Cephalexin',
        'Doxycycline', 'Tetracycline',
        'Fluconazole', 'Itraconazole',
        'Acyclovir', 'Valacyclovir', 'Emeset',
        'Alprazolam', 'Clonazepam', 'Lorazepam',
        'Sertraline', 'Escitalopram', 'Fluoxetine',
    ]
    
    # Standard name mappings
    standard_names = {
        'paracetamol': 'Paracetamol',
        'ondem': 'Ondem',
        'ondansetron': 'Ondem',
        'dolo': 'Dolo 650',
        'dolo 650': 'Dolo 650',
        'dolo-650': 'Dolo 650',
        'calpol': 'Calpol',
        'combiflam': 'Combiflam',
        'brufen': 'Brufen',
        'pantoprazole': 'Pantoprazole',
        'omez': 'Omez',
        'cetrizine': 'Cetrizine',
        'cetirizine': 'Cetrizine',
        'bifilac': 'Bifilac',
        'rabemi-dsr': 'Rabemi-DSR',
        'crocin': 'Paracetamol',
    }
    
    # Convert text to lines for processing
    lines = text.split('\n')
    full_text_lower = text.lower()
    
    logger.info(f"Searching for medicines in text ({len(text)} chars)")
    
    # PRIORITY 1: Direct search for specific medicine names using regex (handles OCR variations)
    # Look for PARACETAMOL variations
    paracetamol_patterns = [
        r'paracetamol',
        r'paracetam[o0]l',
        r'paracetam[o0][l1]',
        r'p[a@]r[a@]cet[a@]m[o0][l1]',
        r'parcetamol',
        r'paracetmol',
    ]
    for pattern in paracetamol_patterns:
        if re.search(pattern, full_text_lower):
            if 'Paracetamol' not in medicines:
                medicines.append('Paracetamol')
                logger.info(f"Found Paracetamol via pattern: {pattern}")
            break
    
    # Look for ONDEM variations
    ondem_patterns = [
        r'ondem',
        r'[o0]ndem',
        r'[o0]nd[e3]m',
        r'onderm',
    ]
    for pattern in ondem_patterns:
        if re.search(pattern, full_text_lower):
            if 'Ondem' not in medicines:
                medicines.append('Ondem')
                logger.info(f"Found Ondem via pattern: {pattern}")
            break
    
    # PRIORITY 2: Check for known medicines in the entire text (case-insensitive)
    for med in known_medicines:
        med_lower = med.lower()
        if med_lower in full_text_lower:
            # Found a known medicine - add the properly capitalized version
            standard_name = standard_names.get(med_lower, med)
            if standard_name not in medicines:
                medicines.append(standard_name)
                logger.info(f"Found known medicine: {standard_name}")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for known medicines in each line
        for med in known_medicines:
            if med.lower() in line.lower():
                # Extract the full medicine name with dosage if present
                pattern = rf'({re.escape(med)}[\s\-]*\d*(?:\s*mg|\s*mcg|\s*ml)?)'
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    clean_name = match.strip()
                    # Normalize the name
                    clean_name_lower = clean_name.lower().split()[0] if clean_name.split() else clean_name.lower()
                    standard_names = {
                        'paracetamol': 'Paracetamol',
                        'ondem': 'Ondem',
                        'dolo': 'Dolo 650',
                        'calpol': 'Calpol',
                    }
                    normalized = standard_names.get(clean_name_lower, clean_name)
                    if normalized and normalized not in medicines:
                        medicines.append(normalized)
        
        # Also try pattern matching for unknown medicines
        # Look for words followed by dosage numbers
        dosage_pattern = r'([A-Z][a-zA-Z\-]+)\s*(\d+)\s*(mg|mcg|ml|g)?'
        matches = re.findall(dosage_pattern, line)
        for match in matches:
            name = f"{match[0]} {match[1]}"
            if match[2]:
                name += f" {match[2]}"
            if name.strip() and name not in medicines:
                # Filter out common non-medicine words
                skip_words = ['the', 'and', 'for', 'with', 'take', 'daily', 'twice', 'once', 'after', 'before', 'food', 'meal', 'days', 'week', 'tablet', 'tablets', 'capsule', 'capsules', 'age', 'date', 'oct', 'nov', 'dec', 'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep']
                if match[0].lower() not in skip_words:
                    medicines.append(name.strip())
        
        # Also look for ALL CAPS words that might be medicine names (like PARACETAMOL, ONDEM)
        all_caps_pattern = r'\b([A-Z]{4,})\b'
        caps_matches = re.findall(all_caps_pattern, line)
        for caps_match in caps_matches:
            caps_lower = caps_match.lower()
            # Check if it's a known medicine
            for med in known_medicines:
                if med.lower() == caps_lower:
                    standard_names = {
                        'paracetamol': 'Paracetamol',
                        'ondem': 'Ondem',
                        'bifilac': 'Bifilac',
                    }
                    normalized = standard_names.get(caps_lower, med)
                    if normalized not in medicines:
                        medicines.append(normalized)
                        logger.info(f"Found ALL CAPS medicine: {normalized}")
                    break
    
    # Remove duplicates while preserving order
    seen = set()
    unique_medicines = []
    for med in medicines:
        med_lower = med.lower().split()[0] if med.split() else med.lower()  # Compare base name
        if med_lower not in seen:
            seen.add(med_lower)
            unique_medicines.append(med)
    
    logger.info(f"Final extracted medicines: {unique_medicines}")
    return unique_medicines


def extract_medicines_from_prescription(image_content):
    """Extract medicines from prescription - tries multiple methods"""
    logger.info("=" * 50)
    logger.info("EXTRACTING MEDICINES FROM PRESCRIPTION")
    logger.info("=" * 50)
    
    # METHOD 1: Try Gemini first (better accuracy for prescription images)
    gemini_key = os.environ.get('GEMINI_API_KEY') or GEMINI_API_KEY_FALLBACK
    if GEMINI_AVAILABLE and gemini_key:
        logger.info("Trying Gemini API for prescription analysis (best accuracy)...")
        try:
            medicines = extract_medicines_with_gemini(image_content)
            if medicines is not None and len(medicines) > 0:
                logger.info(f"Successfully extracted {len(medicines)} medicines with Gemini: {medicines}")
                return medicines
            elif medicines is not None:
                logger.info("Gemini found no medicines, trying other methods...")
        except Exception as e:
            logger.warning(f"Gemini extraction failed: {e}")
    else:
        logger.info(f"Gemini not available (GEMINI_AVAILABLE={GEMINI_AVAILABLE}, key_set={bool(gemini_key)})")
    
    # METHOD 2: Try Google Vision API (uses vision-key.json)
    logger.info("Trying Google Vision API for prescription OCR...")
    try:
        image = vision.Image(content=image_content)
        response = global_vision_client.text_detection(image=image)
        texts = response.text_annotations
        
        if texts:
            full_text = texts[0].description
            logger.info(f"Google Vision extracted text ({len(full_text)} chars): {full_text[:500]}...")
            medicines = extract_medicine_names_from_text(full_text)
            if medicines:
                logger.info(f"Successfully extracted {len(medicines)} medicines with Google Vision: {medicines}")
                return medicines
            else:
                logger.info("Google Vision found text but no medicines matched")
        else:
            logger.warning("Google Vision returned no text")
    except Exception as e:
        logger.warning(f"Google Vision extraction failed: {e}")
    
    # METHOD 3: Try FREE Tesseract OCR (no API key needed!)
    if TESSERACT_AVAILABLE:
        logger.info("Using FREE Tesseract OCR for prescription analysis...")
        try:
            medicines = extract_medicines_with_tesseract(image_content)
            if medicines is not None and len(medicines) > 0:
                logger.info(f"Successfully extracted {len(medicines)} medicines with Tesseract (FREE): {medicines}")
                return medicines
            elif medicines is not None:
                logger.info("Tesseract found no medicines, trying other methods...")
        except Exception as e:
            logger.warning(f"Tesseract extraction failed: {e}")
    else:
        logger.warning("Tesseract not available. Install from: https://github.com/UB-Mannheim/tesseract/wiki")
    
    # METHOD 4: Try ChatGPT if API key is available
    openai_key = os.environ.get('OPENAI_API_KEY')
    if OPENAI_AVAILABLE and openai_key:
        logger.info("Trying OpenAI API...")
        try:
            medicines = extract_medicines_with_chatgpt(image_content)
            if medicines is not None:
                logger.info(f"Successfully extracted {len(medicines)} medicines with ChatGPT: {medicines}")
                return medicines
        except Exception as e:
            logger.warning(f"ChatGPT extraction failed: {e}")
    
    # If we got here, no method found medicines
    logger.info("No medicines found in prescription (all methods tried)")
    return []
    
    # If nothing works, return error
    logger.error("No OCR method available. Please install Tesseract OCR (FREE): https://github.com/UB-Mannheim/tesseract/wiki")
    return None

@app.route('/api/debug_prescription', methods=['POST'])
def debug_prescription():
    """Debug endpoint to test prescription OCR"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        if 'prescription' not in request.files:
            return jsonify({'error': 'No prescription file provided'}), 400
        
        file = request.files['prescription']
        image_content = file.read()
        
        result = {
            'file_size': len(image_content),
            'tesseract_available': TESSERACT_AVAILABLE,
            'tesseract_path': TESSERACT_PATH,
            'gemini_available': GEMINI_AVAILABLE,
            'gemini_key_set': bool(os.environ.get('GEMINI_API_KEY') or GEMINI_API_KEY_FALLBACK),
        }
        
        # Try Google Vision
        try:
            image = vision.Image(content=image_content)
            response = global_vision_client.text_detection(image=image)
            texts = response.text_annotations
            if texts:
                result['vision_text'] = texts[0].description[:1000]
                result['vision_success'] = True
            else:
                result['vision_text'] = 'No text detected'
                result['vision_success'] = False
        except Exception as e:
            result['vision_error'] = str(e)
            result['vision_success'] = False
        
        # Try Tesseract
        if TESSERACT_AVAILABLE:
            try:
                from io import BytesIO
                from PIL import Image
                image_pil = Image.open(BytesIO(image_content))
                text = pytesseract.image_to_string(image_pil)
                result['tesseract_text'] = text[:1000] if text else 'No text detected'
                result['tesseract_success'] = bool(text.strip())
            except Exception as e:
                result['tesseract_error'] = str(e)
                result['tesseract_success'] = False
        
        # Try to extract medicines from any text we got
        combined_text = result.get('vision_text', '') + '\n' + result.get('tesseract_text', '')
        if combined_text.strip():
            medicines = extract_medicine_names_from_text(combined_text)
            result['extracted_medicines'] = medicines
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/test_api_key', methods=['GET'])
def test_api_key():
    """Test endpoint to check API key configuration"""
    gemini_key = os.environ.get('GEMINI_API_KEY') or GEMINI_API_KEY_FALLBACK
    openai_key = os.environ.get('OPENAI_API_KEY')
    
    result = {
        'GEMINI_AVAILABLE': GEMINI_AVAILABLE,
        'GEMINI_API_KEY_set': bool(gemini_key),
        'GEMINI_API_KEY_length': len(gemini_key) if gemini_key else 0,
        'GEMINI_API_KEY_preview': gemini_key[:10] + '...' if gemini_key else 'Not set',
        'OPENAI_AVAILABLE': OPENAI_AVAILABLE,
        'OPENAI_API_KEY_set': bool(openai_key),
        'using_fallback': not os.environ.get('GEMINI_API_KEY') and bool(GEMINI_API_KEY_FALLBACK)
    }
    
    # Try to actually call the API to test if it works
    if GEMINI_AVAILABLE and gemini_key:
        try:
            genai.configure(api_key=gemini_key)
            
            # First, try to list available models
            try:
                available_models = [m.name for m in genai.list_models()]
                result['available_models'] = available_models[:10]  # First 10 models
            except Exception as list_error:
                result['list_models_error'] = str(list_error)
            
            # Try available models - prioritize flash models
            preferred_models = [
                'models/gemini-2.0-flash',
                'models/gemini-2.5-flash',
                'models/gemini-2.5-pro',
                'models/gemini-2.0-flash-001',
            ]
            
            model_worked = False
            # First try preferred models from available list
            for model_name in preferred_models:
                if model_name in available_models:
                    try:
                        model = genai.GenerativeModel(model_name)
                        test_response = model.generate_content("Say 'API test successful'")
                        result['api_test'] = 'SUCCESS'
                        result['api_response'] = test_response.text[:100] if test_response.text else 'No response'
                        result['model_used'] = model_name
                        model_worked = True
                        break
                    except Exception as model_error:
                        result[f'model_{model_name.replace("/", "_")}_error'] = str(model_error)[:200]
                        continue
            
            # If preferred didn't work, try any gemini model
            if not model_worked:
                for model_name in available_models:
                    if 'gemini' in model_name.lower() and 'embedding' not in model_name.lower():
                        try:
                            model = genai.GenerativeModel(model_name)
                            test_response = model.generate_content("Say 'API test successful'")
                            result['api_test'] = 'SUCCESS'
                            result['api_response'] = test_response.text[:100] if test_response.text else 'No response'
                            result['model_used'] = model_name
                            model_worked = True
                            break
                        except Exception as model_error:
                            continue
            
            if not model_worked:
                result['api_test'] = 'FAILED'
                result['api_error'] = 'All available models failed. Check model_*_error fields above.'
                result['error_type'] = 'AllModelsFailed'
                
        except Exception as e:
            result['api_test'] = 'FAILED'
            result['api_error'] = str(e)
            result['error_type'] = type(e).__name__
    
    return jsonify(result)

def extract_medicines_with_vision_api(image_content):
    """Extract medicine names using Google Vision API OCR"""
    try:
        logger.info("Trying Google Vision API for prescription OCR...")
        image = vision.Image(content=image_content)
        response = global_vision_client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts:
            logger.warning("Google Vision returned no text")
            return None
        
        full_text = texts[0].description
        logger.info(f"Google Vision extracted text ({len(full_text)} chars): {full_text[:500]}...")
        
        # Extract medicine names from the text
        medicines = extract_medicine_names_from_text(full_text)
        logger.info(f"Extracted {len(medicines)} medicines from Vision API text: {medicines}")
        return medicines
        
    except Exception as e:
        logger.error(f"Google Vision API error: {e}")
        return None


@app.route('/api/analyze_prescription', methods=['POST'])
def analyze_prescription():
    """Analyze prescription image and check medicine availability"""
    logger.info("=" * 50)
    logger.info("PRESCRIPTION UPLOAD REQUEST RECEIVED")
    logger.info("=" * 50)
    
    if not session.get('logged_in'):
        logger.warning("Unauthorized request - user not logged in")
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        logger.info("Checking for prescription file...")
        if 'prescription' not in request.files:
            logger.error("No 'prescription' key in request.files")
            return jsonify({'error': 'No prescription file provided'}), 400
        
        file = request.files['prescription']
        logger.info(f"File received: {file.filename if file else 'None'}")
        
        if file.filename == '':
            logger.error("Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        # Read image content
        logger.info("Reading image content...")
        image_content = file.read()
        logger.info(f"Image content size: {len(image_content)} bytes")
        
        if not image_content:
            logger.error("Empty image content")
            return jsonify({'error': 'Could not read file content'}), 400
        
        # Extract medicines using available methods
        logger.info("Starting prescription analysis...")
        medicines_list = extract_medicines_from_prescription(image_content)
        logger.info(f"Primary extraction result: {medicines_list}")
        
        # If primary methods failed or returned empty, try Google Vision API
        if not medicines_list:
            logger.info("Primary methods returned empty, trying Google Vision API...")
            try:
                medicines_list = extract_medicines_with_vision_api(image_content)
                logger.info(f"Vision API extraction result: {medicines_list}")
            except Exception as ve:
                logger.warning(f"Vision API failed: {ve}")
        
        if medicines_list is None:
            # Check if Tesseract is available
            if not TESSERACT_AVAILABLE:
                error_msg = ('❌ Tesseract OCR not installed! Please install it (FREE):\n'
                           '1. Download from: https://github.com/UB-Mannheim/tesseract/wiki\n'
                           '2. Install to: C:\\Program Files\\Tesseract-OCR\\\n'
                           '3. Restart the Flask app')
                logger.error(error_msg)
                return jsonify({'error': error_msg}), 500
            
            error_msg = 'Failed to process prescription. Please try with a clearer image.'
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 500
        
        if not medicines_list:
            logger.info("No medicines found after all extraction attempts")
            return jsonify({'medicines': []})
        
        # Check availability for each medicine
        results = []
        for med_name in medicines_list:
            availability = check_medicine_availability_in_db(med_name)
            results.append({
                'name': availability['name'],
                'available': availability['available'],
                'quantity': availability['quantity'],
                'price': availability['price']
            })
        
        logger.info(f"Returning {len(results)} medicines: {results}")
        return jsonify({'medicines': results})
        
    except Exception as e:
        error_details = str(e)
        logger.error(f"Error analyzing prescription: {error_details}", exc_info=True)
        import traceback
        full_trace = traceback.format_exc()
        logger.error(f"Full traceback:\n{full_trace}")
        
        # Return more detailed error to user
        user_error = f'Error processing prescription: {error_details}'
        if len(error_details) > 200:
            user_error = error_details[:200] + "... (see Flask logs for full error)"
        
        return jsonify({'error': user_error}), 500

def post_process_extracted_data(brand, dosage, batch, mfd_date, exp_date, manufacturer, mrp_str, full_text):
    """
    Post-process and validate extracted medicine data.
    Applies specific corrections for known medicine patterns.
    """
    # Known medicine brand corrections
    brand_corrections = {
        # BIFILAC variations
        'bifilac': 'BIFILAC',
        'bifiiac': 'BIFILAC',
        'bifllac': 'BIFILAC',
        'bif1lac': 'BIFILAC',
        # O2 variations
        'o 2': 'O2',
        '02': 'O2',
        'oz': 'O2',
        # Dolo-650 variations
        'dolo 650': 'Dolo-650',
        'dolo650': 'Dolo-650',
        'dol0 650': 'Dolo-650',
        'dolo-65o': 'Dolo-650',
        # RABEMI-DSR variations
        'rabemi dsr': 'RABEMI-DSR',
        'rabemidsr': 'RABEMI-DSR',
        'rabemi-dsr': 'RABEMI-DSR',
    }
    
    # Try to correct brand name
    if brand:
        brand_lower = brand.lower().strip()
        if brand_lower in brand_corrections:
            brand = brand_corrections[brand_lower]
        # Check if brand contains known medicine names
        elif 'bifilac' in brand_lower:
            brand = 'BIFILAC'
        elif 'rabemi' in brand_lower and 'dsr' in brand_lower:
            brand = 'RABEMI-DSR'
        elif 'dolo' in brand_lower and '650' in brand_lower:
            brand = 'Dolo-650'
        elif brand_lower in ['o2', 'o 2', '02']:
            brand = 'O2'
    
    # If brand still not found, try to detect from full text
    if not brand and full_text:
        text_lower = full_text.lower()
        if 'bifilac' in text_lower:
            brand = 'BIFILAC'
        elif 'rabemi' in text_lower and 'dsr' in text_lower:
            brand = 'RABEMI-DSR'
        elif 'dolo' in text_lower and '650' in text_lower:
            brand = 'Dolo-650'
        elif 'ofloxacin' in text_lower and 'ornidazole' in text_lower:
            # O2 is Ofloxacin + Ornidazole combination
            brand = 'O2'
        elif 'paracetamol' in text_lower and '650' in text_lower:
            brand = 'Dolo-650'
        elif 'rabeprazole' in text_lower and 'domperidone' in text_lower:
            brand = 'RABEMI-DSR'
    
    # Manufacturer corrections
    manufacturer_corrections = {
        'toa': 'TOA Pharmaceuticals',
        'toa pharma': 'TOA Pharmaceuticals',
        'meyer': 'Meyer Organics',
        'meyer organics': 'Meyer Organics',
        'micro labs': 'Micro Labs',
        'microlabs': 'Micro Labs',
        'paalmi': 'Paalmi Pharmaceuticals',
        'renewed life': 'Renewed Life Sciences',
    }
    
    if manufacturer:
        mfr_lower = manufacturer.lower().strip()
        for key, value in manufacturer_corrections.items():
            if key in mfr_lower:
                manufacturer = value
                break
    
    # Try to detect manufacturer from full text if not found
    if not manufacturer and full_text:
        text_lower = full_text.lower()
        if 'toa' in text_lower and 'pharma' in text_lower:
            manufacturer = 'TOA Pharmaceuticals'
        elif 'meyer' in text_lower:
            manufacturer = 'Meyer Organics'
        elif 'micro labs' in text_lower or 'microlabs' in text_lower:
            manufacturer = 'Micro Labs'
        elif 'paalmi' in text_lower:
            manufacturer = 'Paalmi Pharmaceuticals'
        elif 'renewed life' in text_lower:
            manufacturer = 'Renewed Life Sciences'
    
    # Clean up dosage format
    if dosage:
        dosage = dosage.strip()
        # Standardize format: "200mg + 500mg" -> "200 mg + 500 mg"
        dosage = re.sub(r'(\d+)\s*(mg|mcg|g|ml)', r'\1 \2', dosage, flags=re.IGNORECASE)
    
    return brand, dosage, batch, mfd_date, exp_date, manufacturer, mrp_str


@app.route('/index', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        logger.info("POST request received for image upload")
        
        # Check if file is in request
        if 'image' not in request.files:
            logger.error("No 'image' in request.files")
            return render_template('index.html', error_message="❌ No file part in request")
        
        file = request.files['image']
        logger.info(f"File received: {file.filename if file else 'None'}")
        
        if not file or file.filename == '':
            logger.error("No selected file")
            return render_template('index.html', error_message="❌ No file selected")
        
        try:
            # Read the image
            logger.info("Reading image content")
            image_content = file.read()
            if not image_content:
                logger.error("No content read from file")
                return render_template('index.html', error_message="❌ Could not read file content")
            
            # Initialize variables
            brand = None
            dosage = None
            batch = None
            mfd_date = None
            exp_date = None
            manufacturer = None
            mrp_str = None
            full_text = ""
            
            # Filter out invalid brand names (generic descriptions)
            invalid_brand_patterns = [
                r"(?i)^each\s", r"(?i)^film\s", r"(?i)^coated", r"(?i)^tablet",
                r"(?i)^capsule", r"(?i)^contains", r"(?i)^information",
                r"(?i)^store", r"(?i)^keep", r"(?i)^protect", r"(?i)^the\s",
                r"(?i)^this\s", r"(?i)^for\s", r"(?i)^use\s"
            ]
            
            def is_valid_brand(val):
                if not val or not str(val).strip():
                    return False
                val = str(val).strip()
                for pattern in invalid_brand_patterns:
                    if re.match(pattern, val):
                        return False
                return True
            
            # METHOD 1: Try Gemini direct image extraction first (most accurate)
            logger.info("Attempting Gemini direct image extraction...")
            try:
                gem_direct = gemini_extract_fields_from_image(image_content)
                if gem_direct and isinstance(gem_direct, dict):
                    logger.info(f"Gemini direct extraction result: {gem_direct}")
                    
                    # Clean and validate each field
                    extracted_brand = clean_extracted_value(gem_direct.get('brand'), 'brand')
                    if extracted_brand and is_valid_brand(extracted_brand):
                        brand = extracted_brand
                    
                    dosage = clean_extracted_value(gem_direct.get('dosage'), 'text')
                    batch = clean_extracted_value(gem_direct.get('batch_number'), 'batch')
                    mfd_date = clean_extracted_value(gem_direct.get('manufacture_date'), 'date')
                    exp_date = clean_extracted_value(gem_direct.get('expiry_date'), 'date')
                    manufacturer = clean_extracted_value(gem_direct.get('manufacturer'), 'text')
                    mrp_str = clean_extracted_value(gem_direct.get('mrp'), 'mrp')
                    
                    logger.info(f"Cleaned Gemini data: brand={brand}, batch={batch}, mfd={mfd_date}, exp={exp_date}, mrp={mrp_str}")
            except Exception as e:
                logger.warning(f"Gemini direct extraction failed: {e}")
            
            # METHOD 2: OCR + regex extraction as fallback
            logger.info(f"Performing OCR (Tesseract={TESSERACT_AVAILABLE}, Gemini={GEMINI_AVAILABLE})")
            full_text = ocr_extract_text(image_content)
            
            if full_text:
                logger.info(f"OCR Text extracted: {full_text[:200]}...")
                full_text = normalize_vertical(full_text)
                
                # Extract fields using regex if not already found
                if not brand:
                    brand = find_first_match(full_text, PATTERNS['brand_name'])
                    if not is_valid_brand(brand):
                        brand = None
                if not dosage:
                    dosage = find_first_match(full_text, PATTERNS['dosage'])
                if not batch:
                    batch = find_first_match(full_text, PATTERNS['batch_number'])
                if not mfd_date:
                    mfd_date = find_first_match(full_text, PATTERNS['mfd'])
                if not exp_date:
                    exp_date = find_first_match(full_text, PATTERNS['expiry'])
                if not manufacturer:
                    manufacturer = find_first_match(full_text, PATTERNS['manufacturer'])
                if not mrp_str:
                    mrp_str = find_first_match(full_text, PATTERNS['mrp'])
                
                # METHOD 3: Try Gemini text extraction as additional fallback
                if not brand or not batch or not mfd_date or not exp_date:
                    try:
                        gem_fields = extract_fields_with_gemini_from_text(full_text)
                        if gem_fields and isinstance(gem_fields, dict):
                            if not brand and is_valid_brand(gem_fields.get('brand')):
                                brand = gem_fields.get('brand', '').strip()
                            if not dosage and gem_fields.get('dosage'):
                                dosage = gem_fields.get('dosage', '').strip()
                            if not batch and gem_fields.get('batch_number'):
                                batch = gem_fields.get('batch_number', '').strip()
                            if not mfd_date and gem_fields.get('manufacture_date'):
                                mfd_date = gem_fields.get('manufacture_date', '').strip()
                            if not exp_date and gem_fields.get('expiry_date'):
                                exp_date = gem_fields.get('expiry_date', '').strip()
                            if not manufacturer and gem_fields.get('manufacturer'):
                                manufacturer = gem_fields.get('manufacturer', '').strip()
                            if not mrp_str and gem_fields.get('mrp'):
                                mrp_str = gem_fields.get('mrp', '').strip()
                    except Exception as e:
                        logger.warning(f"Gemini text extraction failed: {e}")
            
            # If still no OCR text and no Gemini results, show error
            if not full_text and not brand:
                return render_template(
                    'index.html',
                    error_message=(
                        "❌ Could not extract text from this image. "
                        "Please try with a clearer image."
                    )
                )

            logger.info(f"Extracted fields (before post-processing): Brand={brand}, Dosage={dosage}, Batch={batch}, MFD={mfd_date}, EXP={exp_date}, Manufacturer={manufacturer}, MRP={mrp_str}")

            # Apply post-processing to correct and validate extracted data
            brand, dosage, batch, mfd_date, exp_date, manufacturer, mrp_str = post_process_extracted_data(
                brand, dosage, batch, mfd_date, exp_date, manufacturer, mrp_str, full_text
            )
            
            logger.info(f"Extracted fields (after post-processing): Brand={brand}, Dosage={dosage}, Batch={batch}, MFD={mfd_date}, EXP={exp_date}, Manufacturer={manufacturer}, MRP={mrp_str}")

            # Fallback batch: look for patterns like E40001 or any alphanumeric batch
            if not batch or batch == "Information not available":
                batch_patterns = [
                    r"(?i)B\.?\s*No\.?\s*[:#.\-]?\s*([A-Z]?\d{4,}[A-Z0-9]*)",
                    r"(?i)Batch\s*[:#.\-]?\s*([A-Z]?\d{4,}[A-Z0-9]*)",
                    r"\b([A-Z]\d{5,})\b",
                    r'(\d{6,})',
                ]
                for pattern in batch_patterns:
                    m = re.search(pattern, full_text or "")
                    if m:
                        batch = m.group(1)
                        break
            # Parse MRP robustly
            try:
                import re as _re
                mrp_val = 0.0
                if mrp_str:
                    m = _re.search(r"(\d+(?:[.,]\d{1,2})?)", str(mrp_str))
                    if m:
                        mrp_val = float(m.group(1).replace(',', ''))
            except Exception:
                mrp_val = 0.0

            # Parse dates - prioritize Gemini extracted dates
            mfd_dt = None
            exp_dt = None
            
            logger.info(f"Parsing dates - MFD: '{mfd_date}', EXP: '{exp_date}'")
            
            # First try to parse the extracted date strings (from Gemini or regex)
            if mfd_date and mfd_date != 'Information not available':
                mfd_dt = parse_date_from_gemini(mfd_date)
                logger.info(f"Parsed MFD from extracted string: {mfd_dt}")
            
            if exp_date and exp_date != 'Information not available':
                exp_dt = parse_date_from_gemini(exp_date)
                logger.info(f"Parsed EXP from extracted string: {exp_dt}")
            
            # Fallback: try to find dates near labels in OCR text
            if not mfd_dt or not exp_dt:
                try:
                    if not mfd_dt:
                        labeled_mfd = find_labeled_date_dt(full_text or "", ['mfg', 'mfg.', 'mfd', 'manufactured', 'mfg.dt', 'mfg dt'])
                        if labeled_mfd:
                            mfd_dt = labeled_mfd
                            logger.info(f"Found MFD from labeled search: {mfd_dt}")
                    if not exp_dt:
                        labeled_exp = find_labeled_date_dt(full_text or "", ['exp', 'exp.', 'expiry', 'use before', 'best before', 'exp.dt', 'exp dt'])
                        if labeled_exp:
                            exp_dt = labeled_exp
                            logger.info(f"Found EXP from labeled search: {exp_dt}")
                except Exception as e:
                    logger.warning(f"Error in labeled date search: {e}")
            
            # Reconcile with OCR text context (handles swapped/missing)
            if full_text:
                mfd_dt, exp_dt = reconcile_dates_from_text(full_text, mfd_dt, exp_dt)
            
            # Provide safe defaults if still missing
            if not mfd_dt:
                logger.warning("MFD not found, using current date")
                mfd_dt = datetime.utcnow().date()
            if not exp_dt:
                logger.warning("EXP not found, defaulting to MFD + 24 months")
                exp_dt = add_months(mfd_dt, 24)

            # Ensure EXP is after MFD
            if exp_dt and mfd_dt and exp_dt < mfd_dt:
                logger.warning(f"EXP ({exp_dt}) is before MFD ({mfd_dt}), swapping")
                mfd_dt, exp_dt = exp_dt, mfd_dt
            
            logger.info(f"Final dates - MFD: {mfd_dt}, EXP: {exp_dt}")

            # Save to DB
            med = Medicine(
                medicine_name = brand or "N/A",
                brand = brand or "N/A",
                category = "N/A",
                batch_number = batch or "N/A",
                quantity = 0,
                price_per_unit = mrp_val,
                manufacture_date = mfd_dt,
                expiry_date = exp_dt
            )
            db.session.add(med)
            db.session.commit()
            logger.info("Medicine record saved to database")

            # Build result
            mfd_display = mfd_dt.strftime("%b %Y") if mfd_dt else 'N/A'
            exp_display = exp_dt.strftime("%b %Y") if exp_dt else 'N/A'
            result = {
                'brand': brand or 'N/A',
                'dosage': dosage or 'N/A',
                'batch': batch or 'N/A',
                'mfd_date': mfd_display,
                'exp_date': exp_display,
                'manufacturer': manufacturer or 'N/A',
                'mrp_val': f"{mrp_val:.2f}"
            }

            # Cross-verify: fetch last known price for same brand (if any)
            prev_price = None
            try:
                if brand:
                    last_med = Medicine.query.filter(Medicine.medicine_name.ilike(brand)).order_by(Medicine.batch_id.desc()).first()
                    if last_med and last_med.price_per_unit:
                        prev_price = float(last_med.price_per_unit)
            except Exception:
                prev_price = None

            return render_template('index.html', result=result, prev_price=prev_price)

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}", exc_info=True)
            return render_template('index.html', error_message=f"❌ Error processing image: {str(e)}")

    return render_template('index.html')

@app.route('/save_ocr', methods=['POST'])
def save_ocr():
    if 'user_type' not in session or session['user_type'] != 'owner':
        flash('Access denied. Please log in as an owner.', 'danger')
        return redirect(url_for('login_owner'))

    try:
        brand = request.form.get('brand') or 'N/A'
        dosage = request.form.get('dosage') or 'N/A'
        batch_number = request.form.get('batch') or request.form.get('batch_number') or 'N/A'
        manufacturer = request.form.get('manufacturer') or 'N/A'
        mrp_input = request.form.get('mrp') or request.form.get('mrp_val') or ''
        mfd_input = request.form.get('mfd_date') or request.form.get('mfd') or ''
        exp_input = request.form.get('exp_date') or request.form.get('exp') or ''

        # Price parsing with fallback to last known price for this brand
        mrp_val = 0.0
        if mrp_input:
            m = re.search(r"(\d+(?:[.,]\d{1,2})?)", mrp_input)
            if m:
                try:
                    mrp_val = float(m.group(1).replace(',', ''))
                except Exception:
                    mrp_val = 0.0
        if mrp_val == 0.0 and brand:
            last = Medicine.query.filter(Medicine.medicine_name.ilike(brand)).order_by(Medicine.batch_id.desc()).first()
            if last and last.price_per_unit:
                mrp_val = float(last.price_per_unit)

        # Dates: parse input flexibly; ensure EXP after MFD
        mfd_dt = parse_date_flexible(mfd_input) if mfd_input else None
        exp_dt = parse_date_flexible(exp_input) if exp_input else None
        mfd_dt, exp_dt = reconcile_dates_from_text("" , mfd_dt, exp_dt)
        if not mfd_dt:
            mfd_dt = datetime.utcnow().date()
        if not exp_dt or exp_dt < mfd_dt:
            exp_dt = add_months(mfd_dt, 12)

        # Upsert by batch_number when available; otherwise create new
        med = None
        if batch_number and batch_number != 'N/A':
            med = Medicine.query.filter(Medicine.batch_number == batch_number).first()

        if med:
            med.medicine_name = brand
            med.brand = brand
            med.category = med.category or 'N/A'
            med.batch_number = batch_number
            med.quantity = med.quantity or 0
            med.price_per_unit = mrp_val
            med.manufacture_date = mfd_dt
            med.expiry_date = exp_dt
        else:
            med = Medicine(
                medicine_name=brand,
                brand=brand,
                category='N/A',
                batch_number=batch_number or 'N/A',
                quantity=0,
                price_per_unit=mrp_val,
                manufacture_date=mfd_dt,
                expiry_date=exp_dt
            )
            db.session.add(med)

        db.session.commit()
        flash('Medicine details verified and saved successfully.', 'success')
        return redirect(url_for('medicine_database'))
    except Exception as e:
        logger.error(f"Error saving verified OCR data: {e}", exc_info=True)
        flash(f'Failed to save: {e}', 'danger')
        return redirect(url_for('index'))

@app.route('/owner/add_medicine', methods=['GET', 'POST'])
def add_medicine():
    if 'user_type' not in session or session['user_type'] != 'owner':
        flash('Access denied. Please log in as an owner.', 'danger')
        return redirect(url_for('login_owner'))

    if request.method == 'POST':
        try:
            medicine_name = request.form['medicine_name']
            brand = request.form['brand']
            category = request.form['category']
            batch_number = request.form['batch_number']
            quantity = int(request.form['quantity'])
            price_per_unit = float(request.form['price_per_unit'])
            manufacture_date_str = request.form['manufacture_date']
            expiry_date_str = request.form['expiry_date']

            manufacture_date = datetime.strptime(manufacture_date_str, '%Y-%m-%d').date()
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
            
            # Find the next available batch_id
            last_medicine = Medicine.query.order_by(Medicine.batch_id.desc()).first()
            next_batch_id = (last_medicine.batch_id + 1) if last_medicine else 1

            new_medicine = Medicine(
                batch_id=next_batch_id,
                medicine_name=medicine_name,
                brand=brand,
                category=category,
                batch_number=batch_number,
                quantity=quantity,
                price_per_unit=price_per_unit,
                manufacture_date=manufacture_date,
                expiry_date=expiry_date
            )

            db.session.add(new_medicine)
            db.session.commit()
            flash(f'Medicine \'{medicine_name}\' added successfully!', 'success')
            return redirect(url_for('medicine_database'))
        except ValueError:
            flash('Invalid input for quantity or price. Please enter valid numbers.', 'danger')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')

    return render_template('add_medicine.html')

@app.route('/owner/medicines')
def medicine_database():
    if 'user_type' not in session or session['user_type'] != 'owner':
        flash('Access denied. Please log in as an owner.', 'danger')
        return redirect(url_for('login_owner'))

    from datetime import datetime, timedelta
    
    # Get all medicines
    medicines = Medicine.query.all()
    current_date = datetime.utcnow().date()
    six_months_later = current_date + timedelta(days=180)
    
    # Debug logging
    print(f"Current date: {current_date}")
    print(f"Six months later: {six_months_later}")
    
    expiring_medicines = []
    
    # Check each medicine's expiry date
    for med in medicines:
        # Convert string date to date object if needed
        if isinstance(med.expiry_date, str):
            med.expiry_date = datetime.strptime(med.expiry_date, '%Y-%m-%d').date()
        
        days_until_expiry = (med.expiry_date - current_date).days
        is_expiring_soon = med.expiry_date <= six_months_later
        
        # Add attributes to medicine object
        med.is_expiring_soon = is_expiring_soon
        med.days_until_expiry = days_until_expiry
        
        if is_expiring_soon:
            expiring_medicines.append({
                'name': med.medicine_name,
                'batch': med.batch_number,
                'expiry_date': med.expiry_date,
                'days_left': days_until_expiry
            })
    
    # Debug logging
    print(f"Found {len(expiring_medicines)} medicines expiring within 6 months")
    for med in expiring_medicines:
        print(f"- {med['name']} (Batch: {med['batch']}): {med['days_left']} days left (expires {med['expiry_date']})")
    
    # Sort medicines by expiry date (soonest first)
    medicines.sort(key=lambda x: x.expiry_date)
    
    return render_template('medicine_database.html',
                         medicines=medicines,
                         show_alert=len(expiring_medicines) > 0,
                         expiring_meds=expiring_medicines[:10])  # Show top 10 expiring soon

@app.route('/owner/enquiries')
def view_enquiries():
    if 'user_type' not in session or session['user_type'] != 'owner':
        flash('Access denied. Please log in as an owner.', 'danger')
        return redirect(url_for('login_owner'))

    # Ensure the table exists when accessing this page
    with app.app_context():
        db.create_all()
    
    enquiries = MedicineEnquiry.query.order_by(MedicineEnquiry.enquiry_date.desc()).all()
    return render_template('enquiries.html', enquiries=enquiries)

# ─── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Log API key status on startup
    gemini_key = os.environ.get('GEMINI_API_KEY')
    openai_key = os.environ.get('OPENAI_API_KEY')
    logger.info("=" * 50)
    logger.info("Starting Flask application...")
    logger.info(f"GEMINI_AVAILABLE: {GEMINI_AVAILABLE}")
    logger.info(f"GEMINI_API_KEY set: {bool(gemini_key)}")
    if gemini_key:
        logger.info(f"GEMINI_API_KEY starts with: {gemini_key[:10]}...")
    logger.info(f"OPENAI_AVAILABLE: {OPENAI_AVAILABLE}")
    logger.info(f"OPENAI_API_KEY set: {bool(openai_key)}")
    logger.info("=" * 50)
    
    with app.app_context():
        db.create_all()  # This will create all tables including MedicineEnquiry
        # Check if the database is empty before populating
        if not Medicine.query.first():
            for data in initial_medicine_data:
                data['manufacture_date'] = datetime.strptime(data['manufacture_date'], '%Y-%m-%d').date()
                data['expiry_date'] = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
                medicine = Medicine(**data)
                db.session.add(medicine)
            db.session.commit()
    app.run(debug=True)