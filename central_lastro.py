import os, json, secrets, sqlite3, uuid, re
from pathlib import Path
from datetime import date, timedelta, datetime
from functools import wraps
from flask import Flask, request, session, redirect, url_for, abort, flash, send_file, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = Path(os.getenv('DATA_DIR', '/data'))
BASE.mkdir(parents=True, exist_ok=True)
UPLOADS = BASE / 'uploads'
UPLOADS.mkdir(parents=True, exist_ok=True)
DB_PATH = BASE / 'lastro.db'
MAX_UPLOAD = 8 * 1024 * 1024
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp'}
ROLES = ['ADMINISTRADOR', 'LÍDER', 'VICE-LÍDER', 'GERENTE']

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=MAX_UPLOAD,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '1') == '1',
)

MEMBERS = [
('Vocaro','LÍDER',None),('Nicole Lastro','LÍDER',4202),('Zeca Lastro','VICE-LÍDER',17147),
('Andrey Magnata','GERENTE',28459),('Breno Gomes','GERENTE',32110),('Alice','MEMBRO',72884),
('Bak Tarik','MEMBRO',28996),('Cassimiro','MEMBRO',34553),('dancollins','MEMBRO',None),('Dante','MEMBRO',41728),
('Gabriel Garcia','MEMBRO',33858),('Marcelo Correia','MEMBRO',6027),('Marco Peixoto','MEMBRO',18976),
('Negralha Oliveira','MEMBRO',28804),('Olindo Martins','MEMBRO',23525),('Oliver Bueno','MEMBRO',19975),
('Paulo Miriam','MEMBRO',33250),('Pedro Pinto','MEMBRO',30692),('Sidney Santos','MEMBRO',25419),('Vitin Caiçara','MEMBRO',33952),
('Willian Silveira','MEMBRO',23317),('Zoen Costa','MEMBRO',31195),('Barba Lenda','MEMBRO',24731),('Barrabas Belen','MEMBRO',24089),
('Bene Oliveira','MEMBRO',26158),('Cartola Do Morro','MEMBRO',35159),('Cleiton Rasta','MEMBRO',34549),('Eduardo Madruga','MEMBRO',40203),
('Eneias Silva','MEMBRO',14066),('Erik Mitrovic','MEMBRO',28539),('Fernando Fortes','MEMBRO',12288),('Gustavo Hammes','MEMBRO',42747),
('Gustavo Henrique','MEMBRO',41395),('Josivaldo Rocha','MEMBRO',34623),('Kevin Smity','MEMBRO',42560),('Mameluco Camargo','MEMBRO',42506),
('Miguel Andrade','MEMBRO',31551),('Mirna Santos','MEMBRO',34200),('Muniz Santos','MEMBRO',37700),('Pedro Rocha','MEMBRO',34595),
('Pedro Rossa','MEMBRO',31909),('PH','MEMBRO',42684),('Pulcenio Ferraz','MEMBRO',39908),('Ronan Pires','MEMBRO',None),
('Tony Gentil','MEMBRO',36332),('Velasco Montana','MEMBRO',39323),('Victor Santos','MEMBRO',42677)]

