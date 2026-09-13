from pathlib import Path

p = Path('app_lastro.py')
s = p.read_text(encoding='utf-8')

# Keep the sidebar endpoint valid. The action details route requires an ID.
s = s.replace("('Ações','actions')", "('Ações','dashboard')")

# Replace the malformed action-detail return block with a valid template.
marker = "@app.get('/actions/result/<int:record_id>')"
end = s.find(marker)
start = s.rfind("\n return lay(a['name'],f'", 0, end)
if start != -1 and end != -1 and start < end:
    replacement = """\n page_html = '<div class=\"card\"><span class=\"pill\">Frequência: '+str(n)+'/'+('∞' if l is None else str(l))+'</span><p class=\"muted\">Valor: '+(money(a['action_value']) if a['action_value'] else 'Ainda não definido')+'</p><div class=\"rules\">'+rh+'</div></div><div class=\"card section\"><h2>Participantes</h2><p class=\"muted\">Selecione os participantes e finalize a ação quando os dados estiverem completos.</p></div>'\n return lay(a['name'],page_html)\n\n"""
    s = s[:start] + replacement + s[end:]

p.write_text(s, encoding='utf-8')
compile(s, 'app_lastro.py', 'exec')
print('Lastro source validated')
