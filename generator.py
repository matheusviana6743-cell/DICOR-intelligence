import io, json, re, zipfile
from datetime import datetime


def slug(value):
    value = re.sub(r'[^a-zA-Z0-9_-]+', '-', str(value or '').strip()).strip('-').lower()
    return value or 'bot-forge-project'


def text(value):
    if isinstance(value, list):
        return ', '.join(map(str, value))
    return str(value or '')


def js_string(value):
    return json.dumps(str(value or ''), ensure_ascii=False)


def lua_string(value):
    return json.dumps(str(value or ''), ensure_ascii=False)


def lua_list(values):
    values = values if isinstance(values, list) else [values] if values else []
    return '{' + ', '.join(lua_string(v) for v in values) + '}'


def make_readme(order, config, product_name):
    lines = [f'# {product_name} — BOT FORGE', '', f'Pedido: `{order["id"]}`', f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}', '', '## Configuração']
    for key, value in config.items():
        if key.startswith('_') or not value:
            continue
        lines.append(f'- **{key.replace("_", " ").title()}:** {text(value)}')
    lines += ['', '## Instalação', 'Consulte o README específico e os arquivos `.env.example`/`config.json` quando existirem.', '', '## Importante', 'Este pacote foi gerado automaticamente. Tokens, senhas e credenciais nunca são incluídos. Revise permissões e dependências antes de produção.']
    return '\n'.join(lines) + '\n'


def discord_files(order, config):
    name = config.get('bot_name') or 'BOT FORGE Bot'
    prefix = config.get('prefix') or '!'
    moderation = config.get('moderation') or []
    tickets = config.get('tickets') or []
    economy = config.get('economy') or []
    automation = config.get('automation') or []
    logs = config.get('logs') or []
    ui = config.get('ui') or []
    integrations = config.get('integrations') or []
    package = {'name': slug(name), 'version': '1.0.0', 'private': True, 'description': 'Bot Discord funcional gerado pelo BOT FORGE', 'main': 'src/index.js', 'scripts': {'start': 'node src/index.js'}, 'dependencies': {'discord.js': '^14.16.3', 'dotenv': '^16.4.5'}}
    commands = ['ping', 'ajuda']
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
    command_cases = []
    for cmd in commands:
        if cmd == 'ping': response = 'Pong! BOT FORGE está online.'
        elif cmd == 'ajuda': response = 'Comandos disponíveis: ' + ', '.join(prefix + c for c in commands)
        elif cmd == 'ban': response = 'Uso: ' + prefix + 'ban @usuario motivo'
        elif cmd == 'kick': response = 'Uso: ' + prefix + 'kick @usuario motivo'
        elif cmd == 'mute': response = 'Uso: ' + prefix + 'mute @usuario'
        elif cmd == 'ticket': response = 'Ticket solicitado. Configure a categoria no arquivo config/features.json.'
        elif cmd == 'fecharticket': response = 'Ticket fechado. Conecte esta ação ao canal de tickets.'
        elif cmd == 'saldo': response = 'Saldo de teste: 0 moedas. Conecte persistência para produção.'
        elif cmd == 'loja': response = 'Loja de teste ativa. Cadastre produtos em config/shop.json.'
        elif cmd == 'ranking': response = 'Ranking de teste ativo.'
        elif cmd == 'autorole': response = 'AutoRole ativo como base. Defina o cargo em config/features.json.'
        elif cmd == 'verificar': response = 'Sistema de verificação ativo como base.'
        else: response = f'Comando {cmd} ativo.'
        command_cases.append(f"  if (message.content === PREFIX + {json.dumps(cmd)}) return message.reply({js_string(response)});")
    intents = ['GatewayIntentBits.Guilds', 'GatewayIntentBits.GuildMessages', 'GatewayIntentBits.MessageContent']
    if 'Entradas/Saídas' in logs or 'Auditoria' in logs: intents.append('GatewayIntentBits.GuildMembers')
    js = """const { Client, GatewayIntentBits, Partials } = require('discord.js');
require('dotenv').config();
const fs = require('fs');
const PREFIX = process.env.PREFIX || '!';
const features = JSON.parse(fs.readFileSync('./config/features.json', 'utf8'));
const client = new Client({ intents: [%s], partials: [Partials.Channel] });
client.once('ready', () => console.log(`✓ ${client.user.tag} online`));
client.on('messageCreate', async (message) => {
  if (message.author.bot || !message.guild) return;
%s
});
client.on('guildMemberAdd', member => {
  if (features.automation.includes('Boas-vindas')) console.log(`Novo membro: ${member.user.tag}`);
});
process.on('unhandledRejection', console.error);
client.login(process.env.DISCORD_TOKEN);
""" % (', '.join(intents), '\n'.join(command_cases))
    features = {'tickets': tickets, 'moderation': moderation, 'logs': logs, 'automation': automation, 'economy': economy, 'ui': ui, 'integrations': integrations, 'permissions': config.get('permissions') or '', 'language': config.get('language') or 'Português'}
    return {'package.json': json.dumps(package, indent=2, ensure_ascii=False), '.env.example': f'DISCORD_TOKEN=COLOQUE_SEU_TOKEN_AQUI\nPREFIX={prefix}\n', 'src/index.js': js, 'config/features.json': json.dumps(features, indent=2, ensure_ascii=False) + '\n', 'config/shop.json': json.dumps({'items': []}, indent=2, ensure_ascii=False) + '\n', 'README.md': make_readme(order, config, name)}


