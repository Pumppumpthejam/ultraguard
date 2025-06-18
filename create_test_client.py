from app import create_app, db
from app.models import Client, User
from datetime import datetime, timezone

def create_test_client():
    app = create_app()
    with app.app_context():
        # Create test client
        client = Client(
            name='Test Client',
            contact_person='Test Contact',
            contact_email='test@example.com',
            contact_phone='1234567890',
            is_active=True
        )
        db.session.add(client)
        db.session.commit()
        
        # Create client admin user
        admin = User(
            username='clientadmin',
            email='clientadmin@example.com',
            role='CLIENT_ADMIN',
            is_active=True,
            client_id=client.id,
            created_at=datetime.now(timezone.utc)
        )
        admin.set_password('Test@123')  # Set a test password
        
        db.session.add(admin)
        db.session.commit()
        
        print("Test client and admin user created successfully!")
        print(f"Client: {client.name}")
        print(f"Admin Username: {admin.username}")
        print(f"Admin Email: {admin.email}")
        print(f"Admin Role: {admin.role}")

if __name__ == '__main__':
    create_test_client() 