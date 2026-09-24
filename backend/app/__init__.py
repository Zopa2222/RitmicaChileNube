from flask import Flask
from flask_cors import CORS
from flask import jsonify
from sqlalchemy import text

from app.config import get_config
from app.extensions import db, jwt, limiter, migrate


def create_app(config_name=None, config_overrides=None):
    """Create and configure Flask application"""
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))
    if config_overrides:
        app.config.update(config_overrides)
    if (
        app.config['APP_ENV'] == 'production'
        and app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite')
    ):
        raise RuntimeError('DATABASE_URL de PostgreSQL es obligatorio en producción')
    if (
        app.config['APP_ENV'] == 'production'
        and app.config['JWT_SECRET_KEY']
        == 'development-only-change-in-production'
    ):
        raise RuntimeError('JWT_SECRET_KEY es obligatorio en producción')
    if (
        app.config['APP_ENV'] == 'production'
        and app.config['FILE_STORAGE_BACKEND'] == 'gcs'
        and not app.config['GCS_BUCKET']
    ):
        raise RuntimeError('GCS_BUCKET es obligatorio en producción')

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)

    # Import models after initializing the extension so Alembic can discover
    # the complete normalized cloud schema.
    from app import models  # noqa: F401
    from app.commands import (
        bootstrap_fixed_users,
        purge_expired_championships_command,
    )
    from app.routes import (
        admin_scoring,
        auth,
        cloud_administration,
        cloud_championships,
        cloud_exports,
        cloud_operations,
        judge_cabin,
        publication,
    )

    # Configure CORS
    CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=True)

    # Register blueprints
    app.register_blueprint(auth.bp)
    app.register_blueprint(cloud_administration.bp)
    app.register_blueprint(cloud_championships.bp)
    app.register_blueprint(cloud_exports.bp)
    app.register_blueprint(cloud_operations.bp)
    app.register_blueprint(judge_cabin.bp)
    app.register_blueprint(admin_scoring.bp)
    app.register_blueprint(publication.bp)
    if app.config['ENABLE_LEGACY_ROUTES']:
        from app.routes import championships

        app.register_blueprint(championships.bp)
    app.cli.add_command(bootstrap_fixed_users)
    app.cli.add_command(purge_expired_championships_command)

    @app.after_request
    def protect_api_responses(response):
        from flask import request
        if request.path.startswith('/api/v1/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({
            'error': 'Debe iniciar sesión',
            'code': 'AUTHENTICATION_REQUIRED',
        }), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({
            'error': 'La sesión no es válida',
            'code': 'INVALID_TOKEN',
        }), 401

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return jsonify({
            'error': 'La sesión expiró',
            'code': 'TOKEN_EXPIRED',
        }), 401

    # Health check endpoint
    @app.route('/health', methods=['GET'])
    def health_check():
        return {
            'status': 'ok',
            'message': 'Gymnastics Scoring API is running',
            'environment': app.config['APP_ENV'],
        }, 200

    @app.route('/health/ready', methods=['GET'])
    def readiness_check():
        try:
            db.session.execute(text('SELECT 1'))
        except Exception:
            app.logger.exception('PostgreSQL readiness check failed')
            return {'status': 'error', 'database': 'unavailable'}, 503
        return {'status': 'ok', 'database': 'available'}, 200

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Endpoint no encontrado'}, 404

    @app.errorhandler(500)
    def internal_error(error):
        return {'error': 'Error interno del servidor'}, 500

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify({
            'error': 'Demasiados intentos. Intente nuevamente más tarde.',
            'code': 'RATE_LIMIT_EXCEEDED',
        }), 429

    @app.shell_context_processor
    def shell_context():
        return {'db': db}

    return app
