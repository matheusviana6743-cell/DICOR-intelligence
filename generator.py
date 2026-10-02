import io, json, re, zipfile
from datetime import datetime


def slug(value):
    value = re.sub(r'[^a-zA-Z0-9_-]+', '-', str(value or '').strip()).strip('-').lower()
    return value or 'bot-forge-project'

def text(value):
    if isinstance(value, list): return ', '.join(map(str, value))
    return str(value or '')

def js_string(value): return json.dumps(str(value or ''), ensure_ascii=False)
def lua_string(value): return json.dumps(str(value or ''), ensure_ascii=False)
def lua_list(values):
    values = values if isinstance(values, list) else [values] if values else []
    return '{' + ', '.join(lua_string(v) for v in values) + '}'

def make_readme(order, config, product_name):
    lines=[f'# {product_name} — BOT FORGE','',f'Pedido: `{order["id"]}`',f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}','','## Configuração']
    for key,value in config.items():
        if not key.startswith('_') and value: lines.append(f'- **{key.replace("_"," ").title()}:** {text(value)}')
    lines += ['','## Instalação','Consulte os arquivos de configuração e o README específico do produto.','','## Segurança','Tokens, senhas e credenciais não são incluídos automaticamente.']
    return '\n'.join(lines)+'\n'

def discord_files(order, config):
    name=config.get('bot_name') or 'BOT FORGE Bot'; prefix=config.get('prefix') or '!'
    moderation=config.get('moderation') or []; tickets=config.get('tickets') or []; economy=config.get('economy') or []; automation=config.get('automation') or []; logs=config.get('logs') or []
    package={'name':slug(name),'version':'1.0.0','private':True,'main':'src/index.js','scripts':{'start':'node src/index.js'},'dependencies':{'discord.js':'^14.16.3','dotenv':'^16.4.5'}}
    commands=['ping','ajuda']
    if 'Ban' in moderation: commands.append('ban')
    if 'Kick' in moderation: commands.append('kick')
    if 'Mute' in moderation: commands.append('mute')
    if 'Criar ticket' in tickets: commands.append('ticket')
    if 'Fechamento automático' in tickets: commands.append('fecharticket')
    if 'Saldo' in economy: commands.append('saldo')
    if 'Loja' in economy: commands.append('loja')
    if 'Ranking' in economy: commands.append('ranking')
    if 'AutoRole' in automation: commands.append('autorole')
    if 'Verificação' in automation: commands.append('verificar')
    cases=[]
    for cmd in commands:
        response={'ping':'Pong! BOT FORGE está online.','ajuda':'Comandos: '+', '.join(prefix+c for c in commands),'ban':'Uso: '+prefix+'ban @usuario motivo','kick':'Uso: '+prefix+'kick @usuario motivo','mute':'Uso: '+prefix+'mute @usuario','ticket':'Ticket solicitado.','fecharticket':'Ticket fechado.','saldo':'Saldo de teste: 0 moedas.','loja':'Loja ativa. Configure config/shop.json.','ranking':'Ranking ativo.','autorole':'AutoRole configurado como base.','verificar':'Verificação configurada como base.'}.get(cmd,'Comando ativo.')
        cases.append(f"  if (message.content === PREFIX + {json.dumps(cmd)}) return message.reply({js_string(response)});")
    intents=['GatewayIntentBits.Guilds','GatewayIntentBits.GuildMessages','GatewayIntentBits.MessageContent']
    if any(x in logs for x in ['Entradas/Saídas','Auditoria']): intents.append('GatewayIntentBits.GuildMembers')
    js="""const { Client, GatewayIntentBits } = require('discord.js');\nrequire('dotenv').config();\nconst fs=require('fs');\nconst PREFIX=process.env.PREFIX || '!';\nconst features=JSON.parse(fs.readFileSync('./config/features.json','utf8'));\nconst client=new Client({intents:[%s]});\nclient.once('ready',()=>console.log(`✓ ${client.user.tag} online`));\nclient.on('messageCreate',async message=>{\n if(message.author.bot || !message.guild)return;\n%s\n});\nclient.login(process.env.DISCORD_TOKEN);\n""" % (','.join(intents),'\n'.join(cases))
    features={'tickets':tickets,'moderation':moderation,'logs':logs,'automation':automation,'economy':economy,'permissions':config.get('permissions') or '','language':config.get('language') or 'Português'}
    return {'package.json':json.dumps(package,indent=2,ensure_ascii=False),'.env.example':f'DISCORD_TOKEN=COLOQUE_SEU_TOKEN_AQUI\nPREFIX={prefix}\n','src/index.js':js,'config/features.json':json.dumps(features,indent=2,ensure_ascii=False)+'\n','config/shop.json':json.dumps({'items':[]},indent=2,ensure_ascii=False)+'\n','README.md':make_readme(order,config,name)}

