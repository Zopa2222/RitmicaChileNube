from app import create_app

app = create_app()

if __name__ == '__main__':
    print(f"Starting Gymnastics Scoring API on port {app.config['FLASK_PORT']}")
    print(f"CORS enabled for: {app.config['CORS_ORIGINS']}")

    app.run(
        host='0.0.0.0',
        port=app.config['FLASK_PORT'],
        debug=app.config['FLASK_DEBUG']
    )
