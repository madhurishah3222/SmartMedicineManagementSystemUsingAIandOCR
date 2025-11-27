# Prescription Upload Feature Setup

This feature allows users to upload prescription images, extract medicine names using AI (Gemini or ChatGPT), and check their availability in the store database.

## Features

- Upload prescription images (JPG, PNG, etc.)
- AI-powered medicine name extraction using Gemini or ChatGPT
- Automatic availability checking against the medicine database
- Visual feedback with availability status

## Setup Instructions

### Option 1: Using Google Gemini API (Recommended)

1. Get your Gemini API key:
   - Visit: https://makersuite.google.com/app/apikey
   - Create a new API key

2. Set the environment variable:
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```

   Or add to your `.env` file:
   ```
   GEMINI_API_KEY=your-api-key-here
   ```

### Option 2: Using OpenAI ChatGPT API

1. Get your OpenAI API key:
   - Visit: https://platform.openai.com/api-keys
   - Create a new API key

2. Set the environment variable:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

   Or add to your `.env` file:
   ```
   OPENAI_API_KEY=your-api-key-here
   ```

### Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `google-generativeai` (for Gemini)
- `openai` (for ChatGPT)

### Running the Application

1. Make sure you have at least one API key set (Gemini or OpenAI)
2. The system will automatically use Gemini if available, otherwise fall back to ChatGPT
3. Start your Flask application:
   ```bash
   python app.py
   ```

## Usage

1. Navigate to the chatbot
2. Select option "4. Upload Prescription"
3. Choose a prescription image file
4. Click "Analyze Prescription"
5. The system will:
   - Extract medicine names from the image
   - Check availability in the database
   - Display results with availability status

## Notes

- The feature uses Google Cloud Vision API for initial text extraction (already configured)
- Then uses Gemini or ChatGPT to intelligently extract medicine names
- Medicines are matched against the database (case-insensitive, partial matching supported)
- If a medicine is not found exactly, the system tries partial matching

## Troubleshooting

- **"Failed to process prescription"**: Make sure GEMINI_API_KEY or OPENAI_API_KEY is set
- **"No medicines found"**: Ensure the prescription image is clear and contains readable text
- **API errors**: Check your API key is valid and has sufficient credits/quota


