from flask import Flask, render_template_string
import datetime

app = Flask(__name__)

# Bot information
BOT_INFO = {
    "name": "DrMDipesh Bot",
    "username": "@drmdipeshbot",
    "description": "A multi-functional Telegram bot with AI capabilities, CC checking, and generation features.",
    "features": [
        "🤖 AI Assistant powered by Gemini Flash",
        "💳 Credit Card validation and checking",
        "🔄 CC Generation with BIN lookup",
        "📁 Mass CC checking from files",
        "👤 Fake identity generation",
        "⚡ Fast and reliable processing"
    ],
    "owner": "@andr0idpie9",
    "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ bot_info.name }} - Status</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary: #6c5ce7;
            --secondary: #a29bfe;
            --dark: #2d3436;
            --light: #f5f6fa;
            --success: #00b894;
            --warning: #fdcb6e;
            --danger: #d63031;
            --info: #0984e3;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Poppins', sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            max-width: 900px;
            width: 100%;
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            padding: 30px;
            text-align: center;
            position: relative;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            font-weight: 600;
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .status-badge {
            position: absolute;
            top: 20px;
            right: 20px;
            background: var(--success);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .status-badge .pulse {
            width: 10px;
            height: 10px;
            background: white;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 1; }
            50% { transform: scale(1.1); opacity: 0.7; }
            100% { transform: scale(0.95); opacity: 1; }
        }
        
        .content {
            padding: 30px;
        }
        
        .section {
            margin-bottom: 30px;
        }
        
        .section h2 {
            color: var(--primary);
            margin-bottom: 15px;
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .section h2 i {
            font-size: 1.3rem;
        }
        
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
        }
        
        .feature-card {
            background: var(--light);
            border-radius: 10px;
            padding: 20px;
            display: flex;
            align-items: flex-start;
            gap: 15px;
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        .feature-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }
        
        .feature-icon {
            font-size: 1.5rem;
            color: var(--primary);
        }
        
        .feature-text h3 {
            font-size: 1.1rem;
            margin-bottom: 5px;
            color: var(--dark);
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .stat-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
            text-align: center;
            border-top: 4px solid var(--primary);
        }
        
        .stat-card h3 {
            font-size: 2rem;
            color: var(--primary);
            margin-bottom: 5px;
        }
        
        .stat-card p {
            color: var(--dark);
            opacity: 0.8;
            font-size: 0.9rem;
        }
        
        .btn {
            display: inline-block;
            background: var(--primary);
            color: white;
            padding: 12px 25px;
            border-radius: 30px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s;
            border: none;
            cursor: pointer;
            font-size: 1rem;
            margin-top: 10px;
        }
        
        .btn:hover {
            background: var(--secondary);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(108, 92, 231, 0.3);
        }
        
        .btn i {
            margin-right: 8px;
        }
        
        .footer {
            text-align: center;
            padding: 20px;
            border-top: 1px solid rgba(0, 0, 0, 0.1);
            color: var(--dark);
            opacity: 0.7;
            font-size: 0.9rem;
        }
        
        @media (max-width: 768px) {
            .header h1 {
                font-size: 2rem;
            }
            
            .features {
                grid-template-columns: 1fr;
            }
            
            .stats {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="status-badge">
                <div class="pulse"></div>
                <span>BOT IS RUNNING</span>
            </div>
            <h1>{{ bot_info.name }}</h1>
            <p>{{ bot_info.username }} | {{ bot_info.description }}</p>
        </div>
        
        <div class="content">
            <div class="section">
                <h2><i class="fas fa-rocket"></i> Bot Features</h2>
                <div class="features">
                    {% for feature in bot_info.features %}
                    <div class="feature-card">
                        <div class="feature-icon">
                            <i class="fas fa-{{ 'check-circle' if 'AI' in feature else 'credit-card' if 'CC' in feature else 'user' if 'identity' in feature else 'bolt' }}"></i>
                        </div>
                        <div class="feature-text">
                            <h3>{{ feature.split(' ')[0] }}</h3>
                            <p>{{ ' '.join(feature.split(' ')[1:]) }}</p>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            
            <div class="section">
                <h2><i class="fas fa-chart-line"></i> Bot Statistics</h2>
                <div class="stats">
                    <div class="stat-card">
                        <h3>24/7</h3>
                        <p>Uptime</p>
                    </div>
                    <div class="stat-card">
                        <h3>100%</h3>
                        <p>Reliability</p>
                    </div>
                    <div class="stat-card">
                        <h3>Fast</h3>
                        <p>Performance</p>
                    </div>
                    <div class="stat-card">
                        <h3>{{ bot_info.start_time }}</h3>
                        <p>Last Started</p>
                    </div>
                </div>
            </div>
            
            <div class="section" style="text-align: center;">
                <a href="https://t.me/{{ bot_info.username[1:] }}" class="btn">
                    <i class="fab fa-telegram"></i> Start Using Bot
                </a>
            </div>
        </div>
        
        <div class="footer">
            <p>Developed by {{ bot_info.owner }} | © {{ now.year }} All Rights Reserved</p>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE, 
                               bot_info=BOT_INFO,
                               now=datetime.datetime.now())

if __name__ == "__main__":
    app.run()
