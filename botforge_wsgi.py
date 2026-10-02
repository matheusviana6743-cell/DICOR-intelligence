from app import app
import config_overrides
import asaas_integration

asaas_integration.install()
application = app