def fivem_files(order, config):
    framework = config.get('framework') or 'Standalone'
    system_type = config.get('system_type') or 'Sistema'
    resource = slug(system_type)
    nui = config.get('nui') or []
    cfg = {'framework': framework, 'version': config.get('version') or '', 'system_type': system_type, 'jobs': text(config.get('jobs')), 'commands': text(config.get('commands')), 'permissions': text(config.get('permissions')), 'database': config.get('database') or 'Não', 'discord_logs': config.get('discord_logs') or [], 'optimization': config.get('optimization') or 'Padrão', 'dependencies': config.get('dependencies') or ''}
    fx = """fx_version 'cerulean'\ngame 'gta5'\nauthor 'BOT FORGE'\ndescription 'Sistema FiveM gerado pelo BOT FORGE'\nversion '1.0.0'\n\nshared_script 'config.lua'\nclient_script 'client.lua'\nserver_script 'server.lua'\n"""
    if nui: fx += "ui_page 'web/index.html'\nfiles { 'web/index.html', 'web/app.js', 'web/style.css' }\n"
    framework_adapter = {'QBCore': "local QBCore = exports['qb-core']:GetCoreObject()\n", 'ESX': "local ESX = exports['es_extended']:getSharedObject()\n", 'Standalone': '', 'Outro': ''}.get(framework, '')
    client = framework_adapter + """RegisterCommand('botforge', function()\n    TriggerEvent('chat:addMessage', { args = {'BOT FORGE', 'Sistema carregado com sucesso.'} })\n%s\nend, false)\n\nRegisterNetEvent('botforge:notify', function(message)\n    TriggerEvent('chat:addMessage', { args = {'BOT FORGE', tostring(message)} })\nend)\n""" % ("    SetNuiFocus(true, true)\n    SendNUIMessage({ action = 'open' })" if nui else '')
    server = framework_adapter + """RegisterCommand('botforgeinfo', function(source)\n    print(('[BOT FORGE] Pedido %s — %s — framework %s'):format('%s', '%s', '%s'))\nend, false)\n\nRegisterNetEvent('botforge:serverTest', function()\n    local src = source\n    TriggerClientEvent('botforge:notify', src, 'Cliente/servidor funcionando.')\nend)\n""" % (order['id'], system_type, framework)
    lua_cfg = 'Config = {\n' + '\n'.join([f'    {k} = ' + (lua_list(v) if isinstance(v, list) else lua_string(v)) + ',' for k, v in cfg.items()]) + '\n}\n'
    files = {'fxmanifest.lua': fx, 'client.lua': client, 'server.lua': server, 'config.lua': lua_cfg, 'config.json': json.dumps(cfg, indent=2, ensure_ascii=False) + '\n', 'README.md': make_readme(order, config, resource)}
    if nui:
        files['web/index.html'] = """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>BOT FORGE</title><link rel='stylesheet' href='style.css'></head><body><main><button id='close'>×</button><h1>%s</h1><p>Sistema conectado ao FiveM.</p><button id='test'>Testar</button></main><script src='app.js'></script></body></html>""" % system_type
        files['web/app.js'] = """window.addEventListener('message',e=>{if(e.data.action==='open')document.body.classList.add('open')});document.getElementById('close').onclick=()=>{fetch(`https://${GetParentResourceName()}/close`,{method:'POST'});document.body.classList.remove('open')};document.getElementById('test').onclick=()=>{fetch(`https://${GetParentResourceName()}/test`,{method:'POST'})};"""
        files['web/style.css'] = """body{display:none;margin:0;background:transparent;font-family:Arial}body.open{display:grid;place-items:center;height:100vh}main{background:#fff;padding:32px;border-radius:18px;min-width:360px;box-shadow:0 20px 60px #0005}button{padding:12px 18px;border:0;border-radius:10px;background:#222;color:#fff;cursor:pointer}#close{float:right;background:#eee;color:#222}"""
        files['client.lua'] += "\nRegisterNUICallback('close', function(_, cb) SetNuiFocus(false, false); cb('ok') end)\nRegisterNUICallback('test', function(_, cb) TriggerServerEvent('botforge:serverTest'); cb('ok') end)\n"
    if cfg['database'] == 'MySQL': files['README-DATABASE.md'] = '# MySQL\n\nAdicione oxmysql ao servidor e crie as tabelas conforme a persistência necessária.\n'
    return files


