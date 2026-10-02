import os
import requests
from flask import render_template, request, redirect, url_for, jsonify, abort

from app import app, db, _get_order, now, normalize_phone, PRODUCTS

ASAAS_API_KEY = os.getenv('ASAAS_API_KEY', '').strip()
ASAAS_BASE_URL = os.getenv('ASAAS_BASE_URL', 'https://api.asaas.com/v3').rstrip('/')


def _headers():
    production = not ASAAS_BASE_URL.startswith('https://api-sandbox.asaas.com')
    environment = 'production' if production else 'sandbox'
    return {
        'access_token': ASAAS_API_KEY,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': f'BOT-FORGE/1.0 ({environment})',
    }


def _request(method, path, **kwargs):
    if not ASAAS_API_KEY:
        raise RuntimeError('A integração de pagamento não está configurada.')
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


def _public_base_url():
    configured = os.getenv('PUBLIC_URL', '').strip().rstrip('/')
    if configured:
        return configured
    return request.host_url.rstrip('/')


def create_asaas_payment(row):
    """Create an Asaas hosted Checkout without collecting CPF/CNPJ in BOT FORGE."""
    if row['product'] == 'personalizado':
        raise RuntimeError('Projeto personalizado precisa de orçamento.')

    amount = float(row['price'] or 0)
    if amount <= 0:
        raise RuntimeError('Pedido sem valor fixo.')

    product = PRODUCTS[row['product']]
    base_url = _public_base_url()
    data = {
        'billingTypes': ['PIX'],
        'chargeTypes': ['DETACHED'],
        'minutesToExpire': 60,
        'externalReference': row['id'],
        'callback': {
            'successUrl': f'{base_url}/payment/success/{row["token"]}',
            'cancelUrl': f'{base_url}/payment/cancel/{row["token"]}',
            'expiredUrl': f'{base_url}/payment/expired/{row["token"]}',
        },
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
    if not checkout_url and checkout_id:
        checkout_url = f'https://asaas.com/checkoutSession/show?id={checkout_id}'

    if not checkout_id or not checkout_url:
        raise RuntimeError('O Asaas não retornou um checkout válido.')

    con = db()
    con.execute(
        "UPDATE orders SET asaas_payment_id=?,payment_url=?,updated_at=? WHERE id=?",
        (checkout_id, checkout_url, now(), row['id']),
    )
    con.commit()
    con.close()
    return checkout


def sync_asaas_payment(row):
    """Keep the local order state synchronized when a Checkout event is received."""
    return row


def _render_payment_return(token, title, message):
    con = db()
    row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone()
    con.close()
    if not row:
        abort(404)
    return render_template('checkout.html', order=row, payment_return_title=title, payment_return_message=message)


def payment_success(token):
    return _render_payment_return(
        token,
        'Pagamento enviado',
        'O retorno do Asaas foi recebido. A confirmação financeira será feita automaticamente pelo sistema.',
    )


def payment_cancel(token):
    return _render_payment_return(
        token,
        'Pagamento cancelado',
        'O pagamento não foi concluído. Você pode tentar novamente.',
    )


def payment_expired(token):
    return _render_payment_return(
        token,
        'Checkout expirado',
        'Esse checkout expirou. Volte ao pedido e gere um novo pagamento.',
    )


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
            return redirect(checkout['link'])
        except requests.HTTPError as exc:
            detail = ''
            code = ''
            status_code = exc.response.status_code if exc.response is not None else None
            try:
                payload = exc.response.json() or {}
                errors = payload.get('errors') or []
                if errors:
                    detail = errors[0].get('description', '')
                    code = errors[0].get('code', '')
            except Exception:
                pass

            if status_code == 401:
                message = 'A chave da API do Asaas não foi aceita. Para Produção, use uma chave de Produção e a URL https://api.asaas.com/v3.'
            elif status_code == 400:
                message = 'O Asaas recusou os dados do checkout.'
                if detail:
                    message += f' {detail}'
            else:
                message = 'Não foi possível iniciar o pagamento agora.'
                if detail:
                    message += f' {detail}'

            return render_template(
                'checkout.html',
                order=_get_order(row['id']),
                error=message,
                payment_error_code=code,
            ), 503
        except Exception as exc:
            return render_template(
                'checkout.html',
                order=_get_order(row['id']),
                error='Não foi possível iniciar o pagamento agora. Tente novamente em alguns instantes.',
            ), 503

    return render_template('checkout.html', order=row)


def order_status_asaas(token):
    con = db()
    row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone()
    con.close()
    if not row:
        return jsonify({'error': 'Pedido não encontrado.'}), 404
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
    event = payload.get('event', '')
    checkout = payload.get('checkout') or {}
    checkout_id = checkout.get('id')

    if event_id:
        con = db()
        exists = con.execute('SELECT 1 FROM webhook_events WHERE id=?', (event_id,)).fetchone()
        if exists:
            con.close()
            return jsonify({'ok': True, 'duplicate': True})
        con.execute(
            'INSERT INTO webhook_events(id,event,created_at) VALUES(?,?,?)',
            (event_id, event, now()),
        )
        con.commit()
        con.close()

    if checkout_id:
        con = db()
        row = con.execute(
            'SELECT * FROM orders WHERE asaas_payment_id=? OR id=?',
            (checkout_id, checkout.get('externalReference', '')),
        ).fetchone()
        if row:
            if event == 'CHECKOUT_PAID' or checkout.get('status') == 'PAID':
                con.execute(
                    "UPDATE orders SET payment_status='Pago',status='Em preparação',updated_at=? WHERE id=?",
                    (now(), row['id']),
                )
            elif event == 'CHECKOUT_CANCELED' or checkout.get('status') == 'CANCELED':
                con.execute(
                    "UPDATE orders SET payment_status='Cancelado',status='Cancelado',updated_at=? WHERE id=?",
                    (now(), row['id']),
                )
            elif event == 'CHECKOUT_EXPIRED' or checkout.get('status') == 'EXPIRED':
                con.execute(
                    "UPDATE orders SET payment_status='Expirado',status='Aguardando pagamento',updated_at=? WHERE id=?",
                    (now(), row['id']),
                )
            con.commit()
        con.close()

    return jsonify({'ok': True})


def install():
    if not ASAAS_API_KEY:
        return
    _ensure_schema()
    app.view_functions['checkout'] = checkout_asaas
    app.view_functions['order_status'] = order_status_asaas
    app.view_functions['payment_success'] = payment_success
    app.view_functions['payment_cancel'] = payment_cancel
    app.view_functions['payment_expired'] = payment_expired
    if 'payment_success' not in app.view_functions:
        app.add_url_rule('/payment/success/<token>', 'payment_success', payment_success, methods=['GET'])
    if 'payment_cancel' not in app.view_functions:
        app.add_url_rule('/payment/cancel/<token>', 'payment_cancel', payment_cancel, methods=['GET'])
    if 'payment_expired' not in app.view_functions:
        app.add_url_rule('/payment/expired/<token>', 'payment_expired', payment_expired, methods=['GET'])
    if 'asaas_webhook' not in app.view_functions:
        app.add_url_rule('/webhooks/asaas', 'asaas_webhook', asaas_webhook, methods=['POST'])
    app.config['ASAAS_ENABLED'] = True
