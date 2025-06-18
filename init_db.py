#!/usr/bin/env python3
"""
Database initialization script for Ultraguard.
This script creates all database tables and initial data.
Run this after deployment to set up the database.
"""

import os
import sys
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, Client
from werkzeug.security import generate_password_hash

def init_database():
    """Initialize the database with tables and initial data."""
    app = create_app('production')
    
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("✅ Database tables created successfully!")
        
        # Check if we already have data
        if User.query.first():
            print("✅ Database already contains data. Skipping initial data creation.")
            return
        
        print("Creating initial data...")
        
        # Create a test client
        test_client = Client(
            name="Test Client Company",
            contact_person="Test Contact",
            contact_email="test@example.com",
            contact_phone="+1234567890",
            is_active=True
        )
        db.session.add(test_client)
        db.session.flush()  # Get the ID without committing
        
        # Create an Ultraguard admin user
        admin_user = User(
            username="admin",
            email="admin@ultraguard.com",
            password_hash=generate_password_hash("admin123"),
            role="ULTRAGUARD_ADMIN",
            is_active=True
        )
        db.session.add(admin_user)
        
        # Create a client admin user
        client_admin = User(
            username="client_admin",
            email="admin@testclient.com",
            password_hash=generate_password_hash("client123"),
            role="CLIENT_ADMIN",
            client_id=test_client.id,
            is_active=True
        )
        db.session.add(client_admin)
        
        # Create a client staff user
        client_staff = User(
            username="client_staff",
            email="staff@testclient.com",
            password_hash=generate_password_hash("staff123"),
            role="CLIENT_STAFF",
            client_id=test_client.id,
            is_active=True
        )
        db.session.add(client_staff)
        
        # Commit all changes
        db.session.commit()
        
        print("✅ Initial data created successfully!")
        print("\n📋 Default Login Credentials:")
        print("Ultraguard Admin:")
        print("  Username: admin")
        print("  Password: admin123")
        print("  Email: admin@ultraguard.com")
        print("\nClient Admin:")
        print("  Username: client_admin")
        print("  Password: client123")
        print("  Email: admin@testclient.com")
        print("\nClient Staff:")
        print("  Username: client_staff")
        print("  Password: staff123")
        print("  Email: staff@testclient.com")
        print("\n⚠️  IMPORTANT: Change these passwords immediately after first login!")

if __name__ == '__main__':
    try:
        init_database()
        print("\n🎉 Database initialization completed successfully!")
    except Exception as e:
        print(f"\n❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 