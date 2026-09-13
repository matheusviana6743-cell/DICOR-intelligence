import json, os

from app_lastro import app, init_db

init_db()
client = app.test_client()

with client.session_transaction() as s:
    # Get a CSRF token by opening the login page.
    pass

login_page = client.get('/')
assert login_page.status_code == 200, f'login page: {login_page.status_code}'
with client.session_transaction() as s:
    token = s['csrf']

admin_user = os.getenv('ADMIN_USER', 'Marcelo Correia')
admin_password = os.getenv('ADMIN_PASSWORD') or os.getenv('ADMIN_INITIAL_PASSWORD')
assert admin_password, 'ADMIN_PASSWORD/ADMIN_INITIAL_PASSWORD is missing'

r = client.post('/', data={'csrf': token, 'username': admin_user, 'password': 'wrong-password'}, follow_redirects=False)
assert r.status_code == 200, f'wrong password must stay on login: {r.status_code}'
with client.session_transaction() as s:
    token = s['csrf']
r = client.post('/', data={'csrf': token, 'username': admin_user, 'password': admin_password}, follow_redirects=False)
assert r.status_code == 302 and '/dashboard' in r.headers.get('Location',''), f'admin login: {r.status_code}'

routes = ['/health','/dashboard','/actions','/ranking','/members','/history','/farms','/productions','/chests','/users','/admin/actions','/externals','/admin/audit']
for path in routes:
    r = client.get(path)
    assert r.status_code == 200, f'{path}: {r.status_code}'

client.get('/logout')

raw = os.getenv('INITIAL_USERS_JSON','[]')
users = json.loads(raw) if raw else []
for u in users:
    c = app.test_client()
    page = c.get('/')
    assert page.status_code == 200
    with c.session_transaction() as s:
        token = s['csrf']
    r = c.post('/', data={'csrf': token, 'username': u['username'], 'password': u['password']}, follow_redirects=False)
    assert r.status_code == 302 and '/dashboard' in r.headers.get('Location',''), f'user {u["username"]}: {r.status_code}'

print('LASTRO_SMOKE_TEST_OK')
