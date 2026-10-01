"""Security hardening layer for BOT FORGE.
Loaded by secure_app.py before Gunicorn serves the Flask app.
"""
import time
from collections import defaultdict, deque
from threading import Lock

from flask import request, abort
from werkzeug.middleware.proxy_fix import ProxyFix


def harden(app):
    # Railway sits behind a reverse proxy. Trust one proxy hop so HTTPS/IP
    # information is handled correctly by Flask/Werkzeug.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=1800,
    )

    buckets = defaultdict(deque)
    lock = Lock()

    def client_key():
        return request.remote_addr or "unknown"

    def limited(bucket_name, limit, window):
        now = time.monotonic()
        key = (bucket_name, client_key())
        with lock:
            q = buckets[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return True
            q.append(now)
        return False

    @app.before_request
    def security_gate():
        path = request.path

        # Protect the login and API endpoints from basic brute-force/spam.
        if path == "/admin/login" and request.method == "POST":
            if limited("admin-login", 8, 300):
                abort(429)

        if path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if limited("api-write", 30, 60):
                abort(429)

        # Prevent cross-site form submissions against state-changing routes.
        # Webhooks are intentionally excluded because providers do not send a
        # browser Origin header.
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not path.startswith("/webhooks/"):
            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")
            host = request.host_url.rstrip("/")
            if origin and origin.rstrip("/") != host:
                abort(403)
            if not origin and referer and not referer.startswith(host + "/"):
                abort(403)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self' https:; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline' https:; font-src 'self' data: https:; connect-src 'self' https:; frame-ancestors 'self'; base-uri 'self'; form-action 'self' https://wa.me https://*.asaas.com; object-src 'none'",
        )
        return response

    return app
