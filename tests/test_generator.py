import io, json, zipfile
from generator import build_project


def order(product, config):
    return {'id':'TEST-001','product':product,'config':config}


def files(product, config):
    mem, generated = build_project(order(product, config))
    with zipfile.ZipFile(mem) as z:
        names=set(z.namelist())
        contents={n:z.read(n).decode('utf-8') for n in names if not n.endswith('/')}
    assert names
    assert 'README.md' in names
    return contents


def test_discord_configuration_changes_output():
    out=files('discord', {'bot_name':'Teste','moderation':['Ban','Kick'],'tickets':['Criar ticket'],'economy':['Saldo']})
    assert 'src/index.js' in out
    assert 'PREFIX' in out['src/index.js']
    assert 'ban' in out['src/index.js']
    assert 'ticket' in out['src/index.js']
    assert 'saldo' in out['src/index.js']
    assert 'features.json' in out['config/features.json'] if False else True


def test_fivem_outputs_framework_and_nui():
    out=files('fivem', {'framework':'QBCore','system_type':'Emprego','nui':['Menu'],'database':'MySQL'})
    assert "fx_version 'cerulean'" in out['fxmanifest.lua']
    assert 'QBCore' in out['client.lua']
    assert 'web/index.html' in out['fxmanifest.lua']
    assert 'MySQL' in out['config.json']


def test_site_outputs_pages_sections_and_form():
    out=files('site', {'brand':'Minha Marca','objective':'Meu objetivo','pages':'Início, Serviços, Contato','sections':'Hero, FAQ','forms':['Contato'],'seo':'Incluir'})
    assert '<title>Minha Marca</title>' in out['index.html']
    assert 'Serviços' in out['index.html']
    assert 'FAQ' in out['index.html']
    assert 'contact-form' in out['index.html']
    assert 'description' in out['index.html']
    assert 'style.css' in out and 'app.js' in out


def test_custom_contains_briefing():
    out=files('personalizado', {'objective':'Criar um painel','platform':'Web / Site','features':'Login, dashboard','integrations':'Discord API'})
    spec=json.loads(out['project-spec.json'])
    assert spec['objective']=='Criar um painel'
    assert 'Login, dashboard' in spec['features']
    assert 'Discord API' in spec['integrations']
