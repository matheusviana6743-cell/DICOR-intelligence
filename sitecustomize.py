from pathlib import Path

# Lastro compatibility patch loaded before app_lastro imports.
p = Path('app_lastro.py')
if p.exists():
    s = p.read_text(encoding='utf-8')
    # The navigation needs a real endpoint without arguments; the current
    # application does not expose an /actions index, so route the menu item
    # to the dashboard where all actions are displayed.
    s = s.replace("('Ações','actions')", "('Ações','dashboard')")
    p.write_text(s, encoding='utf-8')
