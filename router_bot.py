import logging
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import subprocess
import requests
import re
import json
import os
from functools import wraps
import asyncio
import nest_asyncio
nest_asyncio.apply()

# ================= CONFIGURATION =================
TOKEN = "YOUR_BOT_TOKEN"
ALLOWED_USERS = [123456789]  # Replace with your actual Telegram user ID(s)
MAC_VENDOR_API = "https://api.macvendors.com/"
CACHE_FILE = "mac_vendor_cache.json"

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("telegram").setLevel(logging.WARNING)  # Reduce Telegram log verbosity

# MAC vendor cache
mac_vendor_cache = {}
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        mac_vendor_cache = json.load(f)


def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(mac_vendor_cache, f)

# ================= UTILITY FUNCTIONS =================
def is_authorized(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in ALLOWED_USERS:
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def execute_command(command):
    try:
        return subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True).strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Shell command error: {e.output}")
        return f"Error: {e.output}"

def is_valid_mac(mac):
    return re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", mac) is not None

def get_mac_vendor(mac):
    mac = mac.upper()
    if mac in mac_vendor_cache:
        return mac_vendor_cache[mac]
    try:
        response = requests.get(f"{MAC_VENDOR_API}{mac}", timeout=5)
        response.raise_for_status()
        vendor = response.text.strip() if "text/plain" in response.headers.get("Content-Type", "") else "Unknown"
        mac_vendor_cache[mac] = vendor
        save_cache()
        return vendor
    except Exception as e:
        logger.error(f"MAC Vendor lookup error: {e}")
        return "Unable to lookup"

def get_static_leases():
    leases = [
        line.split()[2].strip("'")
        for line in execute_command("cat /etc/config/dhcp").splitlines() if "option mac" in line
    ]
    return leases

def is_device_online(ip):
    response = execute_command(f"ping -c 4 -W 1 {ip}")
    return "received" in response and int(response.split()[response.split().index('received') - 1]) > 0

# ================= BOT COMMANDS =================
@is_authorized
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = execute_command("uptime | awk -F', ' '{print $1}'")
    cpu_info = execute_command("cat /proc/stat | grep 'cpu '")
    cpu_values = cpu_info.split()
    total_time = sum(map(int, cpu_values[1:]))
    idle_time = int(cpu_values[4])
    cpu_usage = 100 * (1 - idle_time / total_time)
    mem_info = execute_command("awk '/MemTotal:/ {total=$2} /MemAvailable:/ {available=$2} END {print total, available}' /proc/meminfo")
    mem_total, mem_available = map(int, mem_info.split())
    mem_used = mem_total - mem_available
    
    message = f"""
📊 *Router Status:*

🕒 *Uptime:* {uptime}
💾 *Memory:* {mem_used / 1024:.2f} MB / {mem_total / 1024:.2f} MB
⚙️ *CPU:* {cpu_usage:.2f}% used
"""
    await update.message.reply_text(message, parse_mode='Markdown')

@is_authorized
async def devices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    static_leases = get_static_leases()
    dhcp_leases = execute_command("cat /tmp/dhcp.leases").splitlines()
    devices = []

    for lease in dhcp_leases:
        parts = lease.split()
        if len(parts) >= 4:
            mac, ip, hostname = parts[1], parts[2], parts[3] if parts[3] != "*" else "No name"
            vendor = get_mac_vendor(mac)
            devices.append((hostname, mac, ip, vendor, mac.lower() not in map(str.lower, static_leases)))

    if not devices:
        await update.message.reply_text("No connected devices found.")
        return

    devices.sort(key=lambda x: list(map(int, x[2].split('.'))))

    known, unknown = [], []
    for d in devices:
        (unknown if d[4] else known).append(d)

    for title, group in [("📋 *Known Devices:*", known), ("⚠️ *Unknown Devices:*", unknown)]:
        if group:
            message = title + "\n\n" + "\n\n".join(
                [f"📍 *Hostname*: {d[0]}\n📡 *MAC*: {d[1]}\n🔗 *IP*: {d[2]}\n🏭 *Vendor*: {d[3]}" for d in group]
            )
            await update.message.reply_text(message, parse_mode="Markdown")

