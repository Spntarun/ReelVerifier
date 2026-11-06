import os
import logging
from flask import Flask, render_template, jsonify, request
from flask_wtf.csrf import CSRFProtect
from config import Config
from app.models import db
from app.auth import init_oauth, auth_bp, get_current_user
from app.routes import routes_bp
from app.vision import vision_manager

csrf = CSRFProtect()


def create_app(config_class=Config):
    """Application factory for Reel Verifier."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure logging
    log_level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    init_oauth(app)

    # Initialize vision manager settings
    vision_manager.initialize(app.config)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(routes_bp)

    # Template context processor to make current_user globally available in templates
    @app.context_processor
    def inject_auth_user():
        return {
            "current_user": get_current_user(),
        }

    # Error Handlers
    @app.errorhandler(400)
    def bad_request_error(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"success": False, "error": "Bad request. Please verify your submitted data."}), 400
        return render_template("base.html", error_message="400 - Bad Request"), 400

    @app.errorhandler(403)
    def forbidden_error(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"success": False, "error": "Access denied. You do not have permission to view this resource."}), 403
        return render_template("base.html", error_message="403 - Access Denied"), 403

    @app.errorhandler(404)
    def not_found_error(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"success": False, "error": "The requested resource could not be found."}), 404
        return render_template("base.html", error_message="404 - Page Not Found"), 404

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return jsonify({
            "success": False,
            "error": "Upload is too large. Images must be under 5MB and videos under 60MB."
        }), 413

    @app.errorhandler(429)
    def ratelimit_error(e):
        return jsonify({
            "success": False,
            "error": "Too many requests. Please slow down and try again later.",
            "limit_reached": True,
        }), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"success": False, "error": "An internal server error occurred. Please try again later."}), 500
        return render_template("base.html", error_message="500 - Internal Server Error"), 500

    # Ensure database schema is created
    with app.app_context():
        db.create_all()

    return app

