import os,json,secrets,sqlite3,uuid,re
from pathlib import Path
from datetime import date,timedelta,datetime
from functools import wraps
from flask import Flask,request,session,redirect,url_for,abort,flash,send_file,render_template_string
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.utils import secure_filename
DATA=Path(os.getenv('DATA_DIR','/data'));DATA.mkdir(parents=True,exist_ok=True);UP=DATA/'uploads';UP.mkdir(exist_ok=True);DB=DATA/'lastro.db';MAX=8*1024*1024;ALLOWED={'jpg','jpeg','png','webp'}
app=Flask(__name__);app.secret_key=os.getenv('SECRET_KEY') or secrets.token_hex(32);app.config.update(MAX_CONTENT_LENGTH=MAX,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','1')=='1')
MEMBERS=[('Vocaro','LÍDER',None),('Nicole Lastro','LÍDER',4202),('Zeca Lastro','VICE-LÍDER',17147),('Andrey Magnata','GERENTE',28459),('Breno Gomes','GERENTE',32110),('Alice','MEMBRO',72884),('Bak Tarik','MEMBRO',28996),('Cassimiro','MEMBRO',34553),('dancollins','MEMBRO',None),('Dante','MEMBRO',41728),('Gabriel Garcia','MEMBRO',33858),('Marcelo Correia','MEMBRO',6027),('Marco Peixoto','MEMBRO',18976),('Negralha Oliveira','MEMBRO',28804),('Olindo Martins','MEMBRO',23525),('Oliver Bueno','MEMBRO',19975),('Paulo Miriam','MEMBRO',33250),('Pedro Pinto','MEMBRO',30692),('Sidney Santos','MEMBRO',25419),('Vitin Caiçara','MEMBRO',33952),('Willian Silveira','MEMBRO',23317),('Zoen Costa','MEMBRO',31195),('Barba Lenda','MEMBRO',24731),('Barrabas Belen','MEMBRO',24089),('Bene Oliveira','MEMBRO',26158),('Cartola Do Morro','MEMBRO',35159),('Cleiton Rasta','MEMBRO',34549),('Eduardo Madruga','MEMBRO',40203),('Eneias Silva','MEMBRO',14066),('Erik Mitrovic','MEMBRO',28539),('Fernando Fortes','MEMBRO',12288),('Gustavo Hammes','MEMBRO',42747),('Gustavo Henrique','MEMBRO',41395),('Josivaldo Rocha','MEMBRO',34623),('Kevin Smity','MEMBRO',42560),('Mameluco Camargo','MEMBRO',42506),('Miguel Andrade','MEMBRO',31551),('Mirna Santos','MEMBRO',34200),('Muniz Santos','MEMBRO',37700),('Pedro Rocha','MEMBRO',34595),('Pedro Rossa','MEMBRO',31909),('PH','MEMBRO',42684),('Pulcenio Ferraz','MEMBRO',39908),('Ronan Pires','MEMBRO',None),('Tony Gentil','MEMBRO',36332),('Velasco Montana','MEMBRO',39323),('Victor Santos','MEMBRO',42677)]
R={'Joalheria':(1,'5 a 7','9 a 11, proporcional aos bandidos','Submetralhadora, Fuzil, Escopeta. AP Pistol não é submetralhadora.','Obrigatória','Opcional, máximo 3','Máximo 3 veículos; máximo 3 fora e 4 dentro.'),'Concessionária':(1,'8 a 10, todos dentro','12 obrigatório','Submetralhadora, Fuzil, Escopeta. AP Pistol não é submetralhadora.','Obrigatória','Opcional, máximo 4','Máximo 6 veículos: 3 próprios e 3 da concessionária. Polícia: máximo 5 granadas de gás.'),'Fleeca':(2,'6 a 8','10 obrigatório','A depender de cada local','Obrigatória','Obrigatório, máximo 3','Máximo 3 veículos.'),'Açougue':(1,'8 a 10, todos dentro','12 obrigatório','Submetralhadora, Fuzil, Escopeta. AP Pistol não é submetralhadora.','Obrigatória','Opcional, máximo 3','Máximo 3 veículos. Polícia: máximo 3 granadas de gás. Rotação externa P1/P2 permitida.'),'Galinheiro':(1,'8 a 10, dentro e fora permitidos','12 obrigatório','Submetralhadora, Fuzil','Obrigatória','Opcional, máximo 2','Máximo 3 granadas de gás. Proibido mata/morros atrás dos trilhos, fora do perímetro.'),'Central do Mergulhador':(1,'7 obrigatório','10 obrigatório','Pistola ou submetralhadora. AP Pistol permitida.','Inexistente','Proibido','Polícia usa o mesmo armamento dos bandidos; com submetralhadora, todo o contingente pode usar.'),'Banco Central':(1,'10 obrigatório; máximo 3 em prédios OU 5 no chão','13 obrigatório','Fuzil','Obrigatória','Opcional, máximo 4','Máximo 3 veículos. Refém: neutralizar atiradores OU impedir reposicionamento de helicóptero, nunca ambos. Em fuga, ninguém fora.'),'Banco Paleto':(None,'10 máximo','13 obrigatório','Fuzil','Não há','Proibido','Confronto direto. Bandidos aguardam; começa quando polícia entra no perímetro.'),'Loja de Tatuagens':(None,'2 máximo','2 obrigatório','Apenas armas brancas; pode negociar combate em punhos.','Obrigatória','Proibido',''),'Barbearia':(None,'4 a 10 máximo','Igual ao número de bandidos, obrigatório','Apenas armas brancas; pode negociar combate em punhos.','Obrigatória','Proibido',''),'Loja de Armas — Praça':(None,'2 obrigatório; nenhum fora','3 obrigatório','Apenas pistolas; AP Pistol proibida','Obrigatória','Proibido',''),'Loja de Armas — Porto':(None,'3 a 5 máximo','5 a 7 máximo, proporcional aos bandidos','Apenas pistolas; AP Pistol proibida','Obrigatória','Proibido',''),'Loja de Conveniência':(None,'5 a 6 máximo','7 a 8 máximo, proporcional aos bandidos','Pistola obrigatória; AP Pistol proibida','Inexistente','Proibido','Troca de tiros, sem fuga. Até 2 bandidos fora dentro do perímetro. Inicia no primeiro bandido fechado.')}
SCHEMA='''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,passport INTEGER,cargo TEXT NOT NULL,notes TEXT DEFAULT '',farm_notes TEXT DEFAULT '',action_notes TEXT DEFAULT '',general_notes TEXT DEFAULT '',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,weekly_limit INTEGER,action_value REAL DEFAULT 0,rules_json TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS farms(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,quantity REAL,proof TEXT,created_by INTEGER,created_at TEXT);CREATE TABLE IF NOT EXISTS productions(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,quantity REAL,material TEXT,reason TEXT,proof TEXT,created_by INTEGER,created_at TEXT);CREATE TABLE IF NOT EXISTS chests(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,item TEXT,reason TEXT,proof TEXT,created_by INTEGER,created_at TEXT);CREATE TABLE IF NOT EXISTS action_records(id INTEGER PRIMARY KEY AUTOINCREMENT,action_id INTEGER,week_start TEXT,action_value REAL,family_value REAL,participant_pool REAL,rules_snapshot TEXT,created_by INTEGER,created_at TEXT,status TEXT DEFAULT 'FINALIZADA');CREATE TABLE IF NOT EXISTS external_participants(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,passport TEXT,family TEXT);CREATE TABLE IF NOT EXISTS action_participants(id INTEGER PRIMARY KEY AUTOINCREMENT,record_id INTEGER,member_id INTEGER,external_id INTEGER,side TEXT,weapon TEXT,eligible INTEGER,value_received REAL,reason TEXT,created_at TEXT);CREATE TABLE IF NOT EXISTS financial_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,record_id INTEGER,type TEXT,amount REAL,description TEXT,created_at TEXT);CREATE TABLE IF NOT EXISTS weekly_periods(id INTEGER PRIMARY KEY AUTOINCREMENT,week_start TEXT UNIQUE,week_end TEXT,closed INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,action TEXT,details TEXT,created_at TEXT);'''
def db():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=30000');return c
def now():return datetime.now().astimezone().isoformat(timespec='seconds')
def ws():d=date.today();return d-timedelta(days=d.weekday())
def money(v):return f'R$ {float(v or 0):,.2f}'.replace(',','X').replace('.',',').replace('X','.')
def dt(v):
 try:return datetime.fromisoformat(v).strftime('%d/%m/%Y %H:%M')
 except:return v
def q(sql,a=()):
 c=db();x=c.execute(sql,a).fetchall();c.close();return x
def ex(sql,a=()):
 c=db();r=c.execute(sql,a);c.commit();i=r.lastrowid;c.close();return i
def audit(a,d=''):ex('INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)',(session.get('user_id'),a,d))
def csrf():
 if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(24)
 return session['csrf']
def upload(f):
 if not f or not f.filename:return None
 e=secure_filename(f.filename).rsplit('.',1)[-1].lower() if '.' in f.filename else ''
 if e not in ALLOWED:abort(400,'Arquivo inválido. Use JPG, PNG ou WEBP.')
 n=uuid.uuid4().hex+'.'+e;p=UP/n;f.save(p)
 if p.stat().st_size>MAX:p.unlink(missing_ok=True);abort(413)
 return n
def login_req(f):
 @wraps(f)
 def w(*a,**k):return f(*a,**k) if session.get('user_id') else redirect(url_for('login'))
 return w
def admin(f):
 @wraps(f)
 def w(*a,**k):
  if not session.get('user_id'):return redirect(url_for('login'))
  if session.get('role')!='ADMINISTRADOR':abort(403)
  return f(*a,**k)
 return w
def init():
 c=db();c.executescript(SCHEMA);t=now();u=os.getenv('ADMIN_INITIAL_USER','Marcelo Correia');p=os.getenv('ADMIN_INITIAL_PASSWORD')
 if p and not c.execute('SELECT 1 FROM users WHERE username=?',(u,)).fetchone():c.execute('INSERT INTO users(name,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',(u,u,generate_password_hash(p),'ADMINISTRADOR',t))
 for n,cargo,pa in MEMBERS:
  if not c.execute('SELECT 1 FROM members WHERE name=?',(n,)).fetchone():c.execute('INSERT INTO members(name,passport,cargo,created_at) VALUES(?,?,?,?)',(n,pa,cargo,t))
  else:c.execute('UPDATE members SET passport=?,cargo=?,active=1 WHERE name=?',(pa,cargo,n))
 for n,v in R.items():
  if not c.execute('SELECT 1 FROM actions WHERE name=?',(n,)).fetchone():c.execute('INSERT INTO actions(name,weekly_limit,action_value,rules_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',(n,v[0],0,json.dumps({'Bandidos':v[1],'Policiais':v[2],'Armamento':v[3],'Negociação':v[4],'Reféns':v[5],'Regras adicionais':v[6]},ensure_ascii=False),t,t))
 c.execute('INSERT OR IGNORE INTO weekly_periods(week_start,week_end) VALUES(?,?)',(ws().isoformat(),(ws()+timedelta(days=6)).isoformat()));c.commit();c.close()
@app.before_request
def before():
 init()
 if request.method=='POST' and (not session.get('user_id') or not secrets.compare_digest(request.form.get('csrf',''),session.get('csrf',''))):abort(400)
CSS='''*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% -10%,#2b220b,transparent 30%),#050505;color:#f7f3e8;font:14px Inter,system-ui,sans-serif}a{text-decoration:none;color:inherit}.app{display:flex;min-height:100vh}.side{position:fixed;width:245px;inset:0 auto 0 0;background:#070707;border-right:1px solid #3d3116;padding:22px 14px}.brand{padding:8px 12px 24px}.brand b{font-size:24px;letter-spacing:.14em;color:#d4af37}.brand span{display:block;color:#a79b82;font-size:10px;margin-top:5px;letter-spacing:.1em}.nav a{display:flex;gap:10px;padding:11px 12px;border:1px solid transparent;border-radius:10px;color:#bcb39f;margin:4px 0}.nav a:hover{background:#15120a;border-color:#4a3a16;color:#f0d477}.main{margin-left:245px;width:calc(100% - 245px);padding:28px 34px 50px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.top h1{margin:0;color:#f0d477}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:linear-gradient(#12110e,#0a0a09);border:1px solid #3b2e13;border-radius:16px;padding:18px;box-shadow:0 15px 40px #0008}.metric{font-size:27px;font-weight:800;color:#f0d477;margin-top:7px}.label{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#a79b82}.section{margin-top:18px}.table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:11px;border-bottom:1px solid #27200f;text-align:left;white-space:nowrap}.table th{font-size:10px;text-transform:uppercase;color:#d4af37}.btn{display:inline-block;border:1px solid #d4af37;border-radius:10px;padding:10px 14px;background:linear-gradient(#e3c04e,#c39b25);color:#070707;font-weight:800;cursor:pointer}.btn.secondary{background:#11100d;color:#f0d477}.btn.danger{background:#261010;color:#ff9b9b;border-color:#713030}.form{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.field{display:flex;flex-direction:column;gap:6px}.full{grid-column:1/-1}.input,.select,.textarea{width:100%;background:#080808;color:#fff;border:1px solid #4b3b18;border-radius:10px;padding:11px;outline:0}.textarea{min-height:100px}.input:focus,.select:focus,.textarea:focus{border-color:#d4af37}.flash{padding:11px;border:1px solid #5b4a1e;background:#17140b;border-radius:10px;margin-bottom:12px}.flash.error{border-color:#713030;background:#251010}.muted{color:#a79b82}.pill{display:inline-block;padding:5px 8px;border-radius:99px;background:#211b0c;border:1px solid #4c3d18;color:#f0d477;font-size:11px}.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.rules{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}.rule{padding:11px;background:#090908;border:1px solid #302610;border-radius:10px}.rule b{display:block;color:#d4af37;text-transform:uppercase;font-size:10px;margin-bottom:4px}.member-card{display:flex;gap:10px;align-items:center;background:#090908;border:1px solid #332912;border-radius:11px;padding:12px;margin-top:9px}.login{min-height:100vh;display:grid;place-items:center;padding:20px}.loginbox{width:min(430px,100%)}.external{border-left:3px solid #d4af37;padding-left:12px}.ok{color:#68d391}.no{color:#ff9b9b}.mobile{display:none}@media(max-width:950px){.grid{grid-template-columns:repeat(2,1fr)}.actions{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.side{display:none}.main{margin:0;width:100%;padding:18px 14px 82px}.grid,.form,.rules,.actions{grid-template-columns:1fr}.mobile{display:flex;position:fixed;bottom:0;left:0;right:0;background:#080807;border-top:1px solid #3b2e13;z-index:9;overflow:auto}.mobile a{min-width:70px;text-align:center;padding:8px;font-size:10px;color:#bcb39f}}'''
I={'Painel':'◈','Farm':'⬢','Produção':'◉','Baú':'▣','Ações':'◇','Ranking':'↗','Hierarquia':'♟','Histórico':'◫','Usuários':'⚙','Admin':'◆','Externos':'◌','Logs':'≡'}
def layout(title,body):
 items=[('Painel','dashboard'),('Farm','farms'),('Produção','productions'),('Baú','chests'),('Ações','actions'),('Ranking','ranking'),('Hierarquia','members'),('Histórico','history')]
 if session.get('role')=='ADMINISTRADOR':items += [('Usuários','users'),('Admin','admin_actions'),('Externos','admin_externals'),('Logs','audit_page')]
 nav=''.join(f'<a href="{url_for(r)}"><b>{I[n]}</b>{n}</a>' for n,r in items);fl=''.join(f'<div class="flash {"error" if c=="error" else ""}">{m}</div>' for c,m in session.pop('_flashes',[]))
 return render_template_string(f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · CENTRAL LASTRO</title><style>{CSS}</style></head><body><div class="app"><aside class="side"><div class="brand"><b>LASTRO</b><span>CENTRAL ADMINISTRATIVA</span></div><nav class="nav">{nav}</nav><div style="position:absolute;bottom:20px;left:26px;right:26px"><div class="muted" style="font-size:11px;margin-bottom:9px">{session.get("name","")} · {session.get("role","")}</div><a class="btn secondary" style="display:block;text-align:center" href="{url_for("logout")}">Sair</a></div></aside><main class="main"><div class="top"><h1>{title}</h1><span class="muted">{session.get("role","")}</span></div>{fl}{body}</main><nav class="mobile">{nav}</nav></div></body></html>')
def member_select():
 o=''.join(f'<option value="{m["id"]}">{m["name"]} — {m["passport"] or "sem passaporte"} — {m["cargo"]}</option>' for m in q('SELECT id,name,passport,cargo FROM members WHERE active=1 ORDER BY name'));return f'<input class="input" placeholder="Pesquisar membro..." oninput="f(this)"><select class="select" name="member_id" required>{o}</select><script>function f(i){{let s=i.value.toLowerCase(),x=i.nextElementSibling;[...x.options].forEach(o=>o.hidden=!o.text.toLowerCase().includes(s))}}</script>'
@app.get('/health')
def health():db().close();return {'status':'ok','service':'central-lastro'}
@app.route('/',methods=['GET','POST'])
def login():
 if session.get('user_id'):return redirect(url_for('dashboard'))
 if request.method=='POST':
  r=q('SELECT * FROM users WHERE lower(username)=lower(?) AND active=1',(request.form.get('username','').strip(),));
  if r and check_password_hash(r[0]['password_hash'],request.form.get('password','')):session.clear();session.update(user_id=r[0]['id'],name=r[0]['name'],role=r[0]['role']);csrf();return redirect(url_for('dashboard'))
  flash('Usuário ou senha inválidos.','error')
 return render_template_string(f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body><div class="login"><form class="card loginbox" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="brand"><b>LASTRO</b><span>CENTRAL ADMINISTRATIVA PRIVADA</span></div><div class="field"><label>Usuário</label><input class="input" name="username" required></div><div class="field" style="margin-top:12px"><label>Senha</label><input class="input" type="password" name="password" required></div><button class="btn" style="width:100%;margin-top:18px">Entrar</button></form></div></body></html>')
@app.get('/logout')
def logout():session.clear();return redirect(url_for('login'))
@app.get('/dashboard')
@login_req
def dashboard():
 w=ws().isoformat();m=q('SELECT COALESCE(SUM(action_value),0)v FROM action_records')[0]['v'];lw=q('SELECT COALESCE(SUM(action_value),0)v FROM action_records WHERE week_start=?',(w,))[0]['v'];ac=q('SELECT COUNT(*)n FROM action_records WHERE week_start=?',(w,))[0]['n'];mm=q('SELECT COUNT(DISTINCT member_id)n FROM action_participants ap JOIN action_records ar ON ar.id=ap.record_id WHERE ar.week_start=? AND ap.member_id IS NOT NULL',(w,))[0]['n'];cards=''.join(f'<div class="card"><div class="label">{a}</div><div class="metric">{b}</div></div>' for a,b in [('Total movimentado',money(m)),('Lucro semanal',money(lw)),('Ações realizadas na semana',ac),('Membros participantes',mm)]);aa=[]
 for x in q('SELECT * FROM actions WHERE active=1 ORDER BY id'):
  n=q('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(x['id'],w))[0]['n'];l=x['weekly_limit'];locked=l is not None and n>=l;aa.append(f'<div class="card"><span class="pill">{n}/{l if l is not None else "∞"}</span><h2>{x["name"]}</h2><div class="muted">{money(x["action_value"]) if x["action_value"] else "Valor ainda não definido"}</div><a class="btn {"secondary" if locked else ""}" href="{url_for("action_detail",action_id=x["id"])}" style="display:block;text-align:center;margin-top:15px;opacity:{.55 if locked else 1}">{"Limite atingido" if locked else "Registrar ação"}</a></div>')
 return layout('Painel',f'<div class="grid">{cards}</div><div class="section"><h2>Ações da semana</h2><div class="actions">{"".join(aa)}</div></div>')
@app.route('/farms',methods=['GET','POST'])
@login_req
def farms():
 if request.method=='POST':ex('INSERT INTO farms(member_id,quantity,proof,created_by,created_at) VALUES(?,?,?,?,?)',(request.form['member_id'],float(request.form['quantity']),upload(request.files.get('proof')),session['user_id'],now()));flash('Farm registrado.');return redirect(url_for('farms'))
 d=q('SELECT f.*,m.name,m.passport,u.name creator FROM farms f JOIN members m ON m.id=f.member_id JOIN users u ON u.id=f.created_by ORDER BY f.id DESC LIMIT 100');trs=''.join(f'<tr><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["quantity"]:g}</td><td>{dt(x["created_at"])}</td><td>{x["creator"]}</td><td>{"<a class=proof href="+url_for("proof",name=x["proof"])+">Abrir</a>" if x["proof"] else "—"}</td></tr>' for x in d);return layout('Farm',f'<div class="card"><h2>Membro quem entregou</h2><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field">{member_select()}</div><div class="field"><label>Quantidade</label><input class="input" type="number" step=".01" min=0 name="quantity" required></div><div class="field full"><label>Prova/foto</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><button class="btn full">Salvar</button></form></div><div class="card section"><div class="table-wrap"><table class="table"><tr><th>Membro</th><th>Passaporte</th><th>Qtd.</th><th>Data</th><th>Registrado por</th><th>Prova</th></tr>{trs}</table></div></div>')
@app.route('/productions',methods=['GET','POST'])
@login_req
def productions():
 if request.method=='POST':ex('INSERT INTO productions(member_id,quantity,material,reason,proof,created_by,created_at) VALUES(?,?,?,?,?,?,?)',(request.form['member_id'],float(request.form['quantity']),request.form['material'],request.form['reason'],upload(request.files.get('proof')),session['user_id'],now()));flash('Produção registrada.');return redirect(url_for('productions'))
 d=q('SELECT p.*,m.name,u.name creator FROM productions p JOIN members m ON m.id=p.member_id JOIN users u ON u.id=p.created_by ORDER BY p.id DESC LIMIT 100');trs=''.join(f'<tr><td>{x["name"]}</td><td>{x["quantity"]:g}</td><td>{x["material"]}</td><td>{x["reason"]}</td><td>{dt(x["created_at"])}</td><td>{x["creator"]}</td></tr>' for x in d);return layout('Produção',f'<div class="card"><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field">{member_select()}</div><div class="field"><label>Quantidade</label><input class="input" type="number" step=".01" min=0 name="quantity" required></div><div class="field"><label>Material</label><input class="input" name="material" required></div><div class="field"><label>Motivo</label><select class="select" name="reason"><option>uso</option><option>venda</option><option>estoque</option><option>outro</option></select></div><div class="field full"><label>Prova</label><input class="input" type="file" name="proof"></div><button class="btn full">Salvar</button></form></div><div class="card section"><div class="table-wrap"><table class="table"><tr><th>Responsável</th><th>Qtd.</th><th>Material</th><th>Motivo</th><th>Data</th><th>Registrado por</th></tr>{trs}</table></div></div>')
@app.route('/chests',methods=['GET','POST'])
@login_req
def chests():
 if request.method=='POST':ex('INSERT INTO chests(member_id,item,reason,proof,created_by,created_at) VALUES(?,?,?,?,?,?)',(request.form['member_id'],request.form['item'],request.form['reason'],upload(request.files.get('proof')),session['user_id'],now()));flash('Baú registrado.');return redirect(url_for('chests'))
 d=q('SELECT c.*,m.name,u.name creator FROM chests c JOIN members m ON m.id=c.member_id JOIN users u ON u.id=c.created_by ORDER BY c.id DESC LIMIT 100');trs=''.join(f'<tr><td>{x["name"]}</td><td>{x["item"]}</td><td>{x["reason"]}</td><td>{dt(x["created_at"])}</td><td>{x["creator"]}</td></tr>' for x in d);return layout('Baú',f'<div class="card"><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field">{member_select()}</div><div class="field"><label>Item</label><input class="input" name="item" required></div><div class="field"><label>Motivo</label><input class="input" name="reason" required></div><div class="field"><label>Prova</label><input class="input" type="file" name="proof"></div><button class="btn full">Registrar</button></form></div><div class="card section"><div class="table-wrap"><table class="table"><tr><th>Membro</th><th>Item</th><th>Motivo</th><th>Data</th><th>Registrado por</th></tr>{trs}</table></div></div>')
@app.get('/actions')
@login_req
def actions():return redirect(url_for('dashboard'))
@app.route('/actions/<int:action_id>',methods=['GET','POST'])
@login_req
def action_detail(action_id):
 a=q('SELECT * FROM actions WHERE id=? AND active=1',(action_id,));
 if not a:abort(404)
 a=a[0];rules=json.loads(a['rules_json']);w=ws().isoformat();cnt=q('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(action_id,w))[0]['n'];lim=a['weekly_limit']
 if request.method=='POST':
  if lim is not None and cnt>=lim:flash('Limite semanal atingido.','error');return redirect(url_for('dashboard'))
  mids=[int(x) for x in request.form.getlist('member_ids')];en=request.form.getlist('ext_name');ep=request.form.getlist('ext_passport');ef=request.form.getlist('ext_family');parts=[]
  if len(mids)!=len(set(mids)):flash('Participante duplicado.','error');return redirect(request.url)
  for m in mids:parts.append(('m',m,None,request.form.get('side_'+str(m),'BANDIDO'),request.form.get('weapon_'+str(m),'INDEFINIDO')))
  for i,n in enumerate(en):
   if n.strip():parts.append(('e',None,(n.strip(),ep[i].strip() if i<len(ep) else '',ef[i].strip() if i<len(ef) else ''),request.form.get('ext_side_'+str(i),'BANDIDO'),request.form.get('ext_weapon_'+str(i),'INDEFINIDO')))
  if not parts or any(x[4]=='INDEFINIDO' for x in parts):flash('Adicione participantes e defina o armamento de todos.','error');return redirect(request.url)
  b=sum(x[3]=='BANDIDO' for x in parts);p=sum(x[3]=='POLICIAL' for x in parts)
  def rg(s):
   z=re.match(r'^(\d+)\s*a\s*(\d+)',str(s));return (int(z.group(1)),int(z.group(2))) if z else None
  for k,n in [('Bandidos',b),('Policiais',p)]:
   z=rg(rules.get(k,''));
   if z and not z[0]<=n<=z[1]:flash(f'{k}: permitido {z[0]} a {z[1]}; informado {n}.','error');return redirect(request.url)
  if 'Igual ao número' in rules.get('Policiais','') and p!=b:flash('Policiais devem ser iguais aos bandidos.','error');return redirect(request.url)
  for k,n in [('Bandidos',b),('Policiais',p)]:
   if 'obrigatório' in rules.get(k,'').lower():
    z=re.match(r'^(\d+)',rules[k]);
    if z and n!=int(z.group(1)):flash(f'{k}: quantidade obrigatória inválida.','error');return redirect(request.url)
  val=float(a['action_value'] or 0);fam=round(val*.5,2);pool=round(val-fam,2);elig=[x for x in parts if x[4]=='TROUXE'];base=int(round(pool*100))//len(elig) if elig else 0;rem=int(round(pool*100))-base*len(elig) if elig else 0;c=db()
  try:
   c.execute('BEGIN IMMEDIATE');fresh=c.execute('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(action_id,w)).fetchone()['n'];
   if lim is not None and fresh>=lim:raise ValueError('Limite semanal atingido.')
   rid=c.execute('INSERT INTO action_records(action_id,week_start,action_value,family_value,participant_pool,rules_snapshot,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(action_id,w,val,fam,pool,json.dumps(rules,ensure_ascii=False),session['user_id'],now())).lastrowid;c.execute('INSERT INTO financial_transactions(record_id,type,amount,description,created_at) VALUES(?,?,?,?,?)',(rid,'FAMILIA',fam,'50% da ação',now()));c.execute('INSERT INTO financial_transactions(record_id,type,amount,description,created_at) VALUES(?,?,?,?,?)',(rid,'PARTICIPANTES',pool,'50% da ação',now()))
   ei=0
   for x in parts:
    typ,mid,ext,side,weapon=x;eid=None
    if typ=='e':eid=c.execute('INSERT INTO external_participants(name,passport,family) VALUES(?,?,?)',ext).lastrowid
    ok=weapon=='TROUXE';amount=(base+(1 if ok and ei<rem else 0))/100 if ok else 0
    if ok:ei+=1
    c.execute('INSERT INTO action_participants(record_id,member_id,external_id,side,weapon,eligible,value_received,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(rid,mid,eid,side,weapon,int(ok),amount,'' if ok else 'não trouxe armamento',now()))
   c.commit()
  except Exception as e:c.rollback();c.close();flash(str(e),'error');return redirect(request.url)
  c.close();audit('ACAO_FINALIZADA',f'action={a["name"]};record={rid}');flash('Ação finalizada e cálculo salvo.');return redirect(url_for('result',record_id=rid))
 opts=''.join(f'<option value="{m["id"]}">{m["name"]} — {m["passport"] or "sem passaporte"} — {m["cargo"]}</option>' for m in q('SELECT id,name,passport,cargo FROM members WHERE active=1 ORDER BY name'));rh=''.join(f'<div class="rule"><b>{k}</b>{v}</div>' for k,v in rules.items());return layout(a['name'],f'''<div class="card"><div class="pill">Frequência: {cnt}/{lim if lim is not None else '∞'}</div><h2>Regras</h2><div class="rules">{rh}</div><p class="muted">Valor: {money(a['action_value']) if a['action_value'] else 'Ainda não definido'}</p></div><form class="section" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="card"><div style="display:flex;justify-content:space-between"><h2>Participantes da família</h2><button class="btn secondary" type="button" onclick="addM()">+ Selecionar membro</button></div><div id="ms"></div></div><div class="card section external"><h3>Adicionar participante externo</h3><div class="muted">Pessoa fora da família Lastro.</div><div id="es"></div><button class="btn secondary" type="button" onclick="addE()">+ Adicionar participante externo</button></div><div class="card section"><button class="btn" type="submit">Finalizar ação</button><div class="muted">Todos precisam ter armamento definido.</div></div></form><template id="mt"><div class="member-card"><div style="flex:1"><select class="select" name="member_ids" onchange="sync(this)">{opts}</select><div class="form" style="margin-top:8px"><select class="select" data-s><option>BANDIDO</option><option>POLICIAL</option></select><select class="select" data-w><option value="INDEFINIDO">Não informado</option><option value="TROUXE">Trouxe armamento</option><option value="NAO_TROUXE">Não trouxe</option></select></div></div><button class="btn danger" type="button" onclick="this.closest('.member-card').remove()">Remover</button></div></template><script>function sync(x){{let c=x.closest('.member-card');c.querySelector('[data-s]').name='side_'+x.value;c.querySelector('[data-w]').name='weapon_'+x.value}}function addM(){{let c=document.getElementById('mt').content.cloneNode(true);document.getElementById('ms').appendChild(c);sync(document.querySelector('#ms .member-card:last-child select[name=member_ids]'))}}let ei=0;function addE(){{let i=ei++,d=document.createElement('div');d.className='member-card external';d.innerHTML=`<div style="flex:1"><div class="form"><input class="input" name="ext_name" placeholder="Nome" required><input class="input" name="ext_passport" placeholder="Passaporte"><input class="input" name="ext_family" placeholder="Família" required><select class="select" name="ext_side_${{i}}"><option>BANDIDO</option><option>POLICIAL</option></select><select class="select" name="ext_weapon_${{i}}"><option value="INDEFINIDO">Não informado</option><option value="TROUXE">Trouxe armamento</option><option value="NAO_TROUXE">Não trouxe</option></select></div></div><button class="btn danger" type="button" onclick="this.closest('.member-card').remove()">Remover</button>`;document.getElementById('es').appendChild(d)}}</script>''')
@app.get('/actions/result/<int:record_id>')
@login_req
def result(record_id):
 r=q('SELECT ar.*,a.name,u.name creator FROM action_records ar JOIN actions a ON a.id=ar.action_id JOIN users u ON u.id=ar.created_by WHERE ar.id=?',(record_id,));
 if not r:abort(404)
 r=r[0];p=q('SELECT ap.*,m.name mn,m.passport,ep.name en,ep.passport epass FROM action_participants ap LEFT JOIN members m ON m.id=ap.member_id LEFT JOIN external_participants ep ON ep.id=ap.external_id WHERE ap.record_id=?',(record_id,));yes=''.join(f'<tr><td>{x["mn"] or x["en"]}</td><td>{x["passport"] or x["epass"] or "—"}</td><td>{x["side"]}</td><td class="ok">{money(x["value_received"])}</td></tr>' for x in p if x['eligible']);no=''.join(f'<tr><td>{x["mn"] or x["en"]}</td><td>{x["side"]}</td><td class="no">R$ 0,00</td><td>{x["reason"]}</td></tr>' for x in p if not x['eligible']);return layout('Resultado · '+r['name'],f'<div class="grid"><div class="card"><div class="label">Valor</div><div class="metric">{money(r["action_value"])}</div></div><div class="card"><div class="label">Família · 50%</div><div class="metric">{money(r["family_value"])}</div></div><div class="card"><div class="label">Participantes · 50%</div><div class="metric">{money(r["participant_pool"])}</div></div></div><div class="card section"><h2>Elegíveis</h2><div class="table-wrap"><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Lado</th><th>Recebeu</th></tr>{yes}</table></div></div><div class="card section"><h2>Não elegíveis</h2><div class="table-wrap"><table class="table"><tr><th>Nome</th><th>Lado</th><th>Recebeu</th><th>Motivo</th></tr>{no}</table></div></div><div class="card section"><h2>Snapshot das regras</h2><div class="rules">{''.join(f'<div class="rule"><b>{k}</b>{v}</div>' for k,v in json.loads(r['rules_snapshot']).items())}</div></div>')
@app.get('/ranking')
@login_req
def ranking():
 d=q('''SELECT m.name,m.passport,m.cargo,COUNT(DISTINCT ap.record_id) actions,COALESCE(SUM(ap.value_received),0) received,(SELECT COALESCE(SUM(f.quantity),0) FROM farms f WHERE f.member_id=m.id) farm FROM members m LEFT JOIN action_participants ap ON ap.member_id=m.id LEFT JOIN action_records ar ON ar.id=ap.record_id AND ar.week_start=? WHERE m.active=1 GROUP BY m.id ORDER BY received DESC,actions DESC,m.name''',(ws().isoformat(),));trs=''.join(f'<tr><td>{i}</td><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["cargo"]}</td><td>{x["actions"]}</td><td>{money(x["received"])}</td><td>{x["farm"]:g}</td></tr>' for i,x in enumerate(d,1));return layout('Ranking',f'<div class="card"><div class="table-wrap"><table class="table"><tr><th>#</th><th>Nome</th><th>Passaporte</th><th>Cargo</th><th>Ações</th><th>Valor recebido</th><th>Farm</th></tr>{trs}</table></div></div>')
@app.get('/members')
@login_req
def members():
 s=request.args.get('q','');d=q('SELECT * FROM members WHERE active=1 AND (name LIKE ? OR CAST(passport AS TEXT) LIKE ?) ORDER BY CASE cargo WHEN "LÍDER" THEN 1 WHEN "VICE-LÍDER" THEN 2 WHEN "GERENTE" THEN 3 ELSE 4 END,name',(f'%{s}%',f'%{s}%'));trs=''.join(f'<tr><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["cargo"]}</td><td>{"<a class=proof href="+url_for("member_edit",member_id=x["id"])+">Editar</a>" if session.get("role")=="ADMINISTRADOR" else "—"}</td></tr>' for x in d);return layout('Hierarquia',f'<div class="card"><form class="split"><input class="input" name="q" value="{s}" placeholder="Nome ou passaporte"><button class="btn">Pesquisar</button></form></div><div class="card section"><div class="table-wrap"><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Cargo</th><th></th></tr>{trs}</table></div></div>')
@app.get('/users')
@admin
def users():
 d=q('SELECT * FROM users ORDER BY role,name');trs=''.join(f'<tr><td>{x["name"]}</td><td>{x["username"]}</td><td>{x["role"]}</td><td>{"Ativo" if x["active"] else "Inativo"}</td><td><a class=proof href="{url_for("user_edit",user_id=x["id"])}">Editar</a></td></tr>' for x in d);return layout('Usuários',f'<div class="card"><a class="btn" href="{url_for("user_new")}">+ Nova conta</a></div><div class="card section"><div class="muted">Senhas nunca são exibidas.</div><div class="table-wrap"><table class="table"><tr><th>Nome</th><th>Usuário</th><th>Perfil</th><th>Status</th><th></th></tr>{trs}</table></div></div>')
@app.route('/admin/users/new',methods=['GET','POST'])
@admin
def user_new():
 if request.method=='POST':
  if len(request.form['password'])<8:flash('Senha mínima: 8 caracteres.','error');return redirect(request.url)
  try:ex('INSERT INTO users(name,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',(request.form['name'],request.form['username'],generate_password_hash(request.form['password']),request.form['role'],now()));flash('Conta criada.');return redirect(url_for('users'))
  except sqlite3.IntegrityError:flash('Usuário já existe.','error')
 return layout('Nova conta',f'<div class="card"><form class="form" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" required></div><div class="field"><label>Usuário</label><input class="input" name="username" required></div><div class="field"><label>Senha</label><input class="input" type="password" name="password" minlength=8 required></div><div class="field"><label>Perfil</label><select class="select" name="role"><option>OPERACIONAL</option><option>ADMINISTRADOR</option></select></div><button class="btn full">Criar</button></form></div>')
@app.route('/admin/users/<int:user_id>',methods=['GET','POST'])
@admin
def user_edit(user_id):
 u=q('SELECT * FROM users WHERE id=?',(user_id,));
 if not u:abort(404)
 u=u[0]
 if request.method=='POST':
  if request.form.get('password') and len(request.form['password'])<8:flash('Senha mínima: 8 caracteres.','error');return redirect(request.url)
  if request.form.get('password'):ex('UPDATE users SET name=?,username=?,role=?,active=?,password_hash=? WHERE id=?',(request.form['name'],request.form['username'],request.form['role'],1 if request.form.get('active') else 0,generate_password_hash(request.form['password']),user_id))
  else:ex('UPDATE users SET name=?,username=?,role=?,active=? WHERE id=?',(request.form['name'],request.form['username'],request.form['role'],1 if request.form.get('active') else 0,user_id))
  flash('Conta atualizada.');return redirect(url_for('users'))
 return layout('Editar conta',f'<div class="card"><form class="form" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" value="{u["name"]}" required></div><div class="field"><label>Usuário</label><input class="input" name="username" value="{u["username"]}" required></div><div class="field"><label>Nova senha</label><input class="input" type="password" name="password"></div><div class="field"><label>Perfil</label><select class="select" name="role"><option {'selected' if u["role"]=="OPERACIONAL" else ""}>OPERACIONAL</option><option {'selected' if u["role"]=="ADMINISTRADOR" else ""}>ADMINISTRADOR</option></select></div><div class="field"><label>Ativo</label><input type="checkbox" name="active" {"checked" if u["active"] else ""}></div><button class="btn full">Salvar</button></form></div>')
@app.get('/admin/actions')
@admin
def admin_actions():
 d=q('SELECT * FROM actions ORDER BY id');cards=[]
 for x in d:cards.append(f'<div class="card"><h2>{x["name"]}</h2><form method="post" action="{url_for("admin_action_edit",action_id=x["id"])}"><input type="hidden" name="csrf" value="{csrf()}"><div class="form"><div class="field"><label>Valor</label><input class="input" type="number" step=".01" name="value" value="{x["action_value"]}"></div><div class="field"><label>Limite semanal</label><input class="input" type="number" min=1 name="limit" value="{x["weekly_limit"] or ""}"></div><div class="field full"><label>Regras JSON</label><textarea class="textarea" name="rules">{x["rules_json"]}</textarea></div><button class="btn full">Salvar</button></div></form></div>')
 return layout('Administração · Ações',''.join(cards))
@app.post('/admin/actions/<int:action_id>')
@admin
def admin_action_edit(action_id):
 try:v=float(request.form.get('value','0') or 0);l=request.form.get('limit','').strip();l=int(l) if l else None;r=json.loads(request.form['rules']);ex('UPDATE actions SET action_value=?,weekly_limit=?,rules_json=?,updated_at=? WHERE id=?',(v,l,json.dumps(r,ensure_ascii=False),now(),action_id));flash('Configuração salva.')
 except Exception as e:flash('Configuração inválida: '+str(e),'error')
 return redirect(url_for('admin_actions'))
@app.get('/admin/externals')
@admin
def admin_externals():
 d=q('SELECT ep.*,COUNT(ap.id) n,COALESCE(SUM(ap.value_received),0) received,MAX(ap.created_at) last FROM external_participants ep LEFT JOIN action_participants ap ON ap.external_id=ep.id GROUP BY ep.id ORDER BY ep.name');trs=''.join(f'<tr><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["family"]}</td><td>{x["n"]}</td><td>{money(x["received"])}</td><td>{dt(x["last"]) if x["last"] else "—"}</td></tr>' for x in d);return layout('Participantes externos',f'<div class="card"><div class="table-wrap"><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Família</th><th>Participações</th><th>Recebido</th><th>Última</th></tr>{trs}</table></div></div>')
@app.get('/history')
@login_req
def history():
 d=q('SELECT week_start,COUNT(*)n,COALESCE(SUM(action_value),0)t FROM action_records GROUP BY week_start ORDER BY week_start DESC');cards=''.join(f'<div class="card"><h2>{x["week_start"]} — {(datetime.fromisoformat(x["week_start"])+timedelta(days=6)).date()}</h2><div class="metric">{money(x["t"])}</div><div class="muted">{x["n"]} ações</div><a class="proof" href="{url_for("history_week",week=x["week_start"])}">Abrir semana</a></div>' for x in d);return layout('Histórico',f'<div class="actions">{cards}</div>')
@app.get('/history/<week>')
@login_req
def history_week(week):
 d=q('SELECT ar.id,a.name,ar.action_value,ar.created_at FROM action_records ar JOIN actions a ON a.id=ar.action_id WHERE ar.week_start=? ORDER BY ar.created_at',(week,));trs=''.join(f'<tr><td>{x["name"]}</td><td>{money(x["action_value"])}</td><td>{dt(x["created_at"])}</td><td><a class=proof href="{url_for("result",record_id=x["id"])}">Abrir</a></td></tr>' for x in d);return layout('Histórico da semana',f'<div class="card"><div class="table-wrap"><table class="table"><tr><th>Ação</th><th>Valor</th><th>Data</th><th></th></tr>{trs}</table></div></div>')
@app.route('/admin/members/<int:member_id>',methods=['GET','POST'])
@admin
def member_edit(member_id):
 m=q('SELECT * FROM members WHERE id=?',(member_id,));
 if not m:abort(404)
 m=m[0]
 if request.method=='POST':ex('UPDATE members SET name=?,passport=?,cargo=?,notes=?,farm_notes=?,action_notes=?,general_notes=?,active=? WHERE id=?',(request.form['name'],request.form.get('passport') or None,request.form['cargo'],request.form.get('notes',''),request.form.get('farm_notes',''),request.form.get('action_notes',''),request.form.get('general_notes',''),1 if request.form.get('active') else 0,member_id));flash('Membro atualizado.');return redirect(url_for('members'))
 return layout('Editar membro',f'<div class="card"><form class="form" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" value="{m["name"]}"></div><div class="field"><label>Passaporte</label><input class="input" name="passport" value="{m["passport"] or ""}"></div><div class="field"><label>Cargo</label><input class="input" name="cargo" value="{m["cargo"]}"></div><div class="field"><label>Ativo</label><input type="checkbox" name="active" {"checked" if m["active"] else ""}></div><div class="field full"><label>Observações</label><textarea class="textarea" name="notes">{m["notes"] or ""}</textarea></div><div class="field full"><label>Contribuição Farm</label><textarea class="textarea" name="farm_notes">{m["farm_notes"] or ""}</textarea></div><div class="field full"><label>Contribuição Ações</label><textarea class="textarea" name="action_notes">{m["action_notes"] or ""}</textarea></div><div class="field full"><label>Observações gerais</label><textarea class="textarea" name="general_notes">{m["general_notes"] or ""}</textarea></div><button class="btn full">Salvar</button></form></div>')
@app.get('/admin/audit')
@admin
def audit_page():
 d=q('SELECT a.*,u.name un FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 300');trs=''.join(f'<tr><td>{dt(x["created_at"])}</td><td>{x["un"] or "Sistema"}</td><td>{x["action"]}</td><td>{x["details"] or ""}</td></tr>' for x in d);return layout('Logs administrativos',f'<div class="card"><div class="table-wrap"><table class="table"><tr><th>Data</th><th>Usuário</th><th>Ação</th><th>Detalhes</th></tr>{trs}</table></div></div>')
@app.get('/proof/<path:name>')
@login_req
def proof(name):
 s=secure_filename(name)
 if s!=name or not(UP/s).exists():abort(404)
 return send_file(UP/s)
@app.get('/admin')
@admin
def admin_home():return redirect(url_for('admin_actions'))
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')))
