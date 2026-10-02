import os
import json
import time
import threading
import zipfile
from collections import defaultdict, deque

from flask import request, send_file
from app import app, db, _get_order, now, generated_files, TEST_MODE, UPLOAD_DIR

PRODUCTION = not TEST_MODE
RATE_LIMIT = int(os.getenv('BOT_FORGE_RATE_LIMIT', '120'))
RATE_WINDOW = 60
_hits = defaultdict(deque)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=PRODUCTION,
    MAX_CONTENT_LENGTH=25 * 1024 * 1024,
)


@app.before_request
def production_guardrails():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    now_mono = time.monotonic()
    bucket = _hits[ip]
    while bucket and now_mono - bucket[0] > RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT:
        return ('Muitas requisições. Tente novamente em instantes.', 429)
    bucket.append(now_mono)

    if PRODUCTION:
        if not os.getenv('FLASK_SECRET_KEY', '').strip():
            return ('Configuração de produção incompleta.', 503)
        if request.path.startswith('/admin') and not os.getenv('ADMIN_PASSWORD', '').strip():
            return ('Administração não configurada.', 503)

    # Once the background processor has generated and validated the ZIP, serve that
    # immutable artifact instead of regenerating it on every click.
    if request.path.startswith('/generate/'):
        token = request.path.rsplit('/', 1)[-1]
        row = None
        try:
            con = db(); row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone(); con.close()
        except Exception:
            row = None
        if row and row['status'] == 'Entregue':
            try:
                cfg = json.loads(row['config_json'] or '{}')
                stored = cfg.get('_generated_file')
                if stored:
                    path = UPLOAD_DIR / stored
                    if path.is_file() and path.resolve().parent == UPLOAD_DIR.resolve():
                        return send_file(path, as_attachment=True, download_name=path.name, mimetype='application/zip')
            except Exception:
                pass


@app.after_request
def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if PRODUCTION:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        response.headers.setdefault('Content-Security-Policy', "default-src 'self' https: data: 'unsafe-inline' 'unsafe-eval'; frame-ancestors 'self'")
    return response


def _safe_generated_zip(order):
    files = generated_files(order)
    filename = f"{order['id']}_{order['product'].replace('/', '-')}.zip"
    path = UPLOAD_DIR / filename
    tmp = UPLOAD_DIR / (filename + '.tmp')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    with zipfile.ZipFile(tmp, 'r') as archive:
        if archive.testzip():
            raise RuntimeError('ZIP inválido')
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
            cfg = json.loads(row['config_json'] or '{}')
            cfg['_generated_file'] = filename
            cfg['_generated_at'] = now()
            con = db()
            con.execute("UPDATE orders SET config_json=?, status='Entregue', updated_at=? WHERE id=?", (json.dumps(cfg, ensure_ascii=False), now(), row['id']))
            con.commit(); con.close()
        except Exception:
            con = db()
            con.execute("UPDATE orders SET status='Aguardando cliente', updated_at=? WHERE id=?", (now(), row['id']))
            con.commit(); con.close()


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
