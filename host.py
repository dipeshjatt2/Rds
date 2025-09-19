import os
import uuid
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# --- CONFIGURATION ---
# Replace these with your own values
API_ID = 22118129  # Your API ID from my.telegram.org
API_HASH = "43c66e3314921552d9330a4b05b18800"  # Your API Hash from my.telegram.org
BOT_TOKEN = os.environ.get("hosttok")  # Your bot token from @BotFather

# --- BOT OWNER ---
# Only this user can use the hosting commands
OWNER_ID = 5203820046

# A dictionary to store information about running bot processes
running_bots = {}

# The directory to store hosted bot files and logs
HOSTED_BOTS_DIR = "hosted_bots"

# Initialize the Pyrogram Client
app = Client("bot_hosting_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- HELP MESSAGE ---
HELP_TEXT = """
🤖 **Welcome to your Personal Bot Hosting Service!**

You can host your Python Telegram bots by sending me the `.py` file.

**Commands:**
• `/host` - Reply to a `.py` file to host it.
• `/stop <bot_id>` - Stop a running bot instance.
• `/list` - Show all your currently running bots.
• `/logs <bot_id>` - Get the latest logs for a specific bot.
• `/help` - Show this help message.

**Rules:**
• Your main script file must be a `.py` file.
• Network access is allowed.

⚠️ **Disclaimer:** Running untrusted code is risky. Only host bots from sources you trust.
"""

# --- COMMAND HANDLERS ---

@app.on_message(filters.command("start"))
async def start_command(_, message: Message):
    """Handler for the /start command."""
    await message.reply_text(
        f"👋 Hello, {message.from_user.first_name}!\n\n"
        "This is your personal bot hosting service. "
        "Send /help to see all available commands."
    )

@app.on_message(filters.command("help"))
async def help_command(_, message: Message):
    """Handler for the /help command."""
    await message.reply_text(HELP_TEXT)


@app.on_message(filters.command("host") & filters.user(OWNER_ID))
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

    bot_id = str(uuid.uuid4())[:8]  # Generate a short, unique ID
    bot_dir = os.path.join(HOSTED_BOTS_DIR, bot_id)
    os.makedirs(bot_dir, exist_ok=True)
    
    file_path = os.path.join(bot_dir, doc.file_name)
    log_path = os.path.join(bot_dir, f"{bot_id}.log")

    try:
        # Download the bot script
        await app.download_media(message.reply_to_message, file_name=file_path)

        # Open log file
        log_file_handle = open(log_path, 'w')

        # Start the bot script as a new process
        process = await asyncio.create_subprocess_exec(
            'python3', file_path,
            stdout=log_file_handle,
            stderr=log_file_handle,
            cwd=bot_dir # Set the working directory for the bot
        )

        # Store the process info
        running_bots[bot_id] = {
            "process": process,
            "owner_id": message.from_user.id,
            "dir_path": bot_dir,
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
        # Clean up if setup failed
        if os.path.exists(bot_dir):
            import shutil
            shutil.rmtree(bot_dir)


@app.on_message(filters.command("stop") & filters.user(OWNER_ID))
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
    
    try:
        # Terminate the process
        bot_info["process"].terminate()
        await bot_info["process"].wait() # Wait for the process to fully close
        
        # Close log file handle
        bot_info["log_handle"].close()

        # Clean up the entire directory for that bot
        if os.path.exists(bot_info["dir_path"]):
            import shutil
            shutil.rmtree(bot_info["dir_path"])

        # Remove from tracking
        del running_bots[bot_id]

        await message.reply_text(f"✅ **Bot `{bot_id}` has been stopped and all related files have been deleted.**")
    except Exception as e:
        await message.reply_text(f"❌ **Error stopping bot:**\n`{e}`")


@app.on_message(filters.command("list") & filters.user(OWNER_ID))
async def list_bots(_, message: Message):
    """Lists all bots run by the user."""
    if not running_bots:
        await message.reply_text("You have no bots running currently.")
        return

    response = "🤖 **Your Running Bots:**\n\n"
    for bot_id in running_bots:
        response += f"• `{bot_id}`\n"

    await message.reply_text(response)


@app.on_message(filters.command("logs") & filters.user(OWNER_ID))
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
    log_path = bot_info["log_path"]
    
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        # Check if the process is still alive
        if bot_info["process"].returncode is None:
            await message.reply_text(f"✅ Bot `{bot_id}` is running. Log file is currently empty.")
        else:
            await message.reply_text(f"❌ Bot `{bot_id}` is not running (Exit Code: {bot_info['process'].returncode}). Log file is empty.")
        return

    # Flush the buffer to make sure all logs are written to the file
    bot_info["log_handle"].flush()

    try:
        # If logs are too long, send as a file
        if os.path.getsize(log_path) > 4000:
            await message.reply_document(log_path, caption=f"Logs for bot `{bot_id}`")
        else:
            with open(log_path, "r") as f:
                log_content = f.read().strip()
            if not log_content:
                await message.reply_text(f"Log file for `{bot_id}` is empty.")
            else:
                await message.reply_text(f"📜 **Logs for `{bot_id}`:**\n\n```{log_content}```")
    except Exception as e:
        await message.reply_text(f"❌ **Error reading logs:**\n`{e}`")


async def main():
    """Main function to start the bot."""
    # Create the directory for hosted bots if it doesn't exist
    os.makedirs(HOSTED_BOTS_DIR, exist_ok=True)
    
    if not BOT_TOKEN:
        print("Error: Bot token not found. Please set the 'hosttok' environment variable.")
        return

    print("Starting the bot hosting service...")
    await app.start()
    print("Bot is running!")
    await asyncio.Event().wait() # Keep the bot running indefinitely

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")