def site_files(order, config):
    title = config.get('brand') or 'Meu Projeto'
    objective = config.get('objective') or 'Site gerado pelo BOT FORGE.'
    raw_pages = text(config.get('pages'))
    pages = [p.strip() for p in re.split(r'[,;\n]+', raw_pages) if p.strip()] or ['Início', 'Sobre', 'Contato']
    sections_raw = text(config.get('sections'))
    sections = [p.strip() for p in re.split(r'[,;\n]+', sections_raw) if p.strip()] or ['Apresentação', 'Recursos', 'FAQ']
    integrations = config.get('integrations') or []
    forms = config.get('forms') or []
    client_area = config.get('client_area') == 'Sim'
    admin_panel = config.get('admin_panel') == 'Sim'
    seo = config.get('seo') == 'Incluir'
    colors = config.get('colors') or 'neutro'
    nav = ''.join(f'<a href="#{slug(p)}">{p}</a>' for p in pages)
    page_sections = ''.join(f'<section id="{slug(p)}"><span>BOT FORGE</span><h2>{p}</h2><p>{objective if p == pages[0] else "Seção criada a partir da configuração do seu projeto."}</p><div class="cards">' + ''.join(f'<article><b>{s}</b><p>Conteúdo configurado para esta seção.</p></article>' for s in sections) + '</div></section>' for p in pages)
    form_html = ''
    if forms:
        form_html = "<section id='contato'><span>CONTATO</span><h2>Fale conosco</h2><form id='contact-form'><input name='name' placeholder='Nome' required><input name='email' type='email' placeholder='E-mail' required><textarea name='message' placeholder='Mensagem' required></textarea><button>Enviar</button><p id='form-result'></p></form></section>"
    meta = f'<meta name="description" content="{objective[:150]}">' if seo else ''
    html = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{title}</title><link rel="stylesheet" href="style.css"></head><body><header><b>{title}</b><nav>{nav}</nav></header><main><section class="hero"><span>BOT FORGE</span><h1>{title}</h1><p>{objective}</p><a class="cta" href="#contato">Começar</a></section>{page_sections}{form_html}<footer>Gerado pelo BOT FORGE</footer></main><script src="app.js"></script></body></html>'''
    js = """const form=document.getElementById('contact-form');if(form)form.addEventListener('submit',e=>{e.preventDefault();document.getElementById('form-result').textContent='Formulário validado. Conecte o endpoint de produção para enviar os dados.';form.reset()});"""
    css = f'''*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,Arial,sans-serif;background:#fafafa;color:#172033}}header{{position:sticky;top:0;z-index:5;padding:18px 7%;display:flex;justify-content:space-between;gap:24px;background:#ffffffee;backdrop-filter:blur(12px);border-bottom:1px solid #e8ebef}}nav{{display:flex;gap:18px;flex-wrap:wrap}}nav a{{color:#344054;text-decoration:none}}main{{padding:0 7%}}section{{min-height:55vh;padding:80px 0;border-bottom:1px solid #e9ecf1}}.hero{{min-height:78vh;display:flex;flex-direction:column;justify-content:center}}span{{letter-spacing:.16em;font-weight:800;color:#697386}}h1{{font-size:clamp(44px,7vw,86px);line-height:1.02;margin:18px 0;max-width:950px}}h2{{font-size:42px}}p{{font-size:19px;line-height:1.65;max-width:760px;color:#667085}}.cta,button{{display:inline-block;border:0;border-radius:13px;padding:14px 22px;background:#26354a;color:#fff;text-decoration:none;font-weight:800;cursor:pointer}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}article{{background:#fff;border:1px solid #e7eaf0;border-radius:20px;padding:26px;box-shadow:0 12px 35px #1720330d}}article b{{font-size:20px}}form{{max-width:650px;display:grid;gap:12px}}input,textarea{{font:inherit;padding:14px;border:1px solid #dfe3ea;border-radius:12px}}textarea{{min-height:130px}}footer{{padding:50px 0;color:#98a2b3}}@media(max-width:760px){{header{{align-items:flex-start;flex-direction:column}}.cards{{grid-template-columns:1fr}}main{{padding:0 5%}}}}/* visual: {colors} */'''
    files = {'index.html': html, 'style.css': css, 'app.js': js, 'README.md': make_readme(order, config, title)}
    if client_area: files['CLIENT-AREA.md'] = '# Área do cliente\n\nEstrutura preparada. Conecte autenticação e backend antes de produção.\n'
    if admin_panel: files['ADMIN-PANEL.md'] = '# Painel administrativo\n\nEstrutura preparada. Implemente autenticação forte e permissões antes de produção.\n'
    if integrations: files['INTEGRATIONS.md'] = '# Integrações\n\n' + '\n'.join('- ' + str(x) for x in integrations) + '\n'
    return files


def custom_files(order, config):
    return {'README.md': make_readme(order, config, 'Projeto personalizado'), 'project.json': json.dumps({'order_id': order['id'], 'type': 'custom', 'config': config}, indent=2, ensure_ascii=False), 'SPECIFICATION.md': '# Especificação\n\n## Objetivo\n' + text(config.get('objective')) + '\n\n## Funcionalidades\n' + text(config.get('features')) + '\n\n## Integrações\n' + text(config.get('integrations')) + '\n', 'NEXT-STEPS.md': '# Próximos passos\n\n1. Validar requisitos.\n2. Definir stack.\n3. Implementar funcionalidades.\n4. Testar.\n5. Publicar.\n'}


def build_project(order, config):
    product = order['product']
    if product == 'discord': files = discord_files(order, config)
    elif product == 'fivem': files = fivem_files(order, config)
    elif product == 'site': files = site_files(order, config)
    else: files = custom_files(order, config)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, content in files.items(): z.writestr(path, content)
    out.seek(0)
    return out, files
