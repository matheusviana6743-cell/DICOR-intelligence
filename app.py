import os, re, secrets, sqlite3, uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import Flask, request, session, redirect, url_for, abort, flash, send_file, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = Path(os.getenv("DATA_DIR", "/data"))
BASE.mkdir(parents=True, exist_ok=True)
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
DB = BASE / "lastro.db"
MAX_UPLOAD = 8 * 1024 * 1024
ALLOWED = {"jpg", "jpeg", "png", "webp"}

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "1") == "1"

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'OPERACIONAL', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, cargo TEXT NOT NULL, notes TEXT DEFAULT '', farm_notes TEXT DEFAULT '', action_notes TEXT DEFAULT '', general_notes TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS farms (id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER NOT NULL, quantity REAL NOT NULL, proof_path TEXT, created_by INTEGER NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(member_id) REFERENCES members(id), FOREIGN KEY(created_by) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS productions (id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER NOT NULL, quantity REAL NOT NULL, material TEXT NOT NULL, reason TEXT NOT NULL, proof_path TEXT, created_by INTEGER NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(member_id) REFERENCES members(id), FOREIGN KEY(created_by) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS chests (id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER NOT NULL, item TEXT NOT NULL, reason TEXT NOT NULL, proof_path TEXT, created_by INTEGER NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(member_id) REFERENCES members(id), FOREIGN KEY(created_by) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, fixed_value REAL NOT NULL, notes TEXT DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS action_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action_id INTEGER NOT NULL, member_id INTEGER NOT NULL, value REAL NOT NULL, proof_path TEXT, created_by INTEGER NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(action_id) REFERENCES actions(id), FOREIGN KEY(member_id) REFERENCES members(id), FOREIGN KEY(created_by) REFERENCES users(id));
CREATE INDEX IF NOT EXISTS idx_farms_member ON farms(member_id); CREATE INDEX IF NOT EXISTS idx_actions_member ON action_logs(member_id); CREATE INDEX IF NOT EXISTS idx_farms_created ON farms(created_at); CREATE INDEX IF NOT EXISTS idx_action_logs_created ON action_logs(created_at);
'''

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c

def now(): return datetime.now().astimezone().isoformat(timespec="seconds")

def init_db():
    c=db(); c.executescript(SCHEMA); c.commit()
    if c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"] == 0:
        u=os.getenv("ADMIN_USER"); p=os.getenv("ADMIN_PASSWORD")
        if u and p:
            c.execute("INSERT INTO users(name,username,password_hash,role,active,created_at) VALUES(?,?,?,?,1,?)", ("Administrador", u, generate_password_hash(p), "GERENCIA", now())); c.commit()
    c.close()

def csrf():
    if "csrf" not in session: session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]

def protect_csrf():
    if request.method == "POST" and not secrets.compare_digest(request.form.get("csrf", ""), session.get("csrf", "")): abort(400)

@app.before_request
def before(): init_db(); protect_csrf()

def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("user_id"): return redirect(url_for("login"))
        return f(*a,**k)
    return w

def manager_required(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("user_id"): return redirect(url_for("login"))
        if session.get("role") != "GERENCIA": abort(403)
        return f(*a,**k)
    return w

def save_proof(file):
    if not file or not file.filename: return None
    ext = secure_filename(file.filename).rsplit(".",1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED: abort(400, "Arquivo inválido. Use JPG, PNG ou WEBP.")
    if file.content_length and file.content_length > MAX_UPLOAD: abort(413)
    name=f"{uuid.uuid4().hex}.{ext}"; path=UPLOADS/name; file.save(path)
    if path.stat().st_size > MAX_UPLOAD: path.unlink(missing_ok=True); abort(413)
    return name

def rows(sql,args=()):
    c=db(); r=c.execute(sql,args).fetchall(); c.close(); return r

def execute(sql,args=()):
    c=db(); cur=c.execute(sql,args); c.commit(); rid=cur.lastrowid; c.close(); return rid

def money(v): return f"R$ {v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
def fmt_dt(v):
    try: return datetime.fromisoformat(v).strftime("%d/%m/%Y %H:%M")
    except: return v

CSS='''
:root{--bg:#090b10;--panel:#11151d;--panel2:#171c26;--line:#252c38;--text:#f2f5f8;--muted:#8993a3;--accent:#7c5cff;--accent2:#a68bff;--ok:#39d98a;--danger:#ff5d73;--shadow:0 18px 60px #0006}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% -10%,#231b4b 0,#090b10 38%),var(--bg);color:var(--text);font:14px Inter,system-ui,-apple-system,Segoe UI,sans-serif}a{text-decoration:none;color:inherit}.app{display:flex;min-height:100vh}.side{width:250px;background:#0c0f15eF;border-right:1px solid var(--line);padding:22px 14px;position:fixed;inset:0 auto 0 0}.brand{padding:8px 12px 26px}.brand b{font-size:22px;letter-spacing:.08em}.brand span{display:block;color:var(--muted);font-size:11px;margin-top:4px}.nav a{display:flex;gap:11px;padding:11px 12px;border-radius:10px;color:#aeb7c5;margin:4px 0}.nav a:hover,.nav a.active{background:#191e2a;color:#fff}.main{margin-left:250px;width:calc(100% - 250px);padding:28px 34px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px}.top h1{margin:0;font-size:26px}.user{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.card{background:linear-gradient(180deg,#141922,#10141b);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:var(--shadow)}.metric{font-size:28px;font-weight:750;margin-top:8px}.label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}.section{margin-top:18px}.section h2{font-size:17px}.table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:12px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}.table th{color:#8e99a9;font-size:11px;text-transform:uppercase}.btn{border:0;border-radius:10px;padding:10px 14px;background:var(--accent);color:#fff;font-weight:650;cursor:pointer}.btn.secondary{background:#202631}.form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.field{display:flex;flex-direction:column;gap:6px}.field.full{grid-column:1/-1}.field label{font-size:12px;color:#aeb7c5}.input,.select,.textarea{width:100%;background:#0b0f15;border:1px solid var(--line);border-radius:10px;padding:11px 12px;color:#fff;outline:none}.textarea{min-height:90px;resize:vertical}.input:focus,.select:focus,.textarea:focus{border-color:var(--accent)}.flash{padding:11px 13px;border-radius:10px;background:#18271f;border:1px solid #275c42;margin-bottom:14px}.flash.error{background:#321820;border-color:#6e2c38}.login{min-height:100vh;display:grid;place-items:center;padding:20px}.loginbox{width:min(420px,100%);padding:30px}.loginbox .brand{padding-left:0}.muted{color:var(--muted)}.pill{display:inline-block;padding:5px 8px;border-radius:999px;background:#202632;color:#c5ccd6;font-size:11px}.proof{color:var(--accent2)}.empty{padding:28px;text-align:center;color:var(--muted)}.mobile-nav{display:none}@media(max-width:900px){.side{display:none}.main{margin:0;width:100%;padding:18px 14px 82px}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.form{grid-template-columns:1fr}.mobile-nav{display:flex;position:fixed;z-index:20;bottom:0;left:0;right:0;background:#0c0f15f5;border-top:1px solid var(--line);padding:8px;gap:5px;overflow:auto}.mobile-nav a{min-width:72px;text-align:center;font-size:10px;color:#9da7b7;padding:7px}.mobile-nav a b{display:block;font-size:16px;margin-bottom:2px}.top{align-items:flex-start}.top h1{font-size:21px}}
'''
ICONS={"Painel":"◈","Farm":"⬢","Produção":"◉","Baú":"▣","Ações":"◇","Ranking":"↗","Hierarquia":"♟","Usuários":"⚙"}

def layout(title, body):
    nav=[]
    for name,route in [("Painel","dashboard"),("Farm","farms"),("Produção","productions"),("Baú","chests"),("Ações","actions"),("Ranking","ranking"),("Hierarquia","members"),("Usuários","users")]:
        if name=="Usuários" and session.get("role")!="GERENCIA": continue
        nav.append(f'<a href="{url_for(route)}"><b>{ICONS[name]}</b>{name}</a>')
    flashes=''.join(f'<div class="flash {"error" if c=="error" else ""}">{m}</div>' for c,m in session.pop("_flashes",[]))
    return render_template_string(f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#090b10"><title>{title} · CENTRAL LASTRO</title><style>{CSS}</style></head><body><div class="app"><aside class="side"><div class="brand"><b>LASTRO</b><span>CENTRAL ADMINISTRATIVA</span></div><nav class="nav">{''.join(nav)}</nav><div style="position:absolute;bottom:20px;left:26px;right:26px"><div class="muted" style="font-size:11px;margin-bottom:10px">{session.get('name','')}</div><a class="btn secondary" style="display:block;text-align:center" href="{url_for('logout')}">Sair</a></div></aside><main class="main"><div class="top"><h1>{title}</h1><div class="user">{session.get('role','')}</div></div>{flashes}{body}</main><nav class="mobile-nav">{''.join(nav)}</nav></div></body></html>''')

@app.route("/health")
def health():
    c=db(); c.execute("SELECT 1"); c.close(); return {"status":"ok","service":"central-lastro"}

@app.route("/", methods=["GET","POST"])
def login():
    if session.get("user_id"): return redirect(url_for("dashboard"))
    if request.method=="POST":
        u=request.form.get("username","").strip(); p=request.form.get("password","")
        r=rows("SELECT * FROM users WHERE username=? AND active=1",(u,))
        if r and check_password_hash(r[0]["password_hash"],p):
            session.clear(); session["user_id"]=r[0]["id"]; session["name"]=r[0]["name"]; session["role"]=r[0]["role"]; csrf(); return redirect(url_for("dashboard"))
        flash("Usuário ou senha inválidos.","error")
    return render_template_string(f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Login · CENTRAL LASTRO</title><style>{CSS}</style></head><body><div class="login"><form class="card loginbox" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="brand"><b>LASTRO</b><span>CENTRAL ADMINISTRATIVA PRIVADA</span></div><div class="field"><label>Usuário</label><input class="input" name="username" autocomplete="username" required></div><div class="field" style="margin-top:12px"><label>Senha</label><input class="input" type="password" name="password" autocomplete="current-password" required></div><button class="btn" style="width:100%;margin-top:18px">Entrar</button><p class="muted" style="font-size:11px;margin-top:16px">Acesso restrito a usuários autorizados pela gerência.</p></form></div></body></html>''')

@app.get("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.get("/dashboard")
@login_required
def dashboard():
    total_farm=rows("SELECT COALESCE(SUM(quantity),0) v FROM farms")[0]["v"]; total_prod=rows("SELECT COALESCE(SUM(quantity),0) v FROM productions")[0]["v"]; total_money=rows("SELECT COALESCE(SUM(value),0) v FROM action_logs")[0]["v"]; members=rows("SELECT COUNT(*) n FROM members WHERE active=1")[0]["n"]
    recent=rows('''SELECT * FROM (SELECT 'Farm' kind,m.name person,f.quantity amount,f.created_at dt FROM farms f JOIN members m ON m.id=f.member_id UNION ALL SELECT 'Produção',m.name,p.quantity,p.created_at FROM productions p JOIN members m ON m.id=p.member_id UNION ALL SELECT 'Baú',m.name,0,c.created_at FROM chests c JOIN members m ON m.id=c.member_id UNION ALL SELECT 'Ação',m.name,a.value,a.created_at FROM action_logs a JOIN members m ON m.id=a.member_id) ORDER BY dt DESC LIMIT 8''')
    trs=''.join(f'<tr><td><span class="pill">{r["kind"]}</span></td><td>{r["person"]}</td><td>{money(r["amount"]) if r["kind"]=="Ação" else r["amount"]}</td><td>{fmt_dt(r["dt"])}</td></tr>' for r in recent) or '<tr><td colspan="4" class="empty">Nenhuma atividade registrada.</td></tr>'
    return layout("Painel",f'<div class="grid"><div class="card"><div class="label">Farm entregue</div><div class="metric">{total_farm:g}</div></div><div class="card"><div class="label">Produzido</div><div class="metric">{total_prod:g}</div></div><div class="card"><div class="label">Ações movimentadas</div><div class="metric">{money(total_money)}</div></div><div class="card"><div class="label">Membros ativos</div><div class="metric">{members}</div></div></div><div class="card section"><h2>Atividade recente</h2><div class="table-wrap"><table class="table"><tr><th>Tipo</th><th>Pessoa</th><th>Quantidade/Valor</th><th>Data</th></tr>{trs}</table></div></div>')

def member_options(): return rows("SELECT id,name,cargo FROM members WHERE active=1 ORDER BY name")

@app.route("/farms",methods=["GET","POST"])
@login_required
def farms():
    if request.method=="POST": proof=save_proof(request.files.get("proof")); execute("INSERT INTO farms(member_id,quantity,proof_path,created_by,created_at) VALUES(?,?,?,?,?)",(request.form["member_id"],float(request.form["quantity"]),proof,session["user_id"],now())); flash("Registro de farm salvo.")
    data=rows("SELECT f.*,m.name member,u.name creator FROM farms f JOIN members m ON m.id=f.member_id JOIN users u ON u.id=f.created_by ORDER BY f.id DESC LIMIT 100")
    trs=''.join(f'<tr><td>{r["member"]}</td><td>{r["quantity"]:g}</td><td>{fmt_dt(r["created_at"])}</td><td>{r["creator"]}</td><td>{f"<a class=proof href=\'{url_for(\"proof\",filename=r[\"proof_path\"])}\' target=_blank>abrir prova</a>" if r["proof_path"] else "—"}</td></tr>' for r in data) or '<tr><td colspan="5" class="empty">Nenhum registro.</td></tr>'
    opts=''.join(f'<option value="{m["id"]}">{m["name"]} · {m["cargo"]}</option>' for m in member_options())
    body=f'''<div class="card"><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Pessoa que realizou</label><select class="select" name="member_id" required>{opts}</select></div><div class="field"><label>Quantidade de farm</label><input class="input" type="number" step="0.01" min="0.01" name="quantity" required></div><div class="field full"><label>Prova / foto</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><div class="field full"><button class="btn">Registrar farm</button></div></form></div><div class="card section"><h2>Registros</h2><div class="table-wrap"><table class="table"><tr><th>Pessoa</th><th>Quantidade</th><th>Data</th><th>Lançado por</th><th>Prova</th></tr>{trs}</table></div></div>'''
    return layout("Farm",body)

@app.route("/productions",methods=["GET","POST"])
@login_required
def productions():
    if request.method=="POST": proof=save_proof(request.files.get("proof")); execute("INSERT INTO productions(member_id,quantity,material,reason,proof_path,created_by,created_at) VALUES(?,?,?,?,?,?,?)",(request.form["member_id"],float(request.form["quantity"]),request.form["material"].strip(),request.form["reason"],proof,session["user_id"],now())); flash("Produção registrada.")
    data=rows("SELECT p.*,m.name member,u.name creator FROM productions p JOIN members m ON m.id=p.member_id JOIN users u ON u.id=p.created_by ORDER BY p.id DESC LIMIT 100")
    trs=''.join(f'<tr><td>{r["member"]}</td><td>{r["quantity"]:g}</td><td>{r["material"]}</td><td>{r["reason"]}</td><td>{fmt_dt(r["created_at"])}</td><td>{f"<a class=proof href=\'{url_for(\"proof\",filename=r[\"proof_path\"])}\' target=_blank>abrir</a>" if r["proof_path"] else "—"}</td></tr>' for r in data) or '<tr><td colspan="6" class="empty">Nenhum registro.</td></tr>'
    opts=''.join(f'<option value="{m["id"]}">{m["name"]}</option>' for m in member_options())
    body=f'''<div class="card"><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Responsável</label><select class="select" name="member_id" required>{opts}</select></div><div class="field"><label>Quantidade produzida</label><input class="input" type="number" step="0.01" min="0.01" name="quantity" required></div><div class="field"><label>Produto/material utilizado</label><input class="input" name="material" required></div><div class="field"><label>Motivo</label><select class="select" name="reason"><option>uso</option><option>venda</option><option>estoque</option><option>outro</option></select></div><div class="field full"><label>Prova / foto</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><div class="field full"><button class="btn">Registrar produção</button></div></form></div><div class="card section"><h2>Registros</h2><div class="table-wrap"><table class="table"><tr><th>Responsável</th><th>Quantidade</th><th>Material</th><th>Motivo</th><th>Data</th><th>Prova</th></tr>{trs}</table></div></div>'''
    return layout("Produção",body)

@app.route("/chests",methods=["GET","POST"])
@login_required
def chests():
    if request.method=="POST": proof=save_proof(request.files.get("proof")); execute("INSERT INTO chests(member_id,item,reason,proof_path,created_by,created_at) VALUES(?,?,?,?,?,?)",(request.form["member_id"],request.form["item"].strip(),request.form["reason"].strip(),proof,session["user_id"],now())); flash("Retirada do baú registrada.")
    data=rows("SELECT c.*,m.name member,u.name creator FROM chests c JOIN members m ON m.id=c.member_id JOIN users u ON u.id=c.created_by ORDER BY c.id DESC LIMIT 100")
    trs=''.join(f'<tr><td>{r["member"]}</td><td>{r["item"]}</td><td>{r["reason"]}</td><td>{fmt_dt(r["created_at"])}</td><td>{f"<a class=proof href=\'{url_for(\"proof\",filename=r[\"proof_path\"])}\' target=_blank>abrir</a>" if r["proof_path"] else "—"}</td></tr>' for r in data) or '<tr><td colspan="5" class="empty">Nenhum registro.</td></tr>'
    opts=''.join(f'<option value="{m["id"]}">{m["name"]}</option>' for m in member_options())
    body=f'''<div class="card"><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Pessoa que pegou</label><select class="select" name="member_id" required>{opts}</select></div><div class="field"><label>O que pegou</label><input class="input" name="item" required></div><div class="field full"><label>Motivo da retirada</label><input class="input" name="reason" required></div><div class="field full"><label>Prova / foto</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><div class="field full"><button class="btn">Registrar retirada</button></div></form></div><div class="card section"><h2>Histórico do baú</h2><div class="table-wrap"><table class="table"><tr><th>Pessoa</th><th>Item</th><th>Motivo</th><th>Data</th><th>Prova</th></tr>{trs}</table></div></div>'''
    return layout("Baú",body)

@app.route("/actions",methods=["GET","POST"])
@login_required
def actions():
    if request.method=="POST": execute("INSERT INTO actions(name,fixed_value,notes,created_at) VALUES(?,?,?,?)",(request.form["name"].strip(),float(request.form["fixed_value"]),request.form.get("notes","").strip(),now())); flash("Ação criada.")
    acts=rows("SELECT * FROM actions ORDER BY id DESC"); logs=rows("SELECT l.*,a.name action,m.name member FROM action_logs l JOIN actions a ON a.id=l.action_id JOIN members m ON m.id=l.member_id ORDER BY l.id DESC LIMIT 100")
    atr=''.join(f'<tr><td>{a["name"]}</td><td>{money(a["fixed_value"])}</td><td>{a["notes"] or "—"}</td><td><a class="proof" href="{url_for("action_detail",action_id=a["id"])}">Participações</a></td></tr>' for a in acts) or '<tr><td colspan="4" class="empty">Nenhuma ação cadastrada.</td></tr>'
    ltr=''.join(f'<tr><td>{l["action"]}</td><td>{l["member"]}</td><td>{money(l["value"])}</td><td>{fmt_dt(l["created_at"])}</td><td>{f"<a class=proof href=\'{url_for(\"proof\",filename=l[\"proof_path\"])}\' target=_blank>abrir</a>" if l["proof_path"] else "—"}</td></tr>' for l in logs) or '<tr><td colspan="5" class="empty">Nenhuma participação.</td></tr>'
    opts=''.join(f'<option value="{m["id"]}">{m["name"]}</option>' for m in member_options()); aopts=''.join(f'<option value="{a["id"]}">{a["name"]} · {money(a["fixed_value"])}</option>' for a in acts)
    body=f'''<div class="grid"><div class="card" style="grid-column:span 2"><h2>Nova ação</h2><form class="form" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" required></div><div class="field"><label>Valor fixo por participação</label><input class="input" type="number" step="0.01" min="0" name="fixed_value" required></div><div class="field full"><label>Observações</label><textarea class="textarea" name="notes"></textarea></div><div class="field full"><button class="btn">Criar ação</button></div></form></div><div class="card"><div class="label">Total movimentado</div><div class="metric">{money(sum(a["value"] for a in logs))}</div></div><div class="card"><h2>Registrar participação</h2><form class="form" method="post" action="{url_for("action_participate")}" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Ação</label><select class="select" name="action_id" required>{aopts}</select></div><div class="field"><label>Pessoa</label><select class="select" name="member_id" required>{opts}</select></div><div class="field full"><label>Prova de participação</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><div class="field full"><button class="btn">Registrar participação</button></div></form></div></div><div class="card section"><h2>Ações cadastradas</h2><div class="table-wrap"><table class="table"><tr><th>Ação</th><th>Valor</th><th>Observações</th><th></th></tr>{atr}</table></div></div><div class="card section"><h2>Participações</h2><div class="table-wrap"><table class="table"><tr><th>Ação</th><th>Pessoa</th><th>Recebido</th><th>Data</th><th>Prova</th></tr>{ltr}</table></div></div>'''
    return layout("Ações",body)

@app.post("/actions/participate")
@login_required
def action_participate():
    a=rows("SELECT * FROM actions WHERE id=?",(request.form["action_id"],))
    if not a: abort(404)
    proof=save_proof(request.files.get("proof")); execute("INSERT INTO action_logs(action_id,member_id,value,proof_path,created_by,created_at) VALUES(?,?,?,?,?,?)",(a[0]["id"],request.form["member_id"],a[0]["fixed_value"],proof,session["user_id"],now())); flash(f'Participação registrada. Valor automático: {money(a[0]["fixed_value"])}'); return redirect(url_for("actions"))

@app.get("/actions/<int:action_id>")
@login_required
def action_detail(action_id):
    a=rows("SELECT * FROM actions WHERE id=?",(action_id,));
    if not a: abort(404)
    logs=rows("SELECT l.*,m.name member FROM action_logs l JOIN members m ON m.id=l.member_id WHERE l.action_id=? ORDER BY l.id DESC",(action_id,))
    trs=''.join(f'<tr><td>{l["member"]}</td><td>{money(l["value"])}</td><td>{fmt_dt(l["created_at"])}</td><td>{f"<a class=proof href=\'{url_for(\"proof\",filename=l[\"proof_path\"])}\' target=_blank>abrir</a>" if l["proof_path"] else "—"}</td></tr>' for l in logs) or '<tr><td colspan="4" class="empty">Sem participações.</td></tr>'
    return layout(a[0]["name"],f'<div class="card"><div class="label">Valor fixo</div><div class="metric">{money(a[0]["fixed_value"])}</div><p class="muted">{a[0]["notes"] or "Sem observações."}</p></div><div class="card section"><div class="table-wrap"><table class="table"><tr><th>Pessoa</th><th>Valor</th><th>Data</th><th>Prova</th></tr>{trs}</table></div></div>')

@app.get("/ranking")
@login_required
def ranking():
    farm=rows("SELECT m.name,COALESCE(SUM(f.quantity),0) total FROM members m LEFT JOIN farms f ON f.member_id=m.id WHERE m.active=1 GROUP BY m.id ORDER BY total DESC,m.name")
    act=rows("SELECT m.name,COUNT(l.id) total FROM members m LEFT JOIN action_logs l ON l.member_id=m.id WHERE m.active=1 GROUP BY m.id ORDER BY total DESC,m.name")
    def rank(data): return ''.join(f'<tr><td>#{i}</td><td>{r["name"]}</td><td>{r["total"]:g}</td></tr>' for i,r in enumerate(data,1)) or '<tr><td colspan="3" class="empty">Sem dados.</td></tr>'
    return layout("Ranking",f'<div class="grid"><div class="card"><h2>Ranking de Farm</h2><div class="table-wrap"><table class="table"><tr><th>Pos.</th><th>Nome</th><th>Total</th></tr>{rank(farm)}</table></div></div><div class="card"><h2>Ranking de Ações</h2><div class="table-wrap"><table class="table"><tr><th>Pos.</th><th>Nome</th><th>Participações</th></tr>{rank(act)}</table></div></div></div>')

@app.route("/members",methods=["GET","POST"])
@login_required
def members():
    if request.method=="POST": execute("INSERT INTO members(name,cargo,notes,farm_notes,action_notes,general_notes,created_at) VALUES(?,?,?,?,?,?,?)",(request.form["name"].strip(),request.form["cargo"].strip(),request.form.get("notes",""),request.form.get("farm_notes",""),request.form.get("action_notes",""),request.form.get("general_notes",""),now())); flash("Membro cadastrado.")
    ms=rows("SELECT * FROM members ORDER BY active DESC, cargo, name")
    trs=''.join(f'<tr><td>{m["name"]}</td><td>{m["cargo"]}</td><td>{m["notes"] or "—"}</td><td>{m["farm_notes"] or "—"}</td><td>{m["action_notes"] or "—"}</td><td>{m["general_notes"] or "—"}</td></tr>' for m in ms) or '<tr><td colspan="6" class="empty">Nenhum membro.</td></tr>'
    form='''<div class="card"><h2>Novo membro</h2><form class="form" method="post"><input type="hidden" name="csrf" value="CSRF"><div class="field"><label>Nome</label><input class="input" name="name" required></div><div class="field"><label>Cargo</label><input class="input" name="cargo" required></div><div class="field"><label>Notas</label><textarea class="textarea" name="notes"></textarea></div><div class="field"><label>O que rendeu para o farm</label><textarea class="textarea" name="farm_notes"></textarea></div><div class="field"><label>O que rendeu para ações</label><textarea class="textarea" name="action_notes"></textarea></div><div class="field"><label>Observações gerais</label><textarea class="textarea" name="general_notes"></textarea></div><div class="field full"><button class="btn">Cadastrar membro</button></div></form></div>'''.replace("CSRF",csrf())
    return layout("Hierarquia",form+f'<div class="card section"><h2>Membros</h2><div class="table-wrap"><table class="table"><tr><th>Nome</th><th>Cargo</th><th>Notas</th><th>Farm</th><th>Ações</th><th>Geral</th></tr>{trs}</table></div></div>')

@app.route("/users",methods=["GET","POST"])
@manager_required
def users():
    if request.method=="POST":
        username=request.form["username"].strip(); password=request.form["password"]
        if len(password)<8: flash("A senha precisa ter pelo menos 8 caracteres.","error")
        elif not re.fullmatch(r"[A-Za-z0-9._-]{3,40}",username): flash("Usuário inválido.","error")
        else:
            try: execute("INSERT INTO users(name,username,password_hash,role,active,created_at) VALUES(?,?,?,?,?,?)",(request.form["name"].strip(),username,generate_password_hash(password),request.form["role"],1 if request.form.get("active")=="1" else 0,now())); flash("Usuário criado. A senha não é exibida nem armazenada em texto puro.")
            except sqlite3.IntegrityError: flash("Esse usuário já existe.","error")
    us=rows("SELECT id,name,username,role,active,created_at FROM users ORDER BY id DESC")
    trs=''.join(f'<tr><td>{u["name"]}</td><td>{u["username"]}</td><td><span class="pill">{u["role"]}</span></td><td>{"Ativo" if u["active"] else "Inativo"}</td><td>{fmt_dt(u["created_at"])}</td><td><form method="post" action="{url_for("toggle_user",user_id=u["id"])}"><input type="hidden" name="csrf" value="{csrf()}"><button class="btn secondary">{"Desativar" if u["active"] else "Ativar"}</button></form></td></tr>' for u in us)
    return layout("Usuários",f'''<div class="card"><h2>Novo usuário</h2><form class="form" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" required></div><div class="field"><label>Usuário</label><input class="input" name="username" required></div><div class="field"><label>Senha</label><input class="input" type="password" name="password" minlength="8" required></div><div class="field"><label>Cargo/perfil</label><select class="select" name="role"><option>OPERACIONAL</option><option>GERENCIA</option></select></div><div class="field"><label>Status</label><select class="select" name="active"><option value="1">Ativo</option><option value="0">Inativo</option></select></div><div class="field full"><button class="btn">Criar usuário</button></div></form></div><div class="card section"><h2>Acessos</h2><div class="table-wrap"><table class="table"><tr><th>Nome</th><th>Usuário</th><th>Perfil</th><th>Status</th><th>Criado em</th><th></th></tr>{trs}</table></div></div>''')

@app.post("/users/<int:user_id>/toggle")
@manager_required
def toggle_user(user_id):
    if user_id==session["user_id"]: flash("Não é permitido desativar o próprio acesso.","error")
    else: execute("UPDATE users SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(user_id,)); flash("Status do usuário atualizado.")
    return redirect(url_for("users"))

@app.get("/proof/<path:filename>")
@login_required
def proof(filename):
    if not re.fullmatch(r"[a-f0-9]{32}\.(jpg|jpeg|png|webp)",filename): abort(404)
    p=UPLOADS/filename
    if not p.is_file(): abort(404)
    return send_file(p,as_attachment=False,download_name=filename)

@app.errorhandler(413)
def too_large(e): return ("Arquivo excede o limite de 8 MB.",413)
@app.errorhandler(403)
def forbidden(e): return ("Acesso negado.",403)

if __name__ == "__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)))
