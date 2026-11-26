import os

import pytest

from app import create_app
from app.config import Config
from app.db import init_schema

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://library:library@127.0.0.1:5432/library_test"
)
API_KEY = "test-api-key-0123456789"  # nosec B105  # gitleaks:allow


@pytest.fixture(scope="session")
def schema():
    init_schema(DATABASE_URL, attempts=3, delay=1)


@pytest.fixture
def make_app(schema):
    apps = []

    def build(**overrides):
        settings = {"database_url": DATABASE_URL, "api_key": API_KEY, **overrides}
        app = create_app(Config(**settings))
        apps.append(app)
        return app

    yield build
    for app in apps:
        app.extensions["db"].close()


@pytest.fixture
def app(make_app):
    application = make_app()
    with application.extensions["db"].transaction() as conn:
        conn.execute("TRUNCATE loans, books, members RESTART IDENTITY CASCADE")
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth():
    return {"X-API-Key": API_KEY}
