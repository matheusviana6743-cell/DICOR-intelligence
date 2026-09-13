from pathlib import Path
import re

p = Path('central_lastro.py')
if p.exists():
    s = p.read_text(encoding='utf-8')
    replacement = '''    tr=[]
    for x in rows:
        proof_link='<a href="'+url_for("proof_file",name=x["proof"])+'">Abrir prova</a>' if x["proof"] else "—"
        tr.append("<tr><td>"+x["member_name"]+"</td><td>"+f'{x["quantity"]:g}'+"</td><td>"+x["creator"]+"</td><td>"+x["created_at"][:16].replace("T"," ")+"</td><td>"+proof_link+"</td></tr>")'''
    s, n = re.subn(r'(?m)^    tr=.*$', replacement, s, count=1)
    if n:
        p.write_text(s, encoding='utf-8')
