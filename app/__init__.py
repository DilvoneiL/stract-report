from __future__ import annotations

from flask import Flask, jsonify, Response

def create_app() -> Flask:
    app = Flask(__name__)

    from .routes import bp as reports_bp
    app.register_blueprint(reports_bp)

    @app.get("/healthz")
    def healthz() -> Response:
        return jsonify(status="ok"), 200

    @app.after_request
    def security_headers(resp: Response) -> Response:
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Content-Security-Policy", "default-src 'none'")
        return resp

    @app.errorhandler(Exception)
    def on_error(exc: Exception):
        app.logger.exception("Unhandled error")
        return jsonify(error="internal_error"), 500

    return app
