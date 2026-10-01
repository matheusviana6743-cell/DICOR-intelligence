import io, json, re, zipfile
from datetime import datetime


def slug(value):
    value = re.sub(r'[^a-zA-Z0-9_-]+', '-', str(value or '').strip()).strip('-').lower()
    return value or 'bot-forge-project'


def make_readme(order, config, product_name):
    lines = [
        f'# {product_name} — BOT FORGE',
        '',
        f'Projeto gerado para o pedido `{order["id"]}` em {datetime.now().strftime("%d/%m/%Y %H:%M")}.',
        '',
        '## Configuração recebida',
    ]
    for key, value in config.items():
        if key.startswith('_') or not value:
            continue
        if isinstance(value, list):
            value = ', '.join(map(str, value))
        lines.append(f'- **{key.replace("_", " ").title()}:** {value}')
    lines += ['', 'Este pacote é uma geração inicial de teste. Revise as configurações e dependências antes de usar em produção.']
    return '\n'.join(lines) + '\n'


def discord_files(order, config):
    name = config.get('bot_name') or 'BOT FORGE Bot'
    prefix = config.get('prefix') or '!'
    package = {
        'name': slug(name), 'version': '1.0.0', 'description': 'Bot Discord gerado pelo BOT FORGE',
        'main': 'src/index.js', 'scripts': {'start': 'node src/index.js'},
        'dependencies': {'discord.js': '^14.16.3', 'dotenv': '^16.4.5'}
    }
    env = 'DISCORD_TOKEN=COLOQUE_SEU_TOKEN_AQUI\n'
    js = '''const { Client, GatewayIntentBits } = require('discord.js');\nrequire('dotenv').config();\n\nconst client = new Client({\n  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent]\n});\n\nclient.once('ready', () => console.log(`Bot online: ${client.user.tag}`));\n\nclient.on('messageCreate', async (message) => {\n  if (message.author.bot) return;\n  if (message.content === `${PREFIX}ping`) await message.reply('Pong! BOT FORGE está online.');\n});\n\nconst PREFIX = process.env.PREFIX || 'PREFIX_VALUE';\nclient.login(process.env.DISCORD_TOKEN);\n'''.replace('PREFIX_VALUE', prefix.replace('"','\\"'))
    return {
        'package.json': json.dumps(package, indent=2, ensure_ascii=False),
        '.env.example': env + f'PREFIX={prefix}\n',
        'src/index.js': js,
        'README.md': make_readme(order, config, name),
    }


def fivem_files(order, config):
    resource = slug(config.get('system_type') or 'bot-forge-system')
    fx = '''fx_version 'cerulean'\ngame 'gta5'\n\nauthor 'BOT FORGE'\ndescription 'Sistema FiveM gerado pelo BOT FORGE'\nversion '1.0.0'\n\nclient_script 'client.lua'\nserver_script 'server.lua'\n'''
    client = """RegisterCommand('botforge', function()\n    TriggerEvent('chat:addMessage', { args = {'BOT FORGE', 'Sistema de teste carregado com sucesso.'} })\nend, false)\n"""
    server = """RegisterCommand('botforgeinfo', function(source)\n    print(('[BOT FORGE] Pedido %s — sistema FiveM ativo.'):format('ORDER_ID'))\nend, true)\n""".replace('ORDER_ID', order['id'])
    return {'fxmanifest.lua': fx, 'client.lua': client, 'server.lua': server, 'README.md': make_readme(order, config, resource)}


def site_files(order, config):
    title = config.get('brand') or 'Meu Projeto'
    objective = config.get('objective') or 'Site gerado pelo BOT FORGE.'
    html = f'''<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><link rel="stylesheet" href="style.css"></head>\n<body><main><span>BOT FORGE</span><h1>{title}</h1><p>{objective}</p><a href="#contato">Começar</a></main><section id="contato"><h2>Contato</h2><p>Projeto gerado para teste. Personalize este conteúdo conforme sua necessidade.</p></section></body></html>\n'''
    css = '''*{box-sizing:border-box}body{margin:0;font-family:Inter,Arial,sans-serif;background:#faf8f2;color:#171717}main{min-height:72vh;padding:12vh 8%;display:flex;flex-direction:column;justify-content:center}main span{letter-spacing:.18em;font-weight:800;color:#b88a25}h1{font-size:clamp(42px,8vw,88px);max-width:900px;margin:18px 0}p{font-size:20px;line-height:1.6;max-width:720px}a{display:inline-block;margin-top:20px;padding:15px 22px;border-radius:14px;background:#c89b35;color:#fff;text-decoration:none;font-weight:800;width:max-content}section{padding:80px 8%;background:#fff}'''
    return {'index.html': html, 'style.css': css, 'README.md': make_readme(order, config, title)}


def custom_files(order, config):
    return {
        'README.md': make_readme(order, config, 'Projeto personalizado'),
        'project.json': json.dumps({'order_id': order['id'], 'type': 'custom', 'config': config}, indent=2, ensure_ascii=False),
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
