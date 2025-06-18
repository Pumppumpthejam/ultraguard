from flask import Blueprint

# The 'admin' blueprint.
# template_folder='../templates/admin' tells Flask to look for templates
# in 'ultraguard/app/templates/admin/' relative to this blueprint's location.
bp = Blueprint('admin', __name__, template_folder='../templates/admin')

# Import routes at the end to avoid circular dependencies.
# Forms will be imported within routes.py or forms.py as needed.
from app.admin import routes 