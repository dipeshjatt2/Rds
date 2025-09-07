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
    <title>DIPESH CHOUDHARY Bot - AI Quiz Assistant</title>
    
    <link href='https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css' rel='stylesheet'>
    
    <style>
        /* --- Root Variables for easy theme management --- */
        :root {
            --primary-color: #00aaff; /* Brighter blue for more pop */
            --secondary-color: #1a1f27;
            --background-static: #0d1117; /* Static bg, particles will animate */
            --text-color: #e0e0e0;
            --card-bg: rgba(255, 255, 255, 0.04); /* More transparent for particle visibility */
            --card-border: rgba(255, 255, 255, 0.1);
            --glow-color: rgba(0, 170, 255, 0.6);
            --glow-color-hover: rgba(0, 170, 255, 1);
        }

        *, *::before, *::after {
            box-sizing: border-box;
        }
        
        /* --- Preloader --- */
        #preloader {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: var(--background-static);
            z-index: 1001;
            display: flex;
            justify-content: center;
            align-items: center;
            transition: opacity 0.5s ease, visibility 0.5s ease;
        }
        .spinner {
            width: 60px;
            height: 60px;
            border: 5px solid var(--card-border);
            border-top-color: var(--primary-color);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        #preloader.loaded {
            opacity: 0;
            visibility: hidden;
        }

        /* --- Particle.js Background Container --- */
        #particles-js {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 1;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            color: var(--text-color);
            background-color: var(--background-static);
            overflow-x: hidden;
        }

        /* --- Content sections must sit ABOVE the particles --- */
        header, main, footer {
            position: relative;
            z-index: 2;
        }

        /* --- Header & Title Shimmer --- */
        header {
            text-align: center;
            padding: 120px 20px 80px 20px;
            position: relative;
            overflow: hidden;
        }

        .header-content {
            animation: fadeInDown 1.2s cubic-bezier(0.25, 1, 0.5, 1);
        }

        .bot-name {
            font-size: clamp(2.5rem, 8vw, 4.5rem);
            font-weight: 800;
            margin: 0;
            background: linear-gradient(90deg, #fff, #bbb, #fff);
            background-size: 200% auto;
            color: #fff;
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: textShimmer 4s linear infinite;
        }

        /* Styling for Anime.js tagline animation */
        .bot-tagline {
            font-size: 1.3rem;
            margin-top: 15px;
            color: var(--text-color);
            opacity: 0.9;
        }
        /* Hide individual letters until animated */
        .bot-tagline .letter {
            display: inline-block;
            opacity: 0;
        }


        /* --- Animated CTA Button --- */
        .cta-button {
            display: inline-block;
            background: var(--primary-color);
            color: #fff;
            padding: 16px 35px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: bold;
            font-size: 1.1rem;
            margin-top: 40px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            box-shadow: 0 0 25px var(--glow-color);
            animation: pulseGlow 2s infinite ease-in-out, fadeInUp 1s ease-out 0.8s backwards;
            position: relative;
            z-index: 1;
            overflow: hidden;
        }

        .cta-button:hover {
            transform: translateY(-5px) scale(1.05);
            box-shadow: 0 0 40px var(--glow-color-hover);
            animation-play-state: paused;
        }

        /* --- Container & Section Headers --- */
        .container {
            max-width: 1100px;
            margin: 0 auto;
            padding: 40px 20px;
        }

        h2 {
            text-align: center;
            font-size: 2.8rem;
            margin-bottom: 60px;
            position: relative;
            color: #fff;
            font-weight: 700;
        }

        h2::after {
            content: '';
            display: block;
            width: 80px;
            height: 4px;
            background: var(--primary-color);
            margin: 10px auto 0;
            border-radius: 2px;
            box-shadow: 0 0 15px var(--glow-color);
        }

        /* --- Grids --- */
        .features-grid, .how-it-works-grid, .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
        }
        
        .stats-grid {
             grid-template-columns: 1fr 1fr;
             align-items: center;
             gap: 50px;
        }
        @media (max-width: 768px) {
            .stats-grid {
                grid-template-columns: 1fr;
            }
        }


        /* --- Interactive Glassmorphism Card (Now ready for Vanilla-Tilt.js) --- */
        .feature-card, .step-card {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 15px;
            border: 1px solid var(--card-border);
            text-align: center;
            backdrop-filter: blur(10px); /* The glass effect */
            -webkit-backdrop-filter: blur(10px);
            position: relative;
            overflow: hidden;
            
            /* Vanilla-tilt will control this, but good fallback */
            transition: box-shadow 0.4s ease; 
            
            /* Animation Setup */
            opacity: 0;
            transform: translateY(40px) scale(0.95);
        }
        
        .feature-card:hover, .step-card:hover {
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            border-color: rgba(0, 170, 255, 0.5);
        }

        /* This is required by vanilla-tilt.js to work correctly */
        .feature-card, .step-card {
           transform-style: preserve-3d;
        }
        .feature-card > *, .step-card > * {
            transform: translateZ(20px); /* Makes content pop out a bit in 3D */
        }
        
        .feature-icon, .step-icon {
            font-size: 3.5rem;
            color: var(--primary-color);
            margin-bottom: 20px;
            display: block; 
            text-shadow: 0 0 15px var(--glow-color);
            transform: translateZ(50px); /* Makes icon pop even more */
        }

        .feature-card h3, .step-card h3 {
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #fff;
        }

        /* --- Scroll Animation Class --- */
        .feature-card.visible, .step-card.visible {
            opacity: 1;
            transform: translateY(0) scale(1);
            transition-property: opacity, transform;
            transition-duration: 0.6s;
            transition-timing-function: cubic-bezier(0.215, 0.610, 0.355, 1);
        }

        /* --- How it Works Section --- */
        #how-it-works, #data-stats {
            margin-top: 60px;
        }

        .step-card {
            text-align: left;
            padding-left: 40px;
        }
        .step-card h3 {
            text-align: left;
            display: flex;
            align-items: center;
        }
        .step-icon {
            font-size: 2.5rem;
            margin: 0;
            margin-right: 20px;
            text-align: center;
            width: 50px;
        }
        
        /* --- NEW Stats & Chart Section --- */
        .stats-counters {
            display: flex;
            flex-direction: column;
            gap: 25px;
        }
        .stat-item {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            padding: 20px;
            border-radius: 10px;
        }
        .stat-number {
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--primary-color);
            margin-bottom: 5px;
        }
        .stat-label {
            font-size: 1rem;
            color: var(--text-color);
            opacity: 0.8;
        }
        .chart-container {
            width: 100%;
            max-width: 400px;
            margin: 0 auto;
        }


        /* --- Footer --- */
        footer {
            text-align: center;
            padding: 40px 20px;
            background-color: var(--secondary-color);
            margin-top: 80px;
            border-top: 1px solid var(--card-border);
        }
        footer p { margin: 0; font-size: 1rem; }
        footer p a { color: var(--primary-color); text-decoration: none; font-weight: 600; }

        /* --- Keyframe Animations --- */
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes textShimmer {
            from { background-position: 200% center; }
            to { background-position: -200% center; }
        }
        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 0 25px var(--glow-color); }
            50% { box-shadow: 0 0 40px var(--glow-color-hover); }
        }

    </style>
