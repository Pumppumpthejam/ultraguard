# ultraguard/app/admin/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, abort
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf import FlaskForm
from urllib.parse import urlparse, urljoin
import csv
from io import StringIO
from datetime import datetime, timezone, timedelta
from werkzeug.utils import secure_filename
import os
from functools import wraps
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db, login_manager # login_manager from app/__init__.py
from app.admin import bp # The admin blueprint
from app.models import User, Client, Device, Shift, UploadedPatrolReport, Site, Route # <--- ADD Client model
# Device will be used later
from app.admin.forms import LoginForm, ClientForm, ClientUserCreationForm, SystemUserForm, DeviceForm, DeviceCSVUploadForm, DeleteDeviceForm, DeleteForm, PatrolReportUploadForm # <--- ADD new forms
from wtforms import ValidationError # For custom validation in routes if needed

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_ultraguard_admin():
            flash('Access Denied.', 'danger')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

# Flask-Login user loader function
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@bp.route('/login', methods=['GET', 'POST'])
def login():
    print(f"Login route accessed. Method: {request.method}") # DEBUG
    if current_user.is_authenticated and hasattr(current_user, 'is_ultraguard_admin') and current_user.is_ultraguard_admin():
        print("User already authenticated as admin, redirecting to dashboard.") # DEBUG
        return redirect(url_for('admin.dashboard'))
    
    form = LoginForm()
    print(f"Form created. CSRF enabled: {form.meta.csrf}") # DEBUG
    
    if form.validate_on_submit():
        print("Form validated on submit.") # DEBUG
        username_or_email_input = form.username_or_email.data.strip()
        print(f"Attempting login for: {username_or_email_input}") # DEBUG
        
        user_query = User.query.filter(
            (User.username == username_or_email_input) | (User.email == username_or_email_input)
        ).first()

        if user_query:
            print(f"User found: {user_query.username}, Role: {user_query.role}, Active: {user_query.is_active}") # DEBUG
            password_check = user_query.check_password(form.password.data)
            print(f"Password check result: {password_check}") # DEBUG
        else:
            print("User not found by username/email.") # DEBUG

        if user_query is None or not user_query.check_password(form.password.data):
            print("Condition 1 FAIL: Invalid credentials.") # DEBUG
            flash('Invalid username/email or password.', 'danger')
            return redirect(url_for('admin.login'))
        
        if not user_query.is_active:
            print("Condition 2 FAIL: User not active.") # DEBUG
            flash('Your account has been deactivated. Please contact support.', 'warning')
            return redirect(url_for('admin.login'))

        if not hasattr(user_query, 'is_ultraguard_admin') or not user_query.is_ultraguard_admin():
            print(f"Condition 3 FAIL: User is not UG Admin. Role is '{user_query.role}'.") # DEBUG
            flash('Access denied. This login is for Ultraguard administrators only.', 'danger')
            return redirect(url_for('admin.login'))

        print("All login conditions PASSED. Logging user in.") # DEBUG
        login_user(user_query, remember=form.remember_me.data)
        user_query.last_login_at = datetime.now(timezone.utc)
        db.session.commit()
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '' or urlparse(next_page).scheme != '':
            next_page = url_for('admin.dashboard')
        flash(f'Welcome back, {user_query.username}!', 'success')
        return redirect(next_page)
    else:
        if request.method == 'POST':
            print("Form FAILED validate_on_submit.") # DEBUG
            print(f"Form errors: {form.errors}") # DEBUG
    return render_template('admin/login.html', title='Admin Login', form=form)

@bp.route('/logout')
@login_required # Ensures user must be logged in to logout
def logout():
    logout_user()
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('admin.login'))

@bp.route('/') # Default route for /admin/
@bp.route('/dashboard')
@login_required # Protect this route
def dashboard():
    # Ensure only Ultraguard Admins can access this dashboard
    if not hasattr(current_user, 'is_ultraguard_admin') or not current_user.is_ultraguard_admin():
         flash('Access Denied: You do not have permission to view this page.', 'danger')
         logout_user() # Log them out if they somehow got here without proper role
         return redirect(url_for('admin.login'))
         
    # For now, a simple dashboard. We'll add stats later.
    # Example stats (to be uncommented when Client, Device models are used in queries):
    # from app.models import Client, Device
    num_clients = Client.query.count()
    num_devices = Device.query.count()
    ug_admin_users_count = User.query.filter_by(role='ULTRAGUARD_ADMIN').count() # Example for another card

    return render_template('dashboard.html', 
                           title='Admin Dashboard', 
                           num_clients=num_clients, 
                           num_devices=num_devices,
                           ug_admin_users_count=ug_admin_users_count) # Pass the counts to the template

# --- Client Management Routes ---
@bp.route('/clients')
@login_required
def list_clients():
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    page = request.args.get('page', 1, type=int)
    clients = Client.query.order_by(Client.name.asc()).paginate(page=page, per_page=current_app.config.get('ITEMS_PER_PAGE', 10))
    return render_template('admin/clients/list_clients.html', title='Manage Clients', clients=clients)

