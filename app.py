from flask import Flask, render_template_string

app = Flask(__name__)

@app.route("/")
def home():
    # Use an inline HTML template with basic info about your bot
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DIPESHCHOUDHARYBOT - Bot Overview</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f8f9fa; color: #333; text-align: center; margin: 0; padding: 0; }
            .container { max-width: 700px; margin: 40px auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
            h1 { color: #007bff; }
            ul { text-align: left; }
            .footer { margin-top: 20px; font-size: 14px; color: #555; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 DIPESHCHOUDHARYBOT</h1>
            <p><strong>Username:</strong> <a href="https://t.me/DIPESHCHOUDHARYBOT" target="_blank">@DIPESHCHOUDHARYBOT</a></p>
            <p><strong>Developer:</strong> <a href="https://t.me/dipesh_choudhary_rj" target="_blank">@dipesh_choudhary_rj</a></p>
            
            <h3>✨ What this bot can do:</h3>
            <ul>
                <li>📌 <b>/start</b> – Show welcome message</li>
                <li>📌 <b>/create</b> – Create a quiz manually</li>
                <li>📌 <b>/txqz</b> – Convert text or file into Telegram quiz polls</li>
                <li>📌 <b>/htmk</b> – Convert text/CSV questions into interactive HTML quiz</li>
                <li>📌 <b>/shufftxt</b> – Shuffle questions and options in .txt/.csv files</li>
            </ul>

            <p>This bot is built using <b>Pyrogram</b> and Flask, designed for quiz creation, conversion, and automation.</p>

            <div class="footer">
                🚀 Hosted with ❤️ – Flask is running
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    # Make Flask accessible on all network interfaces, useful for deployment
    app.run(host="0.0.0.0", port=5000)
