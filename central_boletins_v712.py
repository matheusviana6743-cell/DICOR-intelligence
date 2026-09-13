# -*- coding: utf-8 -*-
"""Central V712 - layout profissional para Boletins e Perícias."""
from __future__ import annotations
import html
import time
from datetime import datetime
import central_iframe_v711 as iframe
import central_home_v708 as v708
import central_home_v700 as v700


def esc(v) -> str:
    return html.escape(str(v or ""), quote=True)


def dt(v) -> str:
    try:
        if hasattr(v, "strftime"):
            return v.astimezone().strftime("%d/%m/%Y • %H:%M")
    except Exception:
        pass
    return str(v or "--")


def row_text(row: dict) -> str:
    parts = [row.get("number"), row.get("name"), row.get("subject"), row.get("source"), row.get("full_text")]
    parts += list((row.get("fields") or {}).values())
    return " ".join(str(x or "") for x in parts).casefold()


def module_page(user: dict, kind: str, title: str, desc: str, _unused: str = "") -> str:
    is_bo = kind == "boletins"
    rows = list(v700.C.get(kind, []) or [])
    q = str(getattr(user, "get", lambda *_: "")("q", "") or "")
    # A busca também pode vir pela URL; module_route passa o request, então lemos depois em wrapper.
    label = "BOLETINS DE OCORRÊNCIA" if is_bo else "PERÍCIAS"
    icon = "▣" if is_bo else "◈"
    cards = []
    for row in rows:
        fields = row.get("fields") or {}
        name = row.get("name") or row.get("subject") or "Registro sem identificação"
        number = row.get("number") or "S/N"
        source = row.get("source") or "DISCORD"
        full = row.get("full_text") or "Sem conteúdo adicional."
        field_items = []
        preferred = ("Nome", "RG / Passaporte", "Crimes", "Localização", "Situação")
        for k in preferred:
            if fields.get(k):
                field_items.append(f'<div class="field"><label>{esc(k)}</label><span>{esc(fields[k])}</span></div>')
        for k, val in fields.items():
            if k not in preferred and val and len(field_items) < 6:
                field_items.append(f'<div class="field"><label>{esc(k)}</label><span>{esc(val)}</span></div>')
        fields_html = "".join(field_items) or '<div class="field wide"><label>CONTEÚDO</label><span>Registro operacional disponível abaixo.</span></div>'
        cards.append(f'''<article class="record"><div class="record-head"><div class="record-id"><div class="record-icon">{icon}</div><div><small>{label}</small><h3>Nº {esc(number)}</h3></div></div><span class="source">{esc(source)}</span></div><div class="record-title">{esc(name)}</div><div class="record-date">REGISTRADO EM {esc(dt(row.get("date") or row.get("created")))}</div><div class="fields">{fields_html}</div><details><summary>VER {"BOLETIM" if is_bo else "LAUDO / REGISTRO"} COMPLETO</summary><div class="full-text">{esc(full)}</div></details></article>''')
    cards_html = "".join(cards) or '<div class="empty">Nenhum registro ativo encontrado.</div>'
    now = datetime.now().strftime("%d/%m/%Y • %H:%M")
    body = f'''<div class="shell"><aside class="sidebar"><div class="brand">{v700.img(v700.LOGO, "logo", "DICOR")}<div><b>DICOR</b><small>POLÍCIA FEDERAL</small></div></div><nav><a href="/">⌂ <span>Central</span></a><a class="active" href="/boletins">▣ <span>Boletins</span></a><a href="/procurados">◎ <span>Procurados</span></a><a class="{'active' if not is_bo else ''}" href="/pericias">◈ <span>Perícias</span></a><a href="/fichas">▤ <span>Banco de Dados</span></a><a href="/arvore">⌘ <span>Árvore</span></a></nav><div class="side-foot">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL<br><br>SISTEMA INTEGRADO<br>CONSULTA INTERNA</div></aside><main class="main"><header class="top"><div><div class="pcpt">PCPT - POLÍCIA CAPITAL / POLÍCIA FEDERAL</div><div class="subbrand">DICOR • CENTRAL DE INTELIGÊNCIA</div></div><div class="user"><i></i>{esc(user.get("qra", "OPERADOR"))}</div></header><div class="tabs"><a class="{'on' if is_bo else ''}" href="/boletins">BOLETINS</a><a class="{'on' if not is_bo else ''}" href="/pericias">PERÍCIAS</a></div><section class="hero"><div class="eyebrow">DASHBOARD OPERACIONAL • {"BO" if is_bo else "PERÍCIA"}</div><h1>{label}</h1><p>{esc(desc)}</p><div class="metrics"><div><small>REGISTROS ATIVOS</small><b>{len(rows)}</b></div><div><small>ATUALIZAÇÃO</small><b>{esc(now)}</b></div><div><small>ACESSO</small><b>INTERNO</b></div></div></section><section class="panel"><div class="panel-head"><div><small>CONSULTA DE REGISTROS</small><h2>{label}</h2></div><span>{len(rows):02d} REGISTRO(S)</span></div><form class="search" method="get"><input name="q" value="" placeholder="Pesquisar número, nome, RG, crime ou informação"><button type="submit">PESQUISAR</button></form><div class="grid">{cards_html}</div></section><footer>DICOR • INTELIGÊNCIA E COMBATE AO CRIME ORGANIZADO</footer></main></div>'''
    css = '''*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:Inter,Segoe UI,Arial,sans-serif;background:#02070c;color:#edf3f7}body{overflow-x:hidden}a{text-decoration:none;color:inherit}.shell{min-height:100vh;display:grid;grid-template-columns:225px 1fr;background:radial-gradient(circle at 78% 0,#12384d 0,transparent 28%),#02070c}.sidebar{position:sticky;top:0;height:100vh;padding:18px 13px;border-right:1px solid #1c3445;background:linear-gradient(180deg,#07121c,#03090e)}.brand{display:flex;align-items:center;gap:10px;padding:3px 7px 18px;border-bottom:1px solid #1b2e3d}.logo{width:50px;height:50px;object-fit:contain}.brand b{font-size:14px;letter-spacing:2px}.brand small{display:block;color:#e0c15b;font-size:8px;letter-spacing:1.5px;margin-top:4px}.sidebar nav{display:grid;gap:5px;margin-top:17px}.sidebar nav a{padding:12px 10px;border:1px solid transparent;border-radius:9px;color:#738899;font-size:10px;font-weight:900}.sidebar nav a:hover,.sidebar nav a.active{background:#0d1c28;border-color:#2c4c61;color:#e5c55f;box-shadow:inset 3px 0 #d2ac4d}.side-foot{position:absolute;left:13px;right:13px;bottom:17px;padding:12px;border-top:1px solid #1b2e3d;color:#516878;font-size:7px;line-height:1.7;letter-spacing:.8px}.main{min-width:0;padding:0 27px 40px}.top{height:76px;border-bottom:1px solid #193040;display:flex;align-items:center;justify-content:space-between}.pcpt{font-size:11px;font-weight:900;letter-spacing:1.5px}.subbrand{color:#d7b85c;font-size:8px;font-weight:900;letter-spacing:2px;margin-top:5px}.user{font-size:9px;color:#8aa0af;display:flex;gap:8px;align-items:center}.user i{width:7px;height:7px;border-radius:50%;background:#55d39a;box-shadow:0 0 12px #55d39a}.tabs{display:flex;gap:8px;margin-top:16px}.tabs a{padding:10px 17px;border:1px solid #213a4c;border-radius:9px;color:#6d8393;font-size:9px;font-weight:900;letter-spacing:1.4px}.tabs a.on{background:#17140b;border-color:#85661e;color:#e8c75f}.hero{margin-top:14px;padding:24px 26px;border:1px solid #29485c;border-radius:17px;background:linear-gradient(120deg,#091925,#061019);box-shadow:0 18px 55px #0006}.eyebrow{color:#d9b653;font-size:8px;font-weight:900;letter-spacing:2px}.hero h1{font-size:30px;margin:7px 0}.hero p{margin:0;color:#8398a6;font-size:11px}.metrics{display:flex;gap:9px;margin-top:17px;flex-wrap:wrap}.metrics div{padding:10px 13px;border:1px solid #1e384b;border-radius:9px;background:#07121b;min-width:145px}.metrics small{display:block;color:#587286;font-size:7px;letter-spacing:1px}.metrics b{display:block;color:#dfbf61;font-size:12px;margin-top:5px}.panel{margin-top:16px;border:1px solid #203b4e;border-radius:16px;background:#050c13;overflow:hidden}.panel-head{display:flex;justify-content:space-between;align-items:end;padding:18px 20px;border-bottom:1px solid #172c3d}.panel-head small{color:#5ca5dc;font-size:8px;font-weight:900;letter-spacing:2px}.panel-head h2{margin:5px 0 0;font-size:16px}.panel-head>span{color:#5d7486;font-size:8px;font-weight:900}.search{display:flex;gap:9px;padding:14px 15px;border-bottom:1px solid #132839}.search input{flex:1;height:43px;border:1px solid #27465b;border-radius:9px;background:#07131d;color:#eef3f6;padding:0 12px;outline:0}.search input:focus{border-color:#e1c45e}.search button{height:43px;border:0;border-radius:9px;padding:0 16px;background:linear-gradient(135deg,#f0d274,#a77515);color:#080b0d;font-size:9px;font-weight:900;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:14px}.record{padding:16px;border:1px solid #1c3548;border-radius:13px;background:linear-gradient(150deg,#0a1823,#061018);transition:.16s}.record:hover{border-color:#7a6020;transform:translateY(-2px)}.record-head{display:flex;justify-content:space-between;gap:12px}.record-id{display:flex;align-items:center;gap:10px}.record-icon{width:38px;height:38px;display:grid;place-items:center;border:1px solid #745b20;border-radius:9px;color:#e1bd58;background:#121109;font-size:16px}.record-head small{display:block;color:#60798b;font-size:7px;font-weight:900;letter-spacing:1.2px}.record-head h3{margin:4px 0 0;font-size:12px}.source{padding:5px 7px;height:max-content;border-radius:999px;border:1px solid #315268;color:#91bed7;font-size:7px;font-weight:900}.record-title{margin-top:14px;font-size:16px;font-weight:900}.record-date{margin-top:4px;color:#587084;font-size:8px}.fields{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;margin-top:13px}.field{padding:9px;border:1px solid #183044;border-radius:8px;background:#07131d;min-width:0}.field label{display:block;color:#587488;font-size:7px;font-weight:900;letter-spacing:1px}.field span{display:block;color:#d2dce2;font-size:9px;line-height:1.4;margin-top:4px;overflow-wrap:anywhere}.field.wide{grid-column:1/-1}details{margin-top:12px;border-top:1px solid #173044;padding-top:10px}summary{cursor:pointer;color:#dcb958;font-size:8px;font-weight:900;letter-spacing:1px;list-style:none}summary::-webkit-details-marker{display:none}.full-text{margin-top:9px;padding:12px;border-left:2px solid #c5a344;background:#07131d;color:#aebbc3;font-size:10px;line-height:1.65;white-space:pre-wrap;max-height:360px;overflow:auto}footer{text-align:center;color:#4e6474;font-size:7px;letter-spacing:1px;margin-top:18px}@media(max-width:850px){.shell{display:block}.sidebar{position:relative;height:auto;padding:12px}.sidebar nav{display:flex;overflow:auto}.sidebar nav a{white-space:nowrap}.side-foot{display:none}.main{padding:0 12px 30px}.grid{grid-template-columns:1fr}.hero{padding:20px}.metrics div{flex:1;min-width:110px}}@media(max-width:500px){.top{height:auto;padding:15px 0}.user{font-size:0}.hero h1{font-size:25px}.search{flex-direction:column}.search button{width:100%}.fields{grid-template-columns:1fr}.field.wide{grid-column:auto}.record{padding:13px}}
'''
    return v700.page(f"DICOR • {label}", body, css)


