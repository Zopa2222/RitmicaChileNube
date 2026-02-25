from app import create_app
from app.config import Config

app = create_app()

if __name__ == '__main__':
    print(f"Starting Gymnastics Scoring API on port {Config.FLASK_PORT}")
    print(f"CORS enabled for: {Config.CORS_ORIGINS}")
    print(f"MongoDB URI: {Config.MONGODB_URI}")
    
    app.run(
        host='0.0.0.0',
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG
    )