@is_authorized
async def manage_block(update: Update, context: ContextTypes.DEFAULT_TYPE, block=True):
    if len(context.args) != 1 or not is_valid_mac(context.args[0]):
        await update.message.reply_text(
            "❌ Invalid MAC address. Use: `/block XX:XX:XX:XX:XX:XX`", parse_mode="Markdown"
        )
        return

    mac = context.args[0]

    if block:
        command = f"iptables -I FORWARD -m mac --mac-source {mac} -j DROP"
        success_message = f"✅ Blocked device: {mac}"
        error_message = f"❌ Failed to block device: {mac}"
    else:
        command = f"iptables -D FORWARD -m mac --mac-source {mac} -j DROP"
        success_message = f"✅ Unblocked device: {mac}"
        error_message = f"❌ Failed to unblock device: {mac}"

    result = execute_command(command)

    if result.strip():
        await update.message.reply_text(f"{error_message}\nError detail: {result.strip()}")
    else:
        await update.message.reply_text(success_message)

block = lambda u, c: manage_block(u, c, block=True)
unblock = lambda u, c: manage_block(u, c, block=False)

@is_authorized
async def reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Rebooting router...")
    execute_command("reboot")

@is_authorized
async def reboot_wan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Restarting WAN interface...")
    execute_command("ifdown wan && ifup wan")

@is_authorized
async def wifi_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    execute_command("wifi up")
    await update.message.reply_text("✅ Wi-Fi has been turned *on*.", parse_mode="Markdown")

@is_authorized
async def wifi_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    execute_command("wifi down")
    await update.message.reply_text("🚫 Wi-Fi has been turned *off*.", parse_mode="Markdown")

# ================= AUTO DEVICE CHECK =================
async def check_unknown_devices(context: ContextTypes.DEFAULT_TYPE):
    static_leases = get_static_leases()
    dhcp_leases = execute_command("cat /tmp/dhcp.leases").strip().splitlines()
    unknown_devices = []

    for lease in dhcp_leases:
        parts = lease.split()
        if len(parts) >= 4:
            mac, ip, hostname = parts[1], parts[2], parts[3] if parts[3] != "*" else "No name"
            if mac.lower() not in map(str.lower, static_leases) and is_device_online(ip):
                vendor = get_mac_vendor(mac)
                unknown_devices.append((hostname, mac, ip, vendor))

    if unknown_devices:
        message = "⚠️ *New unknown device(s) detected:*\n\n" + "\n\n".join(
            f"📍 *Hostname*: {d[0]}\n📡 *MAC*: {d[1]}\n🔗 *IP*: {d[2]}\n🏭 *Vendor*: {d[3]}" for d in unknown_devices
        )
        for user_id in ALLOWED_USERS:
            try:
                await context.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error sending alert to user {user_id}: {e}")

def setup_auto_check(application):
    application.job_queue.run_repeating(check_unknown_devices, interval=300, first=10)

# ================= RUN THE BOT =================
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    await app.bot.set_my_commands([
        BotCommand("status", "Check router status"),
        BotCommand("devices", "List connected devices"),
        BotCommand("block", "Block a MAC address"),
        BotCommand("unblock", "Unblock a MAC address"),
        BotCommand("reboot", "Reboot the router"),
        BotCommand("rebootwan", "Restart WAN connection"),
        BotCommand("wifion", "Turn on Wi-Fi"),
        BotCommand("wifioff", "Turn off Wi-Fi"),
    ])

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("devices", devices))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))
    app.add_handler(CommandHandler("reboot", reboot))
    app.add_handler(CommandHandler("rebootwan", reboot_wan))
    app.add_handler(CommandHandler("wifion", wifi_on))
    app.add_handler(CommandHandler("wifioff", wifi_off))

    setup_auto_check(app)

    logger.info("Bot is running...")
    await app.run_polling()

async def shutdown():
    logger.info("Shutting down bot...")
    await app.shutdown()
    await app.stop()
    loop = asyncio.get_event_loop()
    loop.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
    finally:
        loop.close()
