import os,json,secrets,sqlite3,uuid,re
from pathlib import Path
from datetime import date,timedelta,datetime
from functools import wraps
from flask import Flask,request,session,redirect,url_for,abort,flash,send_file,render_template_string
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.utils import secure_filename
D=Path(os.getenv('DATA_DIR','/data'));D.mkdir(parents=True,exist_ok=True);U=D/'uploads';U.mkdir(exist_ok=True);DB=D/'lastro.db';MAX=8*1024*1024;EXT={'jpg','jpeg','png','webp'}
app=Flask(__name__);app.secret_key=os.getenv('SECRET_KEY') or secrets.token_hex(32);app.config.update(MAX_CONTENT_LENGTH=MAX,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','1')=='1')
M=[('Vocaro','LÍDER',None),('Nicole Lastro','LÍDER',4202),('Zeca Lastro','VICE-LÍDER',17147),('Andrey Magnata','GERENTE',28459),('Breno Gomes','GERENTE',32110),('Alice','MEMBRO',72884),('Bak Tarik','MEMBRO',28996),('Cassimiro','MEMBRO',34553),('dancollins','MEMBRO',None),('Dante','MEMBRO',41728),('Gabriel Garcia','MEMBRO',33858),('Marcelo Correia','MEMBRO',6027),('Marco Peixoto','MEMBRO',18976),('Negralha Oliveira','MEMBRO',28804),('Olindo Martins','MEMBRO',23525),('Oliver Bueno','MEMBRO',19975),('Paulo Miriam','MEMBRO',33250),('Pedro Pinto','MEMBRO',30692),('Sidney Santos','MEMBRO',25419),('Vitin Caiçara','MEMBRO',33952),('Willian Silveira','MEMBRO',23317),('Zoen Costa','MEMBRO',31195),('Barba Lenda','MEMBRO',24731),('Barrabas Belen','MEMBRO',24089),('Bene Oliveira','MEMBRO',26158),('Cartola Do Morro','MEMBRO',35159),('Cleiton Rasta','MEMBRO',34549),('Eduardo Madruga','MEMBRO',40203),('Eneias Silva','MEMBRO',14066),('Erik Mitrovic','MEMBRO',28539),('Fernando Fortes','MEMBRO',12288),('Gustavo Hammes','MEMBRO',42747),('Gustavo Henrique','MEMBRO',41395),('Josivaldo Rocha','MEMBRO',34623),('Kevin Smity','MEMBRO',42560),('Mameluco Camargo','MEMBRO',42506),('Miguel Andrade','MEMBRO',31551),('Mirna Santos','MEMBRO',34200),('Muniz Santos','MEMBRO',37700),('Pedro Rocha','MEMBRO',34595),('Pedro Rossa','MEMBRO',31909),('PH','MEMBRO',42684),('Pulcenio Ferraz','MEMBRO',39908),('Ronan Pires','MEMBRO',None),('Tony Gentil','MEMBRO',36332),('Velasco Montana','MEMBRO',39323),('Victor Santos','MEMBRO',42677)]
A={'Joalheria':(1,'5 a 7','9 a 11','Submetralhadora, Fuzil, Escopeta. AP Pistol não é submetralhadora.','Obrigatória','Opcional, máximo 3','Máximo 3 veículos; máximo 3 fora e 4 dentro.'),'Concessionária':(1,'8 a 10','12','Submetralhadora, Fuzil, Escopeta. AP Pistol não é submetralhadora.','Obrigatória','Opcional, máximo 4','Máximo 6 veículos: 3 próprios e 3 da concessionária. Polícia: máximo 5 granadas de gás.'),'Fleeca':(2,'6 a 8','10','A depender de cada local','Obrigatória','Obrigatório, máximo 3','Máximo 3 veículos.'),'Açougue':(1,'8 a 10','12','Submetralhadora, Fuzil, Escopeta. AP Pistol não é submetralhadora.','Obrigatória','Opcional, máximo 3','Máximo 3 veículos. Polícia: máximo 3 granadas de gás. Rotação P1/P2 externa permitida.'),'Galinheiro':(1,'8 a 10','12','Submetralhadora, Fuzil','Obrigatória','Opcional, máximo 2','Máximo 3 granadas de gás. Proibido mata/morros atrás dos trilhos.'),'Central do Mergulhador':(1,'7','10','Pistola ou submetralhadora. AP Pistol permitida.','Inexistente','Proibido','Polícia usa o mesmo armamento dos bandidos; com submetralhadora, todo o contingente pode usar.'),'Banco Central':(1,'10','13','Fuzil','Obrigatória','Opcional, máximo 4','Máximo 3 veículos. Refém: atiradores OU helicóptero, nunca ambos. Em fuga, ninguém fora.'),'Banco Paleto':(None,'10 máximo','13','Fuzil','Não há','Proibido','Confronto direto; começa quando polícia entra no perímetro.'),'Loja de Tatuagens':(None,'2 máximo','2','Apenas armas brancas; pode negociar punhos.','Obrigatória','Proibido',''),'Barbearia':(None,'4 a 10','Igual ao número de bandidos','Apenas armas brancas; pode negociar punhos.','Obrigatória','Proibido',''),'Loja de Armas — Praça':(None,'2','3','Apenas pistolas; AP Pistol proibida','Obrigatória','Proibido','Nenhum bandido fora.'),'Loja de Armas — Porto':(None,'3 a 5','5 a 7','Apenas pistolas; AP Pistol proibida','Obrigatória','Proibido','Proporcional aos bandidos.'),'Loja de Conveniência':(None,'5 a 6','7 a 8','Pistola obrigatória; AP Pistol proibida','Inexistente','Proibido','Troca de tiros, sem fuga. Até 2 bandidos fora dentro do perímetro; inicia no primeiro bandido fechado.')}
SC='''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,passport INTEGER,cargo TEXT NOT NULL,notes TEXT DEFAULT '',farm_notes TEXT DEFAULT '',action_notes TEXT DEFAULT '',general_notes TEXT DEFAULT '',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,weekly_limit INTEGER,action_value REAL DEFAULT 0,rules_json TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS farms(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,quantity REAL,proof TEXT,created_by INTEGER,created_at TEXT);CREATE TABLE IF NOT EXISTS productions(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,quantity REAL,material TEXT,reason TEXT,proof TEXT,created_by INTEGER,created_at TEXT);CREATE TABLE IF NOT EXISTS chests(id INTEGER PRIMARY KEY AUTOINCREMENT,member_id INTEGER,item TEXT,reason TEXT,proof TEXT,created_by INTEGER,created_at TEXT);CREATE TABLE IF NOT EXISTS action_records(id INTEGER PRIMARY KEY AUTOINCREMENT,action_id INTEGER,week_start TEXT,action_value REAL,family_value REAL,participant_pool REAL,rules_snapshot TEXT,created_by INTEGER,created_at TEXT,status TEXT DEFAULT 'FINALIZADA');CREATE TABLE IF NOT EXISTS external_participants(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,passport TEXT,family TEXT);CREATE TABLE IF NOT EXISTS action_participants(id INTEGER PRIMARY KEY AUTOINCREMENT,record_id INTEGER,member_id INTEGER,external_id INTEGER,side TEXT,weapon TEXT,eligible INTEGER,value_received REAL,reason TEXT,created_at TEXT);CREATE TABLE IF NOT EXISTS financial_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,record_id INTEGER,type TEXT,amount REAL,description TEXT,created_at TEXT);CREATE TABLE IF NOT EXISTS weekly_periods(id INTEGER PRIMARY KEY AUTOINCREMENT,week_start TEXT UNIQUE,week_end TEXT,closed INTEGER DEFAULT 0);CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,action TEXT,details TEXT,created_at TEXT);'''
def db():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA busy_timeout=30000');return c
def now():return datetime.now().astimezone().isoformat(timespec='seconds')
def week():d=date.today();return d-timedelta(days=d.weekday())
def money(v):return f'R$ {float(v or 0):,.2f}'.replace(',','X').replace('.',',').replace('X','.')
def q(s,a=()):
 c=db();r=c.execute(s,a).fetchall();c.close();return r
def ex(s,a=()):
 c=db();r=c.execute(s,a);c.commit();x=r.lastrowid;c.close();return x
def csrf():
 if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(24)
 return session['csrf']
def audit(a,d=''):ex('INSERT INTO audit_logs(user_id,action,details,created_at) VALUES(?,?,?,?)',(session.get('uid'),a,d))
def proof(f):
 if not f or not f.filename:return None
 e=secure_filename(f.filename).rsplit('.',1)[-1].lower() if '.' in f.filename else ''
 if e not in EXT:abort(400,'Arquivo inválido.')
 n=uuid.uuid4().hex+'.'+e;p=U/n;f.save(p)
 if p.stat().st_size>MAX:p.unlink(missing_ok=True);abort(413)
 return n
def req(f):
 @wraps(f)
 def w(*a,**k):return f(*a,**k) if session.get('uid') else redirect(url_for('login'))
 return w
def adm(f):
 @wraps(f)
 def w(*a,**k):
  if not session.get('uid'):return redirect(url_for('login'))
  if session.get('role')!='ADMINISTRADOR':abort(403)
  return f(*a,**k)
 return w
def init():
 c=db();c.executescript(SC);t=now();pw=os.getenv('ADMIN_INITIAL_PASSWORD') or os.getenv('ADMIN_PASSWORD')
 if pw and not c.execute('SELECT 1 FROM users WHERE username=?',('Marcelo Correia',)).fetchone():c.execute('INSERT INTO users(name,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',('Marcelo Correia','Marcelo Correia',generate_password_hash(pw),'ADMINISTRADOR',t))
 for n,cargo,p in M:
  if not c.execute('SELECT 1 FROM members WHERE name=?',(n,)).fetchone():c.execute('INSERT INTO members(name,passport,cargo,created_at) VALUES(?,?,?,?)',(n,p,cargo,t))
 for n,v in A.items():
  if not c.execute('SELECT 1 FROM actions WHERE name=?',(n,)).fetchone():c.execute('INSERT INTO actions(name,weekly_limit,action_value,rules_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',(n,v[0],0,json.dumps({'Bandidos':v[1],'Policiais':v[2],'Armamento':v[3],'Negociação':v[4],'Reféns':v[5],'Regras':v[6]},ensure_ascii=False),t,t))
 c.execute('INSERT OR IGNORE INTO weekly_periods(week_start,week_end) VALUES(?,?)',(week().isoformat(),(week()+timedelta(6)).isoformat()));c.commit();c.close()
@app.before_request
def before():
 init()
 if request.method=='POST' and (not session.get('uid') or not secrets.compare_digest(request.form.get('csrf',''),session.get('csrf',''))):abort(400)
CSS='''body{margin:0;background:radial-gradient(circle at 80% -10%,#2d2308,transparent 32%),#050505;color:#f7f3e8;font:14px system-ui,sans-serif}a{text-decoration:none;color:inherit}.app{min-height:100vh}.side{position:fixed;width:245px;inset:0 auto 0 0;background:#070707;border-right:1px solid #3d3116;padding:22px 14px}.brand b{font-size:25px;letter-spacing:.14em;color:#d4af37}.brand span{display:block;color:#a79b82;font-size:10px;margin:5px 0 24px}.nav a{display:block;padding:11px;border-radius:10px;color:#bcb39f;margin:3px 0}.nav a:hover{background:#15120a;color:#f0d477}.main{margin-left:245px;padding:28px 34px}.top{display:flex;justify-content:space-between}.top h1{margin:0 0 22px;color:#f0d477}.grid,.actions{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.actions{grid-template-columns:repeat(3,1fr)}.card{background:linear-gradient(#12110e,#0a0a09);border:1px solid #3b2e13;border-radius:16px;padding:18px;box-shadow:0 15px 40px #0008}.metric{font-size:27px;font-weight:800;color:#f0d477}.label{font-size:10px;text-transform:uppercase;color:#a79b82;letter-spacing:.1em}.section{margin-top:18px}.table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:11px;border-bottom:1px solid #27200f;text-align:left;white-space:nowrap}.table th{font-size:10px;color:#d4af37}.btn{display:inline-block;border:1px solid #d4af37;border-radius:10px;padding:10px 14px;background:linear-gradient(#e3c04e,#c39b25);color:#070707;font-weight:800;cursor:pointer}.secondary{background:#11100d;color:#f0d477}.danger{background:#261010;color:#ff9b9b;border-color:#713030}.form{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.field{display:flex;flex-direction:column;gap:6px}.full{grid-column:1/-1}.input,.select,.textarea{width:100%;background:#080808;color:#fff;border:1px solid #4b3b18;border-radius:10px;padding:11px;outline:0}.textarea{min-height:100px}.flash{padding:11px;border:1px solid #5b4a1e;background:#17140b;border-radius:10px;margin-bottom:12px}.flash.error{border-color:#713030;background:#251010}.muted{color:#a79b82}.pill{padding:5px 8px;border-radius:99px;background:#211b0c;border:1px solid #4c3d18;color:#f0d477;font-size:11px}.rules{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}.rule{padding:11px;background:#090908;border:1px solid #302610;border-radius:10px}.rule b{display:block;color:#d4af37;font-size:10px;text-transform:uppercase}.member{display:flex;gap:10px;align-items:center;background:#090908;border:1px solid #332912;border-radius:11px;padding:12px;margin-top:9px}.login{min-height:100vh;display:grid;place-items:center}.loginbox{width:min(430px,90%)}.ok{color:#68d391}.no{color:#ff9b9b}@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.actions{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.side{display:none}.main{margin:0;padding:18px 14px 80px}.grid,.actions,.form,.rules{grid-template-columns:1fr}}'''
IC={'Painel':'◈','Farm':'⬢','Produção':'◉','Baú':'▣','Ações':'◇','Ranking':'↗','Hierarquia':'♟','Histórico':'◫','Usuários':'⚙','Admin':'◆','Externos':'◌','Logs':'≡'}
def lay(t,b):
 it=[('Painel','dashboard'),('Farm','farms'),('Produção','productions'),('Baú','chests'),('Ações','actions'),('Ranking','ranking'),('Hierarquia','members'),('Histórico','history')]
 if session.get('role')=='ADMINISTRADOR':it += [('Usuários','users'),('Admin','admin_actions'),('Externos','externals'),('Logs','logs')]
 n=''.join(f'<a href="{url_for(r)}">{IC[k]} &nbsp;{k}</a>' for k,r in it);f=''.join(f'<div class="flash {"error" if c=="error" else ""}">{m}</div>' for c,m in session.pop('_flashes',[]))
 return render_template_string(f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{t} · LASTRO</title><style>{CSS}</style></head><body><div class="app"><aside class="side"><div class="brand"><b>LASTRO</b><span>CENTRAL ADMINISTRATIVA</span></div><nav class="nav">{n}</nav><a class="btn secondary" style="position:absolute;bottom:22px;left:25px;right:25px;text-align:center" href="{url_for("logout")}">Sair</a></aside><main class="main"><div class="top"><h1>{t}</h1><span class="muted">{session.get("role","")}</span></div>{f}{b}</main></div></body></html>')
@app.get('/health')
def health():db().close();return {'status':'ok','service':'central-lastro'}
@app.route('/',methods=['GET','POST'])
def login():
 if session.get('uid'):return redirect(url_for('dashboard'))
 if request.method=='POST':
  r=q('SELECT * FROM users WHERE lower(username)=lower(?) AND active=1',(request.form['username'].strip(),))
  if r and check_password_hash(r[0]['password_hash'],request.form['password']):session.clear();session.update(uid=r[0]['id'],name=r[0]['name'],role=r[0]['role']);csrf();return redirect(url_for('dashboard'))
  flash('Usuário ou senha inválidos.','error')
 return render_template_string(f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body><div class="login"><form class="card loginbox" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="brand"><b>LASTRO</b><span>CENTRAL ADMINISTRATIVA PRIVADA</span></div><div class="field"><label>Usuário</label><input class="input" name="username" required></div><div class="field"><label>Senha</label><input class="input" type="password" name="password" required></div><button class="btn full">Entrar</button></form></div></body></html>')
@app.get('/logout')
def logout():session.clear();return redirect(url_for('login'))
@app.get('/dashboard')
@req
def dashboard():
 w=week().isoformat();tot=q('SELECT COALESCE(SUM(action_value),0)v FROM action_records')[0]['v'];lw=q('SELECT COALESCE(SUM(action_value),0)v FROM action_records WHERE week_start=?',(w,))[0]['v'];na=q('SELECT COUNT(*)n FROM action_records WHERE week_start=?',(w,))[0]['n'];nm=q('SELECT COUNT(DISTINCT member_id)n FROM action_participants ap JOIN action_records ar ON ar.id=ap.record_id WHERE ar.week_start=? AND member_id IS NOT NULL',(w,))[0]['n'];cards=''.join(f'<div class="card"><div class="label">{a}</div><div class="metric">{b}</div></div>' for a,b in [('Total movimentado',money(tot)),('Lucro semanal',money(lw)),('Ações realizadas na semana',na),('Membros participantes',nm)]);aa=[]
 for a in q('SELECT * FROM actions WHERE active=1 ORDER BY id'):
  n=q('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(a['id'],w))[0]['n'];l=a['weekly_limit'];lock=l is not None and n>=l;aa.append(f'<div class="card"><span class="pill">{n}/{l if l is not None else "∞"}</span><h2>{a["name"]}</h2><p class="muted">{money(a["action_value"]) if a["action_value"] else "Valor ainda não definido"}</p><a class="btn {"secondary" if lock else ""}" href="{url_for("action",action_id=a["id"])}">{"Limite atingido" if lock else "Registrar"}</a></div>')
 return lay('Painel',f'<div class="grid">{cards}</div><div class="section"><h2>Ações da semana</h2><div class="actions">{"".join(aa)}</div></div>')
@app.route('/farms',methods=['GET','POST'])
@req
def farms():
 if request.method=='POST':ex('INSERT INTO farms(member_id,quantity,proof,created_by,created_at) VALUES(?,?,?,?,?)',(request.form['member_id'],float(request.form['quantity']),proof(request.files.get('proof')),session['uid'],now()));flash('Farm registrado.');return redirect(url_for('farms'))
 o=''.join(f'<option value="{x["id"]}">{x["name"]} — {x["passport"] or "sem passaporte"}</option>' for x in q('SELECT * FROM members WHERE active=1 ORDER BY name'));d=q('SELECT f.*,m.name,u.name un FROM farms f JOIN members m ON m.id=f.member_id JOIN users u ON u.id=f.created_by ORDER BY f.id DESC LIMIT 100');tr=''.join(f'<tr><td>{x["name"]}</td><td>{x["quantity"]:g}</td><td>{x["un"]}</td><td>{x["created_at"][:16].replace("T"," ")}</td><td>{"<a href="+url_for("proof_file",name=x["proof"])+">Abrir</a>" if x["proof"] else "—"}</td></tr>' for x in d);return lay('Farm',f'<div class="card"><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{csrf()}"><div class="field full"><label>Membro quem entregou</label><select class="select" name="member_id" required>{o}</select></div><div class="field"><label>Quantidade</label><input class="input" type="number" step=".01" min=0 name="quantity" required></div><div class="field"><label>Prova/foto</label><input class="input" type="file" name="proof" accept="image/jpeg,image/png,image/webp"></div><button class="btn full">Salvar farm</button></form></div><div class="card section"><div class="table-wrap"><table class="table"><tr><th>Membro</th><th>Qtd.</th><th>Registrado por</th><th>Data</th><th>Prova</th></tr>{tr}</table></div></div>')
@app.route('/productions',methods=['GET','POST'])
@req
def productions():
 if request.method=='POST':ex('INSERT INTO productions(member_id,quantity,material,reason,proof,created_by,created_at) VALUES(?,?,?,?,?,?,?)',(request.form['member_id'],float(request.form['quantity']),request.form['material'],request.form['reason'],proof(request.files.get('proof')),session['uid'],now()));flash('Produção registrada.');return redirect(url_for('productions'))
 return lay('Produção','<div class="card"><p class="muted">Registro de produção.</p><form class="form" method="post"><input type="hidden" name="csrf" value="'+csrf()+'"><div class="field full"><label>Responsável</label><select class="select" name="member_id">'+''.join(f'<option value="{x["id"]}">{x["name"]}</option>' for x in q('SELECT * FROM members WHERE active=1 ORDER BY name'))+'</select></div><div class="field"><label>Quantidade</label><input class="input" name="quantity" type="number" step=".01" required></div><div class="field"><label>Material</label><input class="input" name="material" required></div><div class="field"><label>Motivo</label><select class="select" name="reason"><option>uso</option><option>venda</option><option>estoque</option><option>outro</option></select></div><button class="btn full">Salvar</button></form></div>')
@app.route('/chests',methods=['GET','POST'])
@req
def chests():
 if request.method=='POST':ex('INSERT INTO chests(member_id,item,reason,proof,created_by,created_at) VALUES(?,?,?,?,?,?)',(request.form['member_id'],request.form['item'],request.form['reason'],proof(request.files.get('proof')),session['uid'],now()));flash('Baú registrado.');return redirect(url_for('chests'))
 return lay('Baú','<div class="card"><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="'+csrf()+'"><div class="field full"><label>Quem retirou</label><select class="select" name="member_id">'+''.join(f'<option value="{x["id"]}">{x["name"]}</option>' for x in q('SELECT * FROM members WHERE active=1 ORDER BY name'))+'</select></div><div class="field"><label>Item</label><input class="input" name="item" required></div><div class="field"><label>Motivo</label><input class="input" name="reason" required></div><button class="btn full">Registrar</button></form></div>')
@app.route('/actions/<int:action_id>',methods=['GET','POST'])
@req
def action(action_id):
 a=q('SELECT * FROM actions WHERE id=?',(action_id,));
 if not a:abort(404)
 a=a[0];r=json.loads(a['rules_json']);w=week().isoformat();n=q('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(action_id,w))[0]['n'];l=a['weekly_limit']
 if request.method=='POST':
  if l is not None and n>=l:flash('Limite semanal atingido.','error');return redirect(url_for('dashboard'))
  mids=[int(x) for x in request.form.getlist('member_ids')]
  if len(mids)!=len(set(mids)):flash('Participante duplicado.','error');return redirect(request.url)
  parts=[('m',m,None,request.form.get('side_'+str(m),'BANDIDO'),request.form.get('weapon_'+str(m),'INDEFINIDO')) for m in mids]
  names=request.form.getlist('ext_name');pas=request.form.getlist('ext_pass');fam=request.form.getlist('ext_family')
  for i,x in enumerate(names):
   if x.strip():parts.append(('e',None,(x.strip(),pas[i].strip() if i<len(pas) else '',fam[i].strip() if i<len(fam) else ''),request.form.get('ext_side_'+str(i),'BANDIDO'),request.form.get('ext_weapon_'+str(i),'INDEFINIDO')))
  if not parts or any(x[4]=='INDEFINIDO' for x in parts):flash('Todos os participantes precisam ter armamento definido.','error');return redirect(request.url)
  b=sum(x[3]=='BANDIDO' for x in parts);p=sum(x[3]=='POLICIAL' for x in parts)
  def nums(s):
   z=re.match(r'^(\d+)\s*a\s*(\d+)',str(s));return (int(z[1]),int(z[2])) if z else None
  for k,v in [('Bandidos',b),('Policiais',p)]:
   z=nums(r.get(k,''));
   if z and not z[0]<=v<=z[1]:flash(f'{k}: permitido {z[0]} a {z[1]}; informado {v}.','error');return redirect(request.url)
   z2=re.match(r'^(\d+)',str(r.get(k,'')))
   if z2 and 'obrigatório' in str(r.get(k,'')).lower() and v!=int(z2[1]):flash(f'{k}: quantidade obrigatória inválida.','error');return redirect(request.url)
  if 'Igual ao número' in r.get('Policiais','') and p!=b:flash('Policiais devem ser iguais aos bandidos.','error');return redirect(request.url)
  val=float(a['action_value'] or 0);fv=round(val*.5,2);pool=round(val-fv,2);el=[x for x in parts if x[4]=='TROUXE'];c=db()
  try:
   c.execute('BEGIN IMMEDIATE');fresh=c.execute('SELECT COUNT(*)n FROM action_records WHERE action_id=? AND week_start=?',(action_id,w)).fetchone()['n'];
   if l is not None and fresh>=l:raise ValueError('Limite semanal atingido')
   rid=c.execute('INSERT INTO action_records(action_id,week_start,action_value,family_value,participant_pool,rules_snapshot,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(action_id,w,val,fv,pool,json.dumps(r,ensure_ascii=False),session['uid'],now())).lastrowid;c.execute('INSERT INTO financial_transactions(record_id,type,amount,description,created_at) VALUES(?,?,?,?,?)',(rid,'FAMILIA',fv,'50% família',now()));c.execute('INSERT INTO financial_transactions(record_id,type,amount,description,created_at) VALUES(?,?,?,?,?)',(rid,'PARTICIPANTES',pool,'50% participantes',now()));base=int(round(pool*100))//len(el) if el else 0;rem=int(round(pool*100))-base*len(el) if el else 0;ei=0
   for typ,mid,e,side,weapon in parts:
    eid=None
    if typ=='e':eid=c.execute('INSERT INTO external_participants(name,passport,family) VALUES(?,?,?)',e).lastrowid
    ok=weapon=='TROUXE';amount=(base+(1 if ok and ei<rem else 0))/100 if ok else 0
    if ok:ei+=1
    c.execute('INSERT INTO action_participants(record_id,member_id,external_id,side,weapon,eligible,value_received,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(rid,mid,eid,side,weapon,int(ok),amount,'' if ok else 'não trouxe armamento',now()))
   c.commit()
  except Exception as e:c.rollback();c.close();flash(str(e),'error');return redirect(request.url)
  c.close();audit('ACAO_FINALIZADA',f'action={a["name"]};record={rid}');flash('Ação finalizada.');return redirect(url_for('result',record_id=rid))
 opts=''.join(f'<option value="{x["id"]}">{x["name"]} — {x["passport"] or "sem passaporte"} — {x["cargo"]}</option>' for x in q('SELECT * FROM members WHERE active=1 ORDER BY name'));rh=''.join(f'<div class="rule"><b>{k}</b>{v}</div>' for k,v in r.items())
 return lay(a['name'],f'<div class="card"><span class="pill">Frequência: {n}/{l if l is not None else "∞"}</span><p class="muted">Valor: {money(a["action_value"]) if a["action_value"] else "Ainda não definido"}</p><div class="rules">{rh}</div></div><form class="section" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="card"><h2>Participantes da família</h2><div id="ms"></div><button class="btn secondary" type="button" onclick="addM()">+ Selecionar membro</button></div><div class="card section"><h3>Adicionar participante externo</h3><div id="es"></div><button class="btn secondary" type="button" onclick="addE()">+ Adicionar participante externo</button></div><button class="btn section" type="submit">Finalizar ação</button></form><template id="mt"><div class="member"><div style="flex:1"><select class="select" name="member_ids" onchange="sync(this)">{opts}</select><div class="form"><select class="select" data-s><option>BANDIDO</option><option>POLICIAL</option></select><select class="select" data-w><option value="INDEFINIDO">Não informado</option><option value="TROUXE">Trouxe armamento</option><option value="NAO_TROUXE">Não trouxe</option></select></div></div><button type="button" class="btn danger" onclick="this.closest(\'.member\').remove()">Remover</button></div></template><script>function sync(x){{let c=x.closest('.member');c.querySelector('[data-s]').name='side_'+x.value;c.querySelector('[data-w]').name='weapon_'+x.value}}function addM(){{let x=document.getElementById('mt').content.cloneNode(true);document.getElementById('ms').appendChild(x);sync(document.querySelector('#ms .member:last-child select[name=member_ids]'))}}let ei=0;function addE(){{let i=ei++,d=document.createElement('div');d.className='member';d.innerHTML=`<div style="flex:1"><div class="form"><input class="input" name="ext_name" placeholder="Nome" required><input class="input" name="ext_pass" placeholder="Passaporte"><input class="input" name="ext_family" placeholder="Família" required><select class="select" name="ext_side_${{i}}"><option>BANDIDO</option><option>POLICIAL</option></select><select class="select" name="ext_weapon_${{i}}"><option value="INDEFINIDO">Não informado</option><option value="TROUXE">Trouxe armamento</option><option value="NAO_TROUXE">Não trouxe</option></select></div></div><button type="button" class="btn danger" onclick="this.closest('.member').remove()">Remover</button>`;document.getElementById('es').appendChild(d)}}</script>')
@app.get('/actions/result/<int:record_id>')
@req
def result(record_id):
 r=q('SELECT ar.*,a.name FROM action_records ar JOIN actions a ON a.id=ar.action_id WHERE ar.id=?',(record_id,));
 if not r:abort(404)
 r=r[0];p=q('SELECT ap.*,m.name mn,m.passport,ep.name en,ep.passport epass FROM action_participants ap LEFT JOIN members m ON m.id=ap.member_id LEFT JOIN external_participants ep ON ep.id=ap.external_id WHERE ap.record_id=?',(record_id,));y=''.join(f'<tr><td>{x["mn"] or x["en"]}</td><td>{x["passport"] or x["epass"] or "—"}</td><td>{x["side"]}</td><td class="ok">{money(x["value_received"])}</td></tr>' for x in p if x['eligible']);n=''.join(f'<tr><td>{x["mn"] or x["en"]}</td><td>{x["side"]}</td><td class="no">R$ 0,00</td><td>{x["reason"]}</td></tr>' for x in p if not x['eligible']);return lay('Resultado · '+r['name'],f'<div class="grid"><div class="card"><div class="label">Valor</div><div class="metric">{money(r["action_value"])}</div></div><div class="card"><div class="label">Família 50%</div><div class="metric">{money(r["family_value"])}</div></div><div class="card"><div class="label">Participantes 50%</div><div class="metric">{money(r["participant_pool"])}</div></div></div><div class="card section"><h2>Elegíveis</h2><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Lado</th><th>Recebeu</th></tr>{y}</table></div><div class="card section"><h2>Não elegíveis</h2><table class="table"><tr><th>Nome</th><th>Lado</th><th>Recebeu</th><th>Motivo</th></tr>{n}</table></div>')
@app.get('/ranking')
@req
def ranking():
 d=q('''SELECT m.name,m.passport,m.cargo,COUNT(DISTINCT ap.record_id)n,COALESCE(SUM(ap.value_received),0) v,(SELECT COALESCE(SUM(quantity),0) FROM farms f WHERE f.member_id=m.id) farm FROM members m LEFT JOIN action_participants ap ON ap.member_id=m.id LEFT JOIN action_records ar ON ar.id=ap.record_id AND ar.week_start=? WHERE m.active=1 GROUP BY m.id ORDER BY v DESC,n DESC,m.name''',(week().isoformat(),));tr=''.join(f'<tr><td>{i}</td><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["cargo"]}</td><td>{x["n"]}</td><td>{money(x["v"])}</td><td>{x["farm"]:g}</td></tr>' for i,x in enumerate(d,1));return lay('Ranking',f'<div class="card"><table class="table"><tr><th>#</th><th>Nome</th><th>Passaporte</th><th>Cargo</th><th>Ações</th><th>Recebido</th><th>Farm</th></tr>{tr}</table></div>')
@app.get('/members')
@req
def members():
 s=request.args.get('q','');d=q('SELECT * FROM members WHERE active=1 AND (name LIKE ? OR CAST(passport AS TEXT) LIKE ?) ORDER BY CASE cargo WHEN "LÍDER" THEN 1 WHEN "VICE-LÍDER" THEN 2 WHEN "GERENTE" THEN 3 ELSE 4 END,name',(f'%{s}%',f'%{s}%'));tr=''.join(f'<tr><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["cargo"]}</td><td>{"<a href="+url_for("member_edit",member_id=x["id"])+">Editar</a>" if session.get("role")=="ADMINISTRADOR" else "—"}</td></tr>' for x in d);return lay('Hierarquia',f'<div class="card"><form class="split"><input class="input" name="q" value="{s}" placeholder="Nome ou passaporte"><button class="btn">Pesquisar</button></form></div><div class="card section"><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Cargo</th><th></th></tr>{tr}</table></div>')
@app.route('/admin/members/<int:member_id>',methods=['GET','POST'])
@adm
def member_edit(member_id):
 m=q('SELECT * FROM members WHERE id=?',(member_id,));
 if not m:abort(404)
 m=m[0]
 if request.method=='POST':ex('UPDATE members SET name=?,passport=?,cargo=?,notes=?,farm_notes=?,action_notes=?,general_notes=?,active=? WHERE id=?',(request.form['name'],request.form.get('passport') or None,request.form['cargo'],request.form.get('notes',''),request.form.get('farm_notes',''),request.form.get('action_notes',''),request.form.get('general_notes',''),1 if request.form.get('active') else 0,member_id));flash('Membro atualizado.');return redirect(url_for('members'))
 return lay('Editar membro',f'<div class="card"><form class="form" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" value="{m["name"]}"></div><div class="field"><label>Passaporte</label><input class="input" name="passport" value="{m["passport"] or ""}"></div><div class="field"><label>Cargo</label><input class="input" name="cargo" value="{m["cargo"]}"></div><div class="field"><label>Ativo</label><input type="checkbox" name="active" {"checked" if m["active"] else ""}></div><div class="field full"><label>Observações</label><textarea class="textarea" name="notes">{m["notes"] or ""}</textarea></div><div class="field full"><label>Farm</label><textarea class="textarea" name="farm_notes">{m["farm_notes"] or ""}</textarea></div><div class="field full"><label>Ações</label><textarea class="textarea" name="action_notes">{m["action_notes"] or ""}</textarea></div><div class="field full"><label>Observações gerais</label><textarea class="textarea" name="general_notes">{m["general_notes"] or ""}</textarea></div><button class="btn full">Salvar</button></form></div>')
@app.get('/users')
@adm
def users():
 d=q('SELECT * FROM users ORDER BY role,name');tr=''.join(f'<tr><td>{x["name"]}</td><td>{x["username"]}</td><td>{x["role"]}</td><td>{"Ativo" if x["active"] else "Inativo"}</td><td><a href="{url_for("user_edit",user_id=x["id"])}">Editar</a></td></tr>' for x in d);return lay('Usuários',f'<div class="card"><a class="btn" href="{url_for("user_new")}">+ Nova conta</a></div><div class="card section"><table class="table"><tr><th>Nome</th><th>Usuário</th><th>Perfil</th><th>Status</th><th></th></tr>{tr}</table></div>')
@app.route('/admin/users/new',methods=['GET','POST'])
@adm
def user_new():
 if request.method=='POST':
  if len(request.form['password'])<8:flash('Senha mínima: 8 caracteres.','error');return redirect(request.url)
  try:ex('INSERT INTO users(name,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',(request.form['name'],request.form['username'],generate_password_hash(request.form['password']),request.form['role'],now()));flash('Conta criada.');return redirect(url_for('users'))
  except sqlite3.IntegrityError:flash('Usuário já existe.','error')
 return lay('Nova conta',f'<div class="card"><form class="form" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" required></div><div class="field"><label>Usuário</label><input class="input" name="username" required></div><div class="field"><label>Senha</label><input class="input" type="password" name="password" minlength=8 required></div><div class="field"><label>Perfil</label><select class="select" name="role"><option>OPERACIONAL</option><option>ADMINISTRADOR</option></select></div><button class="btn full">Criar</button></form></div>')
@app.route('/admin/users/<int:user_id>',methods=['GET','POST'])
@adm
def user_edit(user_id):
 u=q('SELECT * FROM users WHERE id=?',(user_id,));
 if not u:abort(404)
 u=u[0]
 if request.method=='POST':
  if request.form.get('password') and len(request.form['password'])<8:flash('Senha mínima: 8 caracteres.','error');return redirect(request.url)
  if request.form.get('password'):ex('UPDATE users SET name=?,username=?,role=?,active=?,password_hash=? WHERE id=?',(request.form['name'],request.form['username'],request.form['role'],1 if request.form.get('active') else 0,generate_password_hash(request.form['password']),user_id))
  else:ex('UPDATE users SET name=?,username=?,role=?,active=? WHERE id=?',(request.form['name'],request.form['username'],request.form['role'],1 if request.form.get('active') else 0,user_id))
  flash('Conta atualizada.');return redirect(url_for('users'))
 return lay('Editar conta',f'<div class="card"><form class="form" method="post"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Nome</label><input class="input" name="name" value="{u["name"]}"></div><div class="field"><label>Usuário</label><input class="input" name="username" value="{u["username"]}"></div><div class="field"><label>Nova senha</label><input class="input" type="password" name="password"></div><div class="field"><label>Perfil</label><select class="select" name="role"><option {'selected' if u["role"]=='OPERACIONAL' else ''}>OPERACIONAL</option><option {'selected' if u["role"]=='ADMINISTRADOR' else ''}>ADMINISTRADOR</option></select></div><div class="field"><label>Ativo</label><input type="checkbox" name="active" {"checked" if u["active"] else ""}></div><button class="btn full">Salvar</button></form></div>')
@app.get('/admin/actions')
@adm
def admin_actions():
 d=q('SELECT * FROM actions ORDER BY id');c=[]
 for x in d:c.append(f'<div class="card"><h2>{x["name"]}</h2><form method="post" action="{url_for("admin_action",action_id=x["id"])}"><input type="hidden" name="csrf" value="{csrf()}"><div class="field"><label>Valor</label><input class="input" name="value" type="number" step=".01" value="{x["action_value"]}"></div><div class="field"><label>Limite semanal</label><input class="input" name="limit" type="number" min=1 value="{x["weekly_limit"] or ""}"></div><div class="field full"><label>Regras JSON</label><textarea class="textarea" name="rules">{x["rules_json"]}</textarea></div><button class="btn">Salvar</button></form></div>')
 return lay('Administração · Ações',''.join(c))
@app.post('/admin/actions/<int:action_id>')
@adm
def admin_action(action_id):
 try:v=float(request.form.get('value') or 0);l=request.form.get('limit','').strip();l=int(l) if l else None;r=json.loads(request.form['rules']);ex('UPDATE actions SET action_value=?,weekly_limit=?,rules_json=?,updated_at=? WHERE id=?',(v,l,json.dumps(r,ensure_ascii=False),now(),action_id));flash('Configuração salva.')
 except Exception as e:flash('Configuração inválida: '+str(e),'error')
 return redirect(url_for('admin_actions'))
@app.get('/externals')
@adm
def externals():
 d=q('SELECT ep.*,COUNT(ap.id)n,COALESCE(SUM(ap.value_received),0)v FROM external_participants ep LEFT JOIN action_participants ap ON ap.external_id=ep.id GROUP BY ep.id ORDER BY ep.name');tr=''.join(f'<tr><td>{x["name"]}</td><td>{x["passport"] or "—"}</td><td>{x["family"]}</td><td>{x["n"]}</td><td>{money(x["v"])}</td></tr>' for x in d);return lay('Participantes externos',f'<div class="card"><table class="table"><tr><th>Nome</th><th>Passaporte</th><th>Família</th><th>Participações</th><th>Recebido</th></tr>{tr}</table></div>')
@app.get('/history')
@req
def history():
 d=q('SELECT week_start,COUNT(*)n,COALESCE(SUM(action_value),0)v FROM action_records GROUP BY week_start ORDER BY week_start DESC');c=''.join(f'<div class="card"><h2>{x["week_start"]}</h2><div class="metric">{money(x["v"])}</div><p>{x["n"]} ações</p><a href="{url_for("history_week",week=x["week_start"])}">Abrir semana</a></div>' for x in d);return lay('Histórico',f'<div class="actions">{c}</div>')
@app.get('/history/<week>')
@req
def history_week(week):
 d=q('SELECT ar.id,a.name,ar.action_value,ar.created_at FROM action_records ar JOIN actions a ON a.id=ar.action_id WHERE ar.week_start=? ORDER BY ar.created_at',(week,));tr=''.join(f'<tr><td>{x["name"]}</td><td>{money(x["action_value"])}</td><td>{x["created_at"][:16].replace("T"," ")}</td><td><a href="{url_for("result",record_id=x["id"])}">Abrir</a></td></tr>' for x in d);return lay('Histórico da semana',f'<div class="card"><table class="table"><tr><th>Ação</th><th>Valor</th><th>Data</th><th></th></tr>{tr}</table></div>')
@app.get('/admin/audit')
@adm
def logs():
 d=q('SELECT a.*,u.name un FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 300');tr=''.join(f'<tr><td>{x["created_at"][:16]}</td><td>{x["un"] or "Sistema"}</td><td>{x["action"]}</td><td>{x["details"] or ""}</td></tr>' for x in d);return lay('Logs administrativos',f'<div class="card"><table class="table"><tr><th>Data</th><th>Usuário</th><th>Ação</th><th>Detalhes</th></tr>{tr}</table></div>')
@app.get('/proof/<path:name>')
@req
def proof_file(name):
 s=secure_filename(name)
 if s!=name or not(U/s).exists():abort(404)
 return send_file(U/s)
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')))
