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
    <title>DIPESH CHOUDHARY Bot</title>
    <style>
        /* General Styling & Cool Background */
        :root {
            --primary-color: #0088cc;
            --secondary-color: #24292e;
            --background-color: #121212;
            --text-color: #e0e0e0;
            --card-bg: #1e1e1e;
            --glow-color: rgba(0, 136, 204, 0.8);
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            background-color: var(--background-color);
            color: var(--text-color);
            overflow-x: hidden;
            background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
        }

        /* Header Section */
        header {
            text-align: center;
            padding: 100px 20px 50px 20px;
            position: relative;
        }

        .header-content {
            position: relative;
            z-index: 2;
            animation: fadeInDown 1s ease-out;
        }

        .bot-name {
            font-size: 3.5rem;
            font-weight: 700;
            margin: 0;
            color: #fff;
            text-shadow: 0 0 10px var(--glow-color), 0 0 20px var(--glow-color);
        }

        .bot-tagline {
            font-size: 1.2rem;
            margin-top: 10px;
            color: var(--text-color);
            opacity: 0.8;
        }

        /* Buttons */
        .cta-button {
            display: inline-block;
            background-color: var(--primary-color);
            color: #fff;
            padding: 15px 30px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: bold;
            margin-top: 30px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            box-shadow: 0 0 20px var(--glow-color);
        }

        .cta-button:hover {
            transform: translateY(-5px) scale(1.05);
            box-shadow: 0 0 35px var(--glow-color);
        }

        /* Features Section */
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 40px 20px;
        }

        h2 {
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 50px;
            position: relative;
            color: #fff;
        }

        h2::after {
            content: '';
            display: block;
            width: 80px;
            height: 4px;
            background: var(--primary-color);
            margin: 10px auto 0;
            border-radius: 2px;
        }
        
        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 30px;
        }

        .feature-card {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 15px;
            border: 1px solid #333;
            text-align: center;
            transition: transform 0.3s, box-shadow 0.3s;
            opacity: 0; /* Initially hidden for animation */
            transform: translateY(30px);
        }

        .feature-card.visible {
            opacity: 1;
            transform: translateY(0);
        }
        
        .feature-card:hover {
            transform: translateY(-10px);
            box-shadow: 0 15px 30px rgba(0, 0, 0, 0.4);
        }

        .feature-icon {
            font-size: 3rem;
            color: var(--primary-color);
            margin-bottom: 20px;
        }

        .feature-card h3 {
            font-size: 1.5rem;
            margin-bottom: 10px;
        }

        /* Footer */
        footer {
            text-align: center;
            padding: 40px 20px;
            background-color: var(--secondary-color);
            margin-top: 50px;
        }

        /* Keyframe Animations */
        @keyframes fadeInDown {
            from {
                opacity: 0;
                transform: translateY(-30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    </style>
</head>
<body>

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
                <div class="feature-card">
                    <div class="feature-icon">📝</div>
                    <h3>Manual Quiz Creation</h3>
                    <p>Use the <code>/create</code> command to build quizzes step-by-step, right inside Telegram.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">⚡</div>
                    <h3>Bulk Poll Sender</h3>
                    <p>Instantly convert text or .txt files into multiple quiz polls with the <code>/txqz</code> command.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🌐</div>
                    <h3>Interactive HTML Quizzes</h3>
                    <p>Transform .txt or .csv files into shareable, timed HTML tests using the <code>/htmk</code> command.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">🔄</div>
                    <h3>Shuffle & Randomize</h3>
                    <p>Easily shuffle question and answer orders for your quizzes to prevent cheating with <code>/shufftxt</code>.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">📄</div>
                    <h3>Multiple Format Support</h3>
                    <p>Intelligently parses various quiz formats, from simple text to complex CSV and JSON structures.</p>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">⚙️</div>
                    <h3>Customizable Tests</h3>
                    <p>Set custom timers, negative marking, and filenames for your generated HTML quizzes.</p>
                </div>
            </div>
        </section>
    </main>

    <footer>
        <p>Developed by @dipesh_choudhary_rj</p>
    </footer>

    <script>
        // Simple Intersection Observer for scroll animations
        document.addEventListener("DOMContentLoaded", () => {
            const cards = document.querySelectorAll('.feature-card');

            const observer = new IntersectionObserver(entries => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, {
                threshold: 0.1 // Trigger when 10% of the card is visible
            });

            cards.forEach(card => {
                observer.observe(card);
            });
        });
    </script>
</body>
</html>

    """
    return render_template_string(html)

if __name__ == "__main__":
    # Make Flask accessible on all network interfaces, useful for deployment
    app.run(host="0.0.0.0", port=5000)
