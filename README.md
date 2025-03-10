# Бот Фича

## Overview
This Telegram bot allows for user registration, message broadcasting, and logging user responses. It supports multiple administrators and ensures persistence using an SQLite database.

## Features
- User registration with nickname
- Message broadcasting by administrators
- Logging user responses
- Admin logging and notifications
- Persistent storage using SQLite

## Requirements
- Python 3.8+
- Telegram Bot API Token
- Dependencies: Install with `pip install -r requirements.txt`

## Installation
1. Clone the repository:
   ```sh
   git clone https://github.com/your-repo.git
   cd your-repo
   ```

2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

3. Create a `.env` file with:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   ADMINS=123456789,987654321  # Admin Telegram IDs, comma-separated
   ```

4. Run the bot:
   ```sh
   python bot.py
   ```

## Usage
### User Commands
- `/start` - Register or change nickname
- `/end` - End session
- `/id` - Get user ID

### Admin Commands
- `/message` - Initiate a broadcast
- `/status` - Show active users and responses
- `/add_admin` - Add a new admin (reply to user message)

## Database Persistence
The bot automatically saves and loads its state using `aiosqlite`. User data and admin pending status are stored and restored on restart.

## License
MIT License

