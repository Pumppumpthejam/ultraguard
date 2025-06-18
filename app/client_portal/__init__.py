from flask import Blueprint

# template_folder will point to 'app/templates/client_portal/'
bp = Blueprint('client_portal', __name__, template_folder='../templates/client_portal')

from app.client_portal import routes  # Import routes 