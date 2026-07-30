import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def normalize_database_url(value):
    """Normalize common provider URLs for SQLAlchemy + Psycopg 3."""
    if value.startswith('postgres://'):
        return value.replace('postgres://', 'postgresql+psycopg://', 1)
    if value.startswith('postgresql://'):
        return value.replace('postgresql://', 'postgresql+psycopg://', 1)
    return value


def env_bool(name, default=False):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}


class Config:
    APP_ENV = os.getenv('APP_ENV', 'development').lower()
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.getenv('DATABASE_URL', 'sqlite:///ritmica_cloud_dev.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }

    FLASK_PORT = int(os.getenv('FLASK_PORT', 8080))
    FLASK_DEBUG = env_bool('FLASK_DEBUG')
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            'CORS_ORIGINS',
            'http://localhost:4200',
        ).split(',')
        if origin.strip()
    ]
    ENABLE_LEGACY_ROUTES = env_bool('ENABLE_LEGACY_ROUTES', True)

    JWT_SECRET_KEY = os.getenv(
        'JWT_SECRET_KEY',
        'development-only-change-in-production',
    )
    JWT_TOKEN_LOCATION = ['cookies']
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_IN_COOKIES = True
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_COOKIE_PATH = '/api/'
    JWT_ACCESS_COOKIE_NAME = 'ritmica_access'
    JWT_ACCESS_CSRF_COOKIE_NAME = 'ritmica_csrf'
    JWT_ACCESS_CSRF_HEADER_NAME = 'X-CSRF-TOKEN'

    RATELIMIT_STORAGE_URI = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True

    FILE_STORAGE_BACKEND = os.getenv('FILE_STORAGE_BACKEND', 'local').lower()
    LOCAL_STORAGE_PATH = os.getenv('LOCAL_STORAGE_PATH')
    GCS_BUCKET = os.getenv('GCS_BUCKET')
    IMPORT_PREVIEW_TTL_HOURS = int(
        os.getenv('IMPORT_PREVIEW_TTL_HOURS', '24')
    )

    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}


class DevelopmentConfig(Config):
    APP_ENV = 'development'


class TestingConfig(Config):
    APP_ENV = 'testing'
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite+pysqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': False,
    }
    ENABLE_LEGACY_ROUTES = False
    JWT_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    APP_ENV = 'production'
    FLASK_DEBUG = False
    ENABLE_LEGACY_ROUTES = env_bool('ENABLE_LEGACY_ROUTES', False)
    JWT_COOKIE_SECURE = True
    FILE_STORAGE_BACKEND = os.getenv('FILE_STORAGE_BACKEND', 'gcs').lower()


CONFIG_BY_NAME = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
}


def get_config(name=None):
    environment = (name or os.getenv('APP_ENV', 'development')).lower()
    return CONFIG_BY_NAME.get(environment, DevelopmentConfig)