</head>
<body>

    <div id="preloader"><div class="spinner"></div></div>

    <div id="particles-js"></div>

    <header>
        <div class="header-content">
            <h1 class="bot-name">@DIPESHCHOUDHARYBOT</h1>
            <p class="bot-tagline">Your Powerful & Versatile Quiz Management Assistant</p>
            <a href="https://t.me/DIPESHCHOUDHARYBOT" target="_blank" class="cta-button">Add to Telegram</a>
        </div>
    </header>

    <main class="container">
        <section id="features">
            <h2>Core Features</h2>
            <div class="features-grid">
                <div class="feature-card" data-tilt data-tilt-max="15" data-tilt-speed="400" data-tilt-perspective="1000">
                    <i class='feature-icon bx bx-edit-alt'></i>
                    <h3>Manual Quiz Creation</h3>
                    <p>Use the <code>/create</code> command to build quizzes step-by-step, right inside Telegram.</p>
                </div>
                <div class="feature-card" data-tilt data-tilt-max="15" data-tilt-speed="400" data-tilt-perspective="1000">
                    <i class='feature-icon bx bx-bolt-circle'></i>
                    <h3>Bulk Poll Sender</h3>
                    <p>Instantly convert text or .txt files into multiple quiz polls with the <code>/txqz</code> command.</p>
                </div>
                <div class="feature-card" data-tilt data-tilt-max="15" data-tilt-speed="400" data-tilt-perspective="1000">
                    <i class='feature-icon bx bx-world'></i>
                    <h3>Interactive HTML Quizzes</h3>
                    <p>Transform .txt or .csv files into shareable, timed HTML tests using the <code>/htmk</code> command.</p>
                </div>
                <div class="feature-card" data-tilt data-tilt-max="15" data-tilt-speed="400" data-tilt-perspective="1000">
                    <i class='feature-icon bx bx-shuffle'></i>
                    <h3>Shuffle & Randomize</h3>
                    <p>Easily shuffle question and answer orders for your quizzes to prevent cheating with <code>/shufftxt</code>.</p>
                </div>
                <div class="feature-card" data-tilt data-tilt-max="15" data-tilt-speed="400" data-tilt-perspective="1000">
                    <i class='feature-icon bx bx-layer'></i>
                    <h3>Multiple Format Support</h3>
                    <p>Intelligently parses various quiz formats, from simple text to complex CSV and JSON structures.</p>
                </div>
                <div class="feature-card" data-tilt data-tilt-max="15" data-tilt-speed="400" data-tilt-perspective="1000">
                    <i class='feature-icon bx bxs-cog'></i>
                    <h3>Customizable Tests</h3>
                    <p>Set custom timers, negative marking, and filenames for your generated HTML quizzes.</p>
                </div>
            </div>
        </section>
        
        <section id="data-stats">
            <h2>Bot Activity & Capabilities</h2>
            <div class="stats-grid">
                <div class="stats-counters" id="stats-container">
                     <div class="stat-item">
                        <div class="stat-number" data-target="1500">0</div>
                        <div class="stat-label">Quizzes Created Daily (Avg)</div>
                     </div>
                     <div class="stat-item">
                        <div class="stat-number" data-target="50000">0</div>
                        <div class="stat-label">Total Users Served</div>
                     </div>
                     <div class="stat-item">
                        <div class="stat-number" data-target="5">0</div>
                        <div class="stat-label">Core Data Formats Parsed</div>
                     </div>
                </div>
                <div class="chart-container">
                    <canvas id="formatChart"></canvas>
                </div>
            </div>
        </section>

        <section id="how-it-works">
            <h2>How It Works</h2>
            <div class="how-it-works-grid">
                <div class="step-card" data-tilt data-tilt-max="10" data-tilt-speed="300" data-tilt-perspective="1000">
                    <h3><i class='step-icon bx bxs-file-import'></i>Send Your Data</h3>
                    <p>Upload a <code>.txt</code>, <code>.csv</code>, or JSON file, or just paste plain text directly to the bot.</p>
                </div>
                 <div class="step-card" data-tilt data-tilt-max="10" data-tilt-speed="300" data-tilt-perspective="1000">
                    <h3><i class='step-icon bx bxs-magic-wand'></i>Pick a Command</h3>
                    <p>Use <code>/htmk</code> for a web quiz, <code>/txqz</code> for Telegram polls, or <code>/shufftxt</code> to randomize it.</p>
                </div>
                 <div class="step-card" data-tilt data-tilt-max="10" data-tilt-speed="300" data-tilt-perspective="1000">
                    <h3><i class='step-icon bx bxs-share-alt'></i>Share Instantly</h3>
                    <p>Receive your formatted quiz, web link, or new file back in seconds, ready to be shared with anyone.</p>
                </div>
            </div>
        </section>

    </main>

    <footer>
        <p>Developed by <a href="https://t.me/dipesh_choudhary_rj" target="_blank">@dipesh_choudhary_rj</a></p>
    </footer>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/animejs/3.2.1/anime.min.js"></script>
    
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/vanilla-tilt/1.8.0/vanilla-tilt.min.js"></script>

    <script src="https://cdn.jsdelivr.net/particles.js/2.0.0/particles.min.js"></script>
    
    <script>
        
        // --- Preloader Script ---
        const preloader = document.getElementById('preloader');
        window.addEventListener('load', () => {
            preloader.classList.add('loaded');
        });

        document.addEventListener("DOMContentLoaded", () => {
            
            // --- 1. Anime.js Tagline Animation ---
            // Wrap each letter in a span
            const tagline = document.querySelector('.bot-tagline');
            tagline.innerHTML = tagline.textContent.replace(/\S/g, "<span class='letter'>$&</span>");

            anime.timeline({loop: false})
              .add({
                targets: '.bot-tagline .letter',
                translateY: [-20, 0],
                opacity: [0,1],
                easing: "easeOutExpo",
                duration: 1400,
                delay: (el, i) => 800 + 30 * i // Staggered start after header fades in
              });

            
            // --- 2. Scroll Animation for Cards (Staggered Fade-in) ---
            const animatedItems = document.querySelectorAll('.feature-card, .step-card');
            const cardObserver = new IntersectionObserver(entries => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const parent = entry.target.parentElement;
                        const items = Array.from(parent.children);
                        const index = items.indexOf(entry.target);
                        entry.target.style.transitionDelay = `${index * 100}ms`;
                        entry.target.classList.add('visible');
                        cardObserver.unobserve(entry.target);
                    }
                });
            }, { threshold: 0.1 });
            animatedItems.forEach(item => cardObserver.observe(item));

            
            // --- 3. Vanilla-Tilt.js Initialization ---
            // This replaces the lightweight spotlight effect with a much heavier 3D effect
            VanillaTilt.init(document.querySelectorAll(".feature-card, .step-card"), {
                // Config options are in the HTML data-tilt attributes
            });


            // --- 4. Stats Counter & Chart.js Animation (Triggered on Scroll) ---
            const statsContainer = document.getElementById('stats-container');
            let hasAnimatedStats = false;

            const statsObserver = new IntersectionObserver(entries => {
                const entry = entries[0];
                if (entry.isIntersecting && !hasAnimatedStats) {
                    hasAnimatedStats = true;
                    
                    // a) Animate Counters
                    const counters = document.querySelectorAll('.stat-number');
                    counters.forEach(counter => {
                        const target = +counter.getAttribute('data-target');
                        const duration = 2000;
                        const stepTime = 20; // run every 20ms
                        const totalSteps = duration / stepTime;
                        const increment = target / totalSteps;
                        let current = 0;

                        const timer = setInterval(() => {
                            current += increment;
                            if (current >= target) {
                                counter.textContent = target.toLocaleString(); // Add commas
                                clearInterval(timer);
                            } else {
                                counter.textContent = Math.floor(current).toLocaleString();
                            }
                        }, stepTime);
                    });

                    // b) Render Chart.js Donut Chart
                    const ctx = document.getElementById('formatChart').getContext('2d');
                    new Chart(ctx, {
                        type: 'doughnut',
                        data: {
                            labels: ['Plain Text (.txt)', 'CSV', 'JSON', 'Manual Input', 'Other'],
                            datasets: [{
                                label: 'Supported Formats',
                                data: [40, 25, 20, 10, 5],
                                backgroundColor: [
                                    'rgba(0, 170, 255, 0.8)', // --primary-color
                                    'rgba(0, 221, 255, 0.8)',
                                    'rgba(130, 235, 255, 0.8)',
                                    'rgba(255, 255, 255, 0.7)',
                                    'rgba(150, 150, 150, 0.6)'
                                ],
                                borderColor: [
                                    'rgba(0, 170, 255, 1)',
                                    'rgba(0, 221, 255, 1)',
                                    'rgba(130, 235, 255, 1)',
                                    'rgba(255, 255, 255, 1)',
                                    'rgba(150, 150, 150, 1)'
                                ],
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            animation: {
                                animateScale: true,
                                animateRotate: true,
                                duration: 1500
                            },
                            plugins: {
                                legend: {
                                    position: 'bottom',
                                    labels: {
                                        color: '#fff' // Legend text color
                                    }
                                }
                            }
                        }
                    });
                    
                    statsObserver.unobserve(statsContainer); // Only run all this once
                }
            }, { threshold: 0.4 }); // Trigger when 40% of the section is visible

            statsObserver.observe(statsContainer);
        });


        // --- 5. Particles.js Initialization (Heavy!) ---
        particlesJS("particles-js", {
          "particles": {
            "number": {
              "value": 80, // Number of particles
              "density": {
                "enable": true,
                "value_area": 800
              }
            },
            "color": {
              "value": "#ffffff" // Particle color
            },
            "shape": {
              "type": "circle",
            },
            "opacity": {
              "value": 0.5,
              "random": false,
              "anim": {
                "enable": false,
              }
            },
            "size": {
              "value": 3,
              "random": true,
              "anim": {
                "enable": false,
              }
            },
            "line_linked": {
              "enable": true,
              "distance": 150,
              "color": "#ffffff", // Line color
              "opacity": 0.4,
              "width": 1
            },
            "move": {
              "enable": true,
              "speed": 2, // Particle speed
              "direction": "none",
              "random": false,
              "straight": false,
              "out_mode": "out",
              "bounce": false,
            }
          },
          "interactivity": {
            "detect_on": "canvas",
            "events": {
              "onhover": {
                "enable": true,
                "mode": "grab" // Grab lines on hover
              },
              "onclick": {
                "enable": true,
                "mode": "push" // Push particles on click
              },
              "resize": true
            },
            "modes": {
              "grab": {
                "distance": 140,
                "line_opacity": 1
              },
              "push": {
                "particles_nb": 4
              },
            }
          },
          "retina_detect": true
        });

    </script>
</body>
</html>'''


if __name__ == "__main__":
    app.run(debug=True) # Added debug=True for development convenience
