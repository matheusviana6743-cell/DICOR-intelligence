import os
import datetime as dt
import requests
from flask import render_template, request, redirect, url_for, jsonify, abort

from app import app, db, _get_order, now, normalize_phone, PRODUCTS

ASAAS_API_KEY = os.getenv('ASAAS_API_KEY', '').strip()
ASAAS_BASE_URL = os.getenv('ASAAS_BASE_URL', 'https://api-sandbox.asaas.com/v3').rstrip('/')


def _headers():
    return {'access_token': ASAAS_API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}


def _request(method, path, **kwargs):
    if not ASAAS_API_KEY:
        raise RuntimeError('ASAAS_API_KEY não configurada.')
    response = requests.request(method, f'{ASAAS_BASE_URL}{path}', headers=_headers(), timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def _ensure_schema():
    con = db()
    cols = {r['name'] for r in con.execute('PRAGMA table_info(orders)').fetchall()}
    if 'asaas_cpf_cnpj' not in cols:
        con.execute('ALTER TABLE orders ADD COLUMN asaas_cpf_cnpj TEXT')
    con.commit()
    con.close()


def _find_or_create_customer(row):
    if row['asaas_customer_id']:
        return row['asaas_customer_id']
    cpf_cnpj = (row['asaas_cpf_cnpj'] or '').strip()
    if len(cpf_cnpj) not in (11, 14):
        raise RuntimeError('Informe um CPF ou CNPJ válido para criar o cliente de teste.')
    data = _request('POST', '/customers', json={
        'name': row['customer_name'],
        'cpfCnpj': cpf_cnpj,
        'email': row['customer_email'],
        'mobilePhone': normalize_phone(row['customer_phone']),
        'externalReference': row['id'],
        'notificationDisabled': True,
    })
    customer_id = data['id']
    con = db()
    con.execute('UPDATE orders SET asaas_customer_id=?,updated_at=? WHERE id=?', (customer_id, now(), row['id']))
    con.commit(); con.close()
    return customer_id


def create_asaas_payment(row):
    if row['product'] == 'personalizado':
        raise RuntimeError('Projeto personalizado precisa de orçamento.')
    amount = float(row['price'] or 0)
    if amount <= 0:
        raise RuntimeError('Pedido sem valor fixo.')
    customer_id = _find_or_create_customer(row)
    due = dt.datetime.now(dt.timezone.utc).date().isoformat()
    payment = _request('POST', '/payments', json={
        'customer': customer_id,
        'billingType': 'PIX',
        'value': round(amount, 2),
        'dueDate': due,
        'description': f"BOT FORGE - {PRODUCTS[row['product']]['name']} - {row['id']}",
        'externalReference': row['id'],
    })
    payment_id = payment['id']
    payment_url = payment.get('invoiceUrl') or payment.get('bankSlipUrl')
    con = db()
    con.execute("UPDATE orders SET asaas_payment_id=?,payment_url=?,updated_at=? WHERE id=?", (payment_id, payment_url, now(), row['id']))
    con.commit(); con.close()
    return payment


def sync_asaas_payment(row):
    if not row or not row['asaas_payment_id']:
        return row
    try:
        payment = _request('GET', f"/payments/{row['asaas_payment_id']}")
    except Exception:
        return row
    status = payment.get('status')
    paid_statuses = {'RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH'}
    failed_statuses = {'OVERDUE', 'REFUNDED', 'REFUND_REQUESTED', 'CHARGEBACK_REQUESTED', 'CHARGEBACK_DISPUTE', 'AWAITING_CHARGEBACK_REVERSAL'}
    con = db()
    if status in paid_statuses:
        con.execute("UPDATE orders SET payment_status='Pago',status='Em preparação',updated_at=? WHERE id=?", (now(), row['id']))
    elif status in failed_statuses:
        con.execute("UPDATE orders SET payment_status='Falhou',status='Aguardando pagamento',updated_at=? WHERE id=?", (now(), row['id']))
    con.commit(); con.close()
    return _get_order(row['id'])


def checkout_asaas(token):
    con = db(); row = con.execute('SELECT * FROM orders WHERE token=?',(token,)).fetchone(); con.close()
    if not row:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = normalize_phone(request.form.get('phone', ''))
        cpf_cnpj = ''.join(c for c in request.form.get('cpf_cnpj', '') if c.isdigit())
        if not name or not email or not phone or len(cpf_cnpj) not in (11, 14):
            return render_template('checkout.html', order=row, error='Preencha nome, e-mail, WhatsApp e um CPF/CNPJ válido.')
        con = db()
        con.execute("UPDATE orders SET customer_name=?,customer_email=?,customer_phone=?,asaas_cpf_cnpj=?,status=?,payment_status=?,updated_at=? WHERE id=?", (name,email,phone,cpf_cnpj,'Aguardando pagamento','Aguardando',now(),row['id']))
        con.commit(); con.close(); row = _get_order(row['id'])
        if row['product'] == 'personalizado':
            return render_template('checkout.html', order=row, error='Projeto personalizado: o valor será definido após análise. Entre em contato pelo WhatsApp para receber a cobrança.')
        try:
            payment = create_asaas_payment(row)
            payment_url = payment.get('invoiceUrl') or payment.get('bankSlipUrl')
            if not payment_url:
                return render_template('checkout.html', order=_get_order(row['id']), error='A cobrança foi criada, mas o Asaas não retornou o link de pagamento.'), 502
            return redirect(payment_url)
        except requests.HTTPError as exc:
            detail = ''
            try: detail = exc.response.json().get('errors',[{}])[0].get('description','')
            except Exception: pass
            message = 'Não foi possível criar a cobrança de teste no Asaas.' + (f' {detail}' if detail else ' Confira os dados e a chave Sandbox.')
            return render_template('checkout.html', order=_get_order(row['id']), error=message), 503
        except Exception as exc:
            return render_template('checkout.html', order=_get_order(row['id']), error=f'Não foi possível criar a cobrança de teste no Asaas: {exc}'), 503
    return render_template('checkout.html', order=row)


def order_status_asaas(token):
    con = db(); row = con.execute('SELECT * FROM orders WHERE token=?',(token,)).fetchone(); con.close()
    if not row:
        return jsonify({'error':'Pedido não encontrado.'}), 404
    row = sync_asaas_payment(row)
    return jsonify({'ok':True,'id':row['id'],'status':row['status'],'payment_status':row['payment_status'],'ready':row['status']=='Entregue','updated_at':row['updated_at'],'payment_url':row['payment_url']})


def asaas_webhook():
    token = os.getenv('ASAAS_WEBHOOK_TOKEN', '').strip()
    if token and request.headers.get('asaas-access-token') != token:
        return jsonify({'error':'unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    event_id = payload.get('id') or payload.get('eventId')
    if event_id:
        con = db()
        exists = con.execute('SELECT 1 FROM webhook_events WHERE id=?',(event_id,)).fetchone()
        if exists:
            con.close()
            return jsonify({'ok':True,'duplicate':True})
        con.execute('INSERT INTO webhook_events(id,event,created_at) VALUES(?,?,?)',(event_id,payload.get('event',''),now()))
        con.commit(); con.close()
    payment = payload.get('payment') or {}
    payment_id = payment.get('id')
    if payment_id:
        con = db(); row = con.execute('SELECT * FROM orders WHERE asaas_payment_id=?',(payment_id,)).fetchone(); con.close()
        if row:
            sync_asaas_payment(row)
    return jsonify({'ok':True})


def install():
    if not ASAAS_API_KEY:
        return
    _ensure_schema()
    app.view_functions['checkout'] = checkout_asaas
    app.view_functions['order_status'] = order_status_asaas
    if 'asaas_webhook' not in app.view_functions:
        app.add_url_rule('/webhooks/asaas', 'asaas_webhook', asaas_webhook, methods=['POST'])
    app.config['ASAAS_ENABLED'] = True
