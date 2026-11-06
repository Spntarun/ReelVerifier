import re
import logging
from functools import wraps
from urllib.parse import urlparse, urljoin
from flask import (
    Blueprint,
    current_app,
    redirect,
    request,
    session,
    url_for,
    g,
    jsonify,
    render_template,
    flash,
)
from app.models import db, User

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_safe_url(target: str) -> bool:
    """Ensure a redirect target URL is safe and stays on the same host."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def get_current_user() -> User | None:
    """Retrieve currently authenticated user from session or request cache."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    if not hasattr(g, "_current_user") or g._current_user is None or getattr(g._current_user, "id", None) != user_id:
        g._current_user = db.session.get(User, user_id)
        if g._current_user is None:
            # User ID in session does not exist in DB (e.g. database was reset)
            session.pop("user_id", None)
    return g._current_user


def login_required(f):
    """Decorator to require user authentication for endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({
                    "success": False,
                    "error": "Authentication required. Please sign in with your email.",
                }), 401
            session["next_url"] = request.url
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def init_oauth(app):
    """Stub kept for factory compatibility."""
    pass


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Simple, passwordless email sign-in route."""
    user = get_current_user()
    if user:
        return redirect(url_for("routes.check_view"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()

        # Validate email presence and format
        if not email or not EMAIL_REGEX.match(email):
            flash("Please enter a valid email address.", "error")
            return render_template("login.html"), 400

        # Optional domain restrictions
        allowed_domains = current_app.config.get("ALLOWED_EMAIL_DOMAINS", [])
        if allowed_domains:
            domain = email.split("@")[-1].lower() if "@" in email else ""
            if domain not in allowed_domains:
                logger.warning(f"Login denied for {email}: domain '{domain}' not in allowed domains")
                flash(f"Access restricted to authorized domains ({', '.join(allowed_domains)}).", "error")
                return render_template("login.html"), 403

        # Match returning user by email, or create a new user
        user = User.query.filter_by(email=email).first()
        if not user:
            # Generate human-friendly display name from email prefix
            raw_prefix = email.split("@")[0]
            display_name = raw_prefix.replace(".", " ").replace("_", " ").replace("-", " ").title()

            user = User(
                email=email,
                name=display_name,
            )
            db.session.add(user)
            try:
                db.session.commit()
                logger.info(f"New user registered with email: {email} (ID: {user.id})")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error creating user record for {email}: {e}")
                flash("Database error during account sign-in. Please try again.", "error")
                return render_template("login.html"), 500

        # Establish authenticated session
        session.clear()
        session["user_id"] = user.id
        session.permanent = True

        # Safe redirect to requested destination or verification page
        next_url = session.pop("next_url", None)
        target = request.args.get("next") or next_url
        if target and is_safe_url(target):
            return redirect(target)
        return redirect(url_for("routes.check_view"))

    # GET request
    return render_template("login.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Clear session and redirect to landing page."""
    session.clear()
    return redirect(url_for("routes.landing"))
