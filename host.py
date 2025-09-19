import os
import uuid
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# --- CONFIGURATION ---
# Replace these with your own values
API_ID = 22118129 # Your API ID from my.telegram.org
API_HASH = "43c66e3314921552d9330a4b05b18800"  # Your API Hash from my.telegram.org
BOT_TOKEN = os.environ.get("hosttok")  # Your bot token from @BotFather
# --- END CONFIGURATION ---

# A dictionary to store information about running bot processes
running_bots = {}

# The directory to store hosted bot files and logs
HOSTED_BOTS_DIR = "hosted_bots"

# Initialize the Pyrogram Client
app = Client("bot_hosting_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- HELP MESSAGE ---
HELP_TEXT = """
🤖 **Welcome to the Bot Hosting Service!**

You can host your Python Telegram bots by sending me the `.py` file.

**Commands:**
• `/host` - Reply to a `.py` file or a zip archive to host it.
• `/stop <bot_id>` - Stop a running bot instance.
• `/list` - Show all your currently running bots.
• `/logs <bot_id>` - Get the latest logs for a specific bot.
• `/install <library_name>` - Install a Python library using pip.
• `/help` - Show this help message.

**Rules:**
• Your main script file must be a `.py` file.
• Network access is allowed.

⚠️ **Disclaimer:** Running untrusted code is risky. Only host bots from sources you trust.
"""

@app.on_message(filters.command("start"))
async def start_command(_, message: Message):
    """Handler for the /start command."""
    await message.reply_text(
        f"👋 Hello, {message.from_user.first_name}!\n\n"
        "I can host your Pyrogram or Telethon bots for you. "
        "Send /help to see all available commands."
    )

@app.on_message(filters.command("help"))
async def help_command(_, message: Message):
    """Handler for the /help command."""
    await message.reply_text(HELP_TEXT)


@app.on_message(filters.command("host"))
async def host_bot(_, message: Message):
    """Hosts a new bot from a .py file."""
    if not message.reply_to_message or not message.reply_to_message.document:
        await message.reply_text("❌ **Error:** Please reply to a `.py` file to host it.")
        return

    doc = message.reply_to_message.document
    if not doc.file_name.endswith(".py"):
        await message.reply_text("❌ **Error:** Only `.py` files are supported.")
        return

    status_msg = await message.reply_text("📥 Downloading and setting up your bot...")

    bot_id = str(uuid.uuid4())[:8]  # Generate a short, unique ID for the bot
    file_path = os.path.join(HOSTED_BOTS_DIR, f"{bot_id}.py")
    log_path = os.path.join(HOSTED_BOTS_DIR, f"{bot_id}.log")

    try:
        # Download the bot script
        await app.download_media(message.reply_to_message, file_name=file_path)

        # Open log file
        log_file_handle = open(log_path, 'w')

        # Start the bot script as a new process
        process = await asyncio.create_subprocess_exec(
            'python3', file_path,
            stdout=log_file_handle,
            stderr=log_file_handle
        )

        # Store the process info
        running_bots[bot_id] = {
            "process": process,
            "owner_id": message.from_user.id,
            "file_path": file_path,
            "log_path": log_path,
            "log_handle": log_file_handle,
        }

        await status_msg.edit_text(
            f"✅ **Bot Hosted Successfully!**\n\n"
            f"Your bot is now running.\n"
            f"🆔 **Bot ID:** `{bot_id}`\n\n"
            f"Use `/logs {bot_id}` to check its status or `/stop {bot_id}` to stop it."
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ **Failed to host bot:**\n`{e}`")


@app.on_message(filters.command("stop"))
async def stop_bot(_, message: Message):
    """Stops a running bot instance."""
    if len(message.command) < 2:
        await message.reply_text("Usage: `/stop <bot_id>`")
        return

    bot_id = message.command[1]
    if bot_id not in running_bots:
        await message.reply_text(f"❌ **Error:** No bot found with ID `{bot_id}`.")
        return

    bot_info = running_bots[bot_id]
    if bot_info["owner_id"] != message.from_user.id:
        await message.reply_text("🚫 **Access Denied:** You are not the owner of this bot.")
        return

    try:
        # Terminate the process
        bot_info["process"].terminate()
        await bot_info["process"].wait() # Wait for the process to fully close
        
        # Close log file handle
        bot_info["log_handle"].close()

        # Clean up files
        if os.path.exists(bot_info["file_path"]):
            os.remove(bot_info["file_path"])
        if os.path.exists(bot_info["log_path"]):
            os.remove(bot_info["log_path"])

        # Remove from tracking
        del running_bots[bot_id]

        await message.reply_text(f"✅ **Bot `{bot_id}` has been stopped and all related files have been deleted.**")
    except Exception as e:
        await message.reply_text(f"❌ **Error stopping bot:**\n`{e}`")


@app.on_message(filters.command("list"))
async def list_bots(_, message: Message):
    """Lists all bots run by the user."""
    user_id = message.from_user.id
    user_bots = [bot_id for bot_id, info in running_bots.items() if info["owner_id"] == user_id]

    if not user_bots:
        await message.reply_text("You have no bots running currently.")
        return

    response = "🤖 **Your Running Bots:**\n\n"
    for bot_id in user_bots:
        response += f"• `{bot_id}`\n"

    await message.reply_text(response)


@app.on_message(filters.command("logs"))
async def get_logs(_, message: Message):
    """Retrieves logs for a specific bot."""
    if len(message.command) < 2:
        await message.reply_text("Usage: `/logs <bot_id>`")
        return

    bot_id = message.command[1]
    if bot_id not in running_bots:
        await message.reply_text(f"❌ **Error:** No bot found with ID `{bot_id}`.")
        return

    bot_info = running_bots[bot_id]
    if bot_info["owner_id"] != message.from_user.id:
        await message.reply_text("🚫 **Access Denied:** You are not the owner of this bot.")
        return

    log_path = bot_info["log_path"]
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        await message.reply_text(f"Log file for bot `{bot_id}` is empty or does not exist.")
        return

    # Flush the buffer to make sure all logs are written to the file
    bot_info["log_handle"].flush()

    try:
        with open(log_path, "r") as f:
            log_content = f.read()

        # If logs are too long, send as a file
        if len(log_content) > 4000:
            await message.reply_document(log_path, caption=f"Logs for bot `{bot_id}`")
        else:
            await message.reply_text(f"📜 **Logs for `{bot_id}`:**\n\n```{log_content[-3500:]}```")
    except Exception as e:
        await message.reply_text(f"❌ **Error reading logs:**\n`{e}`")


@app.on_message(filters.command("install"))
async def install_lib(_, message: Message):
    """Installs a Python library using pip."""
    if len(message.command) < 2:
        await message.reply_text("Usage: `/install <library_name>`")
        return
    
    lib_name = message.command[1]
    status_msg = await message.reply_text(f"⏳ Installing `{lib_name}`...")

    try:
        process = await asyncio.create_subprocess_exec(
            'pip', 'install', lib_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        output = (stdout.decode() + stderr.decode()).strip()

        if process.returncode == 0:
            await status_msg.edit_text(
                f"✅ **Successfully installed `{lib_name}`!**\n\n"
                f"**Output:**\n`{output}`"
            )
        else:
            await status_msg.edit_text(
                f"❌ **Failed to install `{lib_name}`.**\n\n"
                f"**Error:**\n`{output}`"
            )
    except Exception as e:
        await status_msg.edit_text(f"❌ **An error occurred:**\n`{e}`")


async def main():
    """Main function to start the bot."""
    # Create the directory for hosted bots if it doesn't exist
    if not os.path.isdir(HOSTED_BOTS_DIR):
        os.makedirs(HOSTED_BOTS_DIR)
        
    print("Starting the bot hosting service...")
    await app.start()
    print("Bot is running!")
    await asyncio.Event().wait() # Keep the bot running indefinitely

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
