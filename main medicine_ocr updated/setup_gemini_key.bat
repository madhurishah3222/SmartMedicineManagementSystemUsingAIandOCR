@echo off
echo ============================================
echo   Gemini API Key Setup for Medicine OCR
echo ============================================
echo.
echo To use this application, you need a FREE Gemini API key.
echo.
echo Step 1: Go to https://aistudio.google.com/app/apikey
echo Step 2: Sign in with your Google account
echo Step 3: Click "Create API Key"
echo Step 4: Copy the API key
echo.
set /p GEMINI_API_KEY="Enter your Gemini API key: "
echo.
echo Setting environment variable...
setx GEMINI_API_KEY "%GEMINI_API_KEY%"
echo.
echo API key has been saved!
echo Please restart your terminal/command prompt for changes to take effect.
echo.
echo To run the application:
echo   cd "main medicine_ocr updated"
echo   python app.py
echo.
pause
