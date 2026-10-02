import json, subprocess, tempfile
from pathlib import Path
from generator import build_project
from tests.test_generator import order


def test_generated_discord_js_syntax():
    mem,_=build_project(order('discord', {'bot_name':'Teste','moderation':['Ban','Kick']}))
    import zipfile
    with zipfile.ZipFile(mem) as z:
        source=z.read('src/index.js').decode()
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'index.js'; p.write_text(source, encoding='utf-8')
        result=subprocess.run(['node','--check',str(p)],capture_output=True,text=True)
        assert result.returncode==0, result.stderr