@bp.route('/client/add', methods=['GET', 'POST'])
@login_required
def add_client():
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    client_form = ClientForm()
    user_form = ClientUserCreationForm()

    if client_form.validate_on_submit() and user_form.validate_on_submit() and request.method == 'POST':
        try:
            # Check if client name already exists
            existing_client = Client.query.filter_by(name=client_form.name.data).first()
            if existing_client:
                flash('A client with this name already exists.', 'danger')
                return render_template('admin/clients/add_client.html',
                                    title='Add New Client',
                                    client_form=client_form,
                                    user_form=user_form)

            # Check if username or email is already taken
            existing_user = User.query.filter(
                (User.username == user_form.username.data) |
                (User.email == user_form.email.data)
            ).first()
            if existing_user:
                if existing_user.username == user_form.username.data:
                    flash('This username is already taken.', 'danger')
                else:
                    flash('This email is already registered.', 'danger')
                return render_template('admin/clients/add_client.html',
                                    title='Add New Client',
                                    client_form=client_form,
                                    user_form=user_form)

            # Create new client
            new_client = Client(
                name=client_form.name.data,
                contact_person=client_form.contact_person.data,
                contact_email=client_form.contact_email.data,
                contact_phone=client_form.contact_phone.data,
                is_active=client_form.is_active.data
            )
            db.session.add(new_client)
            db.session.flush()  # Get the new_client.id without committing

            # Create client admin user
            client_admin_user = User(
                username=user_form.username.data,
                email=user_form.email.data,
                role='CLIENT_ADMIN',
                client_id=new_client.id,
                is_active=True
            )
            client_admin_user.set_password(user_form.password.data)
            db.session.add(client_admin_user)
            
            # Commit both client and user
            db.session.commit()
            
            flash(f'Client "{new_client.name}" and their admin user "{client_admin_user.username}" created successfully!', 'success')
            return redirect(url_for('admin.list_clients'))

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError creating client {client_form.name.data}: {e}", exc_info=True)
            if 'UNIQUE constraint failed' in str(e).lower():
                if 'client.name' in str(e).lower():
                    flash('Error: A client with this name already exists.', 'danger')
                elif 'user.username' in str(e).lower():
                    flash('Error: This username is already taken.', 'danger')
                elif 'user.email' in str(e).lower():
                    flash('Error: This email is already registered.', 'danger')
                else:
                    flash('Error: This operation violates a data integrity rule.', 'danger')
            else:
                flash('Error: This operation violates a data integrity rule.', 'danger')
            return render_template('admin/clients/add_client.html',
                                title='Add New Client',
                                client_form=client_form,
                                user_form=user_form)

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError creating client {client_form.name.data}: {e}", exc_info=True)
            flash('A database error occurred while creating the client. Please try again.', 'danger')
            return render_template('admin/clients/add_client.html',
                                title='Add New Client',
                                client_form=client_form,
                                user_form=user_form)

        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error creating client {client_form.name.data}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return render_template('admin/clients/add_client.html',
                                title='Add New Client',
                                client_form=client_form,
                                user_form=user_form)

    return render_template('admin/clients/add_client.html',
                         title='Add New Client',
                         client_form=client_form,
                         user_form=user_form)

