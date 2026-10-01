import os, json, secrets, sqlite3, uuid, datetime as dt
from pathlib import Path
from functools import wraps
from urllib.parse import urlparse
import requests
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("BOT_FORGE_DATA_DIR", "/data" if Path("/data").exists() else str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "bot_forge.sqlite3"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

CONTACT_WA = "5571996936743"
CONTACT_EMAIL = "matheusviana6743@gmail.com"
ASAAS_KEY = os.getenv("ASAAS_API_KEY", "").strip()
ASAAS_BASE = os.getenv("ASAAS_API_BASE", "https://api-sandbox.asaas.com/v3").rstrip("/")
ASAAS_WEBHOOK_TOKEN = os.getenv("ASAAS_WEBHOOK_TOKEN", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

PRODUCTS = {
    "discord": {"name": "Bot Discord", "price": 49.90, "type": "fixed"},
    "fivem": {"name": "Sistema FiveM", "price": 40.00, "type": "fixed"},
    "site": {"name": "Site / Web", "price": 30.00, "type": "fixed"},
    "personalizado": {"name": "Projeto personalizado", "min": 50.00, "max": 200.00, "type": "quote"},
}

CONFIGS = {
    "discord": [
        ("Objetivo", "objective", "textarea", True, "Explique em poucas palavras o que o bot precisa fazer."),
        ("Nome do bot", "bot_name", "text", False, "Ex.: Forge Tickets"),
        ("Nome do servidor", "server_name", "text", False, "Opcional"),
        ("Tipo", "bot_type", "select", False, ["Tickets", "Moderação", "Economia", "Atendimento", "Whitelist", "Vendas", "Personalizado"]),
        ("Tickets", "tickets", "multi", False, ["Criar ticket", "Categorias", "Transcrição", "Fechamento automático"]),
        ("Moderação", "moderation", "multi", False, ["Ban", "Kick", "Mute", "Anti-spam", "Filtros"]),
        ("Logs", "logs", "multi", False, ["Mensagens", "Entradas/Saídas", "Moderação", "Tickets", "Auditoria"]),
        ("Automação", "automation", "multi", False, ["AutoRole", "Boas-vindas", "Verificação", "Cargos por reação"]),
        ("Economia", "economy", "multi", False, ["Saldo", "Loja", "Ranking", "XP"]),
        ("Interface", "ui", "multi", False, ["Embeds", "Botões", "Menus", "Slash Commands"]),
        ("Integrações", "integrations", "multi", False, ["Webhooks", "Painel Web", "APIs", "Banco de dados"]),
        ("Permissões", "permissions", "textarea", False, "Quais cargos podem usar cada área?"),
        ("Idioma", "language", "select", False, ["Português", "Português + Inglês", "Outro"]),
        ("Cor/estilo", "style", "text", False, "Opcional"),
        ("Hospedagem", "hosting", "select", False, ["Já tenho", "Quero orientação", "Quero hospedagem"]),
        ("Código-fonte", "source_code", "select", False, ["Incluir", "Não incluir"]),
        ("Observações", "notes", "textarea", False, "Qualquer detalhe adicional."),
    ],
    "fivem": [
        ("Objetivo", "objective", "textarea", True, "Explique em poucas palavras o que o sistema precisa fazer."),
        ("Framework", "framework", "select", False, ["QBCore", "ESX", "Standalone", "Outro"]),
        ("Versão", "version", "text", False, "Ex.: versão atual do seu servidor"),
        ("Tipo de sistema", "system_type", "select", False, ["Emprego", "Administrativo", "Economia", "UI/NUI", "Interação", "Personalizado"]),
        ("Jobs", "jobs", "textarea", False, "Ex.: Polícia, EMS, Mecânico"),
        ("Comandos", "commands", "textarea", False, "Liste comandos desejados."),
        ("Permissões", "permissions", "textarea", False, "Grupos/cargos que terão acesso."),
        ("UI / NUI", "nui", "multi", False, ["Menu", "Dashboard", "Notificações", "Formulários"]),
        ("Banco de dados", "database", "select", False, ["Não", "MySQL", "Outro"]),
        ("Discord", "discord_logs", "multi", False, ["Logs", "Webhooks", "Comandos integrados"]),
        ("Integrações", "integrations", "textarea", False, "Scripts, APIs ou recursos que precisam conversar com o sistema."),
        ("Dependências", "dependencies", "textarea", False, "Opcional"),
        ("Visual", "visual", "text", False, "Cores, estilo, identidade."),
        ("Otimização", "optimization", "select", False, ["Padrão", "Priorizar performance"]),
        ("Documentação", "documentation", "select", False, ["Incluir", "Não incluir"]),
        ("Código-fonte", "source_code", "select", False, ["Incluir", "Não incluir"]),
        ("Observações", "notes", "textarea", False, "Qualquer detalhe adicional."),
    ],
    "site": [
        ("Objetivo", "objective", "textarea", True, "Explique o objetivo do site."),
        ("Tipo", "site_type", "select", False, ["Landing page", "Loja", "Portfólio", "Site para servidor", "Dashboard", "Sistema Web", "Personalizado"]),
        ("Nome / marca", "brand", "text", False, "Opcional"),
        ("Páginas", "pages", "textarea", False, "Ex.: Início, Sobre, Contato"),
        ("Seções", "sections", "textarea", False, "Ex.: Hero, preços, FAQ, depoimentos"),
        ("Formulário", "forms", "multi", False, ["Contato", "Orçamento", "Cadastro", "Login"]),
        ("Integrações", "integrations", "multi", False, ["WhatsApp", "Instagram", "Discord", "APIs"]),
        ("Área do cliente", "client_area", "select", False, ["Não", "Sim"]),
        ("Painel administrativo", "admin_panel", "select", False, ["Não", "Sim"]),
        ("Banco de dados", "database", "select", False, ["Não", "SQLite", "PostgreSQL", "Outro"]),
        ("Responsividade", "responsive", "select", False, ["Celular + PC", "PC apenas"]),
        ("Cores", "colors", "text", False, "Ex.: claro + dourado"),
        ("Estilo", "style", "text", False, "Ex.: moderno, minimalista"),
        ("Animações", "animations", "select", False, ["Discretas", "Sem animações", "Mais dinâmicas"]),
        ("SEO básico", "seo", "select", False, ["Incluir", "Não incluir"]),
        ("Domínio / hospedagem", "hosting", "select", False, ["Já tenho", "Quero orientação", "Quero publicação"]),
        ("Código-fonte", "source_code", "select", False, ["Incluir", "Não incluir"]),
        ("Observações", "notes", "textarea", False, "Qualquer detalhe adicional."),
    ],
    "personalizado": [
        ("O que você quer criar?", "objective", "textarea", True, "Descreva a ideia do projeto."),
        ("Plataforma", "platform", "select", False, ["Discord", "FiveM", "Web / Site", "Discord + FiveM", "Outro"]),
        ("Funcionalidades", "features", "textarea", False, "Liste tudo o que lembrar."),
        ("Integrações", "integrations", "textarea", False, "APIs, Discord, banco de dados, pagamentos etc."),
        ("Referências", "references", "textarea", False, "Links ou exemplos de algo parecido."),
        ("Preferências visuais", "style", "textarea", False, "Cores, estilo e identidade."),
        ("Código-fonte", "source_code", "select", False, ["Incluir", "Não sei ainda"]),
        ("Observações", "notes", "textarea", False, "Detalhes adicionais."),
    ],
}

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS orders(
        id TEXT PRIMARY KEY,
        token TEXT UNIQUE NOT NULL,
        product TEXT NOT NULL,
        config_json TEXT NOT NULL,
        customer_name TEXT,
        customer_email TEXT,
        customer_phone TEXT,
        price REAL,
        price_min REAL,
        price_max REAL,
        status TEXT NOT NULL,
        payment_status TEXT NOT NULL,
        asaas_customer_id TEXT,
        asaas_payment_id TEXT,
        payment_url TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS webhook_events(
        id TEXT PRIMARY KEY,
        event TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS demos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        product TEXT NOT NULL,
        url TEXT NOT NULL,
        description TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)
    con.commit()
    con.close()

init_db()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not ADMIN_PASSWORD or not session.get("admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped

def normalize_phone(p):
    return "".join(c for c in (p or "") if c.isdigit())

def safe_json_loads(v, default=None):
    try:
        return json.loads(v)
    except Exception:
        return default if default is not None else {}

def whatsapp_link(message):
    from urllib.parse import quote
    return f"https://wa.me/{CONTACT_WA}?text={quote(message)}"

def order_message(order):
    return (
        f"Olá! Quero acompanhar o pedido {order['id']} da BOT FORGE.\n"
        f"Produto: {PRODUCTS.get(order['product'], {'name':order['product']})['name']}\n"
        f"Status: {order['status']}."
    )

def calc_price(product):
    p = PRODUCTS[product]
    if p["type"] == "fixed":
        return p["price"], None, None
    return None, p["min"], p["max"]

def asaas_headers():
    return {"access_token": ASAAS_KEY, "Content-Type": "application/json"}

def asaas_create_customer(name, email, phone):
    payload = {"name": name, "email": email}
    if phone:
        payload["mobilePhone"] = phone
    r = requests.post(f"{ASAAS_BASE}/customers", headers=asaas_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def asaas_create_payment(customer_id, order_id, value, billing="UNDEFINED"):
    due = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    payload = {
        "customer": customer_id,
        "billingType": billing,
        "value": round(float(value), 2),
        "dueDate": due,
        "description": f"BOT FORGE - {order_id}",
        "externalReference": order_id,
    }
    if PUBLIC_URL:
        payload["callback"] = {"successUrl": f"{PUBLIC_URL}/order/{_get_token_by_id(order_id)}"}
    r = requests.post(f"{ASAAS_BASE}/payments", headers=asaas_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def _get_token_by_id(order_id):
    con = db()
    row = con.execute("SELECT token FROM orders WHERE id=?", (order_id,)).fetchone()
    con.close()
    return row["token"] if row else ""

@app.context_processor
def inject_globals():
    return {
        "products": PRODUCTS,
        "contact_wa": CONTACT_WA,
        "contact_email": CONTACT_EMAIL,
        "public_url": PUBLIC_URL,
    }

@app.get("/")
def index():
    con = db()
    demos = con.execute("SELECT * FROM demos WHERE active=1 ORDER BY id DESC").fetchall()
    con.close()
    return render_template("index.html", demos=demos)

@app.get("/config/<product>")
def configurator(product):
    if product not in PRODUCTS:
        abort(404)
    return render_template("configurator.html", product=product, product_info=PRODUCTS[product], fields=CONFIGS[product])

@app.post("/api/orders")
def create_order():
    data = request.get_json(silent=True) or request.form.to_dict(flat=False)
    product = data.get("product")
    if isinstance(product, list):
        product = product[0] if product else None
    if product not in PRODUCTS:
        return jsonify({"error": "Produto inválido."}), 400

    config = data.get("config", {})
    if isinstance(config, str):
        config = safe_json_loads(config)
    objective = str(config.get("objective", "")).strip()
    if not objective:
        return jsonify({"error": "O objetivo do projeto é obrigatório."}), 400

    oid = f"BF-{dt.datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    token = secrets.token_urlsafe(24)
    price, pmin, pmax = calc_price(product)
    ts = now()
    con = db()
    con.execute(
        "INSERT INTO orders(id,token,product,config_json,price,price_min,price_max,status,payment_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (oid, token, product, json.dumps(config, ensure_ascii=False), price, pmin, pmax, "Aguardando dados", "Pendente", ts, ts)
    )
    con.commit()
    con.close()
    return jsonify({"ok": True, "id": oid, "token": token, "redirect": url_for("checkout", token=token)})

@app.route("/checkout/<token>", methods=["GET", "POST"])
def checkout(token):
    con = db()
    row = con.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
    con.close()
    if not row:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = normalize_phone(request.form.get("phone", ""))
        if not name or not email or not phone:
            return render_template("checkout.html", order=row, error="Preencha nome, e-mail e WhatsApp.")
        con = db()
        con.execute(
            "UPDATE orders SET customer_name=?,customer_email=?,customer_phone=?,status=?,updated_at=? WHERE id=?",
            (name, email, phone, "Aguardando pagamento", now(), row["id"])
        )
        con.commit()
        con.close()

        if row["price"] is None:
            message = (
                f"Olá! Quero fazer um projeto personalizado na BOT FORGE.\n\n"
                f"Pedido: {row['id']}\nNome: {name}\nE-mail: {email}\nWhatsApp: {phone}\n"
                f"Faixa estimada: R$ {row['price_min']:.2f} a R$ {row['price_max']:.2f}\n\n"
                f"Quero confirmar o orçamento."
            )
            return render_template("checkout.html", order=_get_order(row["id"]), quote=True, wa=whatsapp_link(message))

        if not ASAAS_KEY:
            return render_template(
                "checkout.html",
                order=_get_order(row["id"]),
                payment_unavailable=True,
                error="O checkout online está preparado, mas a conta Asaas ainda não foi conectada ao ambiente."
            )
        try:
            customer = asaas_create_customer(name, email, phone)
            payment = asaas_create_payment(customer["id"], row["id"], row["price"], "UNDEFINED")
            con = db()
            con.execute(
                "UPDATE orders SET asaas_customer_id=?,asaas_payment_id=?,payment_url=?,payment_status=?,updated_at=? WHERE id=?",
                (customer.get("id"), payment.get("id"), payment.get("invoiceUrl"), "Aguardando", now(), row["id"])
            )
            con.commit()
            con.close()
            if payment.get("invoiceUrl"):
                return redirect(payment["invoiceUrl"])
        except requests.RequestException as exc:
            return render_template("checkout.html", order=_get_order(row["id"]), error=f"Não foi possível criar a cobrança agora. Detalhe técnico: {exc}")
    return render_template("checkout.html", order=row)

def _get_order(order_id):
    con = db()
    row = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    con.close()
    return row

@app.get("/order/<token>")
def order_page(token):
    con = db()
    order = con.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
    con.close()
    if not order:
        abort(404)
    return render_template("order.html", order=order, config=safe_json_loads(order["config_json"]), wa=whatsapp_link(order_message(order)))

@app.post("/webhooks/asaas")
def asaas_webhook():
    if ASAAS_WEBHOOK_TOKEN:
        received = request.headers.get("asaas-access-token", "")
        if not secrets.compare_digest(received, ASAAS_WEBHOOK_TOKEN):
            return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    event_id = payload.get("id")
    event = payload.get("event", "")
    payment = payload.get("payment") or {}
    if not event_id:
        return jsonify({"ok": True})
    con = db()
    try:
        con.execute("INSERT INTO webhook_events(id,event,created_at) VALUES(?,?,?)", (event_id, event, now()))
    except sqlite3.IntegrityError:
        con.close()
        return jsonify({"ok": True})
    pid = payment.get("id")
    new_payment = None
    new_status = None
    if event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        new_payment, new_status = "Pago", "Pago"
    elif event in ("PAYMENT_OVERDUE",):
        new_payment, new_status = "Vencido", "Aguardando pagamento"
    elif event in ("PAYMENT_REFUNDED", "PAYMENT_DELETED"):
        new_payment, new_status = "Estornado", "Cancelado"
    if pid and new_payment:
        con.execute(
            "UPDATE orders SET payment_status=?,status=CASE WHEN ?='Pago' THEN 'Pago' ELSE status END,updated_at=? WHERE asaas_payment_id=?",
            (new_payment, new_status, now(), pid)
        )
    con.commit()
    con.close()
    return jsonify({"ok": True})

@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "BOT FORGE"})

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if ADMIN_PASSWORD and secrets.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("admin"))
        return render_template("admin_login.html", error="Senha incorreta.")
    return render_template("admin_login.html")

@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.get("/admin")
@require_admin
def admin():
    con = db()
    stats = {
        "orders": con.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"],
        "paid": con.execute("SELECT COUNT(*) c FROM orders WHERE payment_status='Pago'").fetchone()["c"],
        "pending": con.execute("SELECT COUNT(*) c FROM orders WHERE payment_status IN ('Pendente','Aguardando')").fetchone()["c"],
        "revenue": con.execute("SELECT COALESCE(SUM(price),0) s FROM orders WHERE payment_status='Pago'").fetchone()["s"],
    }
    orders = con.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 100").fetchall()
    customers = con.execute("""
        SELECT customer_name, customer_email, customer_phone, COUNT(*) orders_count,
               COALESCE(SUM(CASE WHEN payment_status='Pago' THEN price ELSE 0 END),0) paid_total
        FROM orders WHERE customer_name IS NOT NULL
        GROUP BY customer_email, customer_name, customer_phone
        ORDER BY orders_count DESC
    """).fetchall()
    demos = con.execute("SELECT * FROM demos ORDER BY id DESC").fetchall()
    con.close()
    return render_template("admin.html", stats=stats, orders=orders, customers=customers, demos=demos, asaas_connected=bool(ASAAS_KEY))

@app.post("/admin/orders/<order_id>/status")
@require_admin
def admin_status(order_id):
    status = request.form.get("status", "").strip()
    allowed = {"Aguardando pagamento","Pago","Em preparação","Em desenvolvimento","Aguardando cliente","Entregue","Cancelado","Aguardando dados"}
    if status not in allowed:
        abort(400)
    con = db()
    con.execute("UPDATE orders SET status=?,updated_at=? WHERE id=?", (status, now(), order_id))
    con.commit()
    con.close()
    return redirect(url_for("admin"))

@app.post("/admin/orders/<order_id>/price")
@require_admin
def admin_price(order_id):
    try:
        value = float(request.form.get("price", "0").replace(",", "."))
    except ValueError:
        abort(400)
    con = db()
    row = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row or row["product"] != "personalizado":
        con.close()
        abort(400)
    value = max(float(row["price_min"]), min(float(row["price_max"]), value))
    con.execute("UPDATE orders SET price=?,updated_at=? WHERE id=?", (value, now(), order_id))
    con.commit()
    con.close()
    return redirect(url_for("admin"))

@app.post("/admin/orders/<order_id>/charge")
@require_admin
def admin_charge(order_id):
    order = _get_order(order_id)
    if not order or not order["price"] or not ASAAS_KEY or not order["customer_name"] or not order["customer_email"]:
        return redirect(url_for("admin"))
    try:
        customer = asaas_create_customer(order["customer_name"], order["customer_email"], normalize_phone(order["customer_phone"]))
        payment = asaas_create_payment(customer["id"], order_id, order["price"], "UNDEFINED")
        con = db()
        con.execute(
            "UPDATE orders SET asaas_customer_id=?,asaas_payment_id=?,payment_url=?,payment_status=?,status=?,updated_at=? WHERE id=?",
            (customer.get("id"), payment.get("id"), payment.get("invoiceUrl"), "Aguardando", "Aguardando pagamento", now(), order_id)
        )
        con.commit()
        con.close()
    except requests.RequestException:
        pass
    return redirect(url_for("admin"))

@app.post("/admin/demos/add")
@require_admin
def admin_demo_add():
    title = request.form.get("title", "").strip()
    product = request.form.get("product", "").strip()
    url = request.form.get("url", "").strip()
    description = request.form.get("description", "").strip()
    if title and product and url:
        con = db()
        con.execute("INSERT INTO demos(title,product,url,description,created_at) VALUES(?,?,?,?,?)", (title, product, url, description, now()))
        con.commit()
        con.close()
    return redirect(url_for("admin"))

@app.post("/admin/demos/<int:demo_id>/delete")
@require_admin
def admin_demo_delete(demo_id):
    con = db()
    con.execute("DELETE FROM demos WHERE id=?", (demo_id,))
    con.commit()
    con.close()
    return redirect(url_for("admin"))

@app.post("/admin/orders/<order_id>/upload")
@require_admin
def admin_upload(order_id):
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect(url_for("admin"))
    order = _get_order(order_id)
    if not order:
        abort(404)
    ext = Path(f.filename).suffix[:10]
    stored = f"{order_id}_{secrets.token_hex(5)}{ext}"
    f.save(UPLOAD_DIR / stored)
    con = db()
    current = safe_json_loads(order["config_json"])
    files = current.get("_delivery_files", [])
    files.append({"name": f.filename, "stored": stored})
    current["_delivery_files"] = files
    con.execute("UPDATE orders SET config_json=?,updated_at=? WHERE id=?", (json.dumps(current, ensure_ascii=False), now(), order_id))
    con.commit()
    con.close()
    return redirect(url_for("admin"))

@app.get("/files/<token>/<stored>")
def public_file(token, stored):
    con = db()
    row = con.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
    con.close()
    if not row:
        abort(404)
    config = safe_json_loads(row["config_json"])
    files = config.get("_delivery_files", [])
    if not any(x.get("stored") == stored for x in files):
        abort(404)
    return send_from_directory(UPLOAD_DIR, stored, as_attachment=True)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
