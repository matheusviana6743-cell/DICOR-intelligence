import os
import io
import json
import sqlite3
import tempfile
import datetime as dt
import smtplib
from email.message import EmailMessage

import requests
from flask import request, redirect, url_for, send_file, abort, render_template, jsonify

from app import app, PRODUCTS, db, now, safe_json, TEST_MODE
from security import harden
from generator import build_project

# Produção: os preços definidos no app.py permanecem ativos.
# O modo de teste continua disponível somente quando TEST_MODE=1.

OWNER_WA = os.getenv('OWNER_WHATSAPP', '').strip()
WA_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN', '').strip()
WA_PHONE_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
WA_TEMPLATE = os.getenv('WHATSAPP_TEMPLATE_NAME', '').strip()
WA_TEMPLATE_LANG = os.getenv('WHATSAPP_TEMPLATE_LANG', 'pt_BR').strip()
SMTP_HOST = os.getenv('SMTP_HOST', '').strip()
SMTP_PORT = int(os.getenv('SMTP_PORT', '587') or 587)
SMTP_USER = os.getenv('SMTP_USER', '').strip()
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '').strip()
NOTIFY_EMAIL = os.getenv('NOTIFY_EMAIL', '').strip()
AUTO_PROCESS = os.getenv('AUTO_PROCESS', '1').strip() != '0'
PREP_SECONDS = int(os.getenv('PREP_SECONDS', '5') or 5)
DEV_SECONDS = int(os.getenv('DEV_SECONDS', '15') or 15)


def order_from_token(token):
    con = db()
    row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone()
    con.close()
    return row


def set_order_status(order_id, status, payment_status=None):
    con = db()
    if payment_status is None:
        con.execute('UPDATE orders SET status=?,updated_at=? WHERE id=?', (status, now(), order_id))
    else:
        con.execute('UPDATE orders SET status=?,payment_status=?,updated_at=? WHERE id=?', (status, payment_status, now(), order_id))
    con.commit()
    con.close()


def auto_process(row):
    """Automatic delivery for generated fixed products; custom projects remain manual."""
    if not AUTO_PROCESS or row['status'] in ('Entregue', 'Cancelado'):
        return row['status']
    if row['product'] == 'personalizado':
        return row['status']
    allowed = TEST_MODE and row['payment_status'] == 'Não necessário' or (not TEST_MODE and row['payment_status'] == 'Pago')
    if not allowed:
        return row['status']
    try:
        start = dt.datetime.fromisoformat(row['updated_at'])
        elapsed = (dt.datetime.now(dt.timezone.utc) - start).total_seconds()
    except Exception:
        elapsed = 0
    target = 'Em preparação' if elapsed < PREP_SECONDS else ('Em desenvolvimento' if elapsed < DEV_SECONDS else 'Entregue')
    if target != row['status']:
        set_order_status(row['id'], target)
    return target


def notify_whatsapp(order):
    """Optional WhatsApp Cloud API notification. Requires an approved template."""
    if not (WA_TOKEN and WA_PHONE_ID and WA_TEMPLATE and OWNER_WA):
        return False
    url = f'https://graph.facebook.com/v20.0/{WA_PHONE_ID}/messages'
    payload = {
        'messaging_product': 'whatsapp',
        'to': OWNER_WA,
        'type': 'template',
        'template': {
            'name': WA_TEMPLATE,
            'language': {'code': WA_TEMPLATE_LANG},
            'components': [{'type': 'body', 'parameters': [
                {'type': 'text', 'text': str(order['id'])},
                {'type': 'text', 'text': str(PRODUCTS[order['product']]['name'])},
                {'type': 'text', 'text': str(order['customer_name'] or '-')},
            ]}]
        }
    }
    try:
        r = requests.post(url, headers={'Authorization': f'Bearer {WA_TOKEN}', 'Content-Type': 'application/json'}, json=payload, timeout=15)
        return r.ok
    except Exception:
        return False


def notify_email(order):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and NOTIFY_EMAIL):
        return False
    msg = EmailMessage()
    msg['Subject'] = f'BOT FORGE — novo pedido {order["id"]}'
    msg['From'] = SMTP_USER
    msg['To'] = NOTIFY_EMAIL
    msg.set_content(
        f'Novo pedido BOT FORGE\n\nPedido: {order["id"]}\nProduto: {PRODUCTS[order["product"]]["name"]}\nCliente: {order["customer_name"] or "-"}\nE-mail: {order["customer_email"] or "-"}\nWhatsApp: {order["customer_phone"] or "-"}\nStatus: {order["status"]}\nPagamento: {order["payment_status"]}\n'
    )
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception:
        return False


