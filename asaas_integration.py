import os
import requests
from flask import render_template, request, redirect, url_for, jsonify, abort

from app import app, db, _get_order, now, normalize_phone, PRODUCTS

ASAAS_API_KEY = os.getenv('ASAAS_API_KEY', '').strip()
ASAAS_BASE_URL = os.getenv('ASAAS_BASE_URL', 'https://api-sandbox.asaas.com/v3').rstrip('/')


def _headers():
    return {
        'access_token': ASAAS_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'BOT-FORGE/1.0 (Sandbox)',
    }


def _request(method, path, **kwargs):
    if not ASAAS_API_KEY:
        raise RuntimeError('O pagamento de teste está temporariamente indisponível.')
    response = requests.request(
        method,
        f'{ASAAS_BASE_URL}{path}',
        headers=_headers(),
        timeout=30,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def _ensure_schema():
    con = db()
    cols = {r['name'] for r in con.execute('PRAGMA table_info(orders)').fetchall()}
    if 'asaas_cpf_cnpj' not in cols:
        con.execute('ALTER TABLE orders ADD COLUMN asaas_cpf_cnpj TEXT')
    con.commit()
    con.close()


def create_asaas_payment(row):
    """Create an Asaas hosted Checkout without collecting CPF/CNPJ in BOT FORGE.

    The payer is sent to the Asaas-hosted checkout page, where Asaas handles
    any additional information it requires. This keeps the BOT FORGE checkout
    short and avoids creating an Asaas customer through /customers.
    """
    if row['product'] == 'personalizado':
        raise RuntimeError('Projeto personalizado precisa de orçamento.')

    amount = float(row['price'] or 0)
    if amount <= 0:
        raise RuntimeError('Pedido sem valor fixo.')

    product = PRODUCTS[row['product']]
    data = {
        'billingTypes': ['PIX'],
        'chargeTypes': ['DETACHED'],
        'minutesToExpire': 60,
        'externalReference': row['id'],
        'items': [{
            'externalReference': row['product'],
            'name': product['name'],
            'description': product.get('description', product['name']),
            'quantity': 1,
            'value': round(amount, 2),
        }],
    }

    checkout = _request('POST', '/checkouts', json=data)
    checkout_id = checkout.get('id')
    checkout_url = checkout.get('link')
    if not checkout_id or not checkout_url:
        raise RuntimeError('O Asaas não retornou um checkout válido.')

    con = db()
    con.execute(
        "UPDATE orders SET payment_url=?,updated_at=? WHERE id=?",
        (checkout_url, now(), row['id']),
    )
    con.commit()
    con.close()
    return checkout


def sync_asaas_payment(row):
    if not row or not row['asaas_payment_id']:
        return row
    try:
        payment = _request('GET', f"/payments/{row['asaas_payment_id']}")
    except Exception:
        return row

    status = payment.get('status')
    paid_statuses = {'RECEIVED', 'CONFIRMED', 'RECEIVED_IN_CASH'}
    failed_statuses = {
        'OVERDUE', 'REFUNDED', 'REFUND_REQUESTED', 'CHARGEBACK_REQUESTED',
        'CHARGEBACK_DISPUTE', 'AWAITING_CHARGEBACK_REVERSAL'
    }

    con = db()
    if status in paid_statuses:
        con.execute(
            "UPDATE orders SET payment_status='Pago',status='Em preparação',updated_at=? WHERE id=?",
            (now(), row['id']),
        )
    elif status in failed_statuses:
        con.execute(
            "UPDATE orders SET payment_status='Falhou',status='Aguardando pagamento',updated_at=? WHERE id=?",
            (now(), row['id']),
        )
    con.commit()
    con.close()
    return _get_order(row['id'])


def checkout_asaas(token):
    con = db()
    row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone()
    con.close()
    if not row:
        abort(404)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = normalize_phone(request.form.get('phone', ''))

        if not name or not email or not phone:
            return render_template(
                'checkout.html',
                order=row,
                error='Preencha nome, e-mail e WhatsApp para continuar.',
            )

        con = db()
        con.execute(
            "UPDATE orders SET customer_name=?,customer_email=?,customer_phone=?,status=?,payment_status=?,updated_at=? WHERE id=?",
            (name, email, phone, 'Aguardando pagamento', 'Aguardando', now(), row['id']),
        )
        con.commit()
        con.close()
        row = _get_order(row['id'])

        if row['product'] == 'personalizado':
            return render_template(
                'checkout.html',
                order=row,
                error='Projeto personalizado: o valor será definido após análise. Entre em contato pelo WhatsApp para receber a cobrança.',
            )

        try:
            checkout = create_asaas_payment(row)
            checkout_url = checkout.get('link')
            if not checkout_url:
                return render_template(
                    'checkout.html',
                    order=_get_order(row['id']),
                    error='O Asaas não retornou o link do pagamento. Tente novamente.',
                ), 502
            return redirect(checkout_url)
        except requests.HTTPError as exc:
            detail = ''
            try:
                payload = exc.response.json() or {}
                detail = payload.get('errors', [{}])[0].get('description', '')
            except Exception:
                pass

            if exc.response is not None and exc.response.status_code == 401:
                message = 'A integração de pagamento de teste não está autenticada. Confira a chave Sandbox e tente novamente.'
            else:
                message = 'Não foi possível iniciar o pagamento de teste.'
                if detail:
                    message += f' {detail}'

            return render_template(
                'checkout.html',
                order=_get_order(row['id']),
                error=message,
            ), 503
        except Exception:
            return render_template(
                'checkout.html',
                order=_get_order(row['id']),
                error='Não foi possível iniciar o pagamento de teste. Tente novamente em alguns instantes.',
            ), 503

    return render_template('checkout.html', order=row)


def order_status_asaas(token):
    con = db()
    row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone()
    con.close()
    if not row:
        return jsonify({'error': 'Pedido não encontrado.'}), 404
    row = sync_asaas_payment(row)
    return jsonify({
        'ok': True,
        'id': row['id'],
        'status': row['status'],
        'payment_status': row['payment_status'],
        'ready': row['status'] == 'Entregue',
        'updated_at': row['updated_at'],
        'payment_url': row['payment_url'],
    })


def asaas_webhook():
    token = os.getenv('ASAAS_WEBHOOK_TOKEN', '').strip()
    if token and request.headers.get('asaas-access-token') != token:
        return jsonify({'error': 'unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    event_id = payload.get('id') or payload.get('eventId')
    if event_id:
        con = db()
        exists = con.execute('SELECT 1 FROM webhook_events WHERE id=?', (event_id,)).fetchone()
        if exists:
            con.close()
            return jsonify({'ok': True, 'duplicate': True})
        con.execute(
            'INSERT INTO webhook_events(id,event,created_at) VALUES(?,?,?)',
            (event_id, payload.get('event', ''), now()),
        )
        con.commit()
        con.close()

    payment = payload.get('payment') or {}
    payment_id = payment.get('id')
    if payment_id:
        con = db()
        row = con.execute(
            'SELECT * FROM orders WHERE asaas_payment_id=?',
            (payment_id,),
        ).fetchone()
        con.close()
        if row:
            sync_asaas_payment(row)

    return jsonify({'ok': True})


def install():
    if not ASAAS_API_KEY:
        return
    _ensure_schema()
    app.view_functions['checkout'] = checkout_asaas
    app.view_functions['order_status'] = order_status_asaas
    if 'asaas_webhook' not in app.view_functions:
        app.add_url_rule('/webhooks/asaas', 'asaas_webhook', asaas_webhook, methods=['POST'])
    app.config['ASAAS_ENABLED'] = True
