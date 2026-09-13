import flask

_GOLD_THEME = r'''
<style id="lastro-gold-theme">
:root{--bg:#050505!important;--panel:#0d0d0d!important;--line:#2b2414!important;--text:#f7f3e8!important;--muted:#a79b82!important;--accent:#d4af37!important;--accent2:#f0d477!important;--ok:#35d58b!important;--danger:#ff5d73!important}
body{background:radial-gradient(circle at 80% -10%,rgba(212,175,55,.16) 0,transparent 32%),linear-gradient(135deg,#030303,#0a0906 55%,#030303)!important;color:#f7f3e8!important}
.side{background:linear-gradient(180deg,#080808f7,#0d0b07f7)!important;border-right:1px solid #4a3b17!important;box-shadow:8px 0 35px rgba(0,0,0,.35)}
.brand b{color:#d4af37!important;text-shadow:0 0 18px rgba(212,175,55,.22)}
.brand span{color:#b9a66e!important}
.nav a{color:#b7ad96!important;border:1px solid transparent}.nav a:hover{background:rgba(212,175,55,.09)!important;color:#f5df91!important;border-color:#4b3b16!important}.nav a:focus{outline:1px solid #d4af37}
.main{background:transparent!important}.top h1{color:#f4e5ac!important}.user{color:#b9a66e!important}
.card{background:linear-gradient(180deg,#12110e,#0b0b0a)!important;border-color:#332a17!important;box-shadow:0 8px 28px rgba(0,0,0,.2)}
.card:hover{border-color:#5a461b}
.metric{color:#d4af37!important;text-shadow:0 0 18px rgba(212,175,55,.13)}
.label{color:#a99a75!important}.section h2{color:#eadba8!important}
.table th{color:#b09d6c!important}.table td{border-bottom-color:#292315!important}.table tr:hover td{background:rgba(212,175,55,.035)}
.btn{background:linear-gradient(135deg,#d4af37,#b88a14)!important;color:#090805!important;box-shadow:0 5px 16px rgba(212,175,55,.16)}.btn:hover{filter:brightness(1.08);transform:translateY(-1px)}
.btn.secondary{background:#17150f!important;color:#d8c98e!important;border:1px solid #4a3a18!important}
.input,.select,.textarea{background:#070706!important;border-color:#3a301b!important;color:#f7f3e8!important}.input:focus,.select:focus,.textarea:focus{border-color:#d4af37!important;box-shadow:0 0 0 2px rgba(212,175,55,.1)}
.field label{color:#b7aa86!important}.muted{color:#a79b82!important}.pill{background:#211b0d!important;color:#e4cf82!important;border:1px solid #493a17}.proof{color:#e4c95e!important}.proof:hover{color:#fff0a8!important}
.flash{background:#16150e!important;border-color:#55451d!important;color:#eadba8}.flash.error{background:#281214!important;border-color:#6e2c38!important;color:#ffb2bd}
.login{background:radial-gradient(circle at center,rgba(212,175,55,.12),transparent 42%)!important}.loginbox{border-color:#4d3c18!important;box-shadow:0 25px 70px rgba(0,0,0,.55),0 0 45px rgba(212,175,55,.06)!important}.loginbox .btn{color:#090805!important}
.mobile-nav{background:#090806f5!important;border-top-color:#4a3b17!important}.mobile-nav a{color:#b7aa85!important}
</style>
'''
_original = flask.render_template_string

def _lastro_render(*args, **kwargs):
    html = _original(*args, **kwargs)
    return html.replace('</head>', _GOLD_THEME + '</head>', 1)

flask.render_template_string = _lastro_render
