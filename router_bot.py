import logging
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import subprocess
import requests
import asyncio
import re
import json
import os
from functools import wraps

# ================= CONFIGURATION =================
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ALLOWED_USERS = [YOUR_TELEGRAM_USER_ID]
MAC_VENDOR_API = "https://api.macvendors.com/"
CACHE_FILE = "mac_vendor_cache.json"

# Logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Cache MAC vendor
mac_vendor_cache = {}
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        mac_vendor_cache = json.load(f)

def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(mac_vendor_cache, f)

# List of reported devices
reported_devices = set()

# ================= UTILITY FUNCTIONS =================
def is_authorized(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in ALLOWED_USERS:
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def execute_command(command_args):
    try:
        result = subprocess.run(command_args, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Shell command error: {e.stderr}")
        return f"Error: {e.stderr}"

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
        logger.error(f"Error querying MAC Vendor: {e}")
        return "Unable to query"

def get_static_leases():
    output = execute_command(["cat", "/etc/config/dhcp"])
    return [line.split()[2].strip("'") for line in output.splitlines() if "option mac" in line]

def is_device_online(ip):
    result = execute_command(["ping", "-c", "1", "-W", "1", ip])
    logger.info(f"Ping {ip}: {result}")
    return "1 packets received" in result

def get_wan_ip():
    iface = execute_command(["uci", "get", "network.wan.ifname"])
    if iface:
        ip_output = execute_command(["ip", "addr", "show", iface])
        match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", ip_output)
        if match:
            return match.group(1)
    wan_ip = execute_command(["uclient-fetch", "-qO", "-", "https://api.ipify.org"])
    return wan_ip if wan_ip else "Unable to retrieve"

# ================= BOT COMMANDS =================
@is_authorized
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = execute_command(["uptime"]).split(",")[0]
    cpu_info = execute_command(["cat", "/proc/stat"]).splitlines()[0].split()
    total_time = sum(map(int, cpu_info[1:]))
    idle_time = int(cpu_info[4])
    cpu_usage = 100 * (1 - idle_time / total_time)
    mem_info = execute_command(["awk", "/MemTotal:/ {total=$2} /MemAvailable:/ {available=$2} END {print total, available}", "/proc/meminfo"])
    mem_total, mem_available = map(int, mem_info.split())
    mem_used = mem_total - mem_available
    wan_ip = get_wan_ip()
    mem_used_mb = mem_used / 1024
    mem_total_mb = mem_total / 1024
    mem_used_str = f"{mem_used_mb:,.2f}" if mem_used_mb >= 1000 else f"{mem_used_mb:.2f}"
    mem_total_str = f"{mem_total_mb:,.2f}" if mem_total_mb >= 1000 else f"{mem_total_mb:.2f}"

    message = f"""
📊 *Router Status:*

🕒 *Uptime:* {uptime}
💾 *Memory:* {mem_used_str} MB / {mem_total_str} MB
⚙️ *CPU:* {cpu_usage:.2f}% used
🌐 *WAN IP:* {wan_ip}
"""
    await update.message.reply_text(message, parse_mode="Markdown")

def parse_dhcp_leases():
    dhcp_leases = execute_command(["cat", "/tmp/dhcp.leases"]).splitlines()
    devices = []
    for lease in dhcp_leases:
        parts = lease.split()
        if len(parts) >= 4:
            mac, ip, hostname = parts[1], parts[2], parts[3] if parts[3] != "*" else "No name"
            vendor = get_mac_vendor(mac)
            devices.append((hostname, mac, ip, vendor))
    return devices

def categorize_devices(devices, static_leases):
    known, unknown = [], []
    for hostname, mac, ip, vendor in devices:
        is_unknown = mac.lower() not in map(str.lower, static_leases)
        (unknown if is_unknown else known).append((hostname, mac, ip, vendor))
    return known, unknown

@is_authorized
async def devices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    static_leases = get_static_leases()
    devices = parse_dhcp_leases()
    if not devices:
        await update.message.reply_text("No devices are connected.")
        return

    devices.sort(key=lambda x: list(map(int, x[2].split("."))))
    known, unknown = categorize_devices(devices, static_leases)

    for title, group in [("📋 *Connected Devices:*", known), ("⚠️ *Unknown Devices:*", unknown)]:
        if group:
            message = title + "\n\n" + "\n\n".join(
                [f"📍 *Hostname*: {d[0]}\n📡 *MAC*: {d[1]}\n🔗 *IP*: {d[2]}\n🏭 *Vendor*: {d[3]}" for d in group]
            )
            await update.message.reply_text(message, parse_mode="Markdown")

@is_authorized
async def manage_block(update: Update, context: ContextTypes.DEFAULT_TYPE, block=True):
    if len(context.args) != 1 or not is_valid_mac(context.args[0]):
        action = "block" if block else "unblock"
        await update.message.reply_text(
            f"❌ Invalid MAC address. Use: `/{action} XX:XX:XX:XX:XX:XX`", parse_mode="Markdown"
        )
        return

    mac = context.args[0]
    action = "DROP" if block else "ACCEPT"
    command = ["iptables", "-I" if block else "-D", "FORWARD", "-m", "mac", "--mac-source", mac, "-j", action]
    success_message = f"✅ Device {mac} has been {'blocked' if block else 'unblocked'}."
    error_message = f"❌ Failed to {'block' if block else 'unblock'} device {mac}."

    result = execute_command(command)
    if "Error" in result:
        await update.message.reply_text(f"{error_message}\nDetails: {result}")
    else:
        await update.message.reply_text(success_message)

block = lambda u, c: manage_block(u, c, block=True)
unblock = lambda u, c: manage_block(u, c, block=False)

@is_authorized
async def reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Rebooting the router...")
    result = execute_command(["reboot"])
    if "Error" in result:
        await update.message.reply_text(f"❌ Failed to reboot: {result}")

@is_authorized
async def reboot_wan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Rebooting WAN connection...")
    result = execute_command(["ifdown", "wan"])
    if "Error" not in result:
        execute_command(["ifup", "wan"])
    else:
        await update.message.reply_text(f"❌ Failed to reboot WAN: {result}")

@is_authorized
async def wifi_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = execute_command(["uci", "set", "wireless.radio0.disabled=0"])
    if "Error" not in result:
        result += "\n" + execute_command(["uci", "commit", "wireless"])
        result += "\n" + execute_command(["wifi", "reload"])
    if "Error" in result:
        await update.message.reply_text(f"❌ Failed to turn WiFi ON: {result}")
    else:
        await update.message.reply_text("✅ WiFi turned ON successfully.")

@is_authorized
async def wifi_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = execute_command(["uci", "set", "wireless.radio0.disabled=1"])
    if "Error" not in result:
        result += "\n" + execute_command(["uci", "commit", "wireless"])
        result += "\n" + execute_command(["wifi", "reload"])
    if "Error" in result:
        await update.message.reply_text(f"❌ Failed to turn WiFi OFF: {result}")
    else:
        await update.message.reply_text("✅ WiFi turned OFF successfully.")

@is_authorized
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 *Command List:*
/status - Check router status
/devices - View connected devices
/block <MAC> - Block a device by MAC
/unblock <MAC> - Unblock a device by MAC
/reboot - Reboot the router
/reboot_wan - Reboot WAN connection
/wifi_on - Turn WiFi on
/wifi_off - Turn WiFi off
/help - Show this command list
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ================= AUTO CHECK =================
async def check_unknown_devices(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Starting unknown device check...")
    static_leases = get_static_leases()
    logger.info(f"Static MAC list: {static_leases}")
    
    dhcp_leases_output = execute_command(["cat", "/tmp/dhcp.leases"])
    if not dhcp_leases_output or "Error" in dhcp_leases_output:
        logger.error(f"Could not read /tmp/dhcp.leases: {dhcp_leases_output}")
        return
    dhcp_leases = dhcp_leases_output.strip().splitlines()
    logger.info(f"Number of DHCP leases: {len(dhcp_leases)}")
    
    unknown_devices = []
    for lease in dhcp_leases:
        parts = lease.split()
        logger.info(f"Processing lease: {lease}")
        if len(parts) >= 4:
            mac, ip, hostname = parts[1], parts[2], parts[3] if parts[3] != "*" else "No name"
            is_static = mac.lower() in map(str.lower, static_leases)
            is_online = is_device_online(ip)
            logger.info(f"MAC: {mac}, IP: {ip}, Hostname: {hostname}, Static: {is_static}, Online: {is_online}")
            if not is_static and is_online and mac not in reported_devices:
                vendor = get_mac_vendor(mac)
                unknown_devices.append((hostname, mac, ip, vendor))
                logger.info(f"New unknown device: {mac} - {ip} - {vendor}")

    if unknown_devices:
        message = "⚠️ *New Unknown Devices Detected:*\n\n" + "\n\n".join(
            f"📍 *Hostname*: {d[0]}\n📡 *MAC*: {d[1]}\n🔗 *IP*: {d[2]}\n🏭 *Vendor*: {d[3]}" for d in unknown_devices
        )
        logger.info(f"Preparing to send notification: {message}")
        for user_id in ALLOWED_USERS:
            try:
                await context.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                logger.info(f"Notification sent to {user_id}")
                reported_devices.update(d[1] for d in unknown_devices)
            except Exception as e:
                logger.error(f"Error sending notification to {user_id}: {e}")
    else:
        logger.info("No new unknown devices detected.")

def setup_auto_check(application):
    application.job_queue.run_repeating(check_unknown_devices, interval=300, first=10)

# ================= RUN BOT =================
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    await app.bot.set_my_commands([
        BotCommand("status", "Check router status"),
        BotCommand("devices", "List connected devices"),
        BotCommand("block", "Block a device by MAC"),
        BotCommand("unblock", "Unblock a device by MAC"),
        BotCommand("reboot", "Reboot the router"),
        BotCommand("reboot_wan", "Reboot WAN connection"),
        BotCommand("wifi_on", "Turn WiFi on"),
        BotCommand("wifi_off", "Turn WiFi off"),
        BotCommand("help", "Show command list"),
    ])

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("devices", devices))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))
    app.add_handler(CommandHandler("reboot", reboot))
    app.add_handler(CommandHandler("reboot_wan", reboot_wan))
    app.add_handler(CommandHandler("wifi_on", wifi_on))
    app.add_handler(CommandHandler("wifi_off", wifi_off))
    app.add_handler(CommandHandler("help", help_command))

    setup_auto_check(app)
    logger.info("Bot is running...")
    
    await app.initialize()
    await app.start()
    try:
        await app.updater.start_polling()
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
