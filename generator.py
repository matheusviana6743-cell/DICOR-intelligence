import io, json, re, zipfile
from datetime import datetime


def slug(value):
    value = re.sub(r'[^a-zA-Z0-9_-]+', '-', str(value or '').strip()).strip('-').lower()
    return value or 'bot-forge-project'


def text(value):
    if isinstance(value, list):
        return ', '.join(map(str, value))
    return str(value or '')


def make_readme(order, config, product_name):
    lines = [
        f'# {product_name} — BOT FORGE', '',
        f'Projeto gerado para o pedido `{order["id"]}` em {datetime.now().strftime("%d/%m/%Y %H:%M")}.', '',
        '## Configuração recebida',
    ]
    for key, value in config.items():
        if key.startswith('_') or not value:
            continue
        lines.append(f'- **{key.replace("_", " ").title()}:** {text(value)}')
    lines += ['', '## Observação', 'Esta é uma geração inicial funcional para teste. Revise credenciais, dependências e regras antes de usar em produção.']
    return '\n'.join(lines) + '\n'


def discord_files(order, config):
    name = config.get('bot_name') or 'BOT FORGE Bot'
    prefix = config.get('prefix') or '!'
    selected = {k: config.get(k, []) for k in ('tickets', 'moderation', 'logs', 'automation', 'economy', 'ui', 'integrations')}
    package = {
        'name': slug(name), 'version': '1.0.0', 'description': 'Bot Discord gerado pelo BOT FORGE',
        'main': 'src/index.js', 'scripts': {'start': 'node src/index.js'},
        'dependencies': {'discord.js': '^14.16.3', 'dotenv': '^16.4.5'}
    }
    commands = ['ping']
    if 'Ban' in selected['moderation']: commands.append('ban')
    if 'Kick' in selected['moderation']: commands.append('kick')
    if 'Mute' in selected['moderation']: commands.append('mute')
    if 'Criar ticket' in selected['tickets']: commands.append('ticket')
    if 'Saldo' in selected['economy']: commands.append('saldo')
    command_lines = []
    for cmd in commands:
        if cmd == 'ping': response = "Pong! BOT FORGE está online."
        elif cmd == 'ticket': response = "Sistema de tickets inicializado. Configure as categorias conforme seu servidor."
        elif cmd == 'saldo': response = "Economia de teste ativa. Conecte um banco de dados para persistência."
        else: response = f"Comando {cmd} criado como base de teste."
        command_lines.append(f"  if (message.content === `${{PREFIX}}{cmd}`) await message.reply({json.dumps(response)});")
    js = """const { Client, GatewayIntentBits } = require('discord.js');
require('dotenv').config();
const PREFIX = process.env.PREFIX || '!';
const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent] });
client.once('ready', () => console.log(`Bot online: ${client.user.tag}`));
client.on('messageCreate', async (message) => {
  if (message.author.bot) return;
%s
});
client.login(process.env.DISCORD_TOKEN);
""" % '\n'.join(command_lines)
    features = json.dumps(selected, indent=2, ensure_ascii=False)
    return {
        'package.json': json.dumps(package, indent=2, ensure_ascii=False),
        '.env.example': f'DISCORD_TOKEN=COLOQUE_SEU_TOKEN_AQUI\nPREFIX={prefix}\n',
        'src/index.js': js,
        'config/features.json': features + '\n',
        'README.md': make_readme(order, config, name),
    }


def fivem_files(order, config):
    resource = slug(config.get('system_type') or 'bot-forge-system')
    settings = {
        'framework': config.get('framework') or 'Standalone',
        'version': config.get('version') or '',
        'system_type': config.get('system_type') or '',
        'jobs': config.get('jobs') or '',
        'commands': config.get('commands') or '',
        'permissions': config.get('permissions') or '',
        'nui': config.get('nui') or [],
        'database': config.get('database') or 'Não',
        'discord_logs': config.get('discord_logs') or [],
        'optimization': config.get('optimization') or 'Padrão',
    }
    fx = """fx_version 'cerulean'
game 'gta5'
author 'BOT FORGE'
description 'Sistema FiveM gerado pelo BOT FORGE'
version '1.0.0'
client_script 'client.lua'
server_script 'server.lua'
"""
    client = """RegisterCommand('botforge', function()
    TriggerEvent('chat:addMessage', { args = {'BOT FORGE', 'Sistema de teste carregado com sucesso.'} })
end, false)

RegisterNetEvent('botforge:notify', function(message)
    TriggerEvent('chat:addMessage', { args = {'BOT FORGE', tostring(message)} })
end)
"""
    server = """RegisterCommand('botforgeinfo', function(source)
    print(('[BOT FORGE] Pedido %s — sistema FiveM ativo.'):format('ORDER_ID'))
end, true)

RegisterNetEvent('botforge:serverTest', function()
    local src = source
    TriggerClientEvent('botforge:notify', src, 'Integração cliente/servidor funcionando.')
end)
""".replace('ORDER_ID', order['id'])
    return {
        'fxmanifest.lua': fx,
        'client.lua': client,
        'server.lua': server,
        'config.json': json.dumps(settings, indent=2, ensure_ascii=False) + '\n',
        'README.md': make_readme(order, config, resource),
    }


