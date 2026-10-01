import os, json, secrets, sqlite3, datetime as dt, io, zipfile
from pathlib import Path
from functools import wraps
from urllib.parse import quote
import requests
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort, send_from_directory, send_file

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv('BOT_FORGE_DATA_DIR', '/data' if Path('/data').exists() else str(BASE_DIR / 'data')))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'bot_forge.sqlite3'

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024
CONTACT_WA = '5571996936743'
CONTACT_EMAIL = 'matheusviana6743@gmail.com'
ASAAS_KEY = os.getenv('ASAAS_API_KEY', '').strip()
ASAAS_BASE = os.getenv('ASAAS_API_BASE', 'https://api-sandbox.asaas.com/v3').rstrip('/')
ASAAS_WEBHOOK_TOKEN = os.getenv('ASAAS_WEBHOOK_TOKEN', '').strip()
PUBLIC_URL = os.getenv('PUBLIC_URL', '').rstrip('/')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '').strip()
TEST_MODE = os.getenv('TEST_MODE', '1').strip() != '0'

PRODUCTS = {
    'discord': {'name': 'Bot Discord', 'price': 0.0, 'type': 'fixed'},
    'fivem': {'name': 'Sistema FiveM', 'price': 0.0, 'type': 'fixed'},
    'site': {'name': 'Site / Web', 'price': 0.0, 'type': 'fixed'},
    'personalizado': {'name': 'Projeto personalizado', 'min': 0.0, 'max': 0.0, 'type': 'quote'},
}

CONFIGS = {
'discord': [
('Objetivo','objective','textarea',True,'Explique em poucas palavras o que o bot precisa fazer.'),('Nome do bot','bot_name','text',False,'Ex.: Forge Tickets'),('Nome do servidor','server_name','text',False,'Opcional'),('Tipo','bot_type','select',False,['Tickets','Moderação','Economia','Atendimento','Whitelist','Vendas','Personalizado']),('Tickets','tickets','multi',False,['Criar ticket','Categorias','Transcrição','Fechamento automático']),('Moderação','moderation','multi',False,['Ban','Kick','Mute','Anti-spam','Filtros']),('Logs','logs','multi',False,['Mensagens','Entradas/Saídas','Moderação','Tickets','Auditoria']),('Automação','automation','multi',False,['AutoRole','Boas-vindas','Verificação','Cargos por reação']),('Economia','economy','multi',False,['Saldo','Loja','Ranking','XP']),('Interface','ui','multi',False,['Embeds','Botões','Menus','Slash Commands']),('Integrações','integrations','multi',False,['Webhooks','Painel Web','APIs','Banco de dados']),('Permissões','permissions','textarea',False,'Quais cargos podem usar cada área?'),('Idioma','language','select',False,['Português','Português + Inglês','Outro']),('Cor/estilo','style','text',False,'Opcional'),('Hospedagem','hosting','select',False,['Já tenho','Quero orientação','Quero hospedagem']),('Código-fonte','source_code','select',False,['Incluir','Não incluir']),('Observações','notes','textarea',False,'Qualquer detalhe adicional.')],
'fivem': [
('Objetivo','objective','textarea',True,'Explique em poucas palavras o que o sistema precisa fazer.'),('Framework','framework','select',False,['QBCore','ESX','Standalone','Outro']),('Versão','version','text',False,'Ex.: versão atual do seu servidor'),('Tipo de sistema','system_type','select',False,['Emprego','Administrativo','Economia','UI/NUI','Interação','Personalizado']),('Jobs','jobs','textarea',False,'Ex.: Polícia, EMS, Mecânico'),('Comandos','commands','textarea',False,'Liste comandos desejados.'),('Permissões','permissions','textarea',False,'Grupos/cargos que terão acesso.'),('UI / NUI','nui','multi',False,['Menu','Dashboard','Notificações','Formulários']),('Banco de dados','database','select',False,['Não','MySQL','Outro']),('Discord','discord_logs','multi',False,['Logs','Webhooks','Comandos integrados']),('Integrações','integrations','textarea',False,'Scripts, APIs ou recursos que precisam conversar com o sistema.'),('Dependências','dependencies','textarea',False,'Opcional'),('Visual','visual','text',False,'Cores, estilo, identidade.'),('Otimização','optimization','select',False,['Padrão','Priorizar performance']),('Documentação','documentation','select',False,['Incluir','Não incluir']),('Código-fonte','source_code','select',False,['Incluir','Não incluir']),('Observações','notes','textarea',False,'Qualquer detalhe adicional.')],
'site': [
('Objetivo','objective','textarea',True,'Explique o objetivo do site.'),('Tipo','site_type','select',False,['Landing page','Loja','Portfólio','Site para servidor','Dashboard','Sistema Web','Personalizado']),('Nome / marca','brand','text',False,'Opcional'),('Páginas','pages','textarea',False,'Ex.: Início, Sobre, Contato'),('Seções','sections','textarea',False,'Ex.: Hero, preços, FAQ, depoimentos'),('Formulário','forms','multi',False,['Contato','Orçamento','Cadastro','Login']),('Integrações','integrations','multi',False,['WhatsApp','Instagram','Discord','APIs']),('Área do cliente','client_area','select',False,['Não','Sim']),('Painel administrativo','admin_panel','select',False,['Não','Sim']),('Banco de dados','database','select',False,['Não','SQLite','PostgreSQL','Outro']),('Responsividade','responsive','select',False,['Celular + PC','PC apenas']),('Cores','colors','text',False,'Ex.: claro + dourado'),('Estilo','style','text',False,'Ex.: moderno, minimalista'),('Animações','animations','select',False,['Discretas','Sem animações','Mais dinâmicas']),('SEO básico','seo','select',False,['Incluir','Não incluir']),('Domínio / hospedagem','hosting','select',False,['Já tenho','Quero orientação','Quero publicação']),('Código-fonte','source_code','select',False,['Incluir','Não incluir']),('Observações','notes','textarea',False,'Qualquer detalhe adicional.')],
'personalizado': [
('O que você quer criar?','objective','textarea',True,'Descreva a ideia do projeto.'),('Plataforma','platform','select',False,['Discord','FiveM','Web / Site','Discord + FiveM','Outro']),('Funcionalidades','features','textarea',False,'Liste tudo o que lembrar.'),('Integrações','integrations','textarea',False,'APIs, Discord, banco de dados, pagamentos etc.'),('Referências','references','textarea',False,'Links ou exemplos de algo parecido.'),('Preferências visuais','style','textarea',False,'Cores, estilo e identidade.'),('Código-fonte','source_code','select',False,['Incluir','Não sei ainda']),('Observações','notes','textarea',False,'Detalhes adicionais.')]
}

