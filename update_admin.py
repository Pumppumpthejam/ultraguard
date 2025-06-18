from app import create_app, db
from app.models import User

def update_admin_user():
    app = create_app('default')
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if admin:
            admin.email = 'jason@ultrasource.co.za'
            admin.set_password('Ultraguard@7474')
            db.session.commit()
            print("Admin user updated successfully!")
            print(f"Username: {admin.username}")
            print(f"Email: {admin.email}")
            print(f"Role: {admin.role}")
            print(f"Is Active: {admin.is_active}")
        else:
            print("Admin user not found!")

if __name__ == '__main__':
    update_admin_user() 