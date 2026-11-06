from app.auth import is_safe_url
from app.models import User, db


def test_landing_page_unauthenticated(client):
    """Unauthenticated users should see the landing page with the email sign-in form."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Reel" in response.data
    assert b"Start Verifying" in response.data


def test_login_page_renders_get(client):
    """GET /login should display the clean email sign-in form."""
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Sign In" in response.data
    assert b"Email Address" in response.data


def test_email_login_new_user_success(client, app):
    """POST /login with valid email should create user and establish session."""
    response = client.post("/login", data={"email": "newuser@example.com"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/check")

    # Check user was created in DB
    with app.app_context():
        u = User.query.filter_by(email="newuser@example.com").first()
        assert u is not None
        assert u.name == "Newuser"

    # Following redirects should allow access to /check
    res_check = client.get("/check")
    assert res_check.status_code == 200
    assert b"Verify an Offer" in res_check.data


def test_email_login_existing_user(client, test_user):
    """POST /login with existing email logs in without creating duplicate records."""
    response = client.post("/login", data={"email": test_user.email}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/check")


def test_email_login_invalid_email_rejected(client):
    """POST /login with invalid email format must return 400."""
    response = client.post("/login", data={"email": "not-an-email"})
    assert response.status_code == 400
    assert b"valid email address" in response.data


def test_email_login_domain_restriction(client):
    """POST /login with unauthorized domain must return 403 when ALLOWED_EMAIL_DOMAINS is set."""
    # TestConfig allows example.com and intrella.com
    response = client.post("/login", data={"email": "hacker@unauthorized.com"})
    assert response.status_code == 403
    assert b"restricted to authorized domains" in response.data


def test_landing_page_redirects_authenticated_user(auth_client):
    """Authenticated users should be redirected from / to /check."""
    response = auth_client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/check")


def test_login_required_protection(client):
    """Protected routes must redirect unauthenticated users to login page."""
    # /check
    res_check = client.get("/check")
    assert res_check.status_code == 302
    assert res_check.headers["Location"].endswith("/login")

    # /history
    res_hist = client.get("/history")
    assert res_hist.status_code == 302
    assert res_hist.headers["Location"].endswith("/login")

    # /result/1
    res_res = client.get("/result/1")
    assert res_res.status_code == 302
    assert res_res.headers["Location"].endswith("/login")


def test_api_analyze_requires_auth(client):
    """API endpoints must return 401 JSON when unauthenticated."""
    response = client.post("/api/analyze", data={"caption": "Test claim"})
    assert response.status_code == 401
    json_data = response.get_json()
    assert json_data["success"] is False
    assert "Authentication required" in json_data["error"]


def test_logout_clears_session(auth_client):
    """Logging out should clear the session and redirect to /."""
    response = auth_client.get("/logout")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")

    # Verify session is cleared by attempting to access protected route
    res2 = auth_client.get("/check")
    assert res2.status_code == 302
    assert res2.headers["Location"].endswith("/login")


def test_safe_url_validation(app):
    """Test open redirect prevention helper."""
    with app.test_request_context("http://localhost:5000/login"):
        assert is_safe_url("/check") is True
        assert is_safe_url("/history") is True
        assert is_safe_url("http://localhost:5000/check") is True

        # Unsafe external targets
        assert is_safe_url("https://malicious-site.com/steal") is False
        assert is_safe_url("//malicious-site.com") is False
        assert is_safe_url("javascript:alert(1)") is False
        assert is_safe_url("") is False
        assert is_safe_url(None) is False