def site_files(order, config):
    title = config.get('brand') or 'Meu Projeto'
    objective = config.get('objective') or 'Site gerado pelo BOT FORGE.'
    raw_pages = text(config.get('pages'))
    pages = [p.strip() for p in re.split(r'[,;\n]+', raw_pages) if p.strip()] or ['Início', 'Sobre', 'Contato']
    colors = config.get('colors') or 'claro + dourado'
    nav = ''.join(f'<a href="#{slug(p)}">{p}</a>' for p in pages)
    sections = ''.join(f'<section id="{slug(p)}"><span>BOT FORGE</span><h2>{p}</h2><p>{objective if p == pages[0] else "Seção criada a partir da configuração do seu projeto."}</p></section>' for p in pages)
    html = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{objective[:150]}"><title>{title}</title><link rel="stylesheet" href="style.css"></head>
<body><header><b>{title}</b><nav>{nav}</nav></header><main><div class="hero"><span>BOT FORGE</span><h1>{title}</h1><p>{objective}</p><a href="#contato">Começar</a></div>{sections}</main><footer>Gerado para teste pelo BOT FORGE</footer></body></html>'''
    css = f'''*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,Arial,sans-serif;background:#faf8f2;color:#171717}}header{{position:sticky;top:0;padding:20px 8%;display:flex;justify-content:space-between;gap:30px;background:#ffffffdd;backdrop-filter:blur(12px);border-bottom:1px solid #eee}}nav{{display:flex;gap:18px;flex-wrap:wrap}}nav a{{color:#333;text-decoration:none}}main{{padding:0 8%}}.hero{{min-height:70vh;padding:12vh 0;display:flex;flex-direction:column;justify-content:center}}.hero span,section span{{letter-spacing:.18em;font-weight:800;color:#b88a25}}h1{{font-size:clamp(42px,8vw,88px);max-width:900px;margin:18px 0}}h2{{font-size:42px}}p{{font-size:20px;line-height:1.6;max-width:720px}}a{{color:#b88a25}}.hero>a{{display:inline-block;margin-top:20px;padding:15px 22px;border-radius:14px;background:#c89b35;color:#fff;text-decoration:none;font-weight:800;width:max-content}}section{{min-height:55vh;padding:80px 0;border-top:1px solid #e8e3d8}}footer{{padding:40px 8%;background:#171717;color:#fff}}/* preferência visual: {colors} */'''
    return {'index.html': html, 'style.css': css, 'README.md': make_readme(order, config, title)}


def custom_files(order, config):
    return {
        'README.md': make_readme(order, config, 'Projeto personalizado'),
        'project.json': json.dumps({'order_id': order['id'], 'type': 'custom', 'config': config}, indent=2, ensure_ascii=False),
        'SPECIFICATION.md': '# Especificação inicial\n\n## Objetivo\n' + text(config.get('objective')) + '\n\n## Funcionalidades\n' + text(config.get('features')) + '\n\n## Integrações\n' + text(config.get('integrations')) + '\n',
        'NEXT-STEPS.md': '# Próximos passos\n\n1. Validar requisitos.\n2. Definir stack e integrações.\n3. Implementar funcionalidades.\n4. Testar e publicar.\n',
    }


def build_project(order, config):
    product = order['product']
    if product == 'discord': files = discord_files(order, config)
    elif product == 'fivem': files = fivem_files(order, config)
    elif product == 'site': files = site_files(order, config)
    else: files = custom_files(order, config)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, content in files.items():
            z.writestr(path, content)
    out.seek(0)
    return out, files
