#!/bin/bash

echo "=========================================="
echo "API Key Setup for Prescription Upload"
echo "=========================================="
echo ""
echo "Choose which API you want to use:"
echo "1. Google Gemini API (Free, Recommended)"
echo "2. OpenAI ChatGPT API (Requires paid account)"
echo ""
read -p "Enter your choice (1 or 2): " choice

if [ "$choice" == "1" ]; then
    echo ""
    echo "To get your Gemini API key:"
    echo "1. Visit: https://makersuite.google.com/app/apikey"
    echo "2. Sign in with your Google account"
    echo "3. Click 'Create API Key'"
    echo "4. Copy the API key"
    echo ""
    read -p "Enter your GEMINI_API_KEY: " api_key
    if [ ! -z "$api_key" ]; then
        echo "export GEMINI_API_KEY=\"$api_key\"" >> ~/.zshrc
        export GEMINI_API_KEY="$api_key"
        echo ""
        echo "✅ Gemini API key set successfully!"
        echo "The key has been added to your ~/.zshrc file for persistence."
        echo "To use it in this session, run: export GEMINI_API_KEY=\"$api_key\""
    else
        echo "❌ No API key provided."
    fi
elif [ "$choice" == "2" ]; then
    echo ""
    echo "To get your OpenAI API key:"
    echo "1. Visit: https://platform.openai.com/api-keys"
    echo "2. Sign in with your OpenAI account"
    echo "3. Click 'Create new secret key'"
    echo "4. Copy the API key"
    echo ""
    read -p "Enter your OPENAI_API_KEY: " api_key
    if [ ! -z "$api_key" ]; then
        echo "export OPENAI_API_KEY=\"$api_key\"" >> ~/.zshrc
        export OPENAI_API_KEY="$api_key"
        echo ""
        echo "✅ OpenAI API key set successfully!"
        echo "The key has been added to your ~/.zshrc file for persistence."
        echo "To use it in this session, run: export OPENAI_API_KEY=\"$api_key\""
    else
        echo "❌ No API key provided."
    fi
else
    echo "❌ Invalid choice."
fi

echo ""
echo "After setting the key, restart your Flask app to use the prescription upload feature."