def db():
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; con.execute('PRAGMA journal_mode=WAL'); return con

def init_db():
    con=db(); con.executescript('''CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,token TEXT UNIQUE NOT NULL,product TEXT NOT NULL,config_json TEXT NOT NULL,customer_name TEXT,customer_email TEXT,customer_phone TEXT,price REAL,price_min REAL,price_max REAL,status TEXT NOT NULL,payment_status TEXT NOT NULL,asaas_customer_id TEXT,asaas_payment_id TEXT,payment_url TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS webhook_events(id TEXT PRIMARY KEY,event TEXT,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS demos(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,product TEXT NOT NULL,url TEXT NOT NULL,description TEXT DEFAULT '',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);'''); con.commit(); con.close()
init_db()

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def safe_json(v):
    try: return json.loads(v)
    except Exception: return {}
def normalize_phone(p): return ''.join(c for c in (p or '') if c.isdigit())
def whatsapp_link(msg): return f'https://wa.me/{CONTACT_WA}?text={quote(msg)}'
def require_admin(view):
    @wraps(view)
    def wrapped(*a,**kw):
        if not ADMIN_PASSWORD or not session.get('admin'): return redirect(url_for('admin_login'))
        return view(*a,**kw)
    return wrapped

def _get_order(order_id):
    con=db(); row=con.execute('SELECT * FROM orders WHERE id=?',(order_id,)).fetchone(); con.close(); return row

def _get_token(order_id):
    row=_get_order(order_id); return row['token'] if row else ''

