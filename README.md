Smart Medicine Management System (AI + OCR)
A Flask-based web app for managing medicines, extracting data from prescriptions using Google Cloud Vision OCR with optional AI parsing, owner inventory alerts, and a full shopping experience with cart and a payment selection step.

Features
Owner portal: add/view medicines, database management
OCR upload for prescriptions (Google Cloud Vision)
AI parsing for medicine info (Gemini/OpenAI optional)
Expiry and low-stock alerts (bell dropdown)
User portal: shop, add to cart, update/remove items
Checkout with payment selection (COD/UPI/Card placeholder)
Orders and order summary page
Tech Stack
Python, Flask, Jinja2
SQLite via Flask-SQLAlchemy
Google Cloud Vision API (OCR)
Optional: Google Generative AI (Gemini) or OpenAI for parsing
Bootstrap 5, Font Awesome
Prerequisites
Python 3.10+
Google Cloud service account key for Vision API (JSON file)
Optionally, Gemini or OpenAI API keys if you enable AI parsing
Database
SQLite files live under main medicine_ocr updated/instance and are ignored by git.
Tables are auto-created on app start. If needed, delete the DB file(s) to reset.
Shopping & Payment Flow
Add items in Shop → View Cart → Place Order → Payment selection (COD/UPI/Card)
On confirm, order is created, stock is updated, and an order success page is shown.
Payment integrations are placeholders; you can integrate a real gateway (Razorpay/Stripe/PayPal) next.
Project Structure (key files)
main medicine_ocr updated/
  app.py                      # Flask app, routes, models
  requirements.txt            # Python dependencies
  templates/                  # Jinja templates (shop, cart, payment, success, etc.)
  instance/                   # SQLite DB files (ignored)
