# Quick Setup Guide - Prescription Upload Feature

## The Error You're Seeing

If you see: *"Failed to process prescription. Please ensure GEMINI_API_KEY or OPENAI_API_KEY is set in environment variables"*

This means you need to set up an API key for the AI service.

## Quick Setup (Choose One)

### Option 1: Google Gemini (FREE - Recommended) ⭐

1. **Get your API key:**
   - Visit: https://makersuite.google.com/app/apikey
   - Sign in with Google
   - Click "Create API Key"
   - Copy the key

2. **Set the key in your terminal:**
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```

3. **To make it permanent (add to ~/.zshrc):**
   ```bash
   echo 'export GEMINI_API_KEY="your-api-key-here"' >> ~/.zshrc
   source ~/.zshrc
   ```

### Option 2: OpenAI ChatGPT (Paid)

1. **Get your API key:**
   - Visit: https://platform.openai.com/api-keys
   - Sign in
   - Click "Create new secret key"
   - Copy the key

2. **Set the key:**
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

3. **To make it permanent:**
   ```bash
   echo 'export OPENAI_API_KEY="your-api-key-here"' >> ~/.zshrc
   source ~/.zshrc
   ```

## Using the Setup Script

You can also use the automated setup script:

```bash
./setup_api_key.sh
```

## After Setting Up

1. **Restart your Flask app** (stop it with Ctrl+C and run `python app.py` again)
2. The prescription upload feature will now work!

## Testing

1. Go to the chatbot
2. Select option "4. Upload Prescription"
3. Upload a prescription image
4. The system will extract medicines and check availability

## Notes

- **Gemini is FREE** and works great for this use case
- You only need ONE API key (Gemini OR OpenAI, not both)
- The app will automatically use Gemini if available, otherwise ChatGPT
- Make sure to restart the Flask app after setting the environment variable


