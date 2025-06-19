import os
from app import create_app, db  # Import factory and db instance from app package
from config import config_by_name # Import the dictionary of config classes
from app import models # <--- ADD THIS IMPORT

# Determine which configuration to use (TEMPORARILY HARDCODED FOR POSTGRESQL TESTING)
config_name = os.getenv('FLASK_CONFIG', 'development')
# selected_config = config_by_name.get(config_name, config_by_name['default']) # No longer needed

# Create the Flask app instance using the selected configuration
# Pass config_name directly to create_app to ensure correct config is loaded
app = create_app(config_name)

@app.shell_context_processor
def make_shell_context():
    """Passes db and models to Flask shell."""
    # Make models available in the shell context for convenience
    return {
        'db': db,
        'Client': models.Client, # Add Client
        'User': models.User,
        'Device': models.Device, # Add Device
        'Site': models.Site,     # Add Site
        'Checkpoint': models.Checkpoint,
        'Route': models.Route,
        'RouteCheckpoint': models.RouteCheckpoint,
        'Shift': models.Shift, # Changed from PatrolAssignment
        'UploadedPatrolReport': models.UploadedPatrolReport,
        'ReportedLocation': models.ReportedLocation,
        'VerifiedVisit': models.VerifiedVisit
    }

if __name__ == '__main__':
    # !!! DEBUGGING AID: Confirm DB URI at startup !!!
    print(f"[*] FLASK_CONFIG environment variable: {os.getenv('FLASK_CONFIG')}")
    print(f"[*] App starting with database URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")
    # !!! END DEBUGGING AID !!!
    # app.run() will use the DEBUG setting from the loaded configuration
    # and FLASK_ENV=development ensures Flask's dev server features are on.
    app.run()