ACTIONS = {
'Joalheria': (1,'5 a 7','9 a 11','Submetralhadora, fuzil ou escopeta. AP Pistol não é considerada submetralhadora.','Obrigatória','Opcional, máximo 3','Máximo 3 veículos; máximo 3 fora e 4 dentro.'),
'Concessionária': (1,'8 a 10','12','Submetralhadora, fuzil ou escopeta. AP Pistol não é considerada submetralhadora.','Obrigatória','Opcional, máximo 4','Máximo 6 veículos: 3 próprios e 3 da concessionária. Polícia: máximo 5 granadas de gás.'),
'Fleeca': (2,'6 a 8','10','A depender do local.','Obrigatória','Obrigatório, máximo 3','Máximo 3 veículos.'),
'Açougue': (1,'8 a 10','12','Submetralhadora, fuzil ou escopeta. AP Pistol não é considerada submetralhadora.','Obrigatória','Opcional, máximo 3','Máximo 3 veículos. Polícia: máximo 3 granadas de gás. Rotação externa P1/P2 permitida.'),
'Galinheiro': (1,'8 a 10','12','Submetralhadora ou fuzil.','Obrigatória','Opcional, máximo 2','Máximo 3 granadas de gás. Proibido posicionamento na mata/morros atrás dos trilhos.'),
'Central do Mergulhador': (1,'7','10','Pistola ou submetralhadora. AP Pistol permitida.','Inexistente','Proibido','A polícia usa o mesmo armamento dos bandidos; com submetralhadora, todo o contingente pode usar.'),
'Banco Central': (1,'10','13','Fuzil.','Obrigatória','Opcional, máximo 4','Máximo 3 veículos. Refém: atiradores OU helicóptero. Em fuga, ninguém fora.'),
'Banco Paleto': (None,'10','13','Fuzil.','Não há.','Proibido','Confronto direto; começa quando a polícia entra no perímetro. Bandidos aguardam.'),
'Loja de Tatuagens': (None,'2','2','Apenas armas brancas; pode negociar combate em punhos.','Obrigatória','Proibido',''),
'Barbearia': (None,'4 a 10','Igual ao número de bandidos','Apenas armas brancas; pode negociar combate em punhos.','Obrigatória','Proibido',''),
'Loja de Armas — Praça': (None,'2','3','Apenas pistolas. AP Pistol proibida.','Obrigatória','Proibido','2 bandidos obrigatórios e nenhum fora.'),
'Loja de Armas — Porto': (None,'3 a 5','5 a 7','Apenas pistolas. AP Pistol proibida.','Obrigatória','Proibido','Proporcional ao número de bandidos.'),
'Loja de Conveniência': (None,'5 a 6','7 a 8','Pistola obrigatória. AP Pistol proibida.','Inexistente','Proibido','Troca de tiros; não há fuga; até 2 bandidos fora dentro do perímetro; inicia quando o primeiro bandido é fechado.')
}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,passport INTEGER,cargo TEXT NOT NULL,notes TEXT DEFAULT '',farm_notes TEXT DEFAULT '',action_notes TEXT DEFAULT '',general_notes TEXT DEFAULT '',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,weekly_limit INTEGER,action_value REAL DEFAULT 0,rules_json TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS farms(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,quantity REAL,proof TEXT,created_by INTEGER,created_at TEXT);
CREATE TABLE IF NOT EXISTS productions(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,quantity REAL,material TEXT,reason TEXT,proof TEXT,created_by INTEGER,created_at TEXT);
CREATE TABLE IF NOT EXISTS chests(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,item TEXT,reason TEXT,proof TEXT,created_by INTEGER,created_at TEXT);
CREATE TABLE IF NOT EXISTS action_records(id INTEGER PRIMARY KEY AUTOINCREMENT,action_id INTEGER,week_start TEXT,action_value REAL,family_value REAL,participant_pool REAL,rules_snapshot TEXT,created_by INTEGER,created_at TEXT,status TEXT DEFAULT 'FINALIZADA');
CREATE TABLE IF NOT EXISTS external_participants(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,passport TEXT,family TEXT);
CREATE TABLE IF NOT EXISTS action_participants(id INTEGER PRIMARY KEY AUTOINCREMENT,record_id INTEGER,member_id INTEGER,external_id INTEGER,side TEXT,weapon TEXT,eligible INTEGER,value_received REAL,reason TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS financial_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,record_id INTEGER,type TEXT,amount REAL,description TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS weekly_periods(id INTEGER PRIMARY KEY AUTOINCREMENT,week_start TEXT UNIQUE,week_end TEXT,closed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,action TEXT,details TEXT,created_at TEXT);
'''

def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=30000')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
def monday(): return date.today() - timedelta(days=date.today().weekday())
def money(v): return f'R$ {float(v or 0):,.2f}'.replace(',','X').replace('.',',').replace('X','.')
def getall(sql,args=()):
    c=conn(); rows=c.execute(sql,args).fetchall(); c.close(); return rows
def execute(sql,args=()):
    c=conn(); cur=c.execute(sql,args); c.commit(); rid=cur.lastrowid; c.close(); return rid

def csrf():
    if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(24)
    return session['csrf']

def audit(action, details=''):
    execute('INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)',(session.get('uid'),action,details,now()))

def save_proof(file):
    if not file or not file.filename: return None
    ext=secure_filename(file.filename).rsplit('.',1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXT: abort(400,'Tipo de arquivo não permitido.')
    name=f'{uuid.uuid4().hex}.{ext}'
    path=UPLOADS/name; file.save(path)
    if path.stat().st_size > MAX_UPLOAD:
        path.unlink(missing_ok=True); abort(413)
    return name

def auth(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('uid'): return redirect(url_for('login'))
        return fn(*args,**kwargs)
    return wrapped

def admin_only(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('uid'): return redirect(url_for('login'))
        if session.get('role')!='ADMINISTRADOR': abort(403)
        return fn(*args,**kwargs)
    return wrapped

@app.before_request
def setup_request():
    c=conn(); c.executescript(SCHEMA); t=now()
    admin_user=os.getenv('ADMIN_USER','Marcelo Correia')
    admin_pass=os.getenv('ADMIN_INITIAL_PASSWORD') or os.getenv('ADMIN_PASSWORD')
    u=c.execute('SELECT id FROM users WHERE username=?',(admin_user,)).fetchone()
    if not u and admin_pass:
        c.execute('INSERT INTO users(name,username,password_hash,role,active,created_at) VALUES(?,?,?,?,?,?)',(admin_user,admin_user,generate_password_hash(admin_pass),'ADMINISTRADOR',1,t))
    c.execute('INSERT OR IGNORE INTO weekly_periods(week_start,week_end) VALUES(?,?)',(monday().isoformat(),(monday()+timedelta(days=6)).isoformat()))
    for name,cargo,p in MEMBERS:
        c.execute('INSERT OR IGNORE INTO members(name,passport,cargo,created_at) VALUES(?,?,?,?)',(name,p,cargo,t))
    for name,data in ACTIONS.items():
        limit,bandits,police,weapon,negotiation,hostages,notes=data
        rules={'bandits':bandits,'police':police,'weapon':weapon,'negotiation':negotiation,'hostages':hostages,'notes':notes}
        c.execute('INSERT OR IGNORE INTO actions(name,weekly_limit,action_value,rules_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',(name,limit,0,json.dumps(rules,ensure_ascii=False),t,t))
    c.commit();c.close()
    if request.method=='POST' and request.endpoint!='login':
        sent=request.form.get('csrf','')
        if not session.get('uid') or not secrets.compare_digest(sent,session.get('csrf','')): abort(400)

CSS='''
:root{--bg:#050505;--panel:#0d0d0d;--panel2:#12100b;--line:#3a2d12;--text:#f8f4e8;--muted:#a69d8a;--gold:#d4af37;--gold2:#f0d477}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% -10%,rgba(212,175,55,.16),transparent 30%),#050505;color:var(--text);font:14px Inter,system-ui,Segoe UI,sans-serif}a{text-decoration:none;color:inherit}.layout{min-height:100vh}.side{position:fixed;left:0;top:0;bottom:0;width:248px;background:#080808;border-right:1px solid #4b3b18;padding:22px 14px;overflow:auto}.brand b{color:var(--gold);font-size:27px;letter-spacing:.16em}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:.12em;margin-top:4px;margin-bottom:22px}.nav a{display:block;padding:11px 12px;color:#bdb5a5;border-radius:10px;margin:3px 0}.nav a:hover{background:#17130a;color:var(--gold2)}.main{margin-left:248px;padding:30px 34px;max-width:1500px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.top h1{margin:0;color:var(--gold2)}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px}.cards3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}.card{background:linear-gradient(180deg,#12100c,#0b0b09);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 18px 45px rgba(0,0,0,.28)}.metric{font-size:27px;font-weight:800;color:var(--gold2);margin-top:8px}.label{font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:.12em}.muted{color:var(--muted)}.section{margin-top:18px}.pill{display:inline-block;padding:5px 9px;border:1px solid #554516;background:#211b0c;color:var(--gold2);border-radius:999px;font-size:11px}.btn{display:inline-flex;align-items:center;justify-content:center;border:1px solid #d4af37;border-radius:10px;padding:10px 14px;background:linear-gradient(#e4c34f,#bd941f);color:#080705;font-weight:800;cursor:pointer}.btn.secondary{background:#12110d;color:var(--gold2);border-color:#4f4018}.btn.danger{background:#25100f;color:#ffaeaa;border-color:#71312e}.formgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.field{display:flex;flex-direction:column;gap:7px}.full{grid-column:1/-1}.input,.select,.textarea{width:100%;background:#070706;color:var(--text);border:1px solid #493916;border-radius:10px;padding:11px;outline:none}.input:focus,.select:focus,.textarea:focus{border-color:var(--gold)}.textarea{min-height:100px;resize:vertical}.tablewrap{overflow:auto}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:11px;border-bottom:1px solid #2a220f;text-align:left;white-space:nowrap}.table th{font-size:10px;color:var(--gold);text-transform:uppercase;letter-spacing:.08em}.flash{padding:12px;border:1px solid #5c4a1d;background:#18140a;border-radius:10px;margin-bottom:12px}.flash.error{border-color:#71312e;background:#24100f}.rules{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.rule{background:#090908;border:1px solid #302610;border-radius:12px;padding:12px}.rule strong{display:block;color:var(--gold);font-size:10px;text-transform:uppercase;margin-bottom:5px}.membercard{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;background:#090908;border:1px solid #332811;border-radius:12px;padding:12px;margin-top:10px}.loginpage{min-height:100vh;display:grid;place-items:center;padding:20px}.loginbox{width:min(440px,94vw)}.searchbox{display:grid;grid-template-columns:1fr auto;gap:10px}.split{display:grid;grid-template-columns:1fr auto;gap:10px}.status-ok{color:#6fda9b}.status-no{color:#ff9f99}
@media(max-width:1000px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cards3{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:720px){.side{position:static;width:auto;border-right:0;border-bottom:1px solid #3a2d12}.main{margin-left:0;padding:18px 14px 30px}.grid,.cards3,.formgrid,.rules{grid-template-columns:1fr}.searchbox,.split{grid-template-columns:1fr}}
'''

IC={'Painel':'◈','Farm':'⬢','Produção':'◉','Baú':'▣','Ações':'◇','Ranking':'↗','Hierarquia':'♟','Histórico':'◫','Usuários':'⚙','Admin':'◆','Externos':'◌','Logs':'≡'}

def shell(title,body):
    items=[('Painel','dashboard'),('Farm','farms'),('Produção','productions'),('Baú','chests'),('Ações','actions'),('Ranking','ranking'),('Hierarquia','members'),('Histórico','history')]
    if session.get('role')=='ADMINISTRADOR': items += [('Usuários','users'),('Admin','admin_actions'),('Externos','externals'),('Logs','logs')]
    nav=''.join(f'<a href="{url_for(route)}">{IC[name]} &nbsp;{name}</a>' for name,route in items)
    messages=''.join(f'<div class="flash {"error" if kind=="error" else ""}">{msg}</div>' for kind,msg in session.pop('_flashes',[]))
    return render_template_string(f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · CENTRAL LASTRO</title><style>{CSS}</style></head><body><div class="layout"><aside class="side"><div class="brand"><b>LASTRO</b><small>CENTRAL ADMINISTRATIVA</small></div><nav class="nav">{nav}</nav><a class="btn secondary" style="width:100%;margin-top:22px" href="{url_for('logout')}">Sair</a></aside><main class="main"><div class="top"><h1>{title}</h1><span class="pill">{session.get('role','')}</span></div>{messages}{body}</main></div></body></html>''')

@app.get('/health')
def health():
    c=conn(); c.execute('SELECT 1'); c.close(); return {'status':'ok','service':'central-lastro'}

@app.route('/',methods=['GET','POST'])
def login():
    if session.get('uid'): return redirect(url_for('dashboard'))
    error=''
    if request.method=='POST':
        row=getall('SELECT * FROM users WHERE lower(username)=lower(?) AND active=1',(request.form.get('username','').strip(),))
        if row and check_password_hash(row[0]['password_hash'],request.form.get('password','')):
            session.clear(); session.update(uid=row[0]['id'],name=row[0]['name'],role=row[0]['role']); csrf(); return redirect(url_for('dashboard'))
        error='Usuário ou senha inválidos.'
    return render_template_string(f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Login · LASTRO</title><style>{CSS}</style></head><body><div class="loginpage"><form class="card loginbox" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="brand"><b>LASTRO</b><small>CENTRAL PRIVADA DE GESTÃO</small></div><div class="field"><label>Usuário</label><input class="input" name="username" autocomplete="username" required></div><div class="field" style="margin-top:12px"><label>Senha</label><input class="input" type="password" name="password" autocomplete="current-password" required></div>{f'<div class="flash error" style="margin-top:12px">{error}</div>' if error else ''}<button class="btn" style="width:100%;margin-top:16px">Entrar</button></form></div></body></html>''')

@app.get('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.get('/dashboard')
@auth
def dashboard():
    ws=monday().isoformat(); total=getall('SELECT COALESCE(SUM(action_value),0)v FROM action_records')[0]['v']; week_total=getall('SELECT COALESCE(SUM(family_value),0)v FROM action_records WHERE week_start=?',(ws,))[0]['v']; actions_count=getall('SELECT COUNT(*)n FROM action_records WHERE week_start=?',(ws,))[0]['n']; members_count=getall('SELECT COUNT(DISTINCT member_id)n FROM action_participants ap JOIN action_records ar ON ar.id=ap.record_id WHERE ar.week_start=? AND ap.member_id IS NOT NULL',(ws,))[0]['n']
    cards=''.join(f'<div class="card"><div class="label">{label}</div><div class="metric">{value}</div></div>' for label,value in [('Total movimentado',money(total)),('Lucro semanal',money(week_total)),('Ações realizadas',actions_count),('Membros participantes',members_count)])
    action_cards=[]
    for a in getall('SELECT * FROM actions WHERE active=1 ORDER BY id'):
        n=getall('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(a['id'],ws))[0]['n']; lim=a['weekly_limit']; lock=lim is not None and n>=lim
        action_cards.append(f'<div class="card"><span class="pill">{n}/{lim if lim is not None else "∞"}</span><h2>{a["name"]}</h2><p class="muted">Valor: {money(a["action_value"]) if a["action_value"] else "Ainda não definido"}</p><a class="btn {"secondary" if lock else ""}" href="{url_for("action_detail",action_id=a["id"])}">{"Limite atingido" if lock else "Abrir ação"}</a></div>')
    return shell('Painel',f'<div class="grid">{cards}</div><div class="section"><h2>Ações da semana</h2><div class="cards3">{"".join(action_cards)}</div></div>')

@app.route('/farms',methods=['GET','POST'])
@auth
def farms():
    if request.method=='POST':
        execute('INSERT INTO farms(member_id,quantity,proof,created_by,created_at) VALUES(?,?,?,?,?)',(int(request.form['member_id']),float(request.form['quantity']),save_proof(request.files.get('proof')),session['uid'],now())); audit('FARM_REGISTRADO',request.form['member_id']); flash('Farm registrado.'); return redirect(url_for('farms'))
    opts=''.join(f'<option value="{m["id"]}">{m["name"]} — {m["passport"] or "sem passaporte"} — {m["cargo"]}</option>' for m in getall('SELECT * FROM members WHERE active=1 ORDER BY name'))
    rows=getall('SELECT f.*,m.name member_name,m.passport,u.name creator FROM farms f JOIN members m ON m.id=f.member_id JOIN users u ON u.id=f.created_by ORDER BY f.id DESC LIMIT 200')
    tr=''.join(f'<tr><td>{x["member_name"]}</td><td>{x["quantity"]:g}</td><td>{x["creator"]}</td><td>{x["created_at"][:16].replace("T"," ")}</td><td>{f"<a href=\"{url_for(\"proof_file\",name=x[\"proof\"])}\">Abrir prova</a>" if x["proof"] else "—"}</td></tr>' for x in rows)
    return shell('Farm',f'<div class="card"><form class="formgrid" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field full"><label>Membro quem entregou</label><input class="input" list="member-list" name="member_name" placeholder="Pesquisar membro por nome ou passaporte" required><datalist id="member-list">{opts}</datalist><select class="select" name="member_id" required style="margin-top:8px"><option value="">Selecione o membro</option>{opts}</select></div><div class="field"><label>Quantidade</label><input class="input" type="number" step=".01" min="0" name="quantity" required></div><div class="field"><label>Prova/foto</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><button class="btn full">Salvar farm</button></form></div><div class="card section tablewrap"><table class="table"><tr><th>Membro</th><th>Quantidade</th><th>Lançado por</th><th>Data</th><th>Prova</th></tr>{tr}</table></div>')

@app.route('/productions',methods=['GET','POST'])
@auth
def productions():
    if request.method=='POST': execute('INSERT INTO productions(member_id,quantity,material,reason,proof,created_by,created_at) VALUES(?,?,?,?,?,?,?)',(int(request.form['member_id']),float(request.form['quantity']),request.form['material'].strip(),request.form['reason'],save_proof(request.files.get('proof')),session['uid'],now())); audit('PRODUCAO_REGISTRADA'); flash('Produção registrada.'); return redirect(url_for('productions'))
    opts=''.join(f'<option value="{m["id"]}">{m["name"]} — {m["passport"] or "sem passaporte"}</option>' for m in getall('SELECT * FROM members WHERE active=1 ORDER BY name'))
    return shell('Produção',f'<div class="card"><form class="formgrid" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field full"><label>Responsável</label><select class="select" name="member_id" required>{opts}</select></div><div class="field"><label>Quantidade produzida</label><input class="input" type="number" step=".01" name="quantity" required></div><div class="field"><label>Material/produto utilizado</label><input class="input" name="material" required></div><div class="field"><label>Motivo</label><select class="select" name="reason"><option>uso</option><option>venda</option><option>estoque</option><option>outro</option></select></div><div class="field"><label>Prova/foto</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><button class="btn full">Salvar produção</button></form></div>')

@app.route('/chests',methods=['GET','POST'])
@auth
def chests():
    if request.method=='POST': execute('INSERT INTO chests(member_id,item,reason,proof,created_by,created_at) VALUES(?,?,?,?,?,?)',(int(request.form['member_id']),request.form['item'].strip(),request.form['reason'].strip(),save_proof(request.files.get('proof')),session['uid'],now())); audit('BAU_REGISTRADO'); flash('Retirada do baú registrada.'); return redirect(url_for('chests'))
    opts=''.join(f'<option value="{m["id"]}">{m["name"]} — {m["passport"] or "sem passaporte"}</option>' for m in getall('SELECT * FROM members WHERE active=1 ORDER BY name'))
    return shell('Baú',f'<div class="card"><form class="formgrid" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field full"><label>Quem pegou</label><select class="select" name="member_id" required>{opts}</select></div><div class="field"><label>O que pegou</label><input class="input" name="item" required></div><div class="field"><label>Motivo da retirada</label><input class="input" name="reason" required></div><div class="field full"><label>Prova/foto</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><button class="btn full">Registrar retirada</button></form></div>')

@app.get('/actions')
@auth
def actions():
    ws=monday().isoformat(); cards=[]
    for a in getall('SELECT * FROM actions WHERE active=1 ORDER BY id'):
        used=getall('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(a['id'],ws))[0]['n']; lim=a['weekly_limit']; data=json.loads(a['rules_json']); badge=f'{used}/{lim}' if lim is not None else f'{used}/∞'; disabled=lim is not None and used>=lim
        cards.append(f'<div class="card"><span class="pill">{badge}</span><h2>{a["name"]}</h2><p class="muted">Valor: {money(a["action_value"]) if a["action_value"] else "A definir"}</p><p class="muted">Bandidos: {data.get("bandits","—")} · Policiais: {data.get("police","—")}</p><a class="btn {"secondary" if disabled else ""}" href="{url_for("action_detail",action_id=a["id"])}">{"Limite semanal atingido" if disabled else "Registrar participação"}</a></div>')
    return shell('Ações',f'<div class="cards3">{"".join(cards)}</div>')

@app.route('/actions/<int:action_id>',methods=['GET','POST'])
@auth
def action_detail(action_id):
    row=getall('SELECT * FROM actions WHERE id=? AND active=1',(action_id,))
    if not row: abort(404)
    a=row[0]; rules=json.loads(a['rules_json']); ws=monday().isoformat(); used=getall('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(action_id,ws))[0]['n']; lim=a['weekly_limit']
    if request.method=='POST':
        if lim is not None and used>=lim: flash('Limite semanal atingido.','error'); return redirect(url_for('actions'))
        member_ids=[]
        for value in request.form.getlist('member_ids'):
            if value and value not in member_ids: member_ids.append(value)
        ext_names=request.form.getlist('external_name'); ext_pass=request.form.getlist('external_passport'); ext_fams=request.form.getlist('external_family')
        participants=[]
        for mid in member_ids:
            weapon=request.form.get(f'weapon_{mid}','INDEFINIDO'); side=request.form.get(f'side_{mid}','BANDIDO')
            if weapon=='INDEFINIDO': flash('Defina o armamento de todos os participantes.','error'); return redirect(request.url)
            participants.append(('member',int(mid),None,side,weapon))
        for i,name in enumerate(ext_names):
            if not name.strip(): continue
            weapon=request.form.get(f'external_weapon_{i}','INDEFINIDO'); side=request.form.get(f'external_side_{i}','BANDIDO')
            if weapon=='INDEFINIDO': flash('Defina o armamento de todos os participantes externos.','error'); return redirect(request.url)
            participants.append(('external',None,(name.strip(), ext_pass[i].strip() if i<len(ext_pass) else '', ext_fams[i].strip() if i<len(ext_fams) else ''),side,weapon))
        if not participants: flash('Adicione pelo menos um participante.','error'); return redirect(request.url)
        b=sum(1 for x in participants if x[3]=='BANDIDO'); p=sum(1 for x in participants if x[3]=='POLICIAL')
        def check_count(rule,val):
            text=str(rule or '').lower()
            m=re.search(r'(\d+)\s*a\s*(\d+)',text)
            if m and not int(m.group(1))<=val<=int(m.group(2)): return False
            if 'igual ao número' in text and val!=b: return False
            if re.fullmatch(r'\d+',text) and val!=int(text): return False
            return True
        if not check_count(rules.get('bandits'),b) or not check_count(rules.get('police'),p): flash(f'Quantidade inválida. Bandidos: {b}. Policiais: {p}.','error'); return redirect(request.url)
        c=conn()
        try:
            c.execute('BEGIN IMMEDIATE')
            fresh=c.execute('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(action_id,ws)).fetchone()['n']
            if lim is not None and fresh>=lim: raise ValueError('Limite semanal atingido')
            value=float(a['action_value'] or 0); family=round(value*.5,2); pool=round(value-family,2); eligible=[x for x in participants if x[4]=='TROUXE']; cents=int(round(pool*100)); each=(cents//len(eligible)) if eligible else 0; remainder=(cents-each*len(eligible)) if eligible else 0
            rid=c.execute('INSERT INTO action_records(action_id,week_start,action_value,family_value,participant_pool,rules_snapshot,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(action_id,ws,value,family,pool,json.dumps(rules,ensure_ascii=False),session['uid'],now())).lastrowid
            c.execute('INSERT INTO financial_transactions(record_id,type,amount,description,created_at) VALUES(?,?,?,?,?)',(rid,'FAMILIA',family,'50% da família',now()))
            c.execute('INSERT INTO financial_transactions(record_id,type,amount,description,created_at) VALUES(?,?,?,?,?)',(rid,'PARTICIPANTES',pool,'50% distribuídos entre elegíveis',now()))
            idx=0
            for typ,mid,ext,side,weapon in participants:
                eid=None
                if typ=='external': eid=c.execute('INSERT INTO external_participants(name,passport,family) VALUES(?,?,?)',ext).lastrowid
                ok=weapon=='TROUXE'; amount=(each + (1 if idx<remainder else 0))/100 if ok else 0
                if ok: idx+=1
                c.execute('INSERT INTO action_participants(record_id,member_id,external_id,side,weapon,eligible,value_received,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(rid,mid,eid,side,weapon,int(ok),amount,'' if ok else 'Não trouxe armamento',now()))
            c.commit()
        except Exception as e:
            c.rollback(); c.close(); flash(str(e),'error'); return redirect(request.url)
        c.close(); audit('ACAO_FINALIZADA',f'{a["name"]} #{rid}'); flash('Ação registrada com sucesso.'); return redirect(url_for('result',record_id=rid))
    members=getall('SELECT * FROM members WHERE active=1 ORDER BY cargo,name')
    options=''.join(f'<option value="{m["id"]}">{m["name"]} — {m["passport"] or "sem passaporte"}</option>' for m in members)
    rules_html=''.join(f'<div class="rule"><strong>{k}</strong>{v}</div>' for k,v in [('Bandidos',rules.get('bandits')),('Policiais',rules.get('police')),('Armamento',rules.get('weapon')),('Negociação',rules.get('negotiation')),('Reféns',rules.get('hostages')),('Observações',rules.get('notes'))])
    script=f'''<script>let extIndex=0;function addMember(){{let box=document.getElementById('memberRows');let id='newm'+Date.now();box.insertAdjacentHTML('beforeend',`<div class="membercard"><div><select class="select" name="member_ids" onchange="syncMember(this)"><option value="">Selecione um membro</option>{options}</select><div class="formgrid" style="margin-top:10px"><div class="field"><label>Equipe</label><select class="select" data-side><option>BANDIDO</option><option>POLICIAL</option></select></div><div class="field"><label>Armamento</label><select class="select" data-weapon><option value="INDEFINIDO">Não informado</option><option value="TROUXE">Trouxe armamento</option><option value="NAO_TROUXE">Não trouxe</option></select></div></div></div><button class="btn danger" type="button" onclick="this.parentElement.remove()">Remover</button></div>`)}}function syncMember(s){{let r=s.closest('.membercard');let side=r.querySelector('[data-side]');let weapon=r.querySelector('[data-weapon]');side.name='side_'+s.value;weapon.name='weapon_'+s.value}}function addExternal(){{let i=extIndex++;document.getElementById('externalRows').insertAdjacentHTML('beforeend',`<div class="membercard"><div class="formgrid" style="flex:1"><div class="field"><label>Nome</label><input class="input" name="external_name" required></div><div class="field"><label>Passaporte</label><input class="input" name="external_passport"></div><div class="field"><label>Família</label><input class="input" name="external_family" required></div><div class="field"><label>Equipe</label><select class="select" name="external_side_${{i}}"><option>BANDIDO</option><option>POLICIAL</option></select></div><div class="field"><label>Armamento</label><select class="select" name="external_weapon_${{i}}"><option value="INDEFINIDO">Não informado</option><option value="TROUXE">Trouxe armamento</option><option value="NAO_TROUXE">Não trouxe</option></select></div></div><button class="btn danger" type="button" onclick="this.parentElement.remove()">Remover</button></div>`)}}</script>'''
    return shell(a['name'],f'<div class="card"><span class="pill">Frequência: {used}/{lim if lim is not None else "∞"}</span><p class="muted">Valor da ação: {money(a["action_value"]) if a["action_value"] else "Ainda não definido"}</p><div class="rules">{rules_html}</div></div><form class="section" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="card"><div style="display:flex;justify-content:space-between;gap:10px;align-items:center"><h2>Participantes da família</h2><button class="btn secondary" type="button" onclick="addMember()">+ Selecionar membro</button></div><div id="memberRows"></div></div><div class="card section"><div style="display:flex;justify-content:space-between;gap:10px;align-items:center"><h2 style="font-size:18px">Adicionar participante externo</h2><button class="btn secondary" type="button" onclick="addExternal()">+ Participante externo</button></div><p class="muted">Participantes externos não pertencem à Família Lastro.</p><div id="externalRows"></div></div><button class="btn section" style="width:100%">Finalizar ação</button></form>{script}')

@app.get('/actions/result/<int:record_id>')
@auth
def result(record_id):
    rr=getall('SELECT ar.*,a.name FROM action_records ar JOIN actions a ON a.id=ar.action_id WHERE ar.id=?',(record_id,))
    if not rr: abort(404)
    r=rr[0]; people=getall('SELECT ap.*,m.name member_name,m.passport,ep.name external_name,ep.passport external_pass FROM action_participants ap LEFT JOIN members m ON m.id=ap.member_id LEFT JOIN external_participants ep ON ep.id=ap.external_id WHERE ap.record_id=?',(record_id,))
    ok=''.join(f'<tr><td>{p["member_name"] or p["external_name"]}</td><td>{p["passport"] or p["external_pass"] or "—"}</td><td>{p["side"]}</td><td class="status-ok">{money(p["value_received"])}</td></tr>' for p in people if p['eligible'])
    no=''.join(f'<tr><td>{p["member_name"] or p["external_name"]}</td><td>{p["side"]}</td><td class="status-no">R$ 0,00</td><td>{p["reason"]}</td></tr>' for p in people if not p['eligible'])
    return shell('Resultado · '+r['name'],f'<div class="grid"><div class="card"><div class="label">Valor da ação</div><div class="metric">{money(r["action_value"])}</div></div><div class="card"><div class="label">Parte da família · 50%</div><div class="metric">{money(r["family_value"])}</div></div><div class="card"><div class="label">Participantes · 50%</div><div class="metric">{money(r["participant_pool"])}</div></div><div class="card"><div class="label">Data</div><div class="metric">{r["created_at"][:10]}</div></div></div><div class="card section tablewrap"><h2>Participantes elegíveis</h2><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Equipe</th><th>Recebeu</th></tr>{ok}</table></div><div class="card section tablewrap"><h2>Não elegíveis</h2><table class="table"><tr><th>Nome</th><th>Equipe</th><th>Recebeu</th><th>Motivo</th></tr>{no}</table></div>')

@app.get('/ranking')
@auth
def ranking():
    farm=getall('SELECT m.id,m.name,m.passport,m.cargo,COALESCE(SUM(f.quantity),0) farm FROM members m LEFT JOIN farms f ON f.member_id=m.id WHERE m.active=1 GROUP BY m.id ORDER BY farm DESC,name')
    action=getall('SELECT m.id,m.name,m.passport,m.cargo,COUNT(ap.id) qty FROM members m LEFT JOIN action_participants ap ON ap.member_id=m.id WHERE m.active=1 GROUP BY m.id ORDER BY qty DESC,name')
    farmtr=''.join(f'<tr><td>{i}</td><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["farm"]:g}</td></tr>' for i,x in enumerate(farm,1))
    acttr=''.join(f'<tr><td>{i}</td><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["qty"]}</td></tr>' for i,x in enumerate(action,1))
    return shell('Ranking',f'<div class="cards3"><div class="card tablewrap"><h2>Ranking de Farm</h2><table class="table"><tr><th>#</th><th>Nome</th><th>Passaporte</th><th>Total</th></tr>{farmtr}</table></div><div class="card tablewrap"><h2>Ranking de Ações</h2><table class="table"><tr><th>#</th><th>Nome</th><th>Passaporte</th><th>Participações</th></tr>{acttr}</table></div></div>')

@app.get('/members')
@auth
def members():
    term=request.args.get('q','').strip(); rows=getall('SELECT * FROM members WHERE active=1 AND (name LIKE ? OR CAST(passport AS TEXT) LIKE ?) ORDER BY CASE cargo WHEN "LÍDER" THEN 1 WHEN "VICE-LÍDER" THEN 2 WHEN "GERENTE" THEN 3 ELSE 4 END,name',(f'%{term}%',f'%{term}%'))
    tr=''.join(f'<tr><td>{m["name"]}</td><td>{m["passport"] or "—"}</td><td>{m["cargo"]}</td><td>{getall("SELECT COUNT(*)n FROM action_participants WHERE member_id=?",(m["id"],))[0]["n"]}</td><td>{getall("SELECT COALESCE(SUM(quantity),0)v FROM farms WHERE member_id=?",(m["id"],))[0]["v"]:g}</td><td>{f"<a href=\"{url_for(\"member_edit\",member_id=m[\"id\"])}\">Editar</a>" if session.get("role")=="ADMINISTRADOR" else "—"}</td></tr>' for m in rows)
    return shell('Hierarquia',f'<div class="card"><form class="searchbox"><input class="input" name="q" value="{term}" placeholder="Pesquisar por nome ou passaporte"><button class="btn">Pesquisar</button></form></div><div class="card section tablewrap"><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Cargo</th><th>Ações</th><th>Farm</th><th></th></tr>{tr}</table></div>')

@app.route('/admin/members/<int:member_id>',methods=['GET','POST'])
@admin_only
def member_edit(member_id):
    row=getall('SELECT * FROM members WHERE id=?',(member_id,));
    if not row: abort(404)
    m=row[0]
    if request.method=='POST':
        execute('UPDATE members SET name=?,passport=?,cargo=?,notes=?,farm_notes=?,action_notes=?,general_notes=?,active=? WHERE id=?',(request.form['name'].strip(),request.form.get('passport') or None,request.form['cargo'],request.form.get('notes',''),request.form.get('farm_notes',''),request.form.get('action_notes',''),request.form.get('general_notes',''),1 if request.form.get('active') else 0,member_id)); audit('MEMBRO_ATUALIZADO',str(member_id)); flash('Membro atualizado.'); return redirect(url_for('members'))
    return shell('Editar membro',f'<div class="card"><form class="formgrid" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" value="{m["name"]}"></div><div class="field"><label>Passaporte</label><input class="input" name="passport" value="{m["passport"] or ""}"></div><div class="field"><label>Cargo</label><select class="select" name="cargo">{''.join(f"<option {'selected' if r==m['cargo'] else ''}>{r}</option>" for r in ['LÍDER','VICE-LÍDER','GERENTE','MEMBRO'])}</select></div><div class="field"><label>Status</label><label><input type="checkbox" name="active" {"checked" if m["active"] else ""}> Ativo</label></div><div class="field full"><label>Notas</label><textarea class="textarea" name="notes">{m["notes"] or ""}</textarea></div><div class="field full"><label>O que rendeu para o farm</label><textarea class="textarea" name="farm_notes">{m["farm_notes"] or ""}</textarea></div><div class="field full"><label>O que rendeu para ações</label><textarea class="textarea" name="action_notes">{m["action_notes"] or ""}</textarea></div><div class="field full"><label>Observações gerais</label><textarea class="textarea" name="general_notes">{m["general_notes"] or ""}</textarea></div><button class="btn full">Salvar membro</button></form></div>')

@app.get('/users')
@admin_only
def users():
    rows=getall('SELECT * FROM users ORDER BY CASE role WHEN "ADMINISTRADOR" THEN 1 WHEN "LÍDER" THEN 2 WHEN "VICE-LÍDER" THEN 3 WHEN "GERENTE" THEN 4 ELSE 5 END,name')
    tr=''.join(f'<tr><td>{u["name"]}</td><td>{u["username"]}</td><td>{u["role"]}</td><td>{"Ativo" if u["active"] else "Inativo"}</td><td><a href="{url_for("user_edit",user_id=u["id"])}">Editar</a></td></tr>' for u in rows)
    return shell('Usuários',f'<div class="card"><a class="btn" href="{url_for("user_new")}">+ Criar usuário</a></div><div class="card section tablewrap"><table class="table"><tr><th>Nome</th><th>Usuário</th><th>Perfil</th><th>Status</th><th></th></tr>{tr}</table></div>')

@app.route('/admin/users/new',methods=['GET','POST'])
@admin_only
def user_new():
    if request.method=='POST':
        try:
            if len(request.form['password'])<8: raise ValueError('A senha precisa ter pelo menos 8 caracteres.')
            execute('INSERT INTO users(name,username,password_hash,role,active,created_at) VALUES(?,?,?,?,?,?)',(request.form['name'].strip(),request.form['username'].strip(),generate_password_hash(request.form['password']),request.form['role'],1,now())); audit('USUARIO_CRIADO',request.form['username']); flash('Usuário criado.'); return redirect(url_for('users'))
        except Exception as e: flash(str(e),'error')
    role_opts=''.join(f'<option>{r}</option>' for r in ROLES)
    return shell('Novo usuário',f'<div class="card"><form class="formgrid" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" required></div><div class="field"><label>Usuário</label><input class="input" name="username" required></div><div class="field"><label>Senha</label><input class="input" type="password" name="password" minlength="8" required></div><div class="field"><label>Cargo/perfil</label><select class="select" name="role">{role_opts}</select></div><button class="btn full">Criar usuário</button></form></div>')

@app.route('/admin/users/<int:user_id>',methods=['GET','POST'])
@admin_only
def user_edit(user_id):
    row=getall('SELECT * FROM users WHERE id=?',(user_id,));
    if not row: abort(404)
    u=row[0]
    if request.method=='POST':
        if request.form.get('password') and len(request.form['password'])<8: flash('A senha precisa ter pelo menos 8 caracteres.','error'); return redirect(request.url)
        if request.form.get('password'): execute('UPDATE users SET name=?,username=?,role=?,active=?,password_hash=? WHERE id=?',(request.form['name'].strip(),request.form['username'].strip(),request.form['role'],1 if request.form.get('active') else 0,generate_password_hash(request.form['password']),user_id))
        else: execute('UPDATE users SET name=?,username=?,role=?,active=? WHERE id=?',(request.form['name'].strip(),request.form['username'].strip(),request.form['role'],1 if request.form.get('active') else 0,user_id))
        audit('USUARIO_ATUALIZADO',str(user_id)); flash('Usuário atualizado.'); return redirect(url_for('users'))
    role_opts=''.join(f'<option {"selected" if r==u["role"] else ""}>{r}</option>' for r in ROLES)
    return shell('Editar usuário',f'<div class="card"><form class="formgrid" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" value="{u["name"]}"></div><div class="field"><label>Usuário</label><input class="input" name="username" value="{u["username"]}"></div><div class="field"><label>Nova senha</label><input class="input" type="password" name="password"></div><div class="field"><label>Cargo/perfil</label><select class="select" name="role">{role_opts}</select></div><div class="field"><label>Status</label><label><input type="checkbox" name="active" {"checked" if u["active"] else ""}> Ativo</label></div><button class="btn full">Salvar</button></form></div>')

@app.get('/admin/actions')
@admin_only
def admin_actions():
    cards=[]
    for a in getall('SELECT * FROM actions ORDER BY id'):
        r=json.loads(a['rules_json'])
        cards.append(f'''<div class="card"><h2>{a['name']}</h2><form class="formgrid" method="post" action="{url_for('admin_action',action_id=a['id'])}"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Valor da ação</label><input class="input" name="value" type="number" step=".01" min="0" value="{a['action_value']}"></div><div class="field"><label>Limite semanal</label><input class="input" name="weekly_limit" type="number" min="1" value="{a['weekly_limit'] or ''}"></div><div class="field"><label>Bandidos</label><input class="input" name="bandits" value="{r.get('bandits','')}"></div><div class="field"><label>Policiais</label><input class="input" name="police" value="{r.get('police','')}"></div><div class="field full"><label>Armamento permitido</label><input class="input" name="weapon" value="{r.get('weapon','')}"></div><div class="field"><label>Negociação</label><input class="input" name="negotiation" value="{r.get('negotiation','')}"></div><div class="field"><label>Reféns</label><input class="input" name="hostages" value="{r.get('hostages','')}"></div><div class="field full"><label>Observações da ação</label><textarea class="textarea" name="notes">{r.get('notes','')}</textarea></div><button class="btn full">Salvar configuração</button></form></div>''')
    return shell('Configuração das ações','<div class="cards3">'+''.join(cards)+'</div>')

@app.post('/admin/actions/<int:action_id>')
@admin_only
def admin_action(action_id):
    row=getall('SELECT * FROM actions WHERE id=?',(action_id,));
    if not row: abort(404)
    r={'bandits':request.form.get('bandits',''),'police':request.form.get('police',''),'weapon':request.form.get('weapon',''),'negotiation':request.form.get('negotiation',''),'hostages':request.form.get('hostages',''),'notes':request.form.get('notes','')}
    try:
        value=float(request.form.get('value') or 0); limit=int(request.form['weekly_limit']) if request.form.get('weekly_limit') else None
        execute('UPDATE actions SET action_value=?,weekly_limit=?,rules_json=?,updated_at=? WHERE id=?',(value,limit,json.dumps(r,ensure_ascii=False),now(),action_id)); audit('ACAO_CONFIGURADA',str(action_id)); flash('Configuração da ação atualizada.')
    except Exception as e: flash('Configuração inválida: '+str(e),'error')
    return redirect(url_for('admin_actions'))

@app.get('/externals')
@admin_only
def externals():
    rows=getall('SELECT ep.*,COUNT(ap.id) qty,COALESCE(SUM(ap.value_received),0) value FROM external_participants ep LEFT JOIN action_participants ap ON ap.external_id=ep.id GROUP BY ep.id ORDER BY ep.name')
    tr=''.join(f'<tr><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["family"]}</td><td>{x["qty"]}</td><td>{money(x["value"])}</td></tr>' for x in rows)
    return shell('Participantes externos',f'<div class="card tablewrap"><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Família</th><th>Participações</th><th>Recebido</th></tr>{tr}</table></div>')

@app.get('/history')
@auth
def history():
    rows=getall('SELECT week_start,COUNT(*) qty,COALESCE(SUM(action_value),0) total,COALESCE(SUM(family_value),0) family FROM action_records GROUP BY week_start ORDER BY week_start DESC')
    cards=''.join(f'<div class="card"><span class="pill">{x["week_start"]}</span><div class="metric">{money(x["total"])}</div><p>{x["qty"]} ações · Família: {money(x["family"])}</p><a class="btn secondary" href="{url_for("history_week",week=x["week_start"])}">Abrir semana</a></div>' for x in rows)
    return shell('Histórico semanal',f'<div class="cards3">{cards or "<div class=card>Nenhuma semana registrada.</div>"}</div>')

@app.get('/history/<week>')
@auth
def history_week(week):
    rows=getall('SELECT ar.*,a.name FROM action_records ar JOIN actions a ON a.id=ar.action_id WHERE ar.week_start=? ORDER BY ar.created_at',(week,))
    tr=''.join(f'<tr><td>{x["name"]}</td><td>{money(x["action_value"])}</td><td>{money(x["family_value"])}</td><td>{x["created_at"][:16].replace("T"," ")}</td><td><a href="{url_for("result",record_id=x["id"])}">Abrir</a></td></tr>' for x in rows)
    return shell('Semana '+week,f'<div class="card tablewrap"><table class="table"><tr><th>Ação</th><th>Valor</th><th>Família</th><th>Data</th><th></th></tr>{tr}</table></div>')

@app.get('/admin/audit')
@admin_only
def logs():
    rows=getall('SELECT l.*,u.name user_name FROM audit_logs l LEFT JOIN users u ON u.id=l.user_id ORDER BY l.id DESC LIMIT 500')
    tr=''.join(f'<tr><td>{x["created_at"][:16]}</td><td>{x["user_name"] or "Sistema"}</td><td>{x["action"]}</td><td>{x["details"] or ""}</td></tr>' for x in rows)
    return shell('Logs',f'<div class="card tablewrap"><table class="table"><tr><th>Data</th><th>Usuário</th><th>Ação</th><th>Detalhes</th></tr>{tr}</table></div>')

@app.get('/proof/<path:name>')
@auth
def proof_file(name):
    safe=secure_filename(name)
    if safe!=name: abort(404)
    path=UPLOADS/safe
    if not path.exists(): abort(404)
    return send_file(path)

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT','8080')))
