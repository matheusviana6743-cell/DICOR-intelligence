import os, sqlite3, uuid
from datetime import datetime
from flask import Flask,request,redirect,session,send_from_directory,render_template_string,flash
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.utils import secure_filename

app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','lastro-change-secret'); app.config['MAX_CONTENT_LENGTH']=12*1024*1024
DB=os.getenv('DB_PATH','/data/lastro.db'); UP=os.getenv('UPLOAD_DIR','/data/uploads'); os.makedirs(os.path.dirname(DB),exist_ok=True); os.makedirs(UP,exist_ok=True)
CSS='''*{box-sizing:border-box}body{margin:0;background:#070a09;color:#e8eee9;font:14px Arial}.side{position:fixed;inset:0 auto 0 0;width:225px;background:#0c1210;border-right:1px solid #1e2a23;padding:24px 14px}.brand{font-size:25px;font-weight:900;letter-spacing:5px;color:#73e0a5;margin:4px 10px 25px}.brand small{display:block;font-size:9px;letter-spacing:2px;color:#718078;margin-top:5px}.nav a,.out{display:block;padding:11px 12px;margin:4px 0;border-radius:9px;text-decoration:none;color:#9aa9a1}.nav a:hover,.nav .on{background:#15231b;color:#8af0b6}.out{position:absolute;bottom:18px;left:14px;right:14px;border:1px solid #29382f}.main{margin-left:225px;padding:28px;max-width:1450px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.title{font-size:26px;font-weight:800}.muted{color:#78877f}.pill{background:#173223;color:#8cf0b7;border-radius:20px;padding:5px 9px;font-size:11px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{background:#0e1511;border:1px solid #1d2a22;border-radius:14px;padding:17px}.kpi{font-size:27px;font-weight:900;color:#8cf0b7;margin-top:5px}.cols{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form{display:grid;gap:10px}input,select,textarea{width:100%;background:#090e0c;border:1px solid #29372f;color:#edf4ef;border-radius:8px;padding:10px}button{background:#67d998;color:#061009;border:0;border-radius:8px;padding:10px 14px;font-weight:800;cursor:pointer}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:10px 7px;border-bottom:1px solid #1c2821;text-align:left}.table th{font-size:10px;color:#6f7d75;text-transform:uppercase}.btn{display:inline-block;padding:6px 9px;background:#17241d;border:1px solid #2b3d32;border-radius:7px;text-decoration:none}.flash{background:#122319;border:1px solid #345c43;padding:10px;border-radius:8px;margin-bottom:12px}.login{min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle,#142a1e,#070a09 58%)}.box{width:min(400px,92vw);background:#0d1410;border:1px solid #26372e;border-radius:17px;padding:28px}.box h1{color:#8cf0b7;letter-spacing:6px;margin:0}.box p{color:#718078}.rank{display:flex;justify-content:space-between;padding:11px 0;border-bottom:1px solid #1c2821}@media(max-width:800px){.side{width:65px}.brand{font-size:0}.brand:after{content:'L';font-size:25px}.brand small,.nav span{display:none}.main{margin-left:65px;padding:15px}.grid,.cols{grid-template-columns:1fr 1fr}}@media(max-width:560px){.grid,.cols{grid-template-columns:1fr}.main{padding:10px}}'''
BASE='''<!doctype html><html lang=pt-br><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>LASTRO • Central</title><style>'''+CSS+'''</style></head><body>{{BODY|safe}}</body></html>'''
def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
 c=conn(); c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,password TEXT,name TEXT,role TEXT,active INTEGER DEFAULT 1);CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY,name TEXT,role TEXT,notes TEXT,results TEXT);CREATE TABLE IF NOT EXISTS farms(id INTEGER PRIMARY KEY,member_id INTEGER,qty REAL,proof TEXT,created TEXT);CREATE TABLE IF NOT EXISTS productions(id INTEGER PRIMARY KEY,member_id INTEGER,produced REAL,used REAL,reason TEXT,proof TEXT,created TEXT);CREATE TABLE IF NOT EXISTS chests(id INTEGER PRIMARY KEY,member_id INTEGER,item TEXT,proof TEXT,reason TEXT,created TEXT);CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY,name TEXT,payout REAL,notes TEXT);CREATE TABLE IF NOT EXISTS action_logs(id INTEGER PRIMARY KEY,action_id INTEGER,member_id INTEGER,proof TEXT,created TEXT);''')
 if not c.execute('select 1 from users limit 1').fetchone(): c.execute('insert into users(username,password,name,role) values(?,?,?,?)',(os.getenv('ADMIN_USER','gerencia'),generate_password_hash(os.getenv('ADMIN_PASSWORD','Lastro@2026')),'Gerência','Gerência'))
 c.commit(); c.close()
init()
def user(): return conn().execute('select * from users where id=? and active=1',(session.get('uid'),)).fetchone() if session.get('uid') else None
def guard(): return None if user() else redirect('/login')
def proof():
 f=request.files.get('proof');
 if not f or not f.filename:return ''
 n=uuid.uuid4().hex+os.path.splitext(secure_filename(f.filename))[1]; f.save(os.path.join(UP,n)); return n
def page(title,body,key):
 links=[('/','▦ Painel','home'),('/farm','◈ Farm','farm'),('/producao','◇ Produção','prod'),('/bau','▣ Baú','bau'),('/acoes','◆ Ações','acoes'),('/ranking','★ Ranking','rank'),('/hierarquia','♟ Hierarquia','hier'),('/usuarios','⚿ Usuários','users')]
 nav=''.join(f'<a class="{"on" if key==k else ""}" href="{h}">{l}</a>' for h,l,k in links)
 b=f'''<div class=wrap><aside class=side><div class=brand>LASTRO<small>CENTRAL DA FAMÍLIA</small></div><nav class=nav>{nav}</nav><a class=out href=/logout>Sair</a></aside><main class=main><div class=top><div><div class=title>{title}</div><div class=muted>Central administrativa • {user()["name"]}</div></div><span class=pill>GERÊNCIA</span></div>{''.join('<div class=flash>'+m+'</div>' for m in __import__('flask').get_flashed_messages())}{body}</main></div>'''
 return render_template_string(BASE.replace('{{BODY|safe}}',b))
def members(c): return c.execute('select * from members order by name').fetchall()

@app.get('/health')
def health(): return {'ok':True,'service':'lastro'}
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  u=conn().execute('select * from users where username=? and active=1',(request.form['username'].strip(),)).fetchone()
  if u and check_password_hash(u['password'],request.form['password']): session['uid']=u['id']; return redirect('/')
  flash('Usuário ou senha inválidos.')
 return render_template_string(BASE.replace('{{BODY|safe}}','<div class=login><div class=box><h1>LASTRO</h1><p>Central privada da família</p><form class=form method=post><input name=username placeholder=Usuário required><input type=password name=password placeholder=Senha required><button>Entrar</button></form></div></div>'))
@app.get('/logout')
def logout(): session.clear(); return redirect('/login')
@app.get('/')
def home():
 if (g:=guard()):return g
 c=conn(); vals=[c.execute('select coalesce(sum(qty),0)n from farms').fetchone()['n'],c.execute('select coalesce(sum(produced),0)n from productions').fetchone()['n'],c.execute('select coalesce(sum(a.payout),0)n from actions a join action_logs l on l.action_id=a.id').fetchone()['n'],c.execute('select count(*)n from members').fetchone()['n']]
 cards=''.join(f'<div class=card><div class=muted>{x}</div><div class=kpi>{v:g}</div></div>' for x,v in zip(['FARM ENTREGUE','PRODUÇÃO','DINHEIRO EM AÇÕES','MEMBROS'],vals))
 return page('Painel',f'<div class=grid>{cards}</div><div class="card" style="margin-top:14px"><b>LASTRO — controle interno</b><p class=muted>Registros de farm, produção, baú, ações, ranking e hierarquia, todos vinculados ao responsável e à prova.</p></div>','home')

def formpage(route,title,key,fields,insert,rows,headers,vals):
 if (g:=guard()):return g
 c=conn(); ms=members(c)
 if request.method=='POST':
  p=proof(); data=insert(p); c.execute(data[0],data[1]); c.commit(); flash(data[2]); return redirect(route)
 opts=''.join(f'<option value={m["id"]}>{m["name"]}</option>' for m in ms)
 return page(title,f'<div class=card><form class=cols method=post enctype=multipart/form-data>{fields.replace("__MEMBERS__",opts)}<button>Registrar</button></form></div><div class="card" style="margin-top:14px"><table class=table><tr>'+''.join(f'<th>{h}</th>' for h in headers)+'</tr>'+rows(c)+'</table></div>',key)
@app.route('/farm',methods=['GET','POST'])
def farm():
 return formpage('/farm','Farm','farm','<div><label>Quem deu o farm</label><select name=member_id required>__MEMBERS__</select></div><div><label>Quantidade</label><input type=number step=.01 name=qty required></div><div><label>Prova</label><input type=file name=proof accept="image/*"></div>',lambda p:('insert into farms(member_id,qty,proof,created) values(?,?,?,?)',(request.form['member_id'],float(request.form['qty']),p,datetime.now().isoformat(timespec='seconds')),'Farm registrado.'),lambda c:''.join(f'<tr><td>{r["name"]}</td><td>{r["qty"]:g}</td><td>{("<a class=btn href=/uploads/"+r["proof"]+">Abrir</a>") if r["proof"] else "-"}</td><td>{r["created"]}</td></tr>' for r in c.execute('select f.*,m.name from farms f left join members m on m.id=f.member_id order by f.id desc limit 50')),['Pessoa','Quantidade','Prova','Data'],None)
@app.route('/producao',methods=['GET','POST'])
def producao():
 return formpage('/producao','Produção','prod','<div><label>Responsável</label><select name=member_id required>__MEMBERS__</select></div><div><label>Quanto produziu</label><input type=number step=.01 name=produced required></div><div><label>Quanto produto usou</label><input type=number step=.01 name=used required></div><div><label>Motivo</label><select name=reason><option>Uso</option><option>Venda</option><option>Estoque</option><option>Outro</option></select></div><div><label>Prova</label><input type=file name=proof accept="image/*"></div>',lambda p:('insert into productions(member_id,produced,used,reason,proof,created) values(?,?,?,?,?,?)',(request.form['member_id'],float(request.form['produced']),float(request.form['used']),request.form['reason'],p,datetime.now().isoformat(timespec='seconds')),'Produção registrada.'),lambda c:''.join(f'<tr><td>{r["name"]}</td><td>{r["produced"]:g}</td><td>{r["used"]:g}</td><td>{r["reason"]}</td><td>{("<a class=btn href=/uploads/"+r["proof"]+">Abrir</a>") if r["proof"] else "-"}</td></tr>' for r in c.execute('select p.*,m.name from productions p left join members m on m.id=p.member_id order by p.id desc limit 50')),['Pessoa','Produziu','Usou','Motivo','Prova'],None)
@app.route('/bau',methods=['GET','POST'])
def bau():
 return formpage('/bau','Baú','bau','<div><label>Quem pegou</label><select name=member_id required>__MEMBERS__</select></div><div><label>O que pegou</label><input name=item required></div><div><label>Motivo</label><input name=reason required></div><div><label>Prova</label><input type=file name=proof accept="image/*"></div>',lambda p:('insert into chests(member_id,item,proof,reason,created) values(?,?,?,?,?)',(request.form['member_id'],request.form['item'],p,request.form['reason'],datetime.now().isoformat(timespec='seconds')),'Baú registrado.'),lambda c:''.join(f'<tr><td>{r["name"]}</td><td>{r["item"]}</td><td>{r["reason"]}</td><td>{("<a class=btn href=/uploads/"+r["proof"]+">Abrir</a>") if r["proof"] else "-"}</td></tr>' for r in c.execute('select b.*,m.name from chests b left join members m on m.id=b.member_id order by b.id desc limit 50')),['Pessoa','Item','Motivo','Prova'],None)
@app.route('/acoes',methods=['GET','POST'])
def acoes():
 if (g:=guard()):return g
 c=conn(); ms=members(c); acts=c.execute('select * from actions order by name').fetchall()
 if request.method=='POST':
  if request.form['kind']=='new': c.execute('insert into actions(name,payout,notes) values(?,?,?)',(request.form['name'],float(request.form['payout']),request.form['notes'])); c.commit(); flash('Ação criada.'); return redirect('/acoes')
  p=proof(); c.execute('insert into action_logs(action_id,member_id,proof,created) values(?,?,?,?)',(request.form['action_id'],request.form['member_id'],p,datetime.now().isoformat(timespec='seconds'))); c.commit(); flash('Participação registrada.'); return redirect('/acoes')
 oa=''.join(f'<option value={a["id"]}>{a["name"]} — R$ {a["payout"]:.2f}</option>' for a in acts); om=''.join(f'<option value={m["id"]}>{m["name"]}</option>' for m in ms)
 rows=''.join(f'<tr><td>{r["action"]}</td><td>{r["name"]}</td><td>R$ {r["payout"]:.2f}</td><td><a class=btn href=/uploads/{r["proof"]}>Abrir</a></td></tr>' for r in c.execute('select l.*,a.name action,a.payout,m.name from action_logs l join actions a on a.id=l.action_id left join members m on m.id=l.member_id order by l.id desc limit 50'))
 body=f'<div class=cols><div class=card><h3>Nova ação</h3><form class=form method=post><input type=hidden name=kind value=new><input name=name placeholder="Nome da ação" required><input type=number step=.01 name=payout placeholder="Valor fixo por participante" required><textarea name=notes placeholder=Observações></textarea><button>Criar ação</button></form></div><div class=card><h3>Registrar participação</h3><form class=form method=post enctype=multipart/form-data><input type=hidden name=kind value=log><select name=action_id required>{oa}</select><select name=member_id required>{om}</select><input type=file name=proof accept="image/*" required><button>Registrar</button></form></div></div><div class=card style="margin-top:14px"><table class=table><tr><th>Ação</th><th>Pessoa</th><th>Valor</th><th>Prova</th></tr>{rows}</table></div>'
 return page('Ações',body,'acoes')
@app.get('/ranking')
def ranking():
 if (g:=guard()):return g
 c=conn(); f=c.execute('select m.name,coalesce(sum(f.qty),0)total from members m left join farms f on f.member_id=m.id group by m.id order by total desc').fetchall(); a=c.execute('select m.name,count(l.id)total from members m left join action_logs l on l.member_id=m.id group by m.id order by total desc').fetchall()
 def box(t,rs,s): return '<div class=card><h3>'+t+'</h3>'+''.join(f'<div class=rank><b>#{i+1} {r["name"]}</b><span class=pill>{r["total"]:g}{s}</span></div>' for i,r in enumerate(rs))+'</div>'
 return page('Ranking','<div class=cols>'+box('Maior entrega de farm',f,' farm')+box('Mais ações',a,' ações')+'</div>','rank')
@app.route('/hierarquia',methods=['GET','POST'])
def hierarquia():
 if (g:=guard()):return g
 c=conn()
 if request.method=='POST': c.execute('insert into members(name,role,notes,results) values(?,?,?,?)',(request.form['name'],request.form['role'],request.form['notes'],request.form['results'])); c.commit(); flash('Membro adicionado.'); return redirect('/hierarquia')
 rows=''.join(f'<tr><td>{r["name"]}</td><td><span class=pill>{r["role"]}</span></td><td>{r["notes"] or "-"}</td><td>{r["results"] or "-"}</td></tr>' for r in members(c))
 return page('Hierarquia',f'<div class=card><form class=cols method=post><input name=name placeholder="Nome" required><input name=role placeholder="Cargo" required><textarea name=notes placeholder=Notas></textarea><textarea name=results placeholder="O que rendeu para farm ou ação"></textarea><button>Adicionar membro</button></form></div><div class=card style="margin-top:14px"><table class=table><tr><th>Membro</th><th>Cargo</th><th>Notas</th><th>Rendimento</th></tr>{rows}</table></div>','hier')
@app.route('/usuarios',methods=['GET','POST'])
def usuarios():
 if (g:=guard()):return g
 c=conn()
 if request.method=='POST': c.execute('insert into users(username,password,name,role) values(?,?,?,?)',(request.form['username'],generate_password_hash(request.form['password']),request.form['name'],request.form['role'])); c.commit(); flash('Usuário criado.'); return redirect('/usuarios')
 rows=''.join(f'<tr><td>{r["name"]}</td><td>{r["username"]}</td><td>{r["role"]}</td></tr>' for r in c.execute('select name,username,role from users'))
 return page('Usuários',f'<div class=card><form class=cols method=post><input name=name placeholder=Nome required><input name=username placeholder="Usuário único" required><input type=password name=password placeholder="Senha única" required><input name=role value="Gerência" required><button>Criar acesso</button></form></div><div class=card style="margin-top:14px"><table class=table><tr><th>Nome</th><th>Usuário</th><th>Perfil</th></tr>{rows}</table></div>','users')
@app.get('/uploads/<path:name>')
def uploads(name):
 if (g:=guard()):return g
 return send_from_directory(UP,name)
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')))