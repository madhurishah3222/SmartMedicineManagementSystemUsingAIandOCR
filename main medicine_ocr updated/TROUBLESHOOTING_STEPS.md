# Step-by-Step Troubleshooting Guide

## Step 1: Stop Your Flask App
1. Go to the terminal where `python app.py` is running
2. Press `Ctrl+C` to stop it
3. Wait until you see the prompt again

## Step 2: Restart Flask App
1. In the same terminal, run:
   ```bash
   python app.py
   ```
2. Wait for it to start (you'll see "Running on http://127.0.0.1:5000")
3. **IMPORTANT**: Look at the startup logs - you should see:
   ```
   ==================================================
   Starting Flask application...
   GEMINI_AVAILABLE: True
   GEMINI_API_KEY set: True
   GEMINI_API_KEY starts with: AIzaSyBU-3...
   ==================================================
   ```

## Step 3: Test API Key Configuration
1. Open your browser
2. Go to: `http://127.0.0.1:5000/api/test_api_key`
3. You should see a JSON response showing:
   - `GEMINI_AVAILABLE: true`
   - `GEMINI_API_KEY_set: true`
   - `GEMINI_API_KEY_preview: "AIzaSyBU-3..."`

## Step 4: Try Prescription Upload
1. Go to the chatbot: `http://127.0.0.1:5000/chatbot`
2. Select option "4. Upload Prescription"
3. Upload a prescription image
4. **Watch the Flask terminal** - you'll see detailed logs

## Step 5: Check the Logs
When you upload, look for these log messages in the Flask terminal:
- `"Starting prescription analysis..."`
- `"GEMINI_AVAILABLE: True, GEMINI_API_KEY available: True"`
- `"Attempting to extract medicines with Gemini..."`
- `"Using Gemini API key (starts with: AIzaSyBU-3...)"`

If you see errors, copy them and share them.

## Common Issues:

### Issue 1: API key not showing in test endpoint
**Solution**: The Flask app needs the API key. Try:
```bash
export GEMINI_API_KEY="AIzaSyBU-35jMZEdequ5R5wsRC-81x4FUFp6aFU"
python app.py
```

### Issue 2: Still getting error after restart
**Solution**: Check the Flask terminal logs - they will show the exact error. The code now has a fallback API key built-in, so it should work even without the environment variable.

### Issue 3: No logs appearing
**Solution**: Make sure you're looking at the correct terminal where Flask is running.

