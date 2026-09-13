import flask
from pathlib import Path

_GOLD_THEME=r'''<style id="lastro-gold-theme">:root{--bg:#050505!important;--panel:#0d0d0d!important;--line:#2b2414!important;--text:#f7f3e8!important;--muted:#a79b82!important;--accent:#d4af37!important;--accent2:#f0d477!important}body{background:radial-gradient(circle at 80% -10%,rgba(212,175,55,.16),transparent 32%),linear-gradient(135deg,#030303,#0a0906 55%,#030303)!important;color:#f7f3e8!important}.side{background:#080808f7!important;border-right:1px solid #4a3b17!important}.brand b{color:#d4af37!important}.nav a:hover{background:rgba(212,175,55,.09)!important;color:#f5df91!important;border-color:#4b3b16!important}.top h1,.section h2{color:#f0df9b!important}.card{background:linear-gradient(180deg,#12110e,#0b0b0a)!important;border-color:#332a17!important}.metric{color:#d4af37!important}.table th{color:#d4af37!important}.btn{background:linear-gradient(135deg,#d4af37,#b88a14)!important;color:#090805!important}.btn.secondary{background:#17150f!important;color:#d8c98e!important;border-color:#4a3a18!important}.input,.select,.textarea{background:#070706!important;border-color:#3a301b!important;color:#f7f3e8!important}.input:focus,.select:focus,.textarea:focus{border-color:#d4af37!important}.muted{color:#a79b82!important}.pill{background:#211b0d!important;color:#e4cf82!important;border-color:#493a17!important}.flash{background:#16150e!important;border-color:#55451d!important}.login{background:radial-gradient(circle at center,rgba(212,175,55,.12),transparent 42%)!important}.mobile{background:#090806f5!important;border-top-color:#4a3b17!important}</style>'''

_original=flask.render_template_string

def _render(*a,**k):
    h=_original(*a,**k)
    return h.replace('</head>',_GOLD_THEME+'</head>',1)

flask.render_template_string=_render

# Permite que o POST público da tela de login chegue à própria rota de login.
p=Path('app_lastro.py')
if p.exists():
    s=p.read_text()
    old="if request.method=='POST' and (not session.get('uid') or not secrets.compare_digest(request.form.get('csrf',''),session.get('csrf',''))):abort(400)"
    new="if request.method=='POST' and request.endpoint != 'login' and (not session.get('uid') or not secrets.compare_digest(request.form.get('csrf',''),session.get('csrf',''))):abort(400)"
    if old in s:
        p.write_text(s.replace(old,new,1))
