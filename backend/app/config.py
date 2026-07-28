import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    FLASK_PORT = int(os.getenv('FLASK_PORT', 8080))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False') == 'True'
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:4200').split(',')
    
    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
