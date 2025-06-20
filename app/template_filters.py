import re
from markupsafe import Markup

def nl2br_filter(value):
    if value is None:
        return ''
    # Replace newlines with <br> tags
    # Ensure that existing HTML is not escaped again if value might contain HTML
    br = Markup("<br>\n")
    result = Markup(br).join(value.splitlines())
    return result

def init_app(app):
    app.jinja_env.filters['nl2br'] = nl2br_filter
    # You can register other custom filters here 