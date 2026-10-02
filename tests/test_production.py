import ast
import json
import zipfile
from pathlib import Path


def test_production_entrypoint_is_valid_python():
    ast.parse(Path('wsgi.py').read_text(encoding='utf-8'))


def test_procfile_uses_production_wsgi():
    text=Path('Procfile').read_text(encoding='utf-8')
    assert 'gunicorn' in text
    assert 'wsgi:application' in text
    assert 'BOT_FORGE_AUTOMATION=1' in text


def test_security_headers_are_declared():
    text=Path('wsgi.py').read_text(encoding='utf-8')
    for header in ['X-Content-Type-Options','X-Frame-Options','Referrer-Policy','Permissions-Policy','Strict-Transport-Security','Content-Security-Policy']:
        assert header in text


def test_generated_artifact_logic_validates_zip():
    text=Path('wsgi.py').read_text(encoding='utf-8')
    assert 'archive.testzip()' in text
    assert "cfg['_generated_file']" in text


def test_download_path_checks_artifact_inside_upload_directory():
    text=Path('wsgi.py').read_text(encoding='utf-8')
    assert "path.resolve().parent == UPLOAD_DIR.resolve()" in text