def fivem_files(order, config):
    framework=config.get('framework') or 'Standalone'; system=config.get('system_type') or 'Sistema'; nui=config.get('nui') or []
    cfg={'framework':framework,'version':config.get('version') or '','system_type':system,'jobs':text(config.get('jobs')),'commands':text(config.get('commands')),'permissions':text(config.get('permissions')),'database':config.get('database') or 'Não','discord_logs':config.get('discord_logs') or [],'optimization':config.get('optimization') or 'Padrão','dependencies':config.get('dependencies') or ''}
    fx="fx_version 'cerulean'\ngame 'gta5'\nauthor 'BOT FORGE'\ndescription 'Sistema FiveM gerado pelo BOT FORGE'\nversion '1.0.0'\nshared_script 'config.lua'\nclient_script 'client.lua'\nserver_script 'server.lua'\n"
    if nui: fx+="ui_page 'web/index.html'\nfiles { 'web/index.html', 'web/app.js', 'web/style.css' }\n"
    adapter={'QBCore':"local QBCore = exports['qb-core']:GetCoreObject()\n",'ESX':"local ESX = exports['es_extended']:getSharedObject()\n",'Standalone':''}.get(framework,'')
    client=adapter+"RegisterCommand('botforge',function() TriggerEvent('chat:addMessage',{args={'BOT FORGE','Sistema carregado.'}}) end,false)\n"
    server=adapter+"RegisterCommand('botforgeinfo',function(source) TriggerClientEvent('chat:addMessage',source,{args={'BOT FORGE','Sistema: %s | Framework: %s'}}) end,false)\n"%(system,framework)
    lua='Config = {\n'+''.join(f'    {k} = '+(lua_list(v) if isinstance(v,list) else lua_string(v))+',\n' for k,v in cfg.items())+'}\n'
    files={'fxmanifest.lua':fx,'client.lua':client,'server.lua':server,'config.lua':lua,'config.json':json.dumps(cfg,indent=2,ensure_ascii=False)+'\n','README.md':make_readme(order,config,system)}
    if nui:
        files['web/index.html']=f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{system}</title><link rel='stylesheet' href='style.css'></head><body><main><button id='close'>×</button><h1>{system}</h1><p>Sistema conectado ao FiveM.</p><button id='test'>Testar</button></main><script src='app.js'></script></body></html>"
        files['web/app.js']="document.getElementById('close').onclick=()=>fetch(`https://${GetParentResourceName()}/close`,{method:'POST'});document.getElementById('test').onclick=()=>fetch(`https://${GetParentResourceName()}/test`,{method:'POST'});"
        files['web/style.css']='body{display:grid;place-items:center;height:100vh;background:transparent;font-family:Arial}main{background:#fff;padding:30px;border-radius:18px;min-width:360px;box-shadow:0 20px 60px #0005}button{padding:12px 18px;border:0;border-radius:10px;background:#222;color:#fff;cursor:pointer}'
    return files

