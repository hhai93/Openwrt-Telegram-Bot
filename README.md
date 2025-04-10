# Openwrt Telegram Bot

![GitHub](https://img.shields.io/badge/license-MIT-blue.svg) ![GitHub last commit](https://img.shields.io/github/last-commit/hhai93/Openwrt_Telegram_Bot)

A lightweight Telegram bot to remotely monitor and control your OpenWRT-based router.

---

## 🚀 Features

- 📡 List connected devices (with MAC Vendor lookup)
- 🧠 Show CPU, memory, and uptime stats
- 🚫 Block or unblock internet access by MAC address
- 🔁 Reboot router or restart WAN connection
- 📶 Turn Wi-Fi on or off
- ⚠️ Auto alert when unknown devices connect

---

## 📦 Requirements

- Python 3.9+
- `python-telegram-bot >= 20.0`
- `requests`, `nest_asyncio`
---
## 🛠️ Setup

1. Edit the following variables in the script:
```python
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ALLOWED_USERS = [123456789]  # Telegram user IDs allowed to use the bot
```

2. Run the bot:

```bash
python router_bot.py
```

The bot needs access to system commands (`iptables`, `ping`, `wifi`, etc.), so make sure it's run with appropriate privileges.

---

## 📚 Commands

| Command        | Description                              |
|----------------|------------------------------------------|
| `/status`      | Show router status                       |
| `/devices`     | List connected devices                   |
| `/block <MAC>` | Block internet access by MAC             |
| `/unblock <MAC>` | Unblock internet access                |
| `/reboot`      | Reboot the router                        |
| `/rebootwan`   | Restart WAN connection                   |
| `/wifion`      | Turn Wi-Fi **on**                        |
| `/wifioff`     | Turn Wi-Fi **off**                       |

---

## 📢 Auto Alerts

The bot checks for unknown devices every 5 minutes and notifies authorized users if any are online.

