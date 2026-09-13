from pathlib import Path
import re

p = Path('central_lastro.py')
if not p.exists():
    raise SystemExit
s = p.read_text(encoding='utf-8')

repls = [
(r"(?m)^        action_cards\.append\(f'.*$", '''        detail_url = url_for("action_detail", action_id=a["id"])
        button_class = "secondary" if lock else ""
        button_label = "Limite atingido" if lock else "Abrir ação"
        action_cards.append(f'<div class="card"><span class="pill">{n}/{lim if lim is not None else "∞"}</span><h2>{a["name"]}</h2><p class="muted">Valor: {money(a["action_value"]) if a["action_value"] else "Ainda não definido"}</p><a class="btn {button_class}" href="{detail_url}">{button_label}</a></div>')'''),
(r"(?m)^    tr=''.join\(f'<tr><td>\{x\[\"member_name\"\]\}.*$", '''    tr=[]
    for x in rows:
        proof_link = f'<a href="{url_for("proof_file", name=x["proof"])}">Abrir prova</a>' if x["proof"] else "—"
        tr.append(f'<tr><td>{x["member_name"]}</td><td>{x["quantity"]:g}</td><td>{x["creator"]}</td><td>{x["created_at"][:16].replace("T"," ")}</td><td>{proof_link}</td></tr>')
    tr=''.join(tr)'''),
(r"(?m)^        cards\.append\(f'<div class=\"card\"><span class=\"pill\">\{badge\}.*$", '''        detail_url = url_for("action_detail", action_id=a["id"])
        button_class = "secondary" if disabled else ""
        button_label = "Limite semanal atingido" if disabled else "Registrar participação"
        cards.append(f'<div class="card"><span class="pill">{badge}</span><h2>{a["name"]}</h2><p class="muted">Valor: {money(a["action_value"]) if a["action_value"] else "A definir"}</p><p class="muted">Bandidos: {data.get("bandits","—")} · Policiais: {data.get("police","—")}</p><a class="btn {button_class}" href="{detail_url}">{button_label}</a></div>')'''),
(r"(?m)^    tr=''.join\(f'<tr><td>\{m\[\"name\"\]\}.*$", '''    tr=[]
    for m in rows:
        edit_link = f'<a href="{url_for("member_edit", member_id=m["id"])}">Editar</a>' if session.get("role")=="ADMINISTRADOR" else "—"
        action_count = getall("SELECT COUNT(*)n FROM action_participants WHERE member_id=?",(m["id"],))[0]["n"]
        farm_total = getall("SELECT COALESCE(SUM(quantity),0)v FROM farms WHERE member_id=?",(m["id"],))[0]["v"]
        tr.append(f'<tr><td>{m["name"]}</td><td>{m["passport"] or "—"}</td><td>{m["cargo"]}</td><td>{action_count}</td><td>{farm_total:g}</td><td>{edit_link}</td></tr>')
    tr=''.join(tr)'''),
(r"(?m)^    return shell\('Editar membro',f'.*$", '''    cargo_options = ''.join('<option '+('selected ' if r==m['cargo'] else '')+'>'+r+'</option>' for r in ['LÍDER','VICE-LÍDER','GERENTE','MEMBRO'])
    active_checked = 'checked' if m['active'] else ''
    body = '<div class="card"><form class="formgrid" method="post"><input type="hidden" name="csrf" value="'+csrf()+'"><div class="field"><label>Nome</label><input class="input" name="name" value="'+str(m['name'])+'"></div><div class="field"><label>Passaporte</label><input class="input" name="passport" value="'+str(m['passport'] or '')+'"></div><div class="field"><label>Cargo</label><select class="select" name="cargo">'+cargo_options+'</select></div><div class="field"><label>Status</label><label><input type="checkbox" name="active" '+active_checked+'> Ativo</label></div><div class="field full"><label>Notas</label><textarea class="textarea" name="notes">'+str(m['notes'] or '')+'</textarea></div><div class="field full"><label>O que rendeu para o farm</label><textarea class="textarea" name="farm_notes">'+str(m['farm_notes'] or '')+'</textarea></div><div class="field full"><label>O que rendeu para ações</label><textarea class="textarea" name="action_notes">'+str(m['action_notes'] or '')+'</textarea></div><div class="field full"><label>Observações gerais</label><textarea class="textarea" name="general_notes">'+str(m['general_notes'] or '')+'</textarea></div><button class="btn full">Salvar membro</button></form></div>'
    return shell('Editar membro', body)''')
]
for pattern, replacement in repls:
    s, _ = re.subn(pattern, replacement, s, count=1)
p.write_text(s, encoding='utf-8')
