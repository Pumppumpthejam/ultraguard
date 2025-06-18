import os
from flask import Flask, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import config_by_name  # <-- Import the config_by_name dictionary
# config_by_name will be passed in from run.py, so we only need the base Config for type hinting if desired
# from config import Config # Not strictly needed here if config object is passed in
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from sqlalchemy import text

db = SQLAlchemy() # Initialize SQLAlchemy extension
migrate = Migrate() # Initialize Flask-Migrate
login_manager = LoginManager() # Initialize LoginManager
# The login_view will point to the login route within our client portal blueprint
login_manager.login_view = 'client_portal.login'
login_manager.login_message_category = 'info'
login_manager.login_message = 'Please log in to access the client portal'

def create_app(config_name: str):
    """
    Application factory: creates and configures the Flask app.
    Accepts a configuration object.
    """
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration from the passed-in object
    selected_config = config_by_name[config_name]
    app.config.from_object(selected_config)

    # !!! DEBUGGING AID !!!
    app.logger.info(f"Loading config: {config_name}")
    app.logger.info(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    # !!! END DEBUGGING AID !!!

    # Ensure the instance folder exists (where SQLite DB will be stored)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass # Folder already exists or cannot be created

    # Initialize Flask extensions with the app
    db.init_app(app)
    migrate.init_app(app, db) # Initialize Flask-Migrate with the app and SQLAlchemy
    login_manager.init_app(app) # Initialize LoginManager with the app

    # Register CLI commands
    from app import commands
    app.cli.add_command(commands.test_db_connection_command)

    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Configure logging
    if not app.debug and not app.testing:
        # Ensure logs directory exists
        log_dir = os.path.join(app.root_path, '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)

        # Create rotating file handler
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'ultraguard.log'),
            maxBytes=102400,  # 100KB
            backupCount=10
        )
        
        # Set log format
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        
        # Set log level based on environment
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        
        # Set overall app logger level
        app.logger.setLevel(logging.INFO)
        app.logger.info('Ultraguard startup')
    else:
        # For debug/testing, use console logging
        app.logger.setLevel(logging.DEBUG)
        app.logger.info('Ultraguard startup (DEBUG/TESTING mode)')

    # Register blueprints within app context
    with app.app_context():
        # Import and register the Admin Blueprint
        from app.admin import bp as admin_bp
        app.register_blueprint(admin_bp, url_prefix='/admin')

        # Import and register the Client Portal Blueprint
        from app.client_portal import bp as client_bp
        app.register_blueprint(client_bp, url_prefix='/portal')

        # Ensure models are known to SQLAlchemy
        from . import models
        
        # Test database connection and create tables if needed
        try:
            app.logger.info("Testing database connection...")
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
            app.logger.info("✅ Database connection successful!")
            
            # Check if tables exist and create them if needed
            try:
                from .models import User
                user_count = User.query.count()
                app.logger.info(f"✅ Database tables exist. Found {user_count} users.")
            except Exception as table_error:
                app.logger.warning(f"⚠️  Database tables may not exist yet: {table_error}")
                app.logger.info("🔄 Creating database tables...")
                try:
                    db.create_all()
                    app.logger.info("✅ Database tables created successfully!")
                except Exception as create_error:
                    app.logger.error(f"❌ Failed to create tables: {create_error}", exc_info=True)
            # Always check if admin user needs to be created
            from .models import User
            if User.query.count() == 0:
                app.logger.info("🔄 Creating initial Ultraguard admin user...")
                from werkzeug.security import generate_password_hash
                admin_user = User(
                    username="admin",
                    email="admin@ultraguard.com",
                    password_hash=generate_password_hash("admin123"),
                    role="ULTRAGUARD_ADMIN",
                    is_active=True
                )
                db.session.add(admin_user)
                db.session.commit()
                app.logger.info("✅ Initial Ultraguard admin user created!")
                app.logger.info("📋 Admin credentials: admin / admin123")
                
        except Exception as db_error:
            app.logger.error(f"❌ Database connection failed: {db_error}")
            app.logger.error("Please check your DATABASE_URL environment variable.")

    # Add root route redirect
    @app.route('/')
    def index_redirect():
        return redirect(url_for('client_portal.login'))

    # Register error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'Server Error: {error}')
        return render_template('errors/500.html'), 500

    return app
