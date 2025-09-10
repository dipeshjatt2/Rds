from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_world():
    # We use a raw triple-quoted string (r''') to embed the entire HTML file.
    # This preserves all newlines, quotes, and special characters in the CSS/JS blocks.
    return r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DO NOT ACTIVATE!</title>
    <style>
        /* General Setup */
        body {
            font-family: 'Comic Sans MS', 'Chalkboard SE', 'Marker Felt', sans-serif;
            text-align: center;
            background-color: #111;
            color: #fff;
            overflow: hidden;
            margin: 0;
            padding: 20px;
            transition: background-color 2s;
        }

        /* The Initial Chaos Zone */
        #chaos-zone {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 100;
            background: #000;
        }

        .chaos-item {
            position: absolute;
            font-size: 2rem;
            color: red;
            animation: fly-around 10s linear infinite, color-shift 3s infinite alternate;
        }

        /* The Main Content (Initially Hidden) */
        #main-content {
            display: none;
            opacity: 0;
            transition: opacity 1s ease-in-out;
            position: relative;
            z-index: 10;
        }

        h1 {
            font-size: 3rem;
            animation: text-glow 2s infinite alternate;
        }
        
        p {
            font-size: 1.5rem;
        }

        /* The Irreversible Toggle Switch */
        .switch {
            position: relative;
            display: inline-block;
            width: 90px;
            height: 44px;
            margin: 20px;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #c0392b; /* Red for OFF */
            transition: .4s;
            border-radius: 34px;
        }

        .slider:before {
            position: absolute;
            content: "OFF";
            height: 36px;
            width: 36px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
            color: #c0392b;
            font-weight: bold;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        input:checked + .slider {
            background-color: #2ecc71; /* Green for ON */
        }

        input:checked + .slider:before {
            transform: translateX(46px);
            content: "ON";
            color: #2ecc71;
        }
        
        /* Message after the trap is sprung */
        #trap-message {
            margin-top: 20px;
            font-size: 2rem;
            color: #f1c40f;
            font-weight: bold;
            transform: scale(0);
            transition: transform 0.5s cubic-bezier(0.68, -0.55, 0.27, 1.55);
        }

        /* Animations */
        @keyframes fly-around {
            0% { transform: translate(0, 0) rotate(0deg); }
            25% { transform: translate(40vw, 50vh) rotate(90deg); }
            50% { transform: translate(80vw, 10vh) rotate(180deg); }
            75% { transform: translate(20vw, 80vh) rotate(270deg); }
            100% { transform: translate(0, 0) rotate(360deg); }
        }
        
        @keyframes color-shift {
            from { color: hsl(0, 100%, 50%); }
            to { color: hsl(360, 100%, 50%); }
        }
        
        @keyframes text-glow {
            from { text-shadow: 0 0 10px #fff, 0 0 20px #fff, 0 0 30px #ff00de; }
            to { text-shadow: 0 0 20px #fff, 0 0 30px #ff00de, 0 0 40px #ff00de; }
        }
        
        /* The final state animation */
        .party-mode-active {
            animation: screen-shake 0.5s infinite;
        }
        
        @keyframes screen-shake {
            0% { transform: translate(2px, 2px) rotate(0deg); }
            10% { transform: translate(-2px, -4px) rotate(-1deg); }
            20% { transform: translate(-6px, 0px) rotate(1deg); }
            30% { transform: translate(6px, 4px) rotate(0deg); }
            40% { transform: translate(2px, -2px) rotate(1deg); }
            50% { transform: translate(-2px, 4px) rotate(-1deg); }
            60% { transform: translate(-6px, 2px) rotate(0deg); }
            70% { transform: translate(6px, 2px) rotate(-1deg); }
            80% { transform: translate(-2px, -2px) rotate(1deg); }
            90% { transform: translate(2px, 4px) rotate(0deg); }
            100% { transform: translate(0px, -4px) rotate(-1deg); }
        }

    </style>
</head>
<body>

    <div id="chaos-zone">
        </div>

    <div id="main-content">
        <h1>THE CHAOS IS... A LOT.</h1>
        <p>It's okay. You can fix this.</p>
        <p>Just toggle the button to turn on the bot and restore order.</p>
        
        <label class="switch">
            <input type="checkbox" id="bot-toggle">
            <span class="slider"></span>
        </label>

        <h2 id="trap-message"></h2>
    </div>

    <script>
        // --- STEP 1: Create the initial chaos ---
        const chaosZone = document.getElementById('chaos-zone');
        const emojis = ['🤯', '💥', '🤖', '🔥', '🚨', 'WTF', '🤪', 'SOS'];
        for (let i = 0; i < 30; i++) {
            let chaosItem = document.createElement('div');
            chaosItem.classList.add('chaos-item');
            chaosItem.innerText = emojis[Math.floor(Math.random() * emojis.length)];
            chaosItem.style.top = `${Math.random() * 100}vh`;
            chaosItem.style.left = `${Math.random() * 100}vw`;
            chaosItem.style.animationDuration = `${Math.random() * 5 + 5}s`;
            chaosItem.style.fontSize = `${Math.random() * 3 + 1}rem`;
            chaosZone.appendChild(chaosItem);
        }

        // --- STEP 2: Reveal the main content after a delay ---
        const mainContent = document.getElementById('main-content');
        setTimeout(() => {
            chaosZone.style.display = 'none';
            mainContent.style.display = 'block';
            setTimeout(() => mainContent.style.opacity = 1, 50); // fade in
        }, 4000); // 4 seconds of chaos


        // --- STEP 3: The Trap ---
        const toggle = document.getElementById('bot-toggle');
        const trapMessage = document.getElementById('trap-message');
        const h1 = document.querySelector('h1');
        const p = document.querySelectorAll('p');

        toggle.addEventListener('change', function() {
            if (this.checked) {
                // THE POINT OF NO RETURN!
                this.disabled = true; // Can't uncheck it now, muhahaha!

                // Change all the text
                h1.innerText = "BOT ACTIVATED!";
                p[0].innerText = "You thought that would help? Foolish mortal.";
                p[1].innerText = "The bot is now in control. There is no escape.";
                
                // Show the final message
                trapMessage.innerText = "ENJOY THE PERMANENT PARTY 🎉";
                trapMessage.style.transform = 'scale(1)';

                // Unleash final, eternal chaos
                document.body.classList.add('party-mode-active');
                document.body.style.backgroundColor = '#5D3FD3'; // Funky purple
            }
        });
    </script>

</body>
</html>
'''


if __name__ == "__main__":
    app.run(debug=True) # Added debug=True for development convenience
