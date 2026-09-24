import os

import pytest
from sqlalchemy import event, select

from app import create_app
from app.extensions import db
from app.models import User
from app.security.judge_links import issue_judge_link


def login_judge_link(client, username):
    judge = db.session.execute(select(User).where(User.username == username)).scalar_one()
    token = issue_judge_link(judge)['access_path'].split('#')[1]
    db.session.commit()
    return client.post('/api/v1/auth/judge/link', json={'token': token})


@pytest.fixture
def app(tmp_path):
    database_url = os.getenv(
        'TEST_DATABASE_URL',
        'sqlite+pysqlite:///:memory:',
    )
    application = create_app(
        'testing',
        {
            'SQLALCHEMY_DATABASE_URI': database_url,
            'SQLALCHEMY_ENGINE_OPTIONS': {},
            'CORS_ORIGINS': ['http://localhost:4200'],
            'FILE_STORAGE_BACKEND': 'local',
            'LOCAL_STORAGE_PATH': str(tmp_path / 'uploads'),
        },
    )

    with application.app_context():
        if db.engine.dialect.name == 'sqlite':
            @event.listens_for(db.engine, 'connect')
            def enable_sqlite_foreign_keys(connection, _):
                cursor = connection.cursor()
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.close()

        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
