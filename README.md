# Openwrt Telegram Bot

![GitHub](https://img.shields.io/badge/license-MIT-blue.svg) ![GitHub last commit](https://img.shields.io/github/last-commit/hhai93/Openwrt_Telegram_Bot)

A lightweight Telegram bot to remotely monitor and control your OpenWRT-based router.

---

## 🚀 Features

- 📡 List connected devices (with MAC Vendor lookup)
- 🧠 Show CPU, memory, WAN IP and uptime
- 🚫 Block or unblock internet access by MAC address
- 🔁 Reboot router or restart WAN connection
- 📶 Turn Wi-Fi on or off
- ⚠️ Auto alert when unknown devices connect (Not yet listed in DHCP/static leases)

---

## 📦 Requirements

`python3`, `python-telegram-bot`, `python-telegram-bot[job-queue]`, `requests`, `asyncio`

```bash
opkg update
opkg install python3
opkg install python3-pip
pip install python-telegram-bot
pip install python-telegram-bot[job-queue]
pip install requests
pip install asyncio
```
---

## 🛠️ Setup

1. Edit the following variables in the script:
```python
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ALLOWED_USERS = "YOUR_TELEGRAM_USER_ID"
```

2. Run the bot:
-  Create init script
```bash
touch /etc/init.d/router_bot
chmod +x /etc/init.d/router_bot
```
- Edit script:
```bash
vi /etc/init.d/router_bot
```
Then paste the followings:
```bash
#!/bin/sh /etc/rc.common

START=99
STOP=10

start() {
    echo "Starting Router bot..."
    python3 /PATH/router_bot.py >> /root/bot.log 2>&1 &
}

stop() {
    echo "Stopping Router bot..."
    killall -9 python3
}
```
- Enable and start the bot
```bash
/etc/init.d/router_bot enable
/etc/init.d/router_bot start
```

*The bot needs access to system commands (`iptables`, `ping`, `wifi`, etc.), so make sure it's run with appropriate privileges.*

---

## 📚 Commands

| Command        | Description                              |
|----------------|------------------------------------------|
| `/status`      | Show router status                       |
| `/devices`     | List connected devices                   |
| `/block <MAC>` | Block internet access by MAC             |
| `/unblock <MAC>` | Unblock internet access by MAC         |
| `/reboot`      | Reboot the router                        |
| `/reboot_wan`   | Restart WAN connection                  |
| `/wifi_on`      | Turn Wi-Fi **on**                       |
| `/wifi_off`     | Turn Wi-Fi **off**                      |

---

## 📢 Auto Alerts

The bot checks for unknown devices every 5 minutes and notifies authorized users if any are online.

