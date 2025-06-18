#!/usr/bin/env python3
"""
Deployment script for Ultraguard
Run this after deployment to initialize the database and create admin users.
"""

import os
import sys
from app import create_app, db
from app.models import User, Client
from flask_migrate import upgrade

def create_admin_user():
    """Create the initial admin user."""
    app = create_app('production')
    
    with app.app_context():
        # Run database migrations
        print("Running database migrations...")
        upgrade()
        
        # Check if admin user already exists
        admin_user = User.query.filter_by(role='ADMIN').first()
        if admin_user:
            print(f"Admin user already exists: {admin_user.username}")
            return admin_user
        
        # Create admin user
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin@ultraguard.com')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        
        admin_user = User(
            username=admin_username,
            email=admin_username,
            role='ADMIN',
            is_active=True
        )
        admin_user.set_password(admin_password)
        
        db.session.add(admin_user)
        db.session.commit()
        
        print(f"Created admin user: {admin_username}")
        print(f"Password: {admin_password}")
        print("Please change the password after first login!")
        
        return admin_user

def create_sample_client():
    """Create a sample client for testing."""
    app = create_app('production')
    
    with app.app_context():
        # Check if sample client already exists
        sample_client = Client.query.filter_by(name='Sample Security Corp').first()
        if sample_client:
            print(f"Sample client already exists: {sample_client.name}")
            return sample_client
        
        # Create sample client
        sample_client = Client(
            name='Sample Security Corp',
            contact_person='John Doe',
            contact_email='john.doe@samplecorp.com'
        )
        
        db.session.add(sample_client)
        db.session.commit()
        
        print(f"Created sample client: {sample_client.name}")
        return sample_client

if __name__ == '__main__':
    print("Ultraguard Deployment Script")
    print("=" * 40)
    
    try:
        # Create admin user
        admin = create_admin_user()
        
        # Create sample client
        client = create_sample_client()
        
        print("\nDeployment completed successfully!")
        print(f"Admin login: {admin.username}")
        print(f"Sample client: {client.name}")
        
    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1) 