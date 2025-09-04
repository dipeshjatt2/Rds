from flask import Flask, render_template

# Create the Flask web application instance
web_app = Flask(__name__)

# Define the main route for your website's homepage
@web_app.route('/')
def home():
    """
    This function runs when someone visits the homepage.
    It renders and displays the index.html file.
    """
    return render_template('index.html')

# This block ensures the web server runs only when you execute this script directly
if __name__ == "__main__":
    # app.run(debug=True) makes the server auto-reload when you save changes
    web_app.run(debug=True)
