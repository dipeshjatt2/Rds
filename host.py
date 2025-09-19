import os
import shutil
import subprocess
import uuid
import requests
import zipfile
from pyrogram import Client, filters
from pyrogram.types import Message

# Replace with your actual API ID and API Hash
API_ID = 22118129  # Your API ID
API_HASH = "43c66e3314921552d9330a4b05b18800"  # Your API Hash
BOT_TOKEN = os.environ.get('hosttok')

# Create directories if not exist
os.makedirs("bots", exist_ok=True)

# Dictionary to track running bots: bot_id -> {'process': Popen, 'dir': str, 'user_id': int}
running_bots = {}

app = Client("hosting_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    help_text = """
🤖 Telegram Bot Hosting Service

Commands:
• /host - Reply to a .py file, .zip file, or a message with GitHub repo URL to host it
• /stop <bot_id> - Stop a running bot
• /list - Show your running bots
• /logs <bot_id> - View bot logs
• /install <lib> - Install Python libraries
• /help - Show this message

Rules:
• Network access is allowed
    """
    await message.reply(help_text)


@app.on_message(filters.command("host"))
async def host_command(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply("Please reply to a .py file, .zip file, or a GitHub repo URL.")
        return

    reply = message.reply_to_message
    user_id = message.from_user.id
    bot_id = str(uuid.uuid4())[:8]
    bot_dir = f"bots/{bot_id}"
    os.makedirs(bot_dir, exist_ok=True)
    log_file = f"{bot_dir}/log.txt"

    try:
        if reply.document:
            file_name = reply.document.file_name
            if file_name.endswith('.py'):
                # Download single .py file
                downloaded_path = await reply.download()
                shutil.move(downloaded_path, f"{bot_dir}/main.py")
            elif file_name.endswith('.zip'):
                # Download and unzip .zip file
                downloaded_path = await reply.download()
                shutil.unpack_archive(downloaded_path, bot_dir)
                os.remove(downloaded_path)
            else:
                await message.reply("Unsupported file type. Please send .py or .zip.")
                shutil.rmtree(bot_dir)
                return
        elif reply.text and 'github.com' in reply.text:
            # Handle GitHub repo URL
            repo_url = reply.text.strip()
            if not repo_url.endswith('/'):
                repo_url += '/'
            zip_url = repo_url + "archive/refs/heads/main.zip"  # Assuming main branch
            response = requests.get(zip_url)
            if response.status_code != 200:
                await message.reply("Failed to download GitHub repo zip.")
                shutil.rmtree(bot_dir)
                return
            zip_path = f"{bot_dir}/repo.zip"
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            shutil.unpack_archive(zip_path, bot_dir)
            os.remove(zip_path)
            # Move contents from subdir if needed (GitHub zip creates a subfolder)
            subdirs = [d for d in os.listdir(bot_dir) if os.path.isdir(os.path.join(bot_dir, d))]
            if subdirs:
                subdir = os.path.join(bot_dir, subdirs[0])
                for item in os.listdir(subdir):
                    shutil.move(os.path.join(subdir, item), bot_dir)
                shutil.rmtree(subdir)
        else:
            await message.reply("Please reply to a valid file or GitHub URL.")
            shutil.rmtree(bot_dir)
            return

        # Check if main.py exists
        if not os.path.exists(f"{bot_dir}/main.py"):
            await message.reply("No main.py found in the provided files.")
            shutil.rmtree(bot_dir)
            return

        # Run the bot in subprocess
        with open(log_file, 'w') as log:
            process = subprocess.Popen(["python", "main.py"], cwd=bot_dir, stdout=log, stderr=subprocess.STDOUT)

        running_bots[bot_id] = {'process': process, 'dir': bot_dir, 'user_id': user_id}
        await message.reply(f"Bot hosted successfully with ID: {bot_id}")

    except Exception as e:
        await message.reply(f"Error hosting bot: {str(e)}")
        shutil.rmtree(bot_dir)


@app.on_message(filters.command("stop"))
async def stop_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: /stop <bot_id>")
        return

    bot_id = message.command[1]
    user_id = message.from_user.id

    if bot_id not in running_bots or running_bots[bot_id]['user_id'] != user_id:
        await message.reply("Bot not found or you don't own it.")
        return

    bot_info = running_bots[bot_id]
    bot_info['process'].kill()
    bot_info['process'].wait()  # Ensure process is terminated
    shutil.rmtree(bot_info['dir'])
    del running_bots[bot_id]
    await message.reply(f"Bot {bot_id} stopped and removed.")


@app.on_message(filters.command("list"))
async def list_command(client: Client, message: Message):
    user_id = message.from_user.id
    user_bots = [bot_id for bot_id, info in running_bots.items() if info['user_id'] == user_id]

    if not user_bots:
        await message.reply("You have no running bots.")
        return

    bot_list = "\n".join(user_bots)
    await message.reply(f"Your running bots:\n{bot_list}")


@app.on_message(filters.command("logs"))
async def logs_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: /logs <bot_id>")
        return

    bot_id = message.command[1]
    user_id = message.from_user.id

    if bot_id not in running_bots or running_bots[bot_id]['user_id'] != user_id:
        await message.reply("Bot not found or you don't own it.")
        return

    log_file = f"{running_bots[bot_id]['dir']}/log.txt"
    if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
        await message.reply_document(log_file, caption=f"Logs for bot {bot_id}")
    else:
        await message.reply("No logs available yet.")


@app.on_message(filters.command("install"))
async def install_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: /install <library>")
        return

    lib = message.command[1]
    try:
        result = subprocess.run(["pip", "install", lib], capture_output=True, text=True)
        if result.returncode == 0:
            await message.reply(f"Installed {lib} successfully.")
        else:
            await message.reply(f"Error installing {lib}: {result.stderr}")
    except Exception as e:
        await message.reply(f"Error: {str(e)}")


app.run()
