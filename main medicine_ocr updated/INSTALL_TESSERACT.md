# Installing Tesseract OCR (FREE)

Tesseract is a FREE, open-source OCR engine that works offline without any API keys.

## Windows Installation

### Option 1: Download Installer (Recommended)
1. Go to: https://github.com/UB-Mannheim/tesseract/wiki
2. Download the latest installer (e.g., `tesseract-ocr-w64-setup-5.3.3.20231005.exe`)
3. Run the installer
4. **Important:** Install to the default path: `C:\Program Files\Tesseract-OCR\`
5. Restart your terminal/command prompt
6. Restart the Flask app

### Option 2: Using Chocolatey
```cmd
choco install tesseract
```

### Option 3: Using Winget
```cmd
winget install UB-Mannheim.TesseractOCR
```

## Verify Installation

After installation, run this command to verify:
```cmd
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

You should see something like:
```
tesseract 5.3.3
```

## Running the App

After installing Tesseract:
```cmd
cd "main medicine_ocr updated"
pip install -r requirements.txt
python app.py
```

The app will automatically detect Tesseract and use it for FREE OCR!

## Troubleshooting

If Tesseract is not detected:
1. Make sure it's installed in `C:\Program Files\Tesseract-OCR\`
2. Or add the Tesseract folder to your system PATH
3. Restart your terminal and the Flask app
