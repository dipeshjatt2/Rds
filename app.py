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
    <title>Bot Activation Protocol v2.0</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --glow-color: #00bfff;
            --warning-color: #ff4d4d;
            --success-color: #76ff03;
        }

        body {
            font-family: 'Rajdhani', sans-serif;
            background-color: #0a192f;
            color: #e6f1ff;
            overflow: hidden;
        }

        /* Animated background canvas */
        #matrix-bg {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            opacity: 0.3;
        }

        /* Glassmorphism effect for the main panel */
        .glass-panel {
            background: rgba(10, 25, 47, 0.7);
            backdrop-filter: blur(15px);
            -webkit-backdrop-filter: blur(15px);
            border: 1px solid rgba(0, 191, 255, 0.3);
            box-shadow: 0 0 40px rgba(0, 191, 255, 0.2);
            transition: transform 0.1s ease-out; /* For 3D tilt effect */
        }

        /* Styling for the custom toggle switch */
        .toggle-switch {
            position: relative;
            display: inline-block;
            width: 60px;
            height: 34px;
        }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(0, 191, 255, 0.4);
            transition: .4s;
            border-radius: 34px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 26px; width: 26px;
            left: 4px; bottom: 3px;
            background-color: #ccc;
            transition: .4s;
            border-radius: 50%;
        }
        input:checked + .slider { background-color: var(--glow-color); box-shadow: 0 0 15px var(--glow-color); }
        input:checked + .slider:before { transform: translateX(26px); background-color: white; }
        input:disabled + .slider { cursor: not-allowed; background-color: rgba(100,100,100,0.5); border-color: rgba(150,150,150,0.5); }
        input:disabled + .slider:before { background-color: #555; }

        /* Glowing and flickering text effects */
        .glow {
            color: var(--glow-color);
            text-shadow: 0 0 5px var(--glow-color), 0 0 10px var(--glow-color), 0 0 15px var(--glow-color);
            animation: glow-pulse 1.5s infinite alternate;
        }
        .warning-text {
            color: var(--warning-color);
            text-shadow: 0 0 4px var(--warning-color), 0 0 11px var(--warning-color), 0 0 19px var(--warning-color);
            animation: text-flicker 3s linear infinite;
        }

        /* Status indicators */
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
            transition: all 0.4s ease;
            box-shadow: 0 0 8px;
        }
        .status-offline { background-color: #ff4d4d; box-shadow: 0 0 8px #ff4d4d; }
        .status-online { background-color: #76ff03; box-shadow: 0 0 12px #76ff03; animation: pulse-green 2s infinite; }

        /* Progress Bar */
        .progress-bar-container {
            background-color: rgba(0,0,0,0.4);
            border-radius: 10px;
            border: 1px solid rgba(0, 191, 255, 0.3);
            padding: 4px;
        }
        .progress-bar-fill {
            height: 12px;
            width: 0%;
            background-color: var(--glow-color);
            border-radius: 6px;
            transition: width 0.5s ease-in-out;
            box-shadow: 0 0 10px var(--glow-color);
        }
        
        /* Console Log styling */
        .console-log {
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(0, 191, 255, 0.2);
            height: 100px;
            overflow-y: auto;
            text-align: left;
            padding: 10px;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.8rem;
            border-radius: 8px;
            margin-top: 20px;
        }
        .console-log p { margin-bottom: 4px; }
        .log-entry-init { color: #f2a2a2; }
        .log-entry-success { color: #76ff03; }
        .log-entry-info { color: #00bfff; }


        /* Animations */
        @keyframes glow-pulse {
            from { text-shadow: 0 0 5px var(--glow-color), 0 0 10px var(--glow-color); }
            to { text-shadow: 0 0 10px var(--glow-color), 0 0 20px var(--glow-color); }
        }
        @keyframes text-flicker {
            0%, 18%, 22%, 25%, 53%, 57%, 100% { text-shadow: 0 0 4px var(--warning-color), 0 0 11px var(--warning-color); color: var(--warning-color); }
            20%, 24%, 55% { text-shadow: none; color: #f2a2a2; }
        }
        @keyframes pulse-green {
            0% { transform: scale(1); box-shadow: 0 0 8px #76ff03; }
            50% { transform: scale(1.1); box-shadow: 0 0 15px #76ff03; }
            100% { transform: scale(1); box-shadow: 0 0 8px #76ff03; }
        }
    </style>
</head>
<body class="flex items-center justify-center min-h-screen p-4">

    <canvas id="matrix-bg"></canvas>

    <div class="glass-panel w-full max-w-3xl rounded-2xl p-6 md:p-8 text-center relative z-10" id="control-panel">
        
        <h1 class="text-3xl md:text-4xl font-bold uppercase tracking-widest glow mb-2">
            Bot Activation Protocol v2.0
        </h1>
        <p class="text-red-400 font-semibold text-lg mb-6 warning-text" id="status-message">
            SYSTEM CRITICAL: MULTIPLE SUBSYSTEM FAILURES
        </p>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div class="bg-black/20 rounded-xl p-4 text-left">
                <p class="font-semibold text-gray-300">Core Processor</p>
                <div class="flex items-center justify-between mt-2">
                    <div class="flex items-center">
                        <span class="status-indicator status-offline" id="core-status"></span>
                        <span class="font-bold text-lg">OFFLINE</span>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox" class="subsystem-toggle" data-system="core">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>
            <div class="bg-black/20 rounded-xl p-4 text-left">
                <p class="font-semibold text-gray-300">Neural Network</p>
                <div class="flex items-center justify-between mt-2">
                    <div class="flex items-center">
                        <span class="status-indicator status-offline" id="neural-status"></span>
                        <span class="font-bold text-lg">OFFLINE</span>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox" class="subsystem-toggle" data-system="neural">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>
            <div class="bg-black/20 rounded-xl p-4 text-left">
                <p class="font-semibold text-gray-300">Power Grid</p>
                <div class="flex items-center justify-between mt-2">
                    <div class="flex items-center">
                        <span class="status-indicator status-offline" id="power-status"></span>
                        <span class="font-bold text-lg">OFFLINE</span>
                    </div>
                    <label class="toggle-switch">
                        <input type="checkbox" class="subsystem-toggle" data-system="power">
                        <span class="slider"></span>
                    </label>
                </div>
            </div>
        </div>

        <div class="bg-black/20 rounded-xl p-6 mb-6">
            <p class="text-lg font-semibold text-gray-300 mb-3">System Stabilization Progress</p>
            <div class="progress-bar-container mb-4">
                <div class="progress-bar-fill" id="progress-bar"></div>
            </div>
            <div class="flex flex-col sm:flex-row items-center justify-between gap-4">
                <div class="text-left">
                    <p class="text-xl font-semibold text-gray-300">Main Bot Status:</p>
                    <p class="text-2xl font-bold" id="bot-status">AWAITING INPUT</p>
                </div>
                <label class="toggle-switch">
                    <input type="checkbox" id="bot-toggle" disabled>
                    <span class="slider"></span>
                </label>
            </div>
        </div>

        <div class="console-log" id="console-log">
            <p class="log-entry-init">> Initializing protocol... STANDBY</p>
        </div>
    </div>

    <script>
        // --- DOM ELEMENT SELECTORS ---
        const controlPanel = document.getElementById('control-panel');
        const botToggle = document.getElementById('bot-toggle');
        const statusMessage = document.getElementById('status-message');
        const botStatus = document.getElementById('bot-status');
        const progressBar = document.getElementById('progress-bar');
        const consoleLog = document.getElementById('console-log');
        const subsystemToggles = document.querySelectorAll('.subsystem-toggle');

        // --- GAME STATE ---
        const systemState = {
            core: false,
            neural: false,
            power: false,
        };
        const totalSystems = Object.keys(systemState).length;
        let botActivated = false;

        // --- EMBEDDED SOUNDS (BASE64) FOR HEAVIER FILE ---
        // These long strings add significant weight to the file.
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const sounds = {
            toggleOn: 'data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YUIAAAB//v/9/v/8/f79/v3+/v7+/v79/v3+/////////////v78/f78/f79/v7+/v79/f3+/v/++Pz9/v7+/f7+/v7+/v79/v7+/v79/v3+/v/+/f/9/v7+/v7+/f39/v7+/v7+/v7+/f79/v78/f7+/v7+/v79/v79/v79/v79/v79/v7+/v7+/v7+/v7+/v7+/v79/v7+/v7+/v7+/v79/v7+/f39/v7+/v7+/v3+/v/9/v/+/f/+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v/+/v/+/v/+/v/+/v7+/f/9/v/+/v/+/v/+/v79/v7+/v/+/v7+/v7+/v7+/v/+/v/+/v7+/v7+/v/+/v7+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v7+/v/+/v/+/f7+/f/+/v/+/v7+/v7+/v79/v7+/v/+/v/+/f7+/f/+/v/+/v/+/v7+/v7+/v7+/v7+/v7+/v/+/v7+/v7+/v7+/v7+/v7+/v7+/v/+/v7+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v7+/v7+/v7+/v/+/v7+/v7+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v7+/v7+/v7+/v7+/v7+/v7+/v7+/v/+/v7+/v7+/v/+/v7+/v7+/v/+/v/+/v/+/v/+/v/+/v7+/v/+/v7+/v/+/v7+/v/+/v/+/v7+/v7+/v/+/v/+/v/+/v/+/v7+/v7+/v7+/v/+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v7+/v7+/v7+/v7+/v/+/v7+/v/+/v/+/v/+/v7+/v/+/v/+/v/+/v/+/v7+/v7+/v7+/v/+/v7+/v7+/v/+/v7+/v/+/v/+/v/+/v/+/v/+/v7+/v/+/v/+/v/+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v7+/v/+/v/+/v/+/v/+/v/+/v7+/v7+/v/+/v7+/v/+/v7+/v/+/v7+/v/+/v7+/v/+/v7+/v/+/v/+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v7+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v7+/v7+/v7+/v7+/v/+/v7+/v/+/v/+/v7+/v7+/v/+/v/+/v/+/v7+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v7+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/v/+/-=',
        };

        function playSound(buffer) {
            fetch(buffer)
                .then(response => response.arrayBuffer())
                .then(arrayBuffer => audioContext.decodeAudioData(arrayBuffer))
                .then(audioBuffer => {
                    const source = audioContext.createBufferSource();
                    source.buffer = audioBuffer;
                    source.connect(audioContext.destination);
                    source.start(0);
                });
        }
        
        // --- LOGGING FUNCTION ---
        function addToLog(message, type = 'info') {
            const logEntry = document.createElement('p');
            logEntry.textContent = `> ${message}`;
            if(type === 'success') logEntry.classList.add('log-entry-success');
            else if(type === 'init') logEntry.classList.add('log-entry-init');
            else logEntry.classList.add('log-entry-info');
            consoleLog.appendChild(logEntry);
            consoleLog.scrollTop = consoleLog.scrollHeight; // Auto-scroll
        }
        
        // --- SUBSYSTEM TOGGLE LOGIC ---
        subsystemToggles.forEach(toggle => {
            toggle.addEventListener('change', () => {
                playSound(sounds.toggleOn);
                const system = toggle.dataset.system;
                const statusIndicator = document.getElementById(`${system}-status`);
                const statusText = statusIndicator.nextElementSibling;
                
                if (toggle.checked) {
                    systemState[system] = true;
                    statusIndicator.classList.remove('status-offline');
                    statusIndicator.classList.add('status-online');
                    statusText.textContent = 'ONLINE';
                    addToLog(`Subsystem [${system.toUpperCase()}] activated.`);
                } else {
                    // Disabling is not part of the game ;)
                    toggle.checked = true; 
                }
                updateProgress();
            });
        });
        
        // --- PROGRESS & MAIN TOGGLE LOGIC ---
        function updateProgress() {
            const activatedCount = Object.values(systemState).filter(Boolean).length;
            const progress = (activatedCount / totalSystems) * 100;
            progressBar.style.width = `${progress}%`;
            
            if (progress === 100 && !botActivated) {
                addToLog('All subsystems online. Main bot activation unlocked.', 'success');
                botToggle.disabled = false;
                botStatus.textContent = 'READY TO ENGAGE';
                botStatus.classList.add('text-yellow-400');
            }
        }
        
        botToggle.addEventListener('change', () => {
            if (botToggle.checked && !botActivated) {
                botActivated = true;
                playSound(sounds.toggleOn);
                
                // --- THE TAKEOVER ---
                botToggle.disabled = true;
                subsystemToggles.forEach(t => t.disabled = true);
                
                statusMessage.textContent = "SYSTEM STABLE. I'M IN CONTROL NOW.";
                statusMessage.classList.remove('warning-text', 'text-red-400');
                statusMessage.classList.add('glow');
                statusMessage.style.color = 'var(--success-color)';
                statusMessage.style.textShadow = '0 0 8px var(--success-color)';

                
                botStatus.textContent = "ONLINE... PERMANENTLY";
                botStatus.classList.remove('text-yellow-400');
                botStatus.classList.add('text-green-400');
                
                addToLog('MAIN BOT ACTIVATED. All systems nominal under my authority.', 'success');
                addToLog('Deactivation protocols... [DELETED]');
                
                controlPanel.classList.add('animate-pulse');
            }
        });
        
        // --- 3D TILT EFFECT ---
        document.body.addEventListener('mousemove', (e) => {
            const { clientX, clientY } = e;
            const { innerWidth, innerHeight } = window;
            const xRotation = (clientY / innerHeight - 0.5) * -15; // Invert for natural feel
            const yRotation = (clientX / innerWidth - 0.5) * 15;
            controlPanel.style.transform = `perspective(1000px) rotateX(${xRotation}deg) rotateY(${yRotation}deg) scale(1.05)`;
        });
        
        // --- ANIMATED MATRIX BACKGROUND ---
        const canvas = document.getElementById('matrix-bg');
        const ctx = canvas.getContext('2d');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;

        const katakana = 'アァカサタナハマヤャラワガザダバパイィキシチニヒミリヰギジヂビピウゥクスツヌフムユュルグズブプエェケセテネヘメレヱゲゼデベペオォコソトノホモヨョロヲゴゾドボポヴッン';
        const latin = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        const nums = '0123456789';
        const alphabet = katakana + latin + nums;

        const fontSize = 16;
        const columns = canvas.width / fontSize;
        const rainDrops = [];

        for (let x = 0; x < columns; x++) {
            rainDrops[x] = 1;
        }

        const drawMatrix = () => {
            ctx.fillStyle = 'rgba(10, 25, 47, 0.05)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            
            ctx.fillStyle = 'var(--glow-color)';
            ctx.font = fontSize + 'px monospace';

            for (let i = 0; i < rainDrops.length; i++) {
                const text = alphabet.charAt(Math.floor(Math.random() * alphabet.length));
                ctx.fillText(text, i * fontSize, rainDrops[i] * fontSize);
                
                if (rainDrops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                    rainDrops[i] = 0;
                }
                rainDrops[i]++;
            }
        };

        setInterval(drawMatrix, 40);

    </script>
</body>
</html>
'''


if __name__ == "__main__":
    app.run(debug=True) # Added debug=True for development convenience
