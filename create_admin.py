from app import create_app, db
from app.models import User
from datetime import datetime, timezone

def create_admin_user():
    app = create_app()
    with app.app_context():
        # Check if admin user already exists
        admin = User.query.filter_by(username='admin').first()
        if admin:
            print("Admin user already exists!")
            return
        
        # Create new admin user
        admin = User(
            username='admin',
            email='jason@ultrasource.co.za',
            role='ULTRAGUARD_ADMIN',
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        admin.set_password('Ultraguard@7474')  # Set the password to Ultraguard@7474
        
        # Add to database
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully!")
        print(f"Username: {admin.username}")
        print(f"Email: {admin.email}")
        print(f"Role: {admin.role}")
        print(f"Is Active: {admin.is_active}")

if __name__ == '__main__':
    create_admin_user() 