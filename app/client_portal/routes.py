from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import text, select, or_
from app import db, login_manager
from app.client_portal import bp
from app.models import User, Client, Site, Checkpoint, Route, Shift, Device, UploadedPatrolReport, RouteCheckpoint
from app.client_portal.forms import ClientLoginForm, SiteForm, PatrolReportUploadForm, CheckpointForm, RouteForm, ShiftForm
from app.exceptions import (
    FileUploadError, InvalidFileTypeError, CSVValidationError,
    DeviceIdentifierMismatchError, VerificationLogicError
)
from app.utils.file_handlers import save_uploaded_file, validate_csv_structure, read_csv_data
from app.utils.verification import verify_patrol_report
from app.utils.report_processing import handle_report_submission_and_processing
from functools import wraps

# Helper decorator for client portal access
def client_portal_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_client_user_type():
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('client_portal.login'))
        if not current_user.client_id: # Ensure client user is associated with a client
            flash('Your account is not properly configured. Please contact support.', 'danger')
            logout_user() # Or handle differently
            return redirect(url_for('client_portal.login'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_ultraguard_admin():
            flash("You are already logged in as an Ultraguard Admin. Redirecting to Admin Dashboard.", "info")
            return redirect(url_for('admin.dashboard'))
        elif current_user.is_client_user_type():
            return redirect(url_for('client_portal.dashboard'))
        else:
            # This case should ideally not happen if roles are well-defined, 
            # but as a fallback, log them out and redirect to client login.
            flash("Your session does not match a client user type. Logging out.", "warning")
            logout_user()
            return redirect(url_for('client_portal.login'))
    
    form = ClientLoginForm()
    if form.validate_on_submit():
        try:
            # Debug: Test basic database connection
            current_app.logger.info("Testing database connection...")
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
            current_app.logger.info("✅ Database connection successful!")
            
            # Debug: Test raw SQL query first
            current_app.logger.info("Testing raw SQL query...")
            try:
                raw_sql_test = db.session.execute(text("SELECT id, username FROM users LIMIT 1")).first()
                if raw_sql_test:
                    current_app.logger.info(f"✅ RAW SQL TEST SUCCESS: Fetched user ID {raw_sql_test[0]}, username {raw_sql_test[1]}")
                else:
                    current_app.logger.info("✅ RAW SQL TEST: No users found, but query executed successfully.")
            except Exception as e_raw:
                current_app.logger.error(f"❌ RAW SQL TEST FAILED: {e_raw}", exc_info=True)
                flash('Database query error. Please try again.', 'danger')
                return redirect(url_for('client_portal.login'))
            
            # Debug: Test simple SQLAlchemy query
            current_app.logger.info("Testing simple SQLAlchemy query...")
            try:
                test_query = User.query.first()
                current_app.logger.info(f"✅ Simple SQLAlchemy query successful. Found user: {test_query.username if test_query else 'None'}")
            except Exception as e_simple:
                current_app.logger.error(f"❌ Simple SQLAlchemy query failed: {e_simple}", exc_info=True)
                flash('Database query error. Please try again.', 'danger')
                return redirect(url_for('client_portal.login'))
            
            # Debug: Test SQLAlchemy 2.0 style query
            current_app.logger.info("Testing SQLAlchemy 2.0 style query...")
            try:
                username_or_email_val = form.username_or_email.data.strip()
                stmt = select(User).where(
                    or_(
                        User.username == username_or_email_val,
                        User.email == username_or_email_val
                    )
                )
                user = db.session.execute(stmt).scalar_one_or_none()
                current_app.logger.info(f"✅ SQLAlchemy 2.0 query successful. Found user: {user.username if user else 'None'}")
            except Exception as e_modern:
                current_app.logger.error(f"❌ SQLAlchemy 2.0 query failed: {e_modern}", exc_info=True)
                # Fall back to legacy style
                current_app.logger.info("Falling back to legacy SQLAlchemy query...")
                try:
                    user = User.query.filter(
                        (User.username == form.username_or_email.data.strip()) | 
                        (User.email == form.username_or_email.data.strip())
                    ).first()
                    current_app.logger.info(f"✅ Legacy query successful. Found user: {user.username if user else 'None'}")
                except Exception as e_legacy:
                    current_app.logger.error(f"❌ Legacy query also failed: {e_legacy}", exc_info=True)
                    flash('Database query error. Please try again.', 'danger')
                    return redirect(url_for('client_portal.login'))
            
        except Exception as e:
            current_app.logger.error(f"❌ Database connection failed: {e}", exc_info=True)
            flash('Database connection error. Please try again.', 'danger')
            return redirect(url_for('client_portal.login'))
        
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username/email or password', 'danger')
            return redirect(url_for('client_portal.login'))
            
        if not user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'warning')
            return redirect(url_for('client_portal.login'))
            
        if not user.is_client_user_type():
            flash('You do not have permission to access the client portal.', 'warning')
            return redirect(url_for('client_portal.login'))
            
        login_user(user, remember=form.remember_me.data)
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        
        next_page = request.args.get('next')
        if not next_page:
            next_page = url_for('client_portal.dashboard')
        else:
            url_next = urlparse(next_page)
            if url_next.netloc != '' and url_next.netloc != urlparse(request.host_url).netloc:
                flash("Redirect to external URL is not allowed.", "warning")
                next_page = url_for('client_portal.dashboard')
        
        flash(f'Welcome back, {user.username}!', 'success')
        return redirect(next_page)
        
    return render_template('client_portal/login.html', title='Client Portal Login', form=form)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been successfully logged out', 'success')
    return redirect(url_for('client_portal.login'))

@bp.route('/')
@bp.route('/dashboard')
@login_required
def dashboard():
    if not (hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type()):
        flash('Please log in to access the client portal', 'info')
        logout_user()
        return redirect(url_for('client_portal.login'))

    client = current_user.client
    if not client:
        flash('Your user account is not associated with a client company. Please contact support.', 'danger')
        logout_user()
        return redirect(url_for('client_portal.login'))

    # Get client's data
    sites = Site.query.filter_by(client_id=client.id).count()
    devices = Device.query.filter_by(client_id=client.id).count()
    routes = Route.query.filter_by(client_id=client.id).count()

    # Count checkpoints associated with client's routes using the correct join
    checkpoints = Checkpoint.query\
        .join(RouteCheckpoint, Checkpoint.id == RouteCheckpoint.checkpoint_id)\
        .join(Route, RouteCheckpoint.route_id == Route.id)\
        .filter(Route.client_id == client.id)\
        .distinct()\
        .count()

    # Count total shifts for client's devices
    total_shifts = Shift.query\
        .join(Device, Shift.device_id == Device.id)\
        .filter(Device.client_id == client.id)\
        .count()

    # Count patrol reports for client's devices through shifts
    reports = UploadedPatrolReport.query\
        .join(Shift, UploadedPatrolReport.shift_id == Shift.id)\
        .join(Device, Shift.device_id == Device.id)\
        .filter(Device.client_id == client.id)\
        .count()

    return render_template('client_portal/dashboard.html',
                         title=f'{client.name} - Dashboard',
                         client=client,
                         num_sites=sites,
                         num_devices=devices,
                         num_routes=routes,
                         num_checkpoints=checkpoints,
                         num_total_shifts=total_shifts,
                         num_reports=reports)

@bp.route('/sites')
@login_required
@client_portal_access_required
def list_sites():
    # client_id is confirmed by client_portal_access_required
    sites = Site.query.filter_by(client_id=current_user.client_id).order_by(Site.name).all()
    # For pagination (optional, can be implemented later):
    # page = request.args.get('page', 1, type=int)
    # sites_pagination = Site.query.filter_by(client_id=current_user.client_id).order_by(Site.name).paginate(
    #     page=page, per_page=current_app.config.get('ITEMS_PER_PAGE', 10), error_out=False
    # )
    # sites = sites_pagination.items
    # return render_template('client_portal/sites/list.html', title='My Sites', sites=sites, pagination=sites_pagination)
    return render_template('client_portal/sites/list.html', title='My Sites', sites=sites)

@bp.route('/sites/add', methods=['GET', 'POST'])
@login_required
@client_portal_access_required
def add_site():
    form = SiteForm(client_id=current_user.client_id) # Pass client_id for validation context
    if form.validate_on_submit():
        try:
            new_site = Site(
                client_id=current_user.client_id,
                name=form.name.data.strip(),
                address=form.address.data.strip() if form.address.data else None,
                description=form.description.data.strip() if form.description.data else None
            )
            db.session.add(new_site)
            db.session.commit()
            flash(f"Site '{new_site.name}' created successfully!", 'success')
            current_app.logger.info(f"ClientUser {current_user.id} (Client {current_user.client_id}) created site {new_site.id} ('{new_site.name}').")
            return redirect(url_for('client_portal.list_sites'))
        except IntegrityError as e: # Should be caught by form validator, but good DB fallback
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError for Client {current_user.client_id} adding site '{form.name.data}': {e}")
            flash('Error: A site with this name already exists for your client.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError for Client {current_user.client_id} adding site '{form.name.data}': {e}", exc_info=True)
            flash('A database error occurred while creating the site. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error for Client {current_user.client_id} adding site '{form.name.data}': {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return render_template('client_portal/sites/add_edit.html', title='Add New Site', form=form, form_action_label='Create Site')

@bp.route('/sites/edit/<int:site_id>', methods=['GET', 'POST'])
@login_required
@client_portal_access_required
def edit_site(site_id):
    site = db.session.get(Site, site_id)
    if not site or site.client_id != current_user.client_id:
        current_app.logger.warning(f"ClientUser {current_user.id} (Client {current_user.client_id}) attempt to edit unauthorized/non-existent site {site_id}.")
        abort(404, description="Site not found or not authorized.")

    form = SiteForm(obj=site, original_name=site.name, client_id=current_user.client_id)
    if form.validate_on_submit():
        try:
            site.name = form.name.data.strip()
            site.address = form.address.data.strip() if form.address.data else None
            site.description = form.description.data.strip() if form.description.data else None
            db.session.commit()
            flash(f"Site '{site.name}' updated successfully!", 'success')
            current_app.logger.info(f"ClientUser {current_user.id} (Client {current_user.client_id}) updated site {site.id} ('{site.name}').")
            return redirect(url_for('client_portal.list_sites'))
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError for Client {current_user.client_id} editing site {site.id} to name '{form.name.data}': {e}")
            flash('Error: A site with this name already exists for your client.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError for Client {current_user.client_id} editing site {site.id}: {e}", exc_info=True)
            flash('A database error occurred while updating the site. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error for Client {current_user.client_id} editing site {site.id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')

    return render_template('client_portal/sites/add_edit.html', title=f"Edit Site: {site.name}", form=form, site=site, form_action_label='Update Site')

@bp.route('/sites/delete/<int:site_id>', methods=['POST'])
@login_required
@client_portal_access_required
def delete_site(site_id):
    site = db.session.get(Site, site_id)
    if not site or site.client_id != current_user.client_id:
        current_app.logger.warning(f"ClientUser {current_user.id} (Client {current_user.client_id}) attempt to delete unauthorized/non-existent site {site_id}.")
        flash("Site not found or you do not have permission to delete it.", 'danger')
        return redirect(url_for('client_portal.list_sites'))

    # Dependency Check (Example: Shifts linked to this site)
    if site.shifts: # .shifts is the backref from Shift model
        flash(f"Error: Site '{site.name}' cannot be deleted because it has shifts associated with it. Please reassign or delete those shifts first.", 'danger')
        current_app.logger.warning(f"ClientUser {current_user.id} (Client {current_user.client_id}) attempt to delete site {site.id} with dependent shifts.")
        return redirect(url_for('client_portal.list_sites'))

    try:
        site_name_for_log = site.name
        db.session.delete(site)
        db.session.commit()
        flash(f"Site '{site_name_for_log}' deleted successfully.", 'success')
        current_app.logger.info(f"ClientUser {current_user.id} (Client {current_user.client_id}) deleted site {site_id} ('{site_name_for_log}').")
    except SQLAlchemyError as e: # Catch potential errors if cascade delete fails, etc.
        db.session.rollback()
        current_app.logger.error(f"SQLAlchemyError for Client {current_user.client_id} deleting site {site.id}: {e}", exc_info=True)
        flash('A database error occurred while deleting the site.', 'danger')
    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error for Client {current_user.client_id} deleting site {site.id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again or contact support.', 'danger')
        
    return redirect(url_for('client_portal.list_sites'))

@bp.route('/checkpoints')
@login_required
@client_portal_access_required
def list_checkpoints():
    checkpoints = Checkpoint.query.filter_by(client_id=current_user.client_id).order_by(Checkpoint.name).all()
    return render_template('client_portal/checkpoints/list.html', title='My Checkpoints', checkpoints=checkpoints)

@bp.route('/routes')
@login_required
@client_portal_access_required
def list_routes():
    routes = Route.query.filter_by(client_id=current_user.client_id).order_by(Route.name).all()
    return render_template('client_portal/routes/list.html', title='My Routes', routes=routes)

@bp.route('/routes/add', methods=['GET', 'POST'])
@login_required
@client_portal_access_required
def add_route():
    form = RouteForm(client_id=current_user.client_id)
    # Populate checkpoints select field with this client's checkpoints
    form.checkpoints.choices = [
        (c.id, c.name) for c in Checkpoint.query.filter_by(
            client_id=current_user.client_id
        ).order_by('name').all()
    ]

    if form.validate_on_submit():
        try:
            new_route = Route(
                client_id=current_user.client_id,
                name=form.name.data.strip(),
                description=form.description.data.strip() if form.description.data else None
            )
            
            # Find selected checkpoints and add them to the route
            selected_checkpoints = db.session.query(Checkpoint).filter(Checkpoint.id.in_(form.checkpoints.data)).all()
            
            order = 1
            for checkpoint in selected_checkpoints:
                 # Ensure the order of checkpoints is preserved as submitted
                if checkpoint in selected_checkpoints:
                    route_checkpoint = RouteCheckpoint(checkpoint=checkpoint, order=order)
                    new_route.checkpoints.append(route_checkpoint)
                    order += 1

            db.session.add(new_route)
            db.session.commit()
            
            flash(f"Route '{new_route.name}' created successfully!", 'success')
            current_app.logger.info(f"ClientUser {current_user.id} created route {new_route.id} with {len(selected_checkpoints)} checkpoints.")
            return redirect(url_for('client_portal.list_routes'))
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError for Client {current_user.client_id} adding route '{form.name.data}': {e}")
            flash('Error: A route with this name already exists.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError adding route for client {current_user.client_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error for Client {current_user.client_id} adding route: {e}", exc_info=True)
            flash('An unexpected error occurred. Please contact support.', 'danger')

    return render_template('client_portal/routes/add_edit.html', title='Add New Route', form=form, form_action_label='Create Route')

@bp.route('/routes/edit/<int:route_id>', methods=['GET', 'POST'])
@login_required
@client_portal_access_required
def edit_route(route_id):
    route = db.session.get(Route, route_id)
    if not route or route.client_id != current_user.client_id:
        abort(404)

    form = RouteForm(obj=route, original_name=route.name, client_id=current_user.client_id)
    form.checkpoints.choices = [
        (c.id, c.name) for c in Checkpoint.query.filter_by(
            client_id=current_user.client_id
        ).order_by('name').all()
    ]

    if form.validate_on_submit():
        try:
            route.name = form.name.data.strip()
            route.description = form.description.data.strip() if form.description.data else None
            
            # Efficiently update checkpoints
            # Get the set of currently associated checkpoint IDs
            current_checkpoint_ids = {rc.checkpoint_id for rc in route.checkpoints}
            # Get the set of submitted checkpoint IDs
            submitted_checkpoint_ids = set(form.checkpoints.data)

            # Find which checkpoints to add and which to remove
            ids_to_add = submitted_checkpoint_ids - current_checkpoint_ids
            ids_to_remove = current_checkpoint_ids - submitted_checkpoint_ids

            # Remove the old ones
            if ids_to_remove:
                RouteCheckpoint.query.filter(
                    RouteCheckpoint.route_id == route.id,
                    RouteCheckpoint.checkpoint_id.in_(ids_to_remove)
                ).delete(synchronize_session=False)

            # Add the new ones
            if ids_to_add:
                order = len(current_checkpoint_ids) - len(ids_to_remove) + 1
                for checkpoint_id in ids_to_add:
                    # Verify checkpoint ownership again for security
                    chk = db.session.get(Checkpoint, checkpoint_id)
                    if chk and chk.client_id == current_user.client_id:
                        db.session.add(RouteCheckpoint(route_id=route.id, checkpoint_id=checkpoint_id, order=order))
                        order += 1
            
            db.session.commit()
            flash(f"Route '{route.name}' updated successfully!", 'success')
            current_app.logger.info(f"ClientUser {current_user.id} updated route {route.id}.")
            return redirect(url_for('client_portal.list_routes'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError editing route {route_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error editing route {route_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please contact support.', 'danger')

    # Pre-populate the form with the route's current checkpoints for the GET request
    if request.method == 'GET':
        form.checkpoints.data = [rc.checkpoint_id for rc in route.checkpoints]

    return render_template('client_portal/routes/add_edit.html', title=f"Edit Route: {route.name}", form=form, route=route, form_action_label='Update Route')

@bp.route('/routes/delete/<int:route_id>', methods=['POST'])
@login_required
@client_portal_access_required
def delete_route(route_id):
    route = db.session.get(Route, route_id)
    if not route or route.client_id != current_user.client_id:
        flash("Route not found or you do not have permission to delete it.", 'danger')
        return redirect(url_for('client_portal.list_routes'))

    # Dependency Check: Check if route is used in any Shifts
    if route.shifts:
        flash(f"Error: Route '{route.name}' cannot be deleted as it is assigned to one or more shifts.", 'danger')
        current_app.logger.warning(f"ClientUser {current_user.id} attempt to delete route {route_id} with dependent shifts.")
        return redirect(url_for('client_portal.list_routes'))

    try:
        route_name_for_log = route.name
        # The cascade delete on the Route model should handle deleting RouteCheckpoint entries
        db.session.delete(route)
        db.session.commit()
        flash(f"Route '{route_name_for_log}' deleted successfully.", 'success')
        current_app.logger.info(f"ClientUser {current_user.id} deleted route {route_id} ('{route_name_for_log}').")
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"SQLAlchemyError deleting route {route_id}: {e}", exc_info=True)
        flash('A database error occurred while deleting the route.', 'danger')
    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error deleting route {route_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please contact support.', 'danger')

    return redirect(url_for('client_portal.list_routes'))

@bp.route('/shifts')
@login_required
@client_portal_access_required
def list_shifts():
    shifts = Shift.query\
        .join(Device, Shift.device_id == Device.id)\
        .filter(Device.client_id == current_user.client_id)\
        .order_by(Shift.scheduled_date.desc(), Shift.scheduled_start_time)\
        .all()
    return render_template('client_portal/shifts/list.html', title='My Shifts', shifts=shifts)

@bp.route('/devices')
@login_required
def list_my_devices():
    if not (hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type()):
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    devices = Device.query.filter_by(client_id=current_user.client.id).all()
    return render_template('client_portal/devices/list.html', title='My Devices', devices=devices)

@bp.route('/devices/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_device(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    device = Device.query.filter_by(id=id, client_id=current_user.client_id).first_or_404()
    from app.admin.forms import DeviceForm
    form = DeviceForm(obj=device)
    # Hide client_id field in the form for client users
    form.client_id.data = device.client_id
    if form.validate_on_submit():
        device.name = form.name.data
        device.model = form.model.data
        device.status = form.status.data
        device.last_seen = form.last_seen.data
        device.notes = form.notes.data
        db.session.commit()
        flash('Device updated successfully!', 'success')
        return redirect(url_for('client_portal.list_my_devices'))
    return render_template('admin/devices/add_edit_device.html', title='Edit Device', form=form, device=device, form_legend='Edit Device')

@bp.route('/reports/upload', methods=['GET', 'POST'])
@login_required
def upload_patrol_report():
    if not (hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type()):
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    form = PatrolReportUploadForm()
    # We need to adjust form.shift_id.choices to only show shifts for the current_user.client
    client_shifts = Shift.query.join(Device).filter(Device.client_id == current_user.client_id)\
        .order_by(Shift.start_time.desc()).limit(100).all()
    
    form.shift_id.choices = [(0, '--- Select a Shift ---')] + \
                           [(s.id, f"ID {s.id}: Device {s.device.imei} ({s.device.name or ''}) on Route '{s.route.name}' - {s.start_time.strftime('%Y-%m-%d %H:%M')}") 
                            for s in client_shifts]

    if form.validate_on_submit():
        # Get the shift
        shift = db.session.get(Shift, form.shift_id.data)
        if shift is None:
            flash('Selected shift not found.', 'danger')
            return redirect(url_for('client_portal.upload_patrol_report'))
        
        # Verify shift belongs to client
        if shift.device.client_id != current_user.client_id:
            flash('Invalid shift selected.', 'danger')
            return redirect(url_for('client_portal.upload_patrol_report'))
        
        # Call the handler function
        success, msg_category, msg_text, report_id = handle_report_submission_and_processing(
            shift_id=shift.id,
            uploaded_file=form.report_file.data,
            current_user_id=current_user.id,
            client_id=current_user.client_id
        )
        
        flash(msg_text, msg_category)
        
        if success and report_id:
            return redirect(url_for('client_portal.view_uploaded_report', report_id=report_id))
        elif report_id:
            return redirect(url_for('client_portal.view_uploaded_report', report_id=report_id))
        else:
            return redirect(url_for('client_portal.upload_patrol_report'))
    
    return render_template('client_portal/reports/upload.html', 
                         title='Upload Patrol Report', 
                         form=form)

@bp.route('/reports')
@login_required
def list_uploaded_reports():
    if not (hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type()):
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    reports = UploadedPatrolReport.query\
        .join(Shift, UploadedPatrolReport.shift_id == Shift.id)\
        .join(Device, Shift.device_id == Device.id)\
        .filter(Device.client_id == current_user.client.id)\
        .order_by(UploadedPatrolReport.upload_timestamp.desc())\
        .all()
    
    return render_template('client_portal/reports/list.html', title='My Reports', reports=reports)

@bp.route('/checkpoints/add', methods=['GET', 'POST'])
@login_required
@client_portal_access_required
def add_checkpoint():
    form = CheckpointForm(client_id=current_user.client_id)
    if form.validate_on_submit():
        try:
            new_checkpoint = Checkpoint(
                client_id=current_user.client_id,
                name=form.name.data.strip(),
                description=form.description.data.strip() if form.description.data else None,
                latitude=form.latitude.data,
                longitude=form.longitude.data,
                radius=form.radius.data
            )
            db.session.add(new_checkpoint)
            db.session.commit()
            flash(f"Checkpoint '{new_checkpoint.name}' created successfully!", 'success')
            current_app.logger.info(f"ClientUser {current_user.id} (Client {current_user.client_id}) created checkpoint {new_checkpoint.id} ('{new_checkpoint.name}').")
            return redirect(url_for('client_portal.list_checkpoints'))
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError for Client {current_user.client_id} adding checkpoint '{form.name.data}': {e}")
            flash('Error: A checkpoint with this name already exists.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError for Client {current_user.client_id} adding checkpoint: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error for Client {current_user.client_id} adding checkpoint: {e}", exc_info=True)
            flash('An unexpected error occurred. Please contact support.', 'danger')
    
    return render_template('client_portal/checkpoints/add_edit.html', title='Add New Checkpoint', form=form, form_action_label='Create Checkpoint')

@bp.route('/checkpoints/edit/<int:checkpoint_id>', methods=['GET', 'POST'])
@login_required
@client_portal_access_required
def edit_checkpoint(checkpoint_id):
    checkpoint = db.session.get(Checkpoint, checkpoint_id)
    if not checkpoint or checkpoint.client_id != current_user.client_id:
        current_app.logger.warning(f"ClientUser {current_user.id} unauthorized edit attempt on checkpoint {checkpoint_id}.")
        abort(404)

    form = CheckpointForm(obj=checkpoint, original_name=checkpoint.name, client_id=current_user.client_id)
    if form.validate_on_submit():
        try:
            checkpoint.name = form.name.data.strip()
            checkpoint.description = form.description.data.strip() if form.description.data else None
            checkpoint.latitude = form.latitude.data
            checkpoint.longitude = form.longitude.data
            checkpoint.radius = form.radius.data
            db.session.commit()
            flash(f"Checkpoint '{checkpoint.name}' updated successfully!", 'success')
            current_app.logger.info(f"ClientUser {current_user.id} updated checkpoint {checkpoint.id}.")
            return redirect(url_for('client_portal.list_checkpoints'))
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError for Client {current_user.client_id} editing checkpoint {checkpoint_id}: {e}")
            flash('Error: A checkpoint with this name already exists.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError editing checkpoint {checkpoint_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error editing checkpoint {checkpoint_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please contact support.', 'danger')

    return render_template('client_portal/checkpoints/add_edit.html', title=f"Edit Checkpoint: {checkpoint.name}", form=form, checkpoint=checkpoint, form_action_label='Update Checkpoint')

@bp.route('/checkpoints/delete/<int:checkpoint_id>', methods=['POST'])
@login_required
@client_portal_access_required
def delete_checkpoint(checkpoint_id):
    checkpoint = db.session.get(Checkpoint, checkpoint_id)
    if not checkpoint or checkpoint.client_id != current_user.client_id:
        flash("Checkpoint not found or you do not have permission to delete it.", 'danger')
        return redirect(url_for('client_portal.list_checkpoints'))

    # Dependency Check: Check if the checkpoint is used in any RouteCheckpoint mapping
    if db.session.query(RouteCheckpoint).filter_by(checkpoint_id=checkpoint.id).first():
        flash(f"Error: Checkpoint '{checkpoint.name}' cannot be deleted because it is part of one or more routes.", 'danger')
        current_app.logger.warning(f"ClientUser {current_user.id} attempt to delete checkpoint {checkpoint_id} with dependent routes.")
        return redirect(url_for('client_portal.list_checkpoints'))

    try:
        checkpoint_name_for_log = checkpoint.name
        db.session.delete(checkpoint)
        db.session.commit()
        flash(f"Checkpoint '{checkpoint_name_for_log}' deleted successfully.", 'success')
        current_app.logger.info(f"ClientUser {current_user.id} deleted checkpoint {checkpoint_id} ('{checkpoint_name_for_log}').")
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"SQLAlchemyError deleting checkpoint {checkpoint_id}: {e}", exc_info=True)
        flash('A database error occurred while deleting the checkpoint.', 'danger')
    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error deleting checkpoint {checkpoint_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please contact support.', 'danger')
        
    return redirect(url_for('client_portal.list_checkpoints'))

@bp.route('/shifts/add', methods=['GET', 'POST'])
@login_required
@client_portal_access_required
def add_shift():
    form = ShiftForm(client_id=current_user.client_id)
    
    # Populate form choices with client's resources
    form.device_id.choices = [(d.id, d.name) for d in Device.query.filter_by(client_id=current_user.client_id).order_by('name').all()]
    form.route_id.choices = [(r.id, r.name) for r in Route.query.filter_by(client_id=current_user.client_id).order_by('name').all()]
    form.site_id.choices = [(s.id, s.name) for s in Site.query.filter_by(client_id=current_user.client_id).order_by('name').all()]
    
    if form.validate_on_submit():
        try:
            new_shift = Shift(
                device_id=form.device_id.data,
                route_id=form.route_id.data,
                site_id=form.site_id.data,
                scheduled_date=form.scheduled_date.data,
                scheduled_start_time=form.scheduled_start_time.data,
                scheduled_end_time=form.scheduled_end_time.data,
                shift_type=form.shift_type.data
            )
            db.session.add(new_shift)
            db.session.commit()
            
            flash(f"Shift scheduled successfully!", 'success')
            current_app.logger.info(f"ClientUser {current_user.id} created shift {new_shift.id}.")
            return redirect(url_for('client_portal.list_shifts'))
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError for Client {current_user.client_id} adding shift: {e}")
            flash('Error: This shift conflicts with an existing schedule.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError adding shift for client {current_user.client_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error for Client {current_user.client_id} adding shift: {e}", exc_info=True)
            flash('An unexpected error occurred. Please contact support.', 'danger')
    
    return render_template('client_portal/shifts/add_edit.html', title='Schedule New Shift', form=form, form_action_label='Schedule Shift')

@bp.route('/shifts/edit/<int:shift_id>', methods=['GET', 'POST'])
@login_required
@client_portal_access_required
def edit_shift(shift_id):
    shift = db.session.get(Shift, shift_id)
    if not shift:
        abort(404)
    
    # Verify ownership through device
    device = db.session.get(Device, shift.device_id)
    if not device or device.client_id != current_user.client_id:
        current_app.logger.warning(f"ClientUser {current_user.id} unauthorized edit attempt on shift {shift_id}.")
        abort(404)
    
    form = ShiftForm(obj=shift, editing_shift_id=shift_id, client_id=current_user.client_id)
    
    # Populate form choices
    form.device_id.choices = [(d.id, d.name) for d in Device.query.filter_by(client_id=current_user.client_id).order_by('name').all()]
    form.route_id.choices = [(r.id, r.name) for r in Route.query.filter_by(client_id=current_user.client_id).order_by('name').all()]
    form.site_id.choices = [(s.id, s.name) for s in Site.query.filter_by(client_id=current_user.client_id).order_by('name').all()]
    
    if form.validate_on_submit():
        try:
            shift.device_id = form.device_id.data
            shift.route_id = form.route_id.data
            shift.site_id = form.site_id.data
            shift.scheduled_date = form.scheduled_date.data
            shift.scheduled_start_time = form.scheduled_start_time.data
            shift.scheduled_end_time = form.scheduled_end_time.data
            shift.shift_type = form.shift_type.data
            
            db.session.commit()
            flash(f"Shift updated successfully!", 'success')
            current_app.logger.info(f"ClientUser {current_user.id} updated shift {shift.id}.")
            return redirect(url_for('client_portal.list_shifts'))
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning(f"IntegrityError for Client {current_user.client_id} editing shift {shift_id}: {e}")
            flash('Error: This shift conflicts with an existing schedule.', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"SQLAlchemyError editing shift {shift_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error editing shift {shift_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please contact support.', 'danger')
    
    return render_template('client_portal/shifts/add_edit.html', title=f"Edit Shift", form=form, shift=shift, form_action_label='Update Shift')

@bp.route('/shifts/delete/<int:shift_id>', methods=['POST'])
@login_required
@client_portal_access_required
def delete_shift(shift_id):
    shift = db.session.get(Shift, shift_id)
    if not shift:
        flash("Shift not found.", 'danger')
        return redirect(url_for('client_portal.list_shifts'))
    
    # Verify ownership through device
    device = db.session.get(Device, shift.device_id)
    if not device or device.client_id != current_user.client_id:
        flash("You do not have permission to delete this shift.", 'danger')
        return redirect(url_for('client_portal.list_shifts'))
    
    # Check if shift has associated reports
    if shift.patrol_reports:
        flash(f"Error: This shift cannot be deleted because it has patrol reports associated with it.", 'danger')
        current_app.logger.warning(f"ClientUser {current_user.id} attempt to delete shift {shift_id} with associated reports.")
        return redirect(url_for('client_portal.list_shifts'))
    
    try:
        shift_info = f"{shift.scheduled_date.strftime('%Y-%m-%d')} {shift.scheduled_start_time.strftime('%H:%M')}-{shift.scheduled_end_time.strftime('%H:%M')}"
        db.session.delete(shift)
        db.session.commit()
        flash(f"Shift ({shift_info}) deleted successfully.", 'success')
        current_app.logger.info(f"ClientUser {current_user.id} deleted shift {shift_id}.")
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"SQLAlchemyError deleting shift {shift_id}: {e}", exc_info=True)
        flash('A database error occurred while deleting the shift.', 'danger')
    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error deleting shift {shift_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please contact support.', 'danger')
    
    return redirect(url_for('client_portal.list_shifts')) 