def site_files(order, config):
    title=config.get('brand') or 'Meu Projeto'; objective=config.get('objective') or 'Site gerado pelo BOT FORGE.'
    pages=[p.strip() for p in re.split(r'[,;\n]+',text(config.get('pages'))) if p.strip()] or ['Início','Sobre','Contato']
    sections=[p.strip() for p in re.split(r'[,;\n]+',text(config.get('sections'))) if p.strip()] or ['Apresentação','Recursos','FAQ']
    forms=config.get('forms') or []; seo=config.get('seo')=='Incluir'
    nav=''.join(f'<a href="#{slug(p)}">{p}</a>' for p in pages)
    page_sections=''.join(f'<section id="{slug(p)}"><span>BOT FORGE</span><h2>{p}</h2><p>{objective if p==pages[0] else "Seção configurada para o projeto."}</p><div class="cards">'+''.join(f'<article><b>{s}</b><p>Conteúdo configurado para esta seção.</p></article>' for s in sections)+'</div></section>' for p in pages)
    form_html="" if not forms else "<section id='contato'><span>CONTATO</span><h2>Fale conosco</h2><form id='contact-form'><input name='name' placeholder='Nome' required><input name='email' type='email' placeholder='E-mail' required><textarea name='message' placeholder='Mensagem' required></textarea><button>Enviar</button><p id='form-result'></p></form></section>"
    meta=f'<meta name="description" content="{objective[:150]}">' if seo else ''
    html=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{title}</title><link rel="stylesheet" href="style.css"></head><body><header><b>{title}</b><nav>{nav}</nav></header><main><section class="hero"><span>BOT FORGE</span><h1>{title}</h1><p>{objective}</p></section>{page_sections}{form_html}<footer>Gerado pelo BOT FORGE</footer></main><script src="app.js"></script></body></html>'''
    js="const form=document.getElementById('contact-form');if(form)form.addEventListener('submit',e=>{e.preventDefault();document.getElementById('form-result').textContent='Formulário validado. Configure um endpoint para produção.';form.reset()});"
    css='*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#fafafa;color:#172033}header{position:sticky;top:0;padding:18px 7%;display:flex;justify-content:space-between;background:#ffffffeF;border-bottom:1px solid #e8ebef}nav{display:flex;gap:18px;flex-wrap:wrap}nav a{color:#344054;text-decoration:none}main{padding:0 7%}section{min-height:55vh;padding:70px 0;border-bottom:1px solid #e9ecf1}.hero{display:flex;flex-direction:column;justify-content:center;min-height:70vh}span{letter-spacing:.16em;font-weight:800;color:#697386}h1{font-size:clamp(44px,7vw,86px);line-height:1.02}h2{font-size:42px}p{font-size:19px;line-height:1.65;color:#667085}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}article{background:#fff;border:1px solid #e7eaf0;border-radius:20px;padding:26px}form{max-width:650px;display:grid;gap:12px}input,textarea{padding:14px;border:1px solid #dfe3ea;border-radius:12px;font:inherit}textarea{min-height:130px}button{padding:13px 20px;border:0;border-radius:12px;background:#26354a;color:#fff;font-weight:800}@media(max-width:800px){.cards{grid-template-columns:1fr}header{display:block}nav{margin-top:12px}}'
    return {'index.html':html,'style.css':css,'app.js':js,'README.md':make_readme(order,config,title)}

def custom_files(order,config):
    spec={'order_id':order['id'],'objective':config.get('objective',''),'platform':config.get('platform',''),'features':config.get('features',''),'integrations':config.get('integrations',''),'references':config.get('references',''),'style':config.get('style',''),'source_code':config.get('source_code',''),'notes':config.get('notes','')}
    return {'README.md':make_readme(order,config,'Projeto personalizado'),'project-spec.json':json.dumps(spec,indent=2,ensure_ascii=False)+'\n','NEXT-STEPS.md':'# Próximos passos\n\n1. Revisar o briefing.\n2. Validar integrações e dependências.\n3. Implementar e testar as funcionalidades específicas.\n'}

def build_project(order):
    config=order['config'] if isinstance(order.get('config'),dict) else json.loads(order.get('config_json','{}'))
    product=order.get('product')
    if product=='discord': files=discord_files(order,config); name='Discord'
    elif product=='fivem': files=fivem_files(order,config); name='FiveM'
    elif product=='site': files=site_files(order,config); name='Site'
    else: files=custom_files(order,config); name='Personalizado'
    if 'README.md' not in files: files['README.md']=make_readme(order,config,name)
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w',zipfile.ZIP_DEFLATED) as z:
        for path,content in files.items(): z.writestr(path,content)
    mem.seek(0)
    return mem,files