def calc_price(product):
    p=PRODUCTS[product]; return (p['price'],None,None) if p['type']=='fixed' else (None,p['min'],p['max'])

def sync_test_status(row):
    if not TEST_MODE or row['status'] in ('Entregue','Cancelado'): return row['status']
    try: start=dt.datetime.fromisoformat(row['updated_at']); elapsed=(dt.datetime.now(dt.timezone.utc)-start).total_seconds()
    except Exception: elapsed=0
    if row['payment_status']=='Não necessário':
        target='Em preparação' if elapsed < 5 else ('Em desenvolvimento' if elapsed < 15 else 'Entregue')
        if target != row['status']:
            con=db(); con.execute("UPDATE orders SET status=?,updated_at=? WHERE id=?",(target,now(),row['id'])); con.commit(); con.close()
        return target
    return row['status']

@app.context_processor
def globals_ctx(): return {'products':PRODUCTS,'contact_wa':CONTACT_WA,'contact_email':CONTACT_EMAIL,'public_url':PUBLIC_URL,'test_mode':TEST_MODE}

@app.get('/')
def index():
    con=db(); demos=con.execute('SELECT * FROM demos WHERE active=1 ORDER BY id DESC').fetchall(); con.close(); return render_template('index.html',demos=demos)

@app.get('/config/<product>')
def configurator(product):
    if product not in PRODUCTS: abort(404)
    return render_template('configurator.html',product=product,product_info=PRODUCTS[product],fields=CONFIGS[product])

