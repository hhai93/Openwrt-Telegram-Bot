# Telegram Bot for OpenWrt
A Telegram bot to monitor and manage devices connected to your OpenWrt router. It can detect new devices, block/unblock internet access, reboot the router, and more — all via chat.

---

## 🚀 Features
- Check router uptime, CPU, and memory usage
- Show all connected devices with MAC vendors
- Identify and notify about unknown devices (devices not listed in static leases)
- Block or unblock internet access by MAC address
- Reboot router or WAN interface
- Automatically checks for new devices every 5 minutes

---

## 🛠️ Requirements

- Python 3.9+
- A router running OpenWrt with access to system shell commands

---

## 🔐 Configuration

Edit the following values:
- TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
- ALLOWED_USERS = [123456789] #Replace with your Telegram user ID(s) (chat with @userinfobot to get)

---

## ▶️ Running the Bot
bash python router_bot.py

---

## 💬 Available Commands

| Command         | Description                            |
|----------------|----------------------------------------|
| `/status`       | Show router uptime, CPU and memory info |
| `/devices`      | List connected devices (known & unknown) |
| `/block XX:XX:XX:XX:XX:XX` | Block internet for a device |
| `/unblock XX:XX:XX:XX:XX:XX` | Unblock internet for a device |
| `/reboot`       | Reboot the router                      |
| `/rebootwan`    | Restart WAN interface                  |

> Note: Only users listed in `ALLOWED_USERS` can use the bot.

---

## 📢 Auto Notifications

The bot checks `/tmp/dhcp.leases` every 5 minutes and sends Telegram alerts if any new unknown devices are found on the network.
