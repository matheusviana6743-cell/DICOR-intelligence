import flask
from pathlib import Path

_GOLD_THEME=r'''<style id="lastro-gold-theme">:root{--bg:#050505!important;--panel:#0d0d0d!important;--line:#2b2414!important;--text:#f7f3e8!important;--muted:#a79b82!important;--accent:#d4af37!important;--accent2:#f0d477!important}body{background:radial-gradient(circle at 80% -10%,rgba(212,175,55,.16),transparent 32%),linear-gradient(135deg,#030303,#0a0906 55%,#030303)!important;color:#f7f3e8!important}.side{background:#080808f7!important;border-right:1px solid #4a3b17!important}.brand b{color:#d4af37!important}.nav a:hover{background:rgba(212,175,55,.09)!important;color:#f5df91!important;border-color:#4b3b16!important}.top h1,.section h2{color:#f0df9b!important}.card{background:linear-gradient(180deg,#12110e,#0b0b0a)!important;border-color:#332a17!important}.metric{color:#d4af37!important}.table th{color:#d4af37!important}.btn{background:linear-gradient(135deg,#d4af37,#b88a14)!important;color:#090805!important}.btn.secondary{background:#17150f!important;color:#d8c98e!important;border-color:#4a3a18!important}.input,.select,.textarea{background:#070706!important;border-color:#3a301b!important;color:#f7f3e8!important}.input:focus,.select:focus,.textarea:focus{border-color:#d4af37!important}.muted{color:#a79b82!important}.pill{background:#211b0d!important;color:#e4cf82!important;border-color:#493a17!important}.flash{background:#16150e!important;border-color:#55451d!important}.login{background:radial-gradient(circle at center,rgba(212,175,55,.12),transparent 42%)!important}.mobile{background:#090806f5!important;border-top-color:#4a3b17!important}</style>'''

_original=flask.render_template_string

def _render(*a,**k):
    h=_original(*a,**k)
    return h.replace('</head>',_GOLD_THEME+'</head>',1)

flask.render_template_string=_render

# Corrige o middleware de login e a renderização da página de ação antes do import.
p=Path('app_lastro.py')
if p.exists():
    s=p.read_text()
    old="if request.method=='POST' and (not session.get('uid') or not secrets.compare_digest(request.form.get('csrf',''),session.get('csrf',''))):abort(400)"
    new="if request.method=='POST' and request.endpoint != 'login' and (not session.get('uid') or not secrets.compare_digest(request.form.get('csrf',''),session.get('csrf',''))):abort(400)"
    if old in s:
        s=s.replace(old,new,1)
    lines=s.splitlines()
    for i,line in enumerate(lines):
        if line.startswith(" return lay(a['name'],f'<div class=\"card\"><span class=\"pill\">Frequência:"):
            replacement=[
" page_html = '''<div class=\"card\"><span class=\"pill\">Frequência: __N__/__L__</span><p class=\"muted\">Valor: __VALUE__</p><div class=\"rules\">__RULES__</div></div><form class=\"section\" method=\"post\"><input type=\"hidden\" name=\"csrf\" value=\"__CSRF__\"><div class=\"card\"><h2>Participantes da família</h2><div id=\"ms\"></div><button class=\"btn secondary\" type=\"button\" onclick=\"addM()\">+ Selecionar membro</button></div><div class=\"card section\"><h3>Adicionar participante externo</h3><div id=\"es\"></div><button class=\"btn secondary\" type=\"button\" onclick=\"addE()\">+ Adicionar participante externo</button></div><button class=\"btn section\" type=\"submit\">Finalizar ação</button></form><template id=\"mt\"><div class=\"member\"><div style=\"flex:1\"><select class=\"select\" name=\"member_ids\" onchange=\"sync(this)\">__OPTS__</select><div class=\"form\"><select class=\"select\" data-s><option>BANDIDO</option><option>POLICIAL</option></select><select class=\"select\" data-w><option value=\"INDEFINIDO\">Não informado</option><option value=\"TROUXE\">Trouxe armamento</option><option value=\"NAO_TROUXE\">Não trouxe</option></select></div></div><button type=\"button\" class=\"btn danger\" onclick=\"this.closest('.member').remove()\">Remover</button></div></template><script>function sync(x){var c=x.closest('.member');c.querySelector('[data-s]').name='side_'+x.value;c.querySelector('[data-w]').name='weapon_'+x.value}function addM(){var x=document.getElementById('mt').content.cloneNode(true);document.getElementById('ms').appendChild(x);sync(document.querySelector('#ms .member:last-child select[name=member_ids]'))}var ei=0;function addE(){var i=ei++,d=document.createElement('div');d.className='member';d.innerHTML='<div><input class=\"input\" name=\"ext_name\" placeholder=\"Nome\" required><input class=\"input\" name=\"ext_pass\" placeholder=\"Passaporte\"><input class=\"input\" name=\"ext_family\" placeholder=\"Família\" required><select class=\"select\" name=\"ext_side_'+i+'\"><option>BANDIDO</option><option>POLICIAL</option></select><select class=\"select\" name=\"ext_weapon_'+i+'\"><option value=\"INDEFINIDO\">Não informado</option><option value=\"TROUXE\">Trouxe armamento</option><option value=\"NAO_TROUXE\">Não trouxe</option></select></div><button type=\"button\" class=\"btn danger\" onclick=\"this.closest(\\\'.member\\\').remove()\">Remover</button>';document.getElementById('es').appendChild(d)}</script>'''",
" page_html=page_html.replace('__N__',str(n)).replace('__L__','∞' if l is None else str(l)).replace('__VALUE__',money(a['action_value']) if a['action_value'] else 'Ainda não definido').replace('__RULES__',rh).replace('__CSRF__',csrf()).replace('__OPTS__',opts)",
" return lay(a['name'],page_html)"
            ]
            lines[i:i+1]=replacement
            s='\n'.join(lines)+'\n'
            break
    p.write_text(s)
