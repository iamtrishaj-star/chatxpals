import os
from flask import Flask, jsonify, request
from flask_wtf.csrf import CSRFProtect, CSRFError
from dotenv import load_dotenv

csrf = CSRFProtect()


def create_app(test_config=None):
    """Application factory for 'What Did I Miss?' Flask application."""
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)

    # Base configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secure-key-what-did-i-miss-2026"),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,  # 2MB file limit to prevent DoS
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_CHECK_DEFAULT=True,
    )

    if test_config is not None:
        app.config.update(test_config)

    # Initialize extensions
    csrf.init_app(app)

    # Register blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # Security Headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Error Handlers
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "CSRF validation failed",
                "message": e.description
            }), 400
        return jsonify({"error": "CSRF validation failed", "message": e.description}), 400

    @app.errorhandler(413)
    def handle_large_file(e):
        return jsonify({
            "error": "File size exceeds limit",
            "message": "Maximum allowed file size is 2MB."
        }), 413

    return app
