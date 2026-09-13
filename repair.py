from pathlib import Path
p=Path('app_lastro.py')
s=p.read_text(encoding='utf-8')
s=s.replace("('Ações','actions')","('Ações','dashboard')")
marker="@app.get('/actions/result/<int:record_id>')"
end=s.find(marker)
start=s.rfind("\n return lay(a['name'],f'",0,end)
if start!=-1 and end!=-1 and start<end:
    s=s[:start]+"\n return lay(a['name'], '<div class=\"card\"><h2>'+a['name']+'</h2><p class=\"muted\">Frequência: '+str(n)+'/'+('∞' if l is None else str(l))+'</p><div class=\"rules\">'+rh+'</div></div>')\n"+s[end:]
else:
    raise SystemExit('target action block not found')
p.write_text(s,encoding='utf-8')
compile(s,'app_lastro.py','exec')
print('LASTRO_SOURCE_OK')
