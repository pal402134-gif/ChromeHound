# ChromeHound

Chrome credential harvester + keylogger for authorized Windows penetration testing. Runs in background with autostart persistence. Saves credentials and keystrokes via Discord webhook.

## Features

- Decrypts Chrome saved passwords (Chrome 80+ AES-GCM)
- Live keylogger (captures all keystrokes)
- No console window or taskbar presence
- Auto-installs to startup (Registry + Scheduled Task + Startup folder)
- Survives reboot and logoff
- Single file deployment

## Requirements

- Windows 10/11
- Chrome browser with saved passwords
- Discord webhook URL

## Setup

1. Edit `chromehound.py` and replace `YOUR_DISCORD_WEBHOOK_URL` with your webhook

2. Install dependencies:
