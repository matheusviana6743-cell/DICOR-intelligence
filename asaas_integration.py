import os
import datetime as dt
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
        'User-Agent': f'BOT-FORGE/1.1 ({environment})',
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


def _error_details(exc):
    detail = ''
    code = ''
    status_code = exc.response.status_code if getattr(exc, 'response', None) is not None else None
    try:
        payload = exc.response.json() or {}
        errors = payload.get('errors') or []
        if errors:
            detail = errors[0].get('description', '')
            code = errors[0].get('code', '')
    except Exception:
        pass
    return status_code, detail, code


def _account_status():
    try:
        return _request('GET', '/myAccount/status/')
    except Exception:
        return {}


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


def _save_payment(row_id, payment_id, payment_url):
    con = db()
    con.execute(
        "UPDATE orders SET asaas_payment_id=?,payment_url=?,updated_at=? WHERE id=?",
        (payment_id, payment_url, now(), row_id),
    )
    con.commit()
    con.close()


def create_asaas_checkout(row):
    """Try the hosted Asaas Checkout first."""
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
        'customerData': {
            'name': row['customer_name'],
            'email': row['customer_email'],
            'phone': row['customer_phone'],
        },
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
    checkout_url = checkout.get('link') or (
        f'https://asaas.com/checkoutSession/show?id={checkout_id}' if checkout_id else None
    )

    if not checkout_id or not checkout_url:
        raise RuntimeError('O Asaas não retornou um checkout válido.')

    _save_payment(row['id'], checkout_id, checkout_url)
    return checkout


def create_asaas_invoice(row):
    """Fallback: create a normal PIX charge and redirect to Asaas invoice."""
    amount = float(row['price'] or 0)
    if amount <= 0:
        raise RuntimeError('Pedido sem valor fixo.')

    customer = _request('POST', '/customers', json={
        'name': row['customer_name'],
        'email': row['customer_email'],
        'mobilePhone': row['customer_phone'],
        'externalReference': row['id'],
    })
    customer_id = customer.get('id')
    if not customer_id:
        raise RuntimeError('O Asaas não retornou um cliente válido.')

    con = db()
    con.execute('UPDATE orders SET asaas_customer_id=?,updated_at=? WHERE id=?', (customer_id, now(), row['id']))
    con.commit()
    con.close()

    base_url = _public_base_url()
    due_date = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1)).isoformat()
    payment = _request('POST', '/payments', json={
        'customer': customer_id,
        'billingType': 'PIX',
        'value': round(amount, 2),
        'dueDate': due_date,
        'description': f"BOT FORGE - {PRODUCTS[row['product']]['name']}",
        'externalReference': row['id'],
        'callback': {
            'successUrl': f'{base_url}/payment/success/{row["token"]}',
            'autoRedirect': True,
        },
    })

    payment_id = payment.get('id')
    payment_url = payment.get('invoiceUrl')
    if not payment_id or not payment_url:
        raise RuntimeError('O Asaas não retornou uma fatura válida.')

    _save_payment(row['id'], payment_id, payment_url)
    return payment


def create_asaas_payment(row):
    """Create a real Asaas payment flow, preferring Checkout and falling back to a PIX invoice."""
    try:
        return create_asaas_checkout(row)
    except requests.HTTPError as checkout_exc:
        status_code, detail, code = _error_details(checkout_exc)
        # Some Asaas accounts can create regular charges while Checkout is not enabled.
        # Only fall back for provider-side Checkout availability/configuration errors.
        if status_code not in (400, 403):
            raise
        try:
            payment = create_asaas_invoice(row)
            payment['_botforge_fallback'] = True
            return payment
        except Exception:
            raise checkout_exc


def sync_asaas_payment(row):
    return row


def _render_payment_return(token, title, message):
    con = db()
    row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone()
    con.close()
    if not row:
        abort(404)
    return render_template('checkout.html', order=row, payment_return_title=title, payment_return_message=message)


def payment_success(token):
    return _render_payment_return(token, 'Pagamento iniciado', 'Você voltou do Asaas. A confirmação financeira será feita automaticamente pelo webhook.')


def payment_cancel(token):
    return _render_payment_return(token, 'Pagamento cancelado', 'O pagamento não foi concluído. Você pode tentar novamente.')


def payment_expired(token):
    return _render_payment_return(token, 'Checkout expirado', 'Esse checkout expirou. Volte ao pedido e gere um novo pagamento.')


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
            return render_template('checkout.html', order=row, error='Preencha nome, e-mail e WhatsApp para continuar.')

        con = db()
        con.execute(
            "UPDATE orders SET customer_name=?,customer_email=?,customer_phone=?,status=?,payment_status=?,updated_at=? WHERE id=?",
            (name, email, phone, 'Aguardando pagamento', 'Aguardando', now(), row['id']),
        )
        con.commit()
        con.close()
        row = _get_order(row['id'])

        if row['product'] == 'personalizado':
            return render_template('checkout.html', order=row, error='Projeto personalizado: o valor será definido após análise. Entre em contato pelo WhatsApp para receber a cobrança.')

        try:
            payment = create_asaas_payment(row)
            payment_url = payment.get('link') or payment.get('invoiceUrl')
            if not payment_url:
                raise RuntimeError('O Asaas não retornou um endereço de pagamento.')
            return redirect(payment_url)
        except requests.HTTPError as exc:
            status_code, detail, code = _error_details(exc)
            if status_code == 401:
                message = 'A chave da API do Asaas não foi aceita. Confira se a chave é de Produção e se a URL está em https://api.asaas.com/v3.'
            elif status_code in (400, 403):
                account = _account_status()
                general = (account.get('general') or '').upper()
                commercial = (account.get('commercialInfo') or '').upper()
                documentation = (account.get('documentation') or '').upper()
                if general and general != 'APPROVED':
                    message = 'O Asaas bloqueou a cobrança porque a conta ainda não está aprovada para receber pagamentos.'
                elif commercial in ('PENDING', 'AWAITING_APPROVAL') or documentation in ('PENDING', 'AWAITING_APPROVAL'):
                    message = 'O Asaas bloqueou a cobrança porque ainda existe uma pendência cadastral na conta.'
                else:
                    message = 'O Asaas recusou a criação da cobrança. Verifique as permissões de recebimento e a situação cadastral da conta.'
                if detail:
                    message += f' Detalhe: {detail}'
            else:
                message = 'Não foi possível iniciar o pagamento agora.'
                if detail:
                    message += f' {detail}'
            return render_template('checkout.html', order=_get_order(row['id']), error=message, payment_error_code=code), 503
        except Exception as exc:
            return render_template('checkout.html', order=_get_order(row['id']), error=str(exc) or 'Não foi possível iniciar o pagamento agora. Tente novamente em alguns instantes.'), 503

    return render_template('checkout.html', order=row)


