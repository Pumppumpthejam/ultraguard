from flask import Blueprint

bp = Blueprint('main', __name__)

# Import routes and forms at the end to avoid circular dependencies
from app.main import routes, forms 