@bp.route('/client/edit/<int:client_id>', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    client = db.session.get(Client, client_id)
    if client is None:
        abort(404, description=f"Client with ID {client_id} not found.")
    form = ClientForm(obj=client)

    if form.validate_on_submit():
        try:
            # Check if new name conflicts with another client (excluding itself)
            if form.name.data != client.name:
                existing_client = Client.query.filter_by(name=form.name.data).first()
                if existing_client:
                    flash('Another client with this name already exists.', 'danger')
                    return render_template('admin/clients/edit_client.html', 
                                        title=f'Edit Client: {client.name}',
                                        form=form, client=client)

            # Update client data
            client.name = form.name.data
            client.contact_person = form.contact_person.data
            client.contact_email = form.contact_email.data
            client.contact_phone = form.contact_phone.data
            client.is_active = form.is_active.data
            
            db.session.commit()
            flash(f'Client "{client.name}" updated successfully!', 'success')
            return redirect(url_for('admin.list_clients'))

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError updating client {client_id}: {e}", exc_info=True)
            if 'UNIQUE constraint failed' in str(e).lower() and 'client.name' in str(e).lower():
                flash('Error: A client with this name already exists.', 'danger')
            else:
                flash('Error: This operation violates a data integrity rule.', 'danger')
            return render_template('admin/clients/edit_client.html', 
                                title=f'Edit Client: {client.name}',
                                form=form, client=client)

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError updating client {client_id}: {e}", exc_info=True)
            flash('A database error occurred while updating the client. Please try again.', 'danger')
            return render_template('admin/clients/edit_client.html', 
                                title=f'Edit Client: {client.name}',
                                form=form, client=client)

        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error updating client {client_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return render_template('admin/clients/edit_client.html', 
                                title=f'Edit Client: {client.name}',
                                form=form, client=client)
            
    return render_template('admin/clients/edit_client.html', 
                        title=f'Edit Client: {client.name}',
                        form=form, client=client)

# We'll need a way to edit a Client's admin users or add more.
# This is more complex and could be a separate view linked from the client list or edit page.
# For now, focus on creating the initial client admin.

# --- System User Management Routes (Ultraguard Admins and Client Admins/Staff) ---
@bp.route('/system-users') # This was a placeholder, let's implement it
@login_required
def list_system_users():
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    page = request.args.get('page', 1, type=int)
    # Fetch all users, perhaps with client info
    users = User.query.order_by(User.username.asc()).paginate(page=page, per_page=current_app.config.get('ITEMS_PER_PAGE', 10))
    delete_form = DeleteForm()  # Use the DeleteForm class for CSRF protection
    return render_template('admin/system_users/list_users.html', 
                         title='Manage System Users', 
                         users=users,
                         delete_form=delete_form)

@bp.route('/system-user/add', methods=['GET', 'POST'])
@login_required
def add_system_user():
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    form = SystemUserForm()
    if form.validate_on_submit():
        try:
            # Check for username uniqueness
            existing_user = User.query.filter_by(username=form.username.data).first()
            if existing_user:
                flash('This username is already taken.', 'danger')
                return render_template('admin/system_users/add_edit_user.html',
                                    title='Add New System User',
                                    form=form,
                                    form_legend='Create New System User')

            # Check for email uniqueness
            existing_email = User.query.filter_by(email=form.email.data).first()
            if existing_email:
                flash('This email is already registered.', 'danger')
                return render_template('admin/system_users/add_edit_user.html',
                                    title='Add New System User',
                                    form=form,
                                    form_legend='Create New System User')

            # Create new user
            new_user = User(
                username=form.username.data,
                email=form.email.data,
                role=form.role.data,
                is_active=form.is_active.data
            )

            # Set client_id based on role
            if form.role.data != 'ULTRAGUARD_ADMIN' and form.client_id.data and form.client_id.data != 0:
                # Verify client exists
                client = db.session.get(Client, form.client_id.data)
                if not client:
                    flash('Selected client does not exist.', 'danger')
                    return render_template('admin/system_users/add_edit_user.html',
                                        title='Add New System User',
                                        form=form,
                                        form_legend='Create New System User')
                new_user.client_id = form.client_id.data
            elif form.role.data == 'ULTRAGUARD_ADMIN':
                new_user.client_id = None  # Ensure UG Admins are not tied to a client

            # Set password
            new_user.set_password(form.password.data)
            
            # Add and commit
            db.session.add(new_user)
            db.session.commit()
            
            flash(f'User "{new_user.username}" created successfully!', 'success')
            current_app.logger.info(f"Successfully created new system user: {new_user.username} (Role: {new_user.role})")
            return redirect(url_for('admin.list_system_users'))

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError creating system user: {e}", exc_info=True)
            if 'UNIQUE constraint failed' in str(e).lower():
                if 'user.username' in str(e).lower():
                    flash('Error: This username is already taken.', 'danger')
                elif 'user.email' in str(e).lower():
                    flash('Error: This email is already registered.', 'danger')
                else:
                    flash('Error: This operation violates a data integrity rule.', 'danger')
            else:
                flash('Error: This operation violates a data integrity rule.', 'danger')
            return render_template('admin/system_users/add_edit_user.html',
                                title='Add New System User',
                                form=form,
                                form_legend='Create New System User')

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError creating system user: {e}", exc_info=True)
            flash('A database error occurred while creating the user. Please try again.', 'danger')
            return render_template('admin/system_users/add_edit_user.html',
                                title='Add New System User',
                                form=form,
                                form_legend='Create New System User')

        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error creating system user: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return render_template('admin/system_users/add_edit_user.html',
                                title='Add New System User',
                                form=form,
                                form_legend='Create New System User')

    return render_template('admin/system_users/add_edit_user.html',
                         title='Add New System User',
                         form=form,
                         form_legend='Create New System User')

@bp.route('/system-user/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_system_user(user_id):
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    user_to_edit = db.session.get(User, user_id)
    if user_to_edit is None:
        abort(404, description=f"User with ID {user_id} not found.")
        
    form = SystemUserForm(obj=user_to_edit)
    form.obj = user_to_edit

    if form.validate_on_submit():
        try:
            # Check for username uniqueness if changed
            if form.username.data != user_to_edit.username:
                existing_user = User.query.filter_by(username=form.username.data).first()
                if existing_user:
                    flash('This username is already taken.', 'danger')
                    return render_template('admin/system_users/add_edit_user.html',
                                        title=f'Edit User: {user_to_edit.username}',
                                        form=form,
                                        user_to_edit=user_to_edit,
                                        form_legend=f'Update User: {user_to_edit.username}')

            # Check for email uniqueness if changed
            if form.email.data != user_to_edit.email:
                existing_email = User.query.filter_by(email=form.email.data).first()
                if existing_email:
                    flash('This email is already registered.', 'danger')
                    return render_template('admin/system_users/add_edit_user.html',
                                        title=f'Edit User: {user_to_edit.username}',
                                        form=form,
                                        user_to_edit=user_to_edit,
                                        form_legend=f'Update User: {user_to_edit.username}')

            # Update user data
            user_to_edit.username = form.username.data
            user_to_edit.email = form.email.data
            user_to_edit.role = form.role.data
            user_to_edit.is_active = form.is_active.data

            if form.role.data != 'ULTRAGUARD_ADMIN' and form.client_id.data and form.client_id.data > 0:
                user_to_edit.client_id = form.client_id.data
            elif form.role.data == 'ULTRAGUARD_ADMIN':
                user_to_edit.client_id = None

            if form.password.data:  # Only set password if a new one was entered
                user_to_edit.set_password(form.password.data)
            
            db.session.commit()
            flash(f'User "{user_to_edit.username}" updated successfully!', 'success')
            return redirect(url_for('admin.list_system_users'))

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError updating user {user_id}: {e}", exc_info=True)
            if 'UNIQUE constraint failed' in str(e).lower():
                if 'user.username' in str(e).lower():
                    flash('Error: This username is already taken.', 'danger')
                elif 'user.email' in str(e).lower():
                    flash('Error: This email is already registered.', 'danger')
                else:
                    flash('Error: This operation violates a data integrity rule.', 'danger')
            else:
                flash('Error: This operation violates a data integrity rule.', 'danger')
            return render_template('admin/system_users/add_edit_user.html',
                                title=f'Edit User: {user_to_edit.username}',
                                form=form,
                                user_to_edit=user_to_edit,
                                form_legend=f'Update User: {user_to_edit.username}')

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError updating user {user_id}: {e}", exc_info=True)
            flash('A database error occurred while updating the user. Please try again.', 'danger')
            return render_template('admin/system_users/add_edit_user.html',
                                title=f'Edit User: {user_to_edit.username}',
                                form=form,
                                user_to_edit=user_to_edit,
                                form_legend=f'Update User: {user_to_edit.username}')

        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error updating user {user_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return render_template('admin/system_users/add_edit_user.html',
                                title=f'Edit User: {user_to_edit.username}',
                                form=form,
                                user_to_edit=user_to_edit,
                                form_legend=f'Update User: {user_to_edit.username}')
            
    elif request.method == 'GET':  # Pre-populate form fields
        form.username.data = user_to_edit.username
        form.email.data = user_to_edit.email
        form.role.data = user_to_edit.role
        form.is_active.data = user_to_edit.is_active
        if user_to_edit.role == 'ULTRAGUARD_ADMIN' or not user_to_edit.client_id:
            form.client_id.data = 0
        else:
            form.client_id.data = user_to_edit.client_id

    return render_template('admin/system_users/add_edit_user.html',
                         title=f'Edit User: {user_to_edit.username}',
                         form=form,
                         user_to_edit=user_to_edit,
                         form_legend=f'Update User: {user_to_edit.username}')

@bp.route('/system-user/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_system_user(user_id):
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        current_app.logger.warning(f"Non-admin user {current_user.id} attempted to access delete_system_user")
        return redirect(url_for('admin.dashboard'))

    form = DeleteForm()
    if not form.validate_on_submit():
        flash('Invalid form submission.', 'danger')
        current_app.logger.warning(f"Invalid form submission in delete_system_user by user {current_user.id}")
        return redirect(url_for('admin.list_system_users'))

    try:
        user_to_delete = db.session.get(User, user_id)
        if user_to_delete is None:
            flash('User not found.', 'danger')
            current_app.logger.warning(f"Attempted to delete non-existent user {user_id} by user {current_user.id}")
            return redirect(url_for('admin.list_system_users'))

        # Prevent self-deletion
        if user_to_delete.id == current_user.id:
            flash('You cannot delete your own account.', 'danger')
            current_app.logger.warning(f"User {current_user.id} attempted to self-delete")
            return redirect(url_for('admin.list_system_users'))

        # Check if this is the last superadmin
        if user_to_delete.role == 'ULTRAGUARD_ADMIN':
            superadmin_count = User.query.filter_by(role='ULTRAGUARD_ADMIN', is_active=True).count()
            if superadmin_count <= 1:
                flash('Cannot delete the last active Ultraguard Admin. At least one admin must remain in the system.', 'danger')
                current_app.logger.warning(f"Attempted to delete last active Ultraguard Admin {user_id} by user {current_user.id}")
                return redirect(url_for('admin.list_system_users'))

        # Check for dependent records
        if user_to_delete.client_id:
            # Check if this is the last admin for their client
            if user_to_delete.role == 'CLIENT_ADMIN':
                client_admin_count = User.query.filter_by(
                    client_id=user_to_delete.client_id,
                    role='CLIENT_ADMIN',
                    is_active=True
                ).count()
                if client_admin_count <= 1:
                    flash(f'Cannot delete the last active admin for client {user_to_delete.client.name}. At least one admin must remain.', 'danger')
                    current_app.logger.warning(f"Attempted to delete last active admin for client {user_to_delete.client_id} by user {current_user.id}")
                    return redirect(url_for('admin.list_system_users'))

        # Log the deletion attempt
        current_app.logger.info(f"Admin {current_user.id} attempting to delete system user {user_id} ({user_to_delete.username})")
        
        # Delete the user
        db.session.delete(user_to_delete)
        db.session.commit()
        
        flash(f'User "{user_to_delete.username}" deleted successfully.', 'success')
        current_app.logger.info(f"Admin {current_user.id} successfully deleted system user {user_id} ({user_to_delete.username})")
        return redirect(url_for('admin.list_system_users'))

    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.warning(f"IntegrityError deleting system user {user_id}: {e}", exc_info=True)
        if 'FOREIGN KEY constraint failed' in str(e).lower():
            flash('Error: Cannot delete user because they have associated records in the system.', 'danger')
        else:
            flash('Error: Cannot delete user due to database constraints.', 'danger')
        return redirect(url_for('admin.list_system_users'))

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"SQLAlchemyError deleting system user {user_id}: {e}", exc_info=True)
        flash('A database error occurred while deleting the user. Please try again.', 'danger')
        return redirect(url_for('admin.list_system_users'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error deleting system user {user_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again or contact support.', 'danger')
        return redirect(url_for('admin.list_system_users'))

# Update placeholder routes from previous step
@bp.route('/devices', methods=['GET'])
@login_required
def list_all_devices():
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Get filter parameters
    client_filter = request.args.get('client_filter', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of devices per page
    
    # Base query
    query = Device.query
    
    # Apply client filter if specified
    if client_filter:
        query = query.filter_by(client_id=client_filter)
    
    # Get all clients for the filter dropdown
    clients_for_filter = Client.query.order_by(Client.name).all()
    
    # Execute query with pagination
    devices = query.order_by(Device.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # Create delete form for CSRF protection
    delete_form = DeleteForm()
    
    return render_template('admin/devices/list_all_devices.html',
                         title='All Devices',
                         devices=devices,
                         clients_for_filter=clients_for_filter,
                         selected_client_id_filter=client_filter,
                         delete_form=delete_form)  # Pass the delete form to the template

# --- Device Management Routes ---
@bp.route('/devices')
@login_required
def list_devices():
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    page = request.args.get('page', 1, type=int)
    client_id = request.args.get('client_id', type=int)
    
    # Base query
    query = Device.query
    
    # Filter by client if specified
    if client_id:
        query = query.filter_by(client_id=client_id)
    
    # Order by client name and device name
    devices = query.order_by(Device.client_id, Device.name).paginate(
        page=page, 
        per_page=current_app.config.get('ITEMS_PER_PAGE', 10)
    )
    
    # Get all clients for the filter dropdown
    clients = Client.query.order_by(Client.name).all()
    
    # Create form for delete confirmation
    delete_form = DeleteDeviceForm()
    
    return render_template('admin/devices/list_devices.html', 
                         title='Manage Devices',
                         devices=devices,
                         clients=clients,
                         selected_client_id=client_id,
                         delete_form=delete_form)

@bp.route('/client/<int:client_id>/devices')
@login_required
def list_client_devices(client_id):
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    client = db.session.get(Client, client_id)
    if client is None:
        abort(404, description=f"Client with ID {client_id} not found.")
    page = request.args.get('page', 1, type=int)
    
    devices = Device.query.filter_by(client_id=client_id).order_by(Device.name.asc()).paginate(
        page=page, per_page=current_app.config.get('ITEMS_PER_PAGE', 10)
    )
    
    # Form for uploading CSV, pass client_id to it
    csv_upload_form = DeviceCSVUploadForm(client_id=client.id)
    # Create an instance of the delete form
    delete_form = DeleteForm()

    return render_template('admin/devices/list_devices.html',
                            title=f'Devices for {client.name}',
                            client=client,
                            devices=devices,
                            csv_upload_form=csv_upload_form,
                            delete_form=delete_form)  # Pass delete_form to template

@bp.route('/client/<int:client_id>/device/add', methods=['GET', 'POST'])
@login_required
def add_client_device(client_id):
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    client = db.session.get(Client, client_id)
    if client is None:
        abort(404, description=f"Client with ID {client_id} not found.")
    form = DeviceForm()
    # Pre-populate the client_id hidden field with the client from the URL
    form.client_id.data = client.id

    # Populate client choices for the dropdown, though it will be hidden/pre-selected
    form.client_id.choices = [(c.id, c.name) for c in Client.query.order_by(Client.name).all()]

    if form.validate_on_submit():
        device = Device(
            name=form.name.data,
            imei=form.imei.data,
            model=form.model.data,
            client_id=client_id,
            status=form.status.data,
            last_seen=form.last_seen.data,
            notes=form.notes.data
        )

        try:
            db.session.add(device)
            db.session.commit()
            flash(f'Device "{device.name}" added successfully for {client.name}!', 'success')
            # Redirect back to the client's device list
            return redirect(url_for('admin.list_client_devices', client_id=client_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding device: {str(e)}', 'danger')
            current_app.logger.error(f"Error adding device for client {client_id}: {e}")

    # For GET request or validation errors
    return render_template('admin/devices/add_edit_device.html',
                         title=f'Add New Device for {client.name}',
                         form=form,
                         form_legend=f'Add New Device for {client.name}')

@bp.route('/device/add', methods=['GET', 'POST'])
@login_required
def add_device():
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    form = DeviceForm()
    # Populate client choices
    form.client_id.choices = [(c.id, c.name) for c in Client.query.order_by(Client.name).all()]
    
    if form.validate_on_submit():
        try:
            # Check if device name is unique for this client
            existing_device = Device.query.filter_by(
                name=form.name.data,
                client_id=form.client_id.data
            ).first()
            if existing_device:
                flash('A device with this name already exists for this client.', 'danger')
                return render_template('admin/devices/add_edit_device.html',
                                    title='Add New Device',
                                    form=form,
                                    form_legend='Add New Device')

            # Check if IMEI is unique
            if form.imei.data:
                existing_imei = Device.query.filter_by(imei=form.imei.data).first()
                if existing_imei:
                    flash('A device with this IMEI already exists.', 'danger')
                    return render_template('admin/devices/add_edit_device.html',
                                        title='Add New Device',
                                        form=form,
                                        form_legend='Add New Device')

            device = Device(
                name=form.name.data,
                imei=form.imei.data,
                model=form.model.data,
                client_id=form.client_id.data,
                status=form.status.data,
                last_seen=form.last_seen.data,
                notes=form.notes.data
            )
            
            db.session.add(device)
            db.session.commit()
            flash(f'Device "{device.name}" added successfully!', 'success')
            return redirect(url_for('admin.list_devices'))

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError adding device {form.name.data}: {e}", exc_info=True)
            if 'UNIQUE constraint failed' in str(e).lower():
                if 'device.name' in str(e).lower():
                    flash('Error: A device with this name already exists for this client.', 'danger')
                elif 'device.imei' in str(e).lower():
                    flash('Error: A device with this IMEI already exists.', 'danger')
                else:
                    flash('Error: This operation violates a data integrity rule.', 'danger')
            else:
                flash('Error: This operation violates a data integrity rule.', 'danger')
            return render_template('admin/devices/add_edit_device.html',
                                title='Add New Device',
                                form=form,
                                form_legend='Add New Device')

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError adding device {form.name.data}: {e}", exc_info=True)
            flash('A database error occurred while adding the device. Please try again.', 'danger')
            return render_template('admin/devices/add_edit_device.html',
                                title='Add New Device',
                                form=form,
                                form_legend='Add New Device')

        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error adding device {form.name.data}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return render_template('admin/devices/add_edit_device.html',
                                title='Add New Device',
                                form=form,
                                form_legend='Add New Device')
    
    return render_template('admin/devices/add_edit_device.html',
                         title='Add New Device',
                         form=form,
                         form_legend='Add New Device')

@bp.route('/device/edit/<int:device_id>', methods=['GET', 'POST'])
@login_required
def edit_device(device_id):
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    device = db.session.get(Device, device_id)
    if device is None:
        abort(404, description=f"Device with ID {device_id} not found.")
    form = DeviceForm(obj=device)
    
    # Populate client choices
    form.client_id.choices = [(c.id, c.name) for c in Client.query.order_by(Client.name).all()]
    
    if form.validate_on_submit():
        try:
            # Check if new name conflicts with another device for the same client
            if form.name.data != device.name or form.client_id.data != device.client_id:
                existing_device = Device.query.filter_by(
                    name=form.name.data,
                    client_id=form.client_id.data
                ).first()
                if existing_device and existing_device.id != device_id:
                    flash('Another device with this name already exists for this client.', 'danger')
                    return render_template('admin/devices/add_edit_device.html',
                                        title=f'Edit Device: {device.name}',
                                        form=form,
                                        form_legend='Edit Device')

            # Check if new IMEI conflicts with another device
            if form.imei.data and form.imei.data != device.imei:
                existing_imei = Device.query.filter_by(imei=form.imei.data).first()
                if existing_imei and existing_imei.id != device_id:
                    flash('Another device with this IMEI already exists.', 'danger')
                    return render_template('admin/devices/add_edit_device.html',
                                        title=f'Edit Device: {device.name}',
                                        form=form,
                                        form_legend='Edit Device')

            # Update device data
            device.name = form.name.data
            device.imei = form.imei.data
            device.model = form.model.data
            device.client_id = form.client_id.data
            device.status = form.status.data
            device.last_seen = form.last_seen.data
            device.notes = form.notes.data
            
            db.session.commit()
            flash(f'Device "{device.name}" updated successfully!', 'success')
            return redirect(url_for('admin.list_devices'))

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError updating device {device_id}: {e}", exc_info=True)
            if 'UNIQUE constraint failed' in str(e).lower():
                if 'device.name' in str(e).lower():
                    flash('Error: Another device with this name already exists for this client.', 'danger')
                elif 'device.imei' in str(e).lower():
                    flash('Error: Another device with this IMEI already exists.', 'danger')
                else:
                    flash('Error: This operation violates a data integrity rule.', 'danger')
            else:
                flash('Error: This operation violates a data integrity rule.', 'danger')
            return render_template('admin/devices/add_edit_device.html',
                                title=f'Edit Device: {device.name}',
                                form=form,
                                form_legend='Edit Device')

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError updating device {device_id}: {e}", exc_info=True)
            flash('A database error occurred while updating the device. Please try again.', 'danger')
            return render_template('admin/devices/add_edit_device.html',
                                title=f'Edit Device: {device.name}',
                                form=form,
                                form_legend='Edit Device')

        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error updating device {device_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return render_template('admin/devices/add_edit_device.html',
                                title=f'Edit Device: {device.name}',
                                form=form,
                                form_legend='Edit Device')
    
    return render_template('admin/devices/add_edit_device.html',
                         title=f'Edit Device: {device.name}',
                         form=form,
                         form_legend='Edit Device')

@bp.route('/devices/upload', methods=['GET', 'POST'])
@login_required
def upload_devices():
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    form = DeviceCSVUploadForm()
    # Populate client choices
    form.client_id.choices = [(c.id, c.name) for c in Client.query.order_by(Client.name).all()]
    
    if form.validate_on_submit():
        if 'csv_file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(request.url)
        
        file = request.files['csv_file']
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file', 'danger')
            return redirect(request.url)
        
        try:
            # Verify client exists
            client = db.session.get(Client, form.client_id.data)
            if not client:
                flash('Selected client does not exist.', 'danger')
                return redirect(url_for('admin.upload_devices'))

            # Read CSV file content
            try:
                stream = StringIO(file.stream.read().decode("UTF-8"), newline=None)
                csv_reader = csv.DictReader(stream)  # Use DictReader as your CSV has headers
            except UnicodeDecodeError:
                flash('Error: The CSV file must be encoded in UTF-8.', 'danger')
                current_app.logger.error("CSV file encoding error - not UTF-8")
                return redirect(url_for('admin.upload_devices'))
            except csv.Error as e:
                flash(f'Error reading CSV file: {str(e)}', 'danger')
                current_app.logger.error(f"CSV parsing error: {e}")
                return redirect(url_for('admin.upload_devices'))

            # Required columns
            required_cols = ['imei', 'name', 'model']
            for col in required_cols:
                if col not in csv_reader.fieldnames:
                    flash(f"CSV file is missing required column: '{col}'", 'danger')
                    return redirect(url_for('admin.upload_devices'))

            devices_added_count = 0
            errors_found = []
            imei_duplicates = set()
            csv_imeis = {}
            valid_rows = []

            # First pass: validate all rows and collect errors
            for row_num, row in enumerate(csv_reader, 1):
                imei = row.get('imei', '').strip()
                name = row.get('name', '').strip()
                model = row.get('model', '').strip() or 'Unknown'
                status = row.get('status', 'active').strip().lower() or 'active'
                last_seen_str = row.get('last_seen', '').strip()
                notes = row.get('notes', '').strip()

                # Parse last_seen if provided
                last_seen = None
                if last_seen_str:
                    try:
                        last_seen = datetime.strptime(last_seen_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        errors_found.append(f"Row {row_num}: Invalid last_seen format '{last_seen_str}'. Use YYYY-MM-DD HH:MM:SS.")
                        continue

                # Check for duplicate IMEI in CSV
                if imei:
                    if imei in csv_imeis:
                        imei_duplicates.add(imei)
                        errors_found.append(f"Row {row_num}: IMEI '{imei}' is duplicated in the CSV (first occurrence at row {csv_imeis[imei]}).")
                    else:
                        csv_imeis[imei] = row_num

                # Validate IMEI format
                if not imei:
                    errors_found.append(f"Row {row_num}: IMEI is missing.")
                    continue

                if not imei.isdigit() or not (14 <= len(imei) <= 16):
                    errors_found.append(f"Row {row_num}: Invalid IMEI format for '{imei}'. Must be 14-16 digits.")
                    continue

                # Check for duplicate IMEI in database
                existing_device = Device.query.filter_by(imei=imei).first()
                if existing_device:
                    errors_found.append(f"Row {row_num}: IMEI '{imei}' already exists in the system (Device ID: {existing_device.id}, Client: {existing_device.client.name}).")
                    continue

                # Validate status
                if status not in ['active', 'inactive']:
                    errors_found.append(f"Row {row_num}: Invalid status '{status}'. Must be 'active' or 'inactive'.")
                    continue

                # If all validations pass, add to valid_rows
                valid_rows.append({
                    'imei': imei,
                    'name': name or f"Device {imei[:4]}...{imei[-4:]}",
                    'model': model,
                    'status': status,
                    'last_seen': last_seen,
                    'notes': notes
                })

            # If there are validation errors, don't proceed with import
            if errors_found:
                for error in errors_found:
                    flash(error, 'danger')
                flash('No devices were added due to errors in the CSV file. Please correct and re-upload.', 'warning')
                return redirect(url_for('admin.upload_devices'))

            # Second pass: add valid devices to database
            try:
                for device_data in valid_rows:
                    new_device = Device(
                        client_id=form.client_id.data,
                        imei=device_data['imei'],
                        name=device_data['name'],
                        model=device_data['model'],
                        status=device_data['status'],
                        last_seen=device_data['last_seen'],
                        notes=device_data['notes']
                    )
                    db.session.add(new_device)
                    devices_added_count += 1

                db.session.commit()
                flash(f'{devices_added_count} new devices successfully imported from CSV!', 'success')
                current_app.logger.info(f"Successfully imported {devices_added_count} devices for client {form.client_id.data}")

            except IntegrityError as e:
                db.session.rollback()
                current_app.logger.warning(f"IntegrityError during device import: {e}", exc_info=True)
                if 'UNIQUE constraint failed' in str(e).lower():
                    if 'device.imei' in str(e).lower():
                        flash('Error: One or more devices could not be added due to duplicate IMEI numbers.', 'danger')
                    elif 'device.name' in str(e).lower():
                        flash('Error: One or more devices could not be added due to duplicate names for the same client.', 'danger')
                    else:
                        flash('Error: Database constraint violation occurred during import.', 'danger')
                else:
                    flash('Error: Database constraint violation occurred during import.', 'danger')
                return redirect(url_for('admin.upload_devices'))

            except SQLAlchemyError as e:
                db.session.rollback()
                current_app.logger.error(f"SQLAlchemyError during device import: {e}", exc_info=True)
                flash('A database error occurred during import. Please try again.', 'danger')
                return redirect(url_for('admin.upload_devices'))

            return redirect(url_for('admin.list_devices'))

        except Exception as e:
            db.session.rollback()
            flash('An unexpected error occurred during CSV processing. Please try again or contact support.', 'danger')
            current_app.logger.critical(f"Unexpected error during device import: {e}", exc_info=True)
            return redirect(url_for('admin.upload_devices'))
    
    return render_template('admin/devices/upload_devices.html',
                         title='Upload Devices',
                         form=form)

@bp.route('/device/delete/<int:device_id>', methods=['POST'])
@login_required
def delete_device(device_id):
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    form = DeleteForm()
    if form.validate_on_submit():
        device = db.session.get(Device, device_id)
        if device is None:
            abort(404, description=f"Device with ID {device_id} not found.")
        client_id_redirect = device.client_id  # Store before deleting
        
        try:
            # Log the deletion attempt
            current_app.logger.info(f"Attempting to delete device {device_id} (IMEI: {device.imei})")
            
            # Check for any dependent records (e.g., patrol reports, shifts)
            # This is a placeholder - add actual checks based on your model relationships
            if hasattr(device, 'patrol_reports') and device.patrol_reports:
                flash('Cannot delete device: It has associated patrol reports.', 'danger')
                current_app.logger.warning(f"Cannot delete device {device_id}: Has associated patrol reports")
                return redirect(url_for('admin.list_client_devices', client_id=client_id_redirect))
            
            # Delete the device
            db.session.delete(device)
            db.session.commit()
            
            flash(f'Device "{device.name}" (IMEI: {device.imei}) deleted successfully.', 'success')
            current_app.logger.info(f"Successfully deleted device {device_id}")
            
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError deleting device {device_id}: {e}", exc_info=True)
            flash('Cannot delete device: It has associated records that must be deleted first.', 'danger')
            return redirect(url_for('admin.list_client_devices', client_id=client_id_redirect))

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError deleting device {device_id}: {e}", exc_info=True)
            flash('A database error occurred while deleting the device. Please try again.', 'danger')
            return redirect(url_for('admin.list_client_devices', client_id=client_id_redirect))

        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error deleting device {device_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return redirect(url_for('admin.list_client_devices', client_id=client_id_redirect))
    else:
        flash('Invalid request for deletion.', 'warning')
        current_app.logger.warning(f"Invalid deletion request for device {device_id}")

    # Redirect back to the appropriate device list
    if 'client_id_redirect' in locals() and client_id_redirect:
        return redirect(url_for('admin.list_client_devices', client_id=client_id_redirect))
    return redirect(url_for('admin.list_all_devices'))

# --- Patrol Report Upload Route ---
@bp.route('/reports/upload', methods=['GET', 'POST'])
@login_required
def upload_patrol_report():
    if not current_user.is_ultraguard_admin(): 
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    form = PatrolReportUploadForm()

    if form.validate_on_submit():
        try:
            shift_id = form.shift_id.data
            report_file = form.report_file.data
            source_system_notes = form.source_system.data

            # Validate shift exists
            selected_shift = db.session.get(Shift, shift_id)
            if not selected_shift:
                flash('Invalid shift selected.', 'danger')
                return redirect(url_for('admin.upload_patrol_report'))

            # Secure the filename
            filename = secure_filename(report_file.filename)
            
            # Create a unique filename to prevent collisions
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            
            # Ensure the upload directory exists
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'patrol_reports')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save the file
            file_path = os.path.join(upload_dir, unique_filename)
            report_file.save(file_path)
            
            # Create the UploadedPatrolReport record
            report = UploadedPatrolReport(
                shift_id=shift_id,
                file_path=file_path,
                original_filename=filename,
                source_system=source_system_notes,
                uploaded_by=current_user.id,
                upload_timestamp=datetime.now()
            )
            
            db.session.add(report)
            db.session.commit()
            flash('Patrol report uploaded successfully!', 'success')
            return redirect(url_for('admin.upload_patrol_report'))

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError uploading patrol report: {e}", exc_info=True)
            # Clean up the uploaded file if it exists
            if 'file_path' in locals() and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    current_app.logger.error(f"Error cleaning up file {file_path}: {cleanup_error}")
            flash('Error: This operation violates a data integrity rule.', 'danger')
            return render_template('admin/reports/upload_report.html',
                                title='Upload Patrol Report',
                                form=form)

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError uploading patrol report: {e}", exc_info=True)
            # Clean up the uploaded file if it exists
            if 'file_path' in locals() and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    current_app.logger.error(f"Error cleaning up file {file_path}: {cleanup_error}")
            flash('A database error occurred while saving the report. Please try again.', 'danger')
            return render_template('admin/reports/upload_report.html',
                                title='Upload Patrol Report',
                                form=form)

        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error uploading patrol report: {e}", exc_info=True)
            # Clean up the uploaded file if it exists
            if 'file_path' in locals() and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as cleanup_error:
                    current_app.logger.error(f"Error cleaning up file {file_path}: {cleanup_error}")
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return render_template('admin/reports/upload_report.html',
                                title='Upload Patrol Report',
                                form=form)

    return render_template('admin/reports/upload_report.html',
                         title='Upload Patrol Report',
                         form=form)

@bp.route('/landing_redirect')
def landing_redirect():
    if current_user.is_authenticated and hasattr(current_user, 'is_ultraguard_admin') and current_user.is_ultraguard_admin():
        return redirect(url_for('admin.dashboard'))
    # elif current_user.is_authenticated and hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type():
    #     return redirect(url_for('client_portal.dashboard'))  # If client portal exists
    else:
        # Default to admin login if no one is logged in
        return redirect(url_for('admin.login')) 

@bp.route('/shifts/view/<int:shift_id>')
@login_required
@admin_required
def view_shift(shift_id):
    selected_shift = db.session.get(Shift, shift_id)
    if selected_shift is None:
        flash('Shift not found.', 'danger')
        return redirect(url_for('admin.shifts'))
    # ... existing code ... 

@bp.route('/clients/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_client():
    form = ClientForm()
    if form.validate_on_submit():
        try:
            client = Client(
                name=form.name.data,
                contact_name=form.contact_name.data,
                contact_email=form.contact_email.data,
                contact_phone=form.contact_phone.data,
                address=form.address.data,
                notes=form.notes.data
            )
            db.session.add(client)
            db.session.commit()
            flash('Client created successfully!', 'success')
            return redirect(url_for('admin.list_clients'))
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError creating client {form.name.data}: {e}", exc_info=True)
            if 'UNIQUE constraint failed' in str(e).lower() and 'client.name' in str(e).lower():
                flash('Error: A client with this name already exists.', 'danger')
            else:
                flash('Error: This operation violates a data integrity rule.', 'danger')
            return render_template('admin/clients/create.html', form=form, title='Create Client')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError creating client {form.name.data}: {e}", exc_info=True)
            flash('A database error occurred while creating the client. Please try again.', 'danger')
            return render_template('admin/clients/create.html', form=form, title='Create Client')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error creating client {form.name.data}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            return render_template('admin/clients/create.html', form=form, title='Create Client')
    return render_template('admin/clients/create.html', form=form, title='Create Client')

@bp.route('/client/delete/<int:client_id>', methods=['POST'])
@login_required
def delete_client(client_id):
    if not current_user.is_ultraguard_admin():
        flash('Access Denied.', 'danger')
        return redirect(url_for('admin.dashboard'))

    form = DeleteForm()
    if not form.validate_on_submit():
        flash('Invalid form submission.', 'danger')
        return redirect(url_for('admin.list_clients'))

    try:
        client = db.session.get(Client, client_id)
        if client is None:
            flash('Client not found.', 'danger')
            return redirect(url_for('admin.list_clients'))

        # Check for dependent records
        has_users = User.query.filter_by(client_id=client_id).first() is not None
        has_devices = Device.query.filter_by(client_id=client_id).first() is not None
        has_sites = Site.query.filter_by(client_id=client_id).first() is not None
        has_routes = Route.query.filter_by(client_id=client_id).first() is not None
        has_shifts = Shift.query.filter_by(client_id=client_id).first() is not None
        has_reports = UploadedPatrolReport.query.filter_by(client_id=client_id).first() is not None

        if any([has_users, has_devices, has_sites, has_routes, has_shifts, has_reports]):
            flash('Cannot delete client: There are associated records (users, devices, sites, routes, shifts, or reports). Please delete these records first.', 'danger')
            return redirect(url_for('admin.list_clients'))

        # Log the deletion attempt
        current_app.logger.info(f"Attempting to delete client {client_id} ({client.name})")
        
        # Delete the client
        db.session.delete(client)
        db.session.commit()
        
        flash(f'Client "{client.name}" deleted successfully.', 'success')
        return redirect(url_for('admin.list_clients'))

    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.warning(f"IntegrityError deleting client {client_id}: {e}", exc_info=True)
        flash('Error: Cannot delete client due to database constraints.', 'danger')
        return redirect(url_for('admin.list_clients'))

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"SQLAlchemyError deleting client {client_id}: {e}", exc_info=True)
        flash('A database error occurred while deleting the client. Please try again.', 'danger')
        return redirect(url_for('admin.list_clients'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error deleting client {client_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again or contact support.', 'danger')
        return redirect(url_for('admin.list_clients')) 