def order_status_asaas(token):
    con = db()
    row = con.execute('SELECT * FROM orders WHERE token=?', (token,)).fetchone()
    con.close()
    if not row:
        return jsonify({'error': 'Pedido não encontrado.'}), 404
    return jsonify({'ok': True, 'id': row['id'], 'status': row['status'], 'payment_status': row['payment_status'], 'ready': row['status'] == 'Entregue', 'updated_at': row['updated_at'], 'payment_url': row['payment_url']})


def _apply_payment_event(con, row, event, payment):
    status = str(payment.get('status') or '').upper()
    if event in ('PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED') or status in ('RECEIVED', 'CONFIRMED'):
        con.execute("UPDATE orders SET payment_status='Pago',status='Em preparação',updated_at=? WHERE id=?", (now(), row['id']))
    elif event in ('PAYMENT_OVERDUE',):
        con.execute("UPDATE orders SET payment_status='Vencido',status='Aguardando pagamento',updated_at=? WHERE id=?", (now(), row['id']))
    elif event in ('PAYMENT_DELETED', 'PAYMENT_REFUNDED'):
        con.execute("UPDATE orders SET payment_status='Cancelado',status='Cancelado',updated_at=? WHERE id=?", (now(), row['id']))


def asaas_webhook():
    token = os.getenv('ASAAS_WEBHOOK_TOKEN', '').strip()
    if token and request.headers.get('asaas-access-token') != token:
        return jsonify({'error': 'unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    event_id = payload.get('id') or payload.get('eventId')
    event = payload.get('event', '')
    checkout = payload.get('checkout') or {}
    payment = payload.get('payment') or {}
    checkout_id = checkout.get('id')
    payment_id = payment.get('id')

    if event_id:
        con = db()
        exists = con.execute('SELECT 1 FROM webhook_events WHERE id=?', (event_id,)).fetchone()
        if exists:
            con.close()
            return jsonify({'ok': True, 'duplicate': True})
        con.execute('INSERT INTO webhook_events(id,event,created_at) VALUES(?,?,?)', (event_id, event, now()))
        con.commit()
        con.close()

    con = db()
    if checkout_id:
        row = con.execute('SELECT * FROM orders WHERE asaas_payment_id=? OR id=?', (checkout_id, checkout.get('externalReference', ''))).fetchone()
        if row:
            if event == 'CHECKOUT_PAID' or checkout.get('status') == 'PAID':
                con.execute("UPDATE orders SET payment_status='Pago',status='Em preparação',updated_at=? WHERE id=?", (now(), row['id']))
            elif event == 'CHECKOUT_CANCELED' or checkout.get('status') == 'CANCELED':
                con.execute("UPDATE orders SET payment_status='Cancelado',status='Cancelado',updated_at=? WHERE id=?", (now(), row['id']))
            elif event == 'CHECKOUT_EXPIRED' or checkout.get('status') == 'EXPIRED':
                con.execute("UPDATE orders SET payment_status='Expirado',status='Aguardando pagamento',updated_at=? WHERE id=?", (now(), row['id']))

    if payment_id:
        row = con.execute('SELECT * FROM orders WHERE asaas_payment_id=? OR id=?', (payment_id, payment.get('externalReference', ''))).fetchone()
        if row:
            _apply_payment_event(con, row, event, payment)

    con.commit()
    con.close()
    return jsonify({'ok': True})


def install():
    if not ASAAS_API_KEY:
        return
    _ensure_schema()
    app.view_functions['checkout'] = checkout_asaas
    app.view_functions['order_status'] = order_status_asaas
    if 'payment_success' not in app.view_functions:
        app.add_url_rule('/payment/success/<token>', 'payment_success', payment_success, methods=['GET'])
    if 'payment_cancel' not in app.view_functions:
        app.add_url_rule('/payment/cancel/<token>', 'payment_cancel', payment_cancel, methods=['GET'])
    if 'payment_expired' not in app.view_functions:
        app.add_url_rule('/payment/expired/<token>', 'payment_expired', payment_expired, methods=['GET'])
    if 'asaas_webhook' not in app.view_functions:
        app.add_url_rule('/webhooks/asaas', 'asaas_webhook', asaas_webhook, methods=['POST'])
    app.config['ASAAS_ENABLED'] = True