@app.before_request
def production_order_processing():
    # Keep the order timeline alive on both the order page and polling endpoint.
    if request.path.startswith('/order/') or request.path.startswith('/api/orders/'):
        token = request.path.rstrip('/').split('/')[-1]
        row = order_from_token(token)
        if row:
            auto_process(row)


@app.after_request
def order_notifications(response):
    # Notify only after customer data has been saved by checkout.
    if request.method == 'POST' and request.path.startswith('/checkout/') and response.status_code in (200, 302, 303):
        token = request.path.rstrip('/').split('/')[-1]
        row = order_from_token(token)
        if row and row['customer_email']:
            notify_whatsapp(row)
            notify_email(row)
    return response


@app.get('/generate/<token>')
def generate_project(token):
    row = order_from_token(token)
    if not row:
        abort(404)
    status = auto_process(row)
    paid_or_test = TEST_MODE and row['payment_status'] == 'Não necessário' or (not TEST_MODE and row['payment_status'] == 'Pago')
    if not paid_or_test or status != 'Entregue':
        return redirect(url_for('order_page', token=token))
    config = safe_json(row['config_json'])
    package, _files = build_project(row, config)
    filename = f"BOT-FORGE-{row['product']}-{row['id']}.zip"
    return send_file(package, mimetype='application/zip', as_attachment=True, download_name=filename)


@app.get('/privacy')
def privacy():
    return render_template('legal.html', title='Política de Privacidade', body='''<h1>Política de Privacidade</h1><p>O BOT FORGE coleta somente os dados necessários para criar, acompanhar, entregar e atender pedidos, como nome, e-mail, WhatsApp e configurações do projeto.</p><p>Os dados são armazenados para execução do serviço, atendimento e histórico do pedido. Não venda ou compartilhe dados pessoais para publicidade de terceiros.</p><p>Para solicitar correção ou exclusão de dados, entre em contato pelo WhatsApp ou e-mail informado no site.</p>''')


@app.get('/terms')
def terms():
    return render_template('legal.html', title='Termos de Uso', body='''<h1>Termos de Uso</h1><p>Os produtos são gerados conforme as configurações informadas pelo cliente. Projetos personalizados podem exigir análise e ajustes antes da entrega.</p><p>O cliente é responsável por tokens, credenciais, conteúdo e integrações que fornecer. Nunca envie senhas ou chaves privadas no briefing.</p><p>Antes de colocar um código gerado em produção, revise dependências, permissões e configurações.</p>''')


@app.get('/admin/backup')
def admin_backup():
    # Reuse the existing admin session guard without duplicating its decorator.
    from flask import session
    if not os.getenv('ADMIN_PASSWORD', '').strip() or not session.get('admin'):
        return redirect(url_for('admin_login'))
    src = sqlite3.connect(str(app.config.get('DB_PATH', os.getenv('BOT_FORGE_DB_PATH', '')) or os.path.join(os.getenv('BOT_FORGE_DATA_DIR', '/data'), 'bot_forge.sqlite3')))
    fd, path = tempfile.mkstemp(suffix='.sqlite3')
    os.close(fd)
    try:
        dst = sqlite3.connect(path)
        src.backup(dst)
        dst.close()
        src.close()
        return send_file(path, as_attachment=True, download_name=f'bot-forge-backup-{dt.datetime.now().strftime("%Y%m%d-%H%M")}.sqlite3', mimetype='application/octet-stream')
    except Exception:
        try: src.close()
        except Exception: pass
        abort(500)


@app.get('/api/system')
def system_status():
    return jsonify({
        'ok': True,
        'test_mode': TEST_MODE,
        'prices_active': True,
        'generator': 'active',
        'auto_processing': AUTO_PROCESS,
        'whatsapp_notifications': bool(WA_TOKEN and WA_PHONE_ID and WA_TEMPLATE and OWNER_WA),
        'email_notifications': bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and NOTIFY_EMAIL),
    })


app = harden(app)
