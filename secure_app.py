import os
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
    con = db(); row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone(); con.close(); return row


def set_order_status(order_id, status):
    con = db(); con.execute('UPDATE orders SET status=?,updated_at=? WHERE id=?', (status, now(), order_id)); con.commit(); con.close()


def auto_process(row):
    if not AUTO_PROCESS or row['status'] in ('Entregue', 'Cancelado') or row['product'] == 'personalizado':
        return row['status']
    allowed = (TEST_MODE and row['payment_status'] == 'Não necessário') or (not TEST_MODE and row['payment_status'] == 'Pago')
    if not allowed: return row['status']
    try:
        start = dt.datetime.fromisoformat(row['updated_at']); elapsed = (dt.datetime.now(dt.timezone.utc) - start).total_seconds()
    except Exception: elapsed = 0
    target = 'Em preparação' if elapsed < PREP_SECONDS else ('Em desenvolvimento' if elapsed < DEV_SECONDS else 'Entregue')
    if target != row['status']: set_order_status(row['id'], target)
    return target


def notify_whatsapp(order):
    if not (WA_TOKEN and WA_PHONE_ID and WA_TEMPLATE and OWNER_WA): return False
    payload = {'messaging_product':'whatsapp','to':OWNER_WA,'type':'template','template':{'name':WA_TEMPLATE,'language':{'code':WA_TEMPLATE_LANG},'components':[{'type':'body','parameters':[{'type':'text','text':str(order['id'])},{'type':'text','text':str(PRODUCTS[order['product']]['name'])},{'type':'text','text':str(order['customer_name'] or '-')}]}]}}
    try:
        r=requests.post(f'https://graph.facebook.com/v20.0/{WA_PHONE_ID}/messages',headers={'Authorization':f'Bearer {WA_TOKEN}','Content-Type':'application/json'},json=payload,timeout=15); return r.ok
    except Exception: return False


def notify_email(order):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and NOTIFY_EMAIL): return False
    msg=EmailMessage(); msg['Subject']=f'BOT FORGE — novo pedido {order["id"]}'; msg['From']=SMTP_USER; msg['To']=NOTIFY_EMAIL
    msg.set_content(f'Pedido: {order["id"]}\nProduto: {PRODUCTS[order["product"]]["name"]}\nCliente: {order["customer_name"] or "-"}\nE-mail: {order["customer_email"] or "-"}\nWhatsApp: {order["customer_phone"] or "-"}\nStatus: {order["status"]}\nPagamento: {order["payment_status"]}\n')
    try:
        with smtplib.SMTP(SMTP_HOST,SMTP_PORT,timeout=15) as smtp:
            smtp.starttls(); smtp.login(SMTP_USER,SMTP_PASSWORD); smtp.send_message(msg)
        return True
    except Exception: return False


@app.before_request
def production_order_processing():
    if request.path.startswith('/order/') or request.path.startswith('/api/orders/'):
        token=request.path.rstrip('/').split('/')[-1]; row=order_from_token(token)
        if row: auto_process(row)


@app.after_request
def order_notifications(response):
    if request.method == 'POST' and request.path.startswith('/checkout/') and response.status_code in (200,302,303):
        token=request.path.rstrip('/').split('/')[-1]; row=order_from_token(token)
        if row and row['customer_email']:
            notify_whatsapp(row); notify_email(row)
    return response


def secure_generate_project(token):
    row=order_from_token(token)
    if not row: abort(404)
    status=auto_process(row)
    allowed=(TEST_MODE and row['payment_status']=='Não necessário') or (not TEST_MODE and row['payment_status']=='Pago')
    if not allowed or status!='Entregue': return redirect(url_for('order_page',token=token))
    package,_files=build_project(row,safe_json(row['config_json']))
    return send_file(package,mimetype='application/zip',as_attachment=True,download_name=f"BOT-FORGE-{row['product']}-{row['id']}.zip")

# Replace the original endpoint without registering a duplicate Flask rule.
app.view_functions['generate_project'] = secure_generate_project


@app.get('/privacy')
def privacy():
    return render_template('legal.html',title='Política de Privacidade',body='''<h1>Política de Privacidade</h1><p>O BOT FORGE coleta somente os dados necessários para criar, acompanhar, entregar e atender pedidos, como nome, e-mail, WhatsApp e configurações do projeto.</p><p>Os dados são usados para execução do serviço, atendimento e histórico do pedido. Para solicitar correção ou exclusão de dados, entre em contato pelos canais informados no site.</p>''')


@app.get('/terms')
def terms():
    return render_template('legal.html',title='Termos de Uso',body='''<h1>Termos de Uso</h1><p>Os produtos são gerados conforme as configurações informadas. Projetos personalizados podem exigir análise e ajustes antes da entrega.</p><p>O cliente é responsável por tokens, credenciais e conteúdo que fornecer. Não envie senhas ou chaves privadas no briefing.</p><p>Revise dependências, permissões e configurações antes de colocar qualquer código gerado em produção.</p>''')


@app.get('/admin/backup')
def admin_backup():
    from flask import session
    if not os.getenv('ADMIN_PASSWORD','').strip() or not session.get('admin'): return redirect(url_for('admin_login'))
    db_path=os.path.join(os.getenv('BOT_FORGE_DATA_DIR','/data'),'bot_forge.sqlite3')
    if not os.path.exists(db_path): abort(404)
    fd,path=tempfile.mkstemp(suffix='.sqlite3'); os.close(fd)
    try:
        src=sqlite3.connect(db_path); dst=sqlite3.connect(path); src.backup(dst); dst.close(); src.close()
        return send_file(path,as_attachment=True,download_name=f"bot-forge-backup-{dt.datetime.now().strftime('%Y%m%d-%H%M')}.sqlite3",mimetype='application/octet-stream')
    except Exception:
        abort(500)


@app.get('/api/system')
def system_status():
    return jsonify({'ok':True,'test_mode':TEST_MODE,'prices_active':True,'generator':'active','auto_processing':AUTO_PROCESS,'whatsapp_notifications':bool(WA_TOKEN and WA_PHONE_ID and WA_TEMPLATE and OWNER_WA),'email_notifications':bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and NOTIFY_EMAIL)})

app = harden(app)
