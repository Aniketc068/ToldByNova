@echo off
cd /d "%~dp0"

set BOT_TOKEN=your_telegram_bot_token
set ADMIN_ID=your_telegram_user_id
set OLLAMA_API_KEY=your_ollama_api_key
set OLLAMA_MODEL=gemma4:31b-cloud

python scripts\telegram_automation.py
