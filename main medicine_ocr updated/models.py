from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(100), default='N/A')
    generic_name = db.Column(db.String(100), default='N/A')
    dosage_strength = db.Column(db.String(50), default='N/A')
    batch_number = db.Column(db.String(50), default='N/A')
    mfd = db.Column(db.String(50), default='N/A')
    expiry = db.Column(db.String(50), default='N/A')
    manufacturer = db.Column(db.String(200), default='N/A')
    mrp = db.Column(db.Float, default=0.0)
    storage = db.Column(db.String(200), default='N/A')
    usage = db.Column(db.Text, default='N/A')
    warnings = db.Column(db.Text, default='N/A')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