async def module_route(req, kind: str, title: str, desc: str):
    user = v700.current(req)
    if not user:
        return web.HTTPFound("/cadastro-operador")
    user = v700.touch(user)
    if not user.get("authorized"):
        return web.Response(text=v708.v706.restricted(user), status=403, content_type="text/html")
    if time.time() - float(v700.C.get("updated", 0.0) or 0.0) > 45 and not v700.C.get("refreshing"):
        await v708.refresh_data_v708()
    # aplica busca diretamente na cópia do cache sem alterar o cache global
    q = str(req.query.get("q", "")).strip().casefold()
    if q:
        original = v700.C.get(kind, [])
        v700.C[kind] = [r for r in original if q in row_text(r)]
        try:
            return web.Response(text=module_page(user, kind, title, desc), content_type="text/html")
        finally:
            v700.C[kind] = original
    return web.Response(text=module_page(user, kind, title, desc), content_type="text/html")


async def start_server(client):
    old = v708.module_route_v708
    v708.module_route_v708 = module_route
    try:
        return await iframe.install.__globals__["v708"].start_server(client) if False else await _start_v711(client)
    finally:
        v708.module_route_v708 = old


# O V711 faz apenas o ajuste do iframe e chama V708.install. Substituímos a rota
# antes dele registrar o aplicativo.
async def _start_v711(client):
    # reproduz o install do V711 sem iniciar duas vezes.
    if not hasattr(v700, "_central_original_login_route"):
        v700._central_original_login_route = v700.login_route
    v700.security = iframe.iframe_security
    v700.login_route = iframe.iframe_login_route
    central = v708.install.__globals__["v708"].install if False else None
    # v708.install is the real installer used by V711.
    return await _server_from_v708(client)


async def _server_from_v708(client):
    # V708's install returns the central object; the actual server is started by central.start().
    # Keep the V711 iframe cookie middleware by using its normal installer.
    central = iframe.install.__globals__["v708"].install(bot_module=None) if False else None
    raise RuntimeError("V712 bootstrap placeholder")


def install(bot_module):
    # The runtime patch is installed by wrapping V711's underlying V708 module.
    old = v708.module_route_v708
    v708.module_route_v708 = module_route
    try:
        return iframe.install(bot_module)
    finally:
        v708.module_route_v708 = old
