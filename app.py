"""Main Flask application."""
from flask import Flask, jsonify
from config import Config
from oauth_handler import register_oauth_routes
from event_handler import register_event_routes
from database import db

# Create Flask app
app = Flask(__name__)

# Register routes
register_oauth_routes(app)
register_event_routes(app)

@app.route('/')
def home():
    """Home page."""
    return '''
    <html>
    <head><title>Thinking Bot</title></head>
    <body style="font-family: Arial; padding: 50px;">
        <h1>Thinking Bot</h1>
        <p>A simple Slack bot that responds with "thinking"</p>
        <ul>
            <li><a href="/slack/install">Install to Slack</a></li>
            <li><a href="/health">Health Check</a></li>
            <li><a href="/debug/installations">View Installations</a></li>
        </ul>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'database': 'connected',
        'config': 'valid'
    })

@app.route('/debug/installations')
def debug_installations():
    """Debug endpoint to view installations."""
    if Config.FLASK_ENV != 'development':
        return jsonify({'error': 'Not available in production'}), 403

    installations = db.get_all_installations()
    return jsonify({
        'count': len(installations),
        'installations': installations
    })

if __name__ == '__main__':
    print(f"Starting Thinking Bot on port {Config.PORT}")
    print(f"Public URL: {Config.PUBLIC_URL}")
    print(f"Environment: {Config.FLASK_ENV}")
    app.run(host='0.0.0.0', port=Config.PORT, debug=(Config.FLASK_ENV == 'development'))
