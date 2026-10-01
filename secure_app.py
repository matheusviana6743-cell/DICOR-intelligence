from app import app
from security import harden

app = harden(app)
