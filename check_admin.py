from app import create_app, db
from app.models import User
from datetime import datetime, timezone

def check_admin_user():
    app = create_app('default')
    with app.app_context():
        # Get all users
        users = User.query.all()
        print("\nAll users in database:")
        print("-" * 50)
        
        for user in users:
            print(f"\nUsername: {user.username}")
            print(f"Email: {user.email}")
            print(f"Role: {user.role}")
            print(f"Is Active: {user.is_active}")
            print(f"Last Login: {user.last_login_at}")
            print(f"Created At: {user.created_at}")
            print("-" * 50)
        
        # Specifically check for ULTRAGUARD_ADMIN users
        admin_users = User.query.filter_by(role='ULTRAGUARD_ADMIN').all()
        print("\nULTRAGUARD_ADMIN users:")
        print("-" * 50)
        
        if not admin_users:
            print("No ULTRAGUARD_ADMIN users found!")
        else:
            for admin in admin_users:
                print(f"\nUsername: {admin.username}")
                print(f"Email: {admin.email}")
                print(f"Is Active: {admin.is_active}")
                print(f"Last Login: {admin.last_login_at}")
                print("-" * 50)

if __name__ == '__main__':
    check_admin_user() 