@app.post('/api/orders')
def create_order():
    data=request.get_json(silent=True) or request.form.to_dict(flat=False); product=data.get('product'); product=product[0] if isinstance(product,list) and product else product
    if product not in PRODUCTS: return jsonify({'error':'Produto inválido.'}),400
    config=data.get('config',{}); config=safe_json(config) if isinstance(config,str) else config
    if not str(config.get('objective','')).strip(): return jsonify({'error':'O objetivo do projeto é obrigatório.'}),400
    oid=f"BF-{dt.datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"; token=secrets.token_urlsafe(24); price,pmin,pmax=calc_price(product); ts=now()
    con=db(); con.execute('INSERT INTO orders(id,token,product,config_json,price,price_min,price_max,status,payment_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(oid,token,product,json.dumps(config,ensure_ascii=False),price,pmin,pmax,'Aguardando dados','Pendente',ts,ts)); con.commit(); con.close()
    return jsonify({'ok':True,'id':oid,'token':token,'redirect':url_for('checkout',token=token)})

@app.route('/checkout/<token>',methods=['GET','POST'])
def checkout(token):
    con=db(); row=con.execute('SELECT * FROM orders WHERE token=?',(token,)).fetchone(); con.close()
    if not row: abort(404)
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip(); phone=normalize_phone(request.form.get('phone',''))
        if not name or not email or not phone: return render_template('checkout.html',order=row,error='Preencha nome, e-mail e WhatsApp.')
        if TEST_MODE:
            con=db(); con.execute("UPDATE orders SET customer_name=?,customer_email=?,customer_phone=?,status=?,payment_status=?,updated_at=? WHERE id=?",(name,email,phone,'Em preparação','Não necessário',now(),row['id'])); con.commit(); con.close()
            return redirect(url_for('order_page',token=token))
        con=db(); con.execute("UPDATE orders SET customer_name=?,customer_email=?,customer_phone=?,status=?,updated_at=? WHERE id=?",(name,email,phone,'Aguardando pagamento',now(),row['id'])); con.commit(); con.close()
        return render_template('checkout.html',order=_get_order(row['id']),payment_unavailable=True,error='Pagamento online ainda não conectado.')
    return render_template('checkout.html',order=row)

@app.get('/order/<token>')
def order_page(token):
    con=db(); order=con.execute('SELECT * FROM orders WHERE token=?',(token,)).fetchone(); con.close()
    if not order: abort(404)
    sync_test_status(order); order=_get_order(order['id']); config=safe_json(order['config_json'])
    return render_template('order.html',order=order,config=config,wa=whatsapp_link(f"Olá! Quero falar sobre o pedido {order['id']} da BOT FORGE."))

@app.get('/api/orders/<token>/status')
def order_status(token):
    con=db(); order=con.execute('SELECT * FROM orders WHERE token=?',(token,)).fetchone(); con.close()
    if not order: return jsonify({'error':'Pedido não encontrado.'}),404
    status=sync_test_status(order); order=_get_order(order['id']); ready=status=='Entregue'
    return jsonify({'ok':True,'id':order['id'],'status':status,'payment_status':order['payment_status'],'ready':ready,'updated_at':order['updated_at']})

def generated_files(order):
    cfg=safe_json(order['config_json']); product=order['product']; files={}
    meta=json.dumps({'order_id':order['id'],'product':product,'config':cfg},ensure_ascii=False,indent=2)
    files['project.json']=meta
    if product=='discord':
        name=cfg.get('bot_name') or 'BOT FORGE Bot'; prefix=cfg.get('prefix') or '!';
        files['package.json']=json.dumps({'name':name.lower().replace(' ','-'),'version':'1.0.0','main':'src/index.js','scripts':{'start':'node src/index.js'},'dependencies':{'discord.js':'^14.0.0'}},indent=2)
        files['.env.example']='DISCORD_TOKEN=coloque_seu_token_aqui\nBOT_PREFIX='+prefix+'\n'
        files['src/index.js']=f"const {{ Client, GatewayIntentBits }} = require('discord.js');\nconst client = new Client({{ intents: Object.values(GatewayIntentBits) }});\nclient.once('ready', () => console.log('{name} online'));\nclient.login(process.env.DISCORD_TOKEN);\n"
        files['README.md']=f"# {name}\n\nProjeto de teste gerado pelo BOT FORGE.\n\nObjetivo: {cfg.get('objective','')}\nRecursos: {json.dumps({k:v for k,v in cfg.items() if k not in ['objective','bot_name']},ensure_ascii=False)}\n"
    elif product=='fivem':
        files['fxmanifest.lua']="fx_version 'cerulean'\ngame 'gta5'\nclient_script 'client.lua'\nserver_script 'server.lua'\n"
        files['client.lua']=f"RegisterCommand('botforge', function()\n  print('BOT FORGE • {cfg.get('system_type','Sistema')}')\nend)\n"
        files['server.lua']=f"print('BOT FORGE FiveM iniciado • Framework: {cfg.get('framework','Standalone')}')\n"
        files['README.md']=f"# Sistema FiveM\n\nObjetivo: {cfg.get('objective','')}\nFramework: {cfg.get('framework','')}\nTipo: {cfg.get('system_type','')}\n"
    elif product=='site':
        brand=cfg.get('brand') or 'BOT FORGE'; colors=cfg.get('colors') or 'claro + dourado'
        files['index.html']=f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{brand}</title><link rel='stylesheet' href='style.css'></head><body><main><span>BOT FORGE</span><h1>{brand}</h1><p>{cfg.get('objective','')}</p><h2>Estrutura</h2><p>{cfg.get('pages','Início')}</p></main></body></html>"
        files['style.css']=f"body{{margin:0;font-family:Arial,sans-serif;background:#faf8f2;color:#202020}}main{{max-width:900px;margin:12vh auto;padding:40px}}h1{{font-size:56px}}span{{font-weight:800}}/* Estilo escolhido: {colors} */"
        files['README.md']=f"# {brand}\nTipo: {cfg.get('site_type','Site')}\nPáginas: {cfg.get('pages','')}\nSeções: {cfg.get('sections','')}\n"
    else:
        files['README.md']=f"# Projeto personalizado\n\nObjetivo: {cfg.get('objective','')}\nPlataforma: {cfg.get('platform','')}\nFuncionalidades: {cfg.get('features','')}\nIntegrações: {cfg.get('integrations','')}\n"
        files['project-spec.json']=meta
    return files

@app.get('/generate/<token>')
def generate_project(token):
    con=db(); order=con.execute('SELECT * FROM orders WHERE token=?',(token,)).fetchone(); con.close()
    if not order: abort(404)
    status=sync_test_status(order)
    if status!='Entregue': return redirect(url_for('order_page',token=token))
    files=generated_files(order); mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in files.items(): z.writestr(name,content)
    mem.seek(0); safe_name=order['product'].replace('/','-'); return send_file(mem,as_attachment=True,download_name=f"BOT-FORGE-{safe_name}-{order['id']}.zip",mimetype='application/zip')

@app.post('/webhooks/asaas')
def asaas_webhook(): return jsonify({'ok':True})

@app.get('/health')
def health(): return jsonify({'ok':True,'service':'BOT FORGE','test_mode':TEST_MODE})

@app.route('/admin/login',methods=['GET','POST'])
def admin_login():
    if request.method=='POST' and ADMIN_PASSWORD and secrets.compare_digest(request.form.get('password',''),ADMIN_PASSWORD): session['admin']=True; return redirect(url_for('admin'))
    return render_template('admin_login.html',error='Senha incorreta.' if request.method=='POST' else None)
@app.get('/admin/logout')
def admin_logout(): session.clear(); return redirect(url_for('admin_login'))
@app.get('/admin')
@require_admin
def admin():
    con=db(); orders=con.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT 100').fetchall(); demos=con.execute('SELECT * FROM demos ORDER BY id DESC').fetchall(); stats={'orders':len(orders),'paid':con.execute("SELECT COUNT(*) c FROM orders WHERE payment_status='Pago'").fetchone()['c'],'pending':con.execute("SELECT COUNT(*) c FROM orders WHERE payment_status IN ('Pendente','Aguardando')").fetchone()['c'],'revenue':0}; con.close(); return render_template('admin.html',stats=stats,orders=orders,customers=[],demos=demos,asaas_connected=bool(ASAAS_KEY))
@app.post('/admin/orders/<order_id>/status')
@require_admin
def admin_status(order_id):
    status=request.form.get('status',''); allowed={'Aguardando pagamento','Pago','Em preparação','Em desenvolvimento','Aguardando cliente','Entregue','Cancelado','Aguardando dados'}
    if status not in allowed: abort(400)
    con=db(); con.execute('UPDATE orders SET status=?,updated_at=? WHERE id=?',(status,now(),order_id)); con.commit(); con.close(); return redirect(url_for('admin'))
@app.post('/admin/demos/add')
@require_admin
def admin_demo_add():
    title=request.form.get('title','').strip(); product=request.form.get('product','').strip(); url=request.form.get('url','').strip(); desc=request.form.get('description','').strip()
    if title and product and url:
        con=db(); con.execute('INSERT INTO demos(title,product,url,description,created_at) VALUES(?,?,?,?,?)',(title,product,url,desc,now())); con.commit(); con.close()
    return redirect(url_for('admin'))
@app.post('/admin/demos/<int:demo_id>/delete')
@require_admin
def admin_demo_delete(demo_id):
    con=db(); con.execute('DELETE FROM demos WHERE id=?',(demo_id,)); con.commit(); con.close(); return redirect(url_for('admin'))
@app.post('/admin/orders/<order_id>/upload')
@require_admin
def admin_upload(order_id):
    f=request.files.get('file'); order=_get_order(order_id)
    if not f or not f.filename or not order: return redirect(url_for('admin'))
    stored=f"{order_id}_{secrets.token_hex(5)}{Path(f.filename).suffix[:10]}"; f.save(UPLOAD_DIR/stored); cfg=safe_json(order['config_json']); files=cfg.get('_delivery_files',[]); files.append({'name':f.filename,'stored':stored}); cfg['_delivery_files']=files
    con=db(); con.execute('UPDATE orders SET config_json=?,updated_at=? WHERE id=?',(json.dumps(cfg,ensure_ascii=False),now(),order_id)); con.commit(); con.close(); return redirect(url_for('admin'))
@app.get('/files/<token>/<stored>')
def public_file(token,stored):
    con=db(); row=con.execute('SELECT * FROM orders WHERE token=?',(token,)).fetchone(); con.close()
    if not row: abort(404)
    cfg=safe_json(row['config_json']);
    if not any(x.get('stored')==stored for x in cfg.get('_delivery_files',[])): abort(404)
    return send_from_directory(UPLOAD_DIR,stored,as_attachment=True)

if __name__=='__main__':
    port=int(os.getenv('PORT','8080')); app.run(host='0.0.0.0',port=port)
