import pytest
from datetime import datetime, timezone
from app import create_app
from app.models import db, User, Check
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key-12345"
    DAILY_LIMIT_PER_USER = 3
    ENABLE_LOCAL_VISION = False
    ENABLE_TRANSCRIPTION = False
    ALLOWED_EMAIL_DOMAINS = ["example.com", "intrella.com"]


@pytest.fixture
def app():
    """Create and configure a clean Flask application instance for each test."""
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """A standard test client for making unauthenticated requests."""
    return app.test_client()


@pytest.fixture
def test_user(app):
    """Create a primary test user."""
    with app.app_context():
        user = User(
            google_sub="google-sub-1001",
            email="alice@example.com",
            name="Alice Smith",
            picture="https://example.com/alice.jpg",
        )
        db.session.add(user)
        db.session.commit()
        # Refresh in session
        db.session.refresh(user)
        return user


@pytest.fixture
def test_user_2(app):
    """Create a secondary test user for cross-user security checks."""
    with app.app_context():
        user = User(
            google_sub="google-sub-2002",
            email="bob@intrella.com",
            name="Bob Jones",
            picture="https://example.com/bob.jpg",
        )
        db.session.add(user)
        db.session.commit()
        db.session.refresh(user)
        return user


@pytest.fixture
def auth_client(app, test_user):
    """Client with active session for test_user."""
    cl = app.test_client()
    with cl.session_transaction() as sess:
        sess["user_id"] = test_user.id
    return cl


@pytest.fixture
def auth_client_2(app, test_user_2):
    """Client with active session for test_user_2."""
    cl = app.test_client()
    with cl.session_transaction() as sess:
        sess["user_id"] = test_user_2.id
    return cl
