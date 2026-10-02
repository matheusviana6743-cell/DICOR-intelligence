import os
import json
import time
import threading
import zipfile
from pathlib import Path

from app import app, db, _get_order, now, generated_files, TEST_MODE, DATA_DIR, UPLOAD_DIR

# Production guardrails. The application itself remains the source of business rules.
PRODUCTION = not TEST_MODE

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=PRODUCTION,
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
)


@app.before_request
def production_guardrails():
    if PRODUCTION:
        # Never expose the administration surface without a configured password.
        if os.getenv("ADMIN_PASSWORD", "").strip() == "" and (str(__import__('flask').request.path).startswith('/admin')):
            return ("Administração não configurada.", 503)


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'; frame-ancestors 'self'")
    return response


def _safe_generated_zip(order):
    """Generate once, validate the archive, and return its stored filename."""
    files = generated_files(order)
    filename = f"{order['id']}_{order['product'].replace('/', '-')}.zip"
    path = UPLOAD_DIR / filename
    tmp = UPLOAD_DIR / (filename + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    with zipfile.ZipFile(tmp, "r") as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP inválido: {bad}")
    tmp.replace(path)
    return filename


def process_paid_orders_once():
    if TEST_MODE:
        return
    con = db()
    rows = con.execute("SELECT * FROM orders WHERE payment_status='Pago' AND status IN ('Em preparação','Em desenvolvimento') ORDER BY created_at ASC LIMIT 5").fetchall()
    con.close()
    for row in rows:
        try:
            filename = _safe_generated_zip(row)
            con = db()
            cfg = json.loads(row['config_json'] or '{}')
            cfg['_generated_file'] = filename
            cfg['_generated_at'] = now()
            con.execute("UPDATE orders SET config_json=?, status='Entregue', updated_at=? WHERE id=?", (json.dumps(cfg, ensure_ascii=False), now(), row['id']))
            con.commit()
            con.close()
        except Exception:
            con = db()
            con.execute("UPDATE orders SET status='Aguardando cliente', updated_at=? WHERE id=?", (now(), row['id']))
            con.commit()
            con.close()


def worker():
    while True:
        try:
            process_paid_orders_once()
        except Exception:
            pass
        time.sleep(int(os.getenv('BOT_FORGE_PROCESS_INTERVAL', '10')))


if os.getenv('BOT_FORGE_AUTOMATION', '0') == '1':
    threading.Thread(target=worker, daemon=True, name='bot-forge-processor').start()


application = app
