from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()
migrate = Migrate(compare_type=True, render_as_batch=False)
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
