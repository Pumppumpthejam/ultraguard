from app import create_app, db
from app.models import User

def check_client_users():
    app = create_app()
    with app.app_context():
        client_users = User.query.filter_by(role='CLIENT_ADMIN').all()
        print("\nClient users in database:")
        print("-" * 50)
        
        if not client_users:
            print("No client users with role 'CLIENT_ADMIN' found!")
        else:
            for user in client_users:
                print(f"\nUsername: {user.username}")
                print(f"Email: {user.email}")
                print(f"Role: {user.role}")
                print(f"Is Active: {user.is_active}")
                print(f"Last Login: {user.last_login_at}")
                print(f"Created At: {user.created_at}")
                print("-" * 50)

if __name__ == '__main__':
    check_client_users() 