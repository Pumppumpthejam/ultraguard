from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.urls import urlparse
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
            db.engine.execute(text("SELECT 1"))
            current_app.logger.info("✅ Database connection successful!")
            
            # Debug: Test raw SQL query first
            current_app.logger.info("Testing raw SQL query...")
            try:
                raw_sql_test = db.session.execute(text("SELECT id, username FROM system_user LIMIT 1")).first()
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
def list_sites():
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    client = current_user.client
    sites = Site.query.filter_by(client_id=client.id).order_by(Site.name).all()
    return render_template('client_portal/sites/list.html', title='My Sites', sites=sites)

@bp.route('/sites/add', methods=['GET', 'POST'])
@login_required
def add_site():
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    form = SiteForm()
    if form.validate_on_submit():
        try:
            # Check for duplicate site name within the same client
            existing_site = Site.query.filter_by(
                client_id=current_user.client_id,
                name=form.name.data
            ).first()
            
            if existing_site:
                flash('A site with this name already exists for your client.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to create duplicate site name: {form.name.data}")
                return render_template('client_portal/sites/add_edit.html', 
                                    title='Add New Site',
                                    form=form,
                                    action='Add')
            
            site = Site(
                client_id=current_user.client_id,
                name=form.name.data,
                address=form.address.data,
                description=form.description.data
            )
            db.session.add(site)
            db.session.commit()
            
            flash('Site added successfully!', 'success')
            current_app.logger.info(f"Client {current_user.client_id} added new site: {site.name} (ID: {site.id})")
            return redirect(url_for('client_portal.list_sites'))
            
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"IntegrityError adding site for client {current_user.client_id}: {e}", exc_info=True)
            flash('Error: A site with this name may already exist.', 'danger')
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error adding site for client {current_user.client_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error adding site for client {current_user.client_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return render_template('client_portal/sites/add_edit.html', 
                         title='Add New Site',
                         form=form,
                         action='Add')

@bp.route('/sites/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_site(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    site = Site.query.filter_by(id=id, client_id=current_user.client_id).first_or_404()
    form = SiteForm(obj=site)
    
    if form.validate_on_submit():
        try:
            # Check for duplicate site name within the same client (excluding current site)
            existing_site = Site.query.filter(
                Site.client_id == current_user.client_id,
                Site.name == form.name.data,
                Site.id != id
            ).first()
            
            if existing_site:
                flash('A site with this name already exists for your client.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to rename site {id} to duplicate name: {form.name.data}")
                return render_template('client_portal/sites/add_edit.html',
                                    title='Edit Site',
                                    form=form,
                                    site=site,
                                    action='Edit')
            
            site.name = form.name.data
            site.address = form.address.data
            site.description = form.description.data
            db.session.commit()
            
            flash('Site updated successfully!', 'success')
            current_app.logger.info(f"Client {current_user.client_id} updated site: {site.name} (ID: {site.id})")
            return redirect(url_for('client_portal.list_sites'))
            
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"IntegrityError updating site {id} for client {current_user.client_id}: {e}", exc_info=True)
            flash('Error: A site with this name may already exist.', 'danger')
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error updating site {id} for client {current_user.client_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error updating site {id} for client {current_user.client_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return render_template('client_portal/sites/add_edit.html',
                         title='Edit Site',
                         form=form,
                         site=site,
                         action='Edit')

@bp.route('/sites/<int:id>/delete', methods=['POST'])
@login_required
def delete_site(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    site = Site.query.filter_by(id=id, client_id=current_user.client_id).first_or_404()
    
    try:
        # Check for dependent shifts
        dependent_shifts = Shift.query.filter_by(site_id=id).first()
        if dependent_shifts:
            flash('Cannot delete site: It has associated shifts. Please delete or reassign the shifts first.', 'danger')
            current_app.logger.warning(f"Client {current_user.client_id} attempted to delete site {id} with dependent shifts")
            return redirect(url_for('client_portal.list_sites'))
        
        # Log the deletion attempt
        current_app.logger.info(f"Client {current_user.client_id} attempting to delete site: {site.name} (ID: {site.id})")
        
        # Delete the site
        db.session.delete(site)
        db.session.commit()
        
        flash('Site deleted successfully!', 'success')
        current_app.logger.info(f"Client {current_user.client_id} successfully deleted site: {site.name} (ID: {site.id})")
        return redirect(url_for('client_portal.list_sites'))
        
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.error(f"IntegrityError deleting site {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('Error: Cannot delete site because it has associated records in the system.', 'danger')
        
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error deleting site {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('A database error occurred. Please try again.', 'danger')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error deleting site {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return redirect(url_for('client_portal.list_sites'))

@bp.route('/checkpoints')
@login_required
def list_checkpoints():
    if not (hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type()):
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    checkpoints = Checkpoint.query\
        .join(RouteCheckpoint, Checkpoint.id == RouteCheckpoint.checkpoint_id)\
        .join(Route, RouteCheckpoint.route_id == Route.id)\
        .filter(Route.client_id == current_user.client.id)\
        .distinct()\
        .all()
    return render_template('client_portal/checkpoints/list.html', title='My Checkpoints', checkpoints=checkpoints)

@bp.route('/routes')
@login_required
def list_routes():
    if not (hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type()):
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    routes = Route.query.filter_by(client_id=current_user.client.id).all()
    return render_template('client_portal/routes/list.html', title='My Routes', routes=routes)

@bp.route('/routes/add', methods=['GET', 'POST'])
@login_required
def add_route():
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    form = RouteForm()
    # Populate checkpoint choices with only checkpoints belonging to the current client
    form.checkpoints.choices = [(c.id, c.name) for c in Checkpoint.query.filter_by(client_id=current_user.client_id).order_by(Checkpoint.name).all()]
    
    if form.validate_on_submit():
        try:
            # Check for duplicate route name within the same client
            existing_route = Route.query.filter_by(
                client_id=current_user.client_id,
                name=form.name.data
            ).first()
            
            if existing_route:
                flash('A route with this name already exists for your client.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to create duplicate route name: {form.name.data}")
                return render_template('client_portal/routes/add_edit.html', 
                                    title='Add New Route',
                                    form=form,
                                    action='Add')
            
            # Create the route
            route = Route(
                client_id=current_user.client_id,
                name=form.name.data,
                description=form.description.data
            )
            db.session.add(route)
            db.session.flush()  # Get the route ID without committing
            
            # Add checkpoints in the specified order
            for sequence, checkpoint_id in enumerate(form.checkpoints.data, start=1):
                route_checkpoint = RouteCheckpoint(
                    route_id=route.id,
                    checkpoint_id=checkpoint_id,
                    sequence_order=sequence
                )
                db.session.add(route_checkpoint)
            
            db.session.commit()
            
            flash('Route added successfully!', 'success')
            current_app.logger.info(f"Client {current_user.client_id} added new route: {route.name} (ID: {route.id}) with {len(form.checkpoints.data)} checkpoints")
            return redirect(url_for('client_portal.list_routes'))
            
        except IntegrityError as e:
            db.session.rollback()
            error_msg = str(e)
            if "UNIQUE constraint failed" in error_msg and "routes.name" in error_msg:
                flash('Error: A route with this name already exists for your client.', 'danger')
            elif "UNIQUE constraint failed" in error_msg and "route_checkpoints" in error_msg:
                flash('Error: Invalid checkpoint selection. Please ensure all checkpoints are valid and unique.', 'danger')
            else:
                flash('Error: A data conflict occurred. Please check your input and try again.', 'danger')
            current_app.logger.error(f"IntegrityError adding route for client {current_user.client_id}: {error_msg}", exc_info=True)
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error adding route for client {current_user.client_id}: {str(e)}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error adding route for client {current_user.client_id}: {str(e)}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return render_template('client_portal/routes/add_edit.html', 
                         title='Add New Route',
                         form=form,
                         action='Add')

@bp.route('/routes/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_route(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    route = Route.query.filter_by(id=id, client_id=current_user.client_id).first_or_404()
    form = RouteForm(obj=route)
    
    # Populate checkpoint choices with only checkpoints belonging to the current client
    form.checkpoints.choices = [(c.id, c.name) for c in Checkpoint.query.filter_by(client_id=current_user.client_id).order_by(Checkpoint.name).all()]
    
    # Pre-select current checkpoints in the correct order
    if request.method == 'GET':
        form.checkpoints.data = [rc.checkpoint_id for rc in route.route_checkpoints.order_by(RouteCheckpoint.sequence_order)]
    
    if form.validate_on_submit():
        try:
            # Check for duplicate route name within the same client (excluding current route)
            existing_route = Route.query.filter(
                Route.client_id == current_user.client_id,
                Route.name == form.name.data,
                Route.id != id
            ).first()
            
            if existing_route:
                flash('A route with this name already exists for your client.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to rename route {id} to duplicate name: {form.name.data}")
                return render_template('client_portal/routes/add_edit.html',
                                    title='Edit Route',
                                    form=form,
                                    route=route,
                                    action='Edit')
            
            # Update route details
            route.name = form.name.data
            route.description = form.description.data
            
            # Update checkpoints
            # First, remove all existing route checkpoints
            RouteCheckpoint.query.filter_by(route_id=route.id).delete()
            
            # Then add the new ones in the specified order
            for sequence, checkpoint_id in enumerate(form.checkpoints.data, start=1):
                route_checkpoint = RouteCheckpoint(
                    route_id=route.id,
                    checkpoint_id=checkpoint_id,
                    sequence_order=sequence
                )
                db.session.add(route_checkpoint)
            
            db.session.commit()
            
            flash('Route updated successfully!', 'success')
            current_app.logger.info(f"Client {current_user.client_id} updated route: {route.name} (ID: {route.id}) with {len(form.checkpoints.data)} checkpoints")
            return redirect(url_for('client_portal.list_routes'))
            
        except IntegrityError as e:
            db.session.rollback()
            error_msg = str(e)
            if "UNIQUE constraint failed" in error_msg and "routes.name" in error_msg:
                flash('Error: A route with this name already exists for your client.', 'danger')
            elif "UNIQUE constraint failed" in error_msg and "route_checkpoints" in error_msg:
                flash('Error: Invalid checkpoint selection. Please ensure all checkpoints are valid and unique.', 'danger')
            else:
                flash('Error: A data conflict occurred. Please check your input and try again.', 'danger')
            current_app.logger.error(f"IntegrityError updating route {id} for client {current_user.client_id}: {error_msg}", exc_info=True)
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error updating route {id} for client {current_user.client_id}: {str(e)}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error updating route {id} for client {current_user.client_id}: {str(e)}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return render_template('client_portal/routes/add_edit.html',
                         title='Edit Route',
                         form=form,
                         route=route,
                         action='Edit')

@bp.route('/routes/<int:id>/delete', methods=['POST'])
@login_required
def delete_route(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    route = Route.query.filter_by(id=id, client_id=current_user.client_id).first_or_404()
    
    try:
        # Check for dependent shifts
        if route.shifts.first():
            flash(f"Error: Route '{route.name}' cannot be deleted because it is currently used in one or more scheduled shifts. Please unassign it from all shifts first.", 'danger')
            current_app.logger.warning(f"Client {current_user.client_id} attempted to delete route {id} used in shifts")
            return redirect(url_for('client_portal.list_routes'))
        
        # Log the deletion attempt
        current_app.logger.info(f"Client {current_user.client_id} attempting to delete route: {route.name} (ID: {route.id})")
        
        # Delete the route (RouteCheckpoint records will be deleted automatically due to cascade)
        db.session.delete(route)
        db.session.commit()
        
        flash('Route deleted successfully!', 'success')
        current_app.logger.info(f"Client {current_user.client_id} successfully deleted route: {route.name} (ID: {route.id})")
        return redirect(url_for('client_portal.list_routes'))
        
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.error(f"IntegrityError deleting route {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('Error: Cannot delete route because it has associated records in the system.', 'danger')
        
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error deleting route {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('A database error occurred. Please try again.', 'danger')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error deleting route {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return redirect(url_for('client_portal.list_routes'))

@bp.route('/shifts')
@login_required
def list_shifts():
    if not (hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type()):
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))

    client = current_user.client
    if not client:
        flash('Your user account is not associated with a client company. Please contact support.', 'danger')
        logout_user()
        return redirect(url_for('client_portal.login'))

    # Get shifts through device relationship
    shifts = Shift.query\
        .join(Device, Shift.device_id == Device.id)\
        .filter(Device.client_id == client.id)\
        .order_by(Shift.start_time.desc())\
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
def add_checkpoint():
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    form = CheckpointForm()
    if form.validate_on_submit():
        try:
            # Check for duplicate checkpoint name within the same client
            existing_checkpoint = Checkpoint.query.filter_by(
                client_id=current_user.client_id,
                name=form.name.data
            ).first()
            
            if existing_checkpoint:
                flash('A checkpoint with this name already exists for your client.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to create duplicate checkpoint name: {form.name.data}")
                return render_template('client_portal/checkpoints/add_edit.html', 
                                    title='Add New Checkpoint',
                                    form=form,
                                    action='Add')
            
            # Validate coordinates
            if not (-90 <= form.latitude.data <= 90):
                flash('Latitude must be between -90 and 90 degrees.', 'danger')
                return render_template('client_portal/checkpoints/add_edit.html',
                                    title='Add New Checkpoint',
                                    form=form,
                                    action='Add')
            
            if not (-180 <= form.longitude.data <= 180):
                flash('Longitude must be between -180 and 180 degrees.', 'danger')
                return render_template('client_portal/checkpoints/add_edit.html',
                                    title='Add New Checkpoint',
                                    form=form,
                                    action='Add')
            
            if form.radius.data <= 0:
                flash('Radius must be a positive number.', 'danger')
                return render_template('client_portal/checkpoints/add_edit.html',
                                    title='Add New Checkpoint',
                                    form=form,
                                    action='Add')
            
            checkpoint = Checkpoint(
                client_id=current_user.client_id,
                name=form.name.data,
                latitude=form.latitude.data,
                longitude=form.longitude.data,
                radius=form.radius.data,
                description=form.description.data
            )
            db.session.add(checkpoint)
            db.session.commit()
            
            flash('Checkpoint added successfully!', 'success')
            current_app.logger.info(f"Client {current_user.client_id} added new checkpoint: {checkpoint.name} (ID: {checkpoint.id})")
            return redirect(url_for('client_portal.list_checkpoints'))
            
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"IntegrityError adding checkpoint for client {current_user.client_id}: {e}", exc_info=True)
            flash('Error: A checkpoint with this name may already exist.', 'danger')
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error adding checkpoint for client {current_user.client_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error adding checkpoint for client {current_user.client_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return render_template('client_portal/checkpoints/add_edit.html', 
                         title='Add New Checkpoint',
                         form=form,
                         action='Add')

@bp.route('/checkpoints/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_checkpoint(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    checkpoint = Checkpoint.query.filter_by(id=id, client_id=current_user.client_id).first_or_404()
    form = CheckpointForm(obj=checkpoint)
    
    if form.validate_on_submit():
        try:
            # Check for duplicate checkpoint name within the same client (excluding current checkpoint)
            existing_checkpoint = Checkpoint.query.filter(
                Checkpoint.client_id == current_user.client_id,
                Checkpoint.name == form.name.data,
                Checkpoint.id != id
            ).first()
            
            if existing_checkpoint:
                flash('A checkpoint with this name already exists for your client.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to rename checkpoint {id} to duplicate name: {form.name.data}")
                return render_template('client_portal/checkpoints/add_edit.html',
                                    title='Edit Checkpoint',
                                    form=form,
                                    checkpoint=checkpoint,
                                    action='Edit')
            
            # Validate coordinates
            if not (-90 <= form.latitude.data <= 90):
                flash('Latitude must be between -90 and 90 degrees.', 'danger')
                return render_template('client_portal/checkpoints/add_edit.html',
                                    title='Edit Checkpoint',
                                    form=form,
                                    checkpoint=checkpoint,
                                    action='Edit')
            
            if not (-180 <= form.longitude.data <= 180):
                flash('Longitude must be between -180 and 180 degrees.', 'danger')
                return render_template('client_portal/checkpoints/add_edit.html',
                                    title='Edit Checkpoint',
                                    form=form,
                                    checkpoint=checkpoint,
                                    action='Edit')
            
            if form.radius.data <= 0:
                flash('Radius must be a positive number.', 'danger')
                return render_template('client_portal/checkpoints/add_edit.html',
                                    title='Edit Checkpoint',
                                    form=form,
                                    checkpoint=checkpoint,
                                    action='Edit')
            
            checkpoint.name = form.name.data
            checkpoint.latitude = form.latitude.data
            checkpoint.longitude = form.longitude.data
            checkpoint.radius = form.radius.data
            checkpoint.description = form.description.data
            db.session.commit()
            
            flash('Checkpoint updated successfully!', 'success')
            current_app.logger.info(f"Client {current_user.client_id} updated checkpoint: {checkpoint.name} (ID: {checkpoint.id})")
            return redirect(url_for('client_portal.list_checkpoints'))
            
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"IntegrityError updating checkpoint {id} for client {current_user.client_id}: {e}", exc_info=True)
            flash('Error: A checkpoint with this name may already exist.', 'danger')
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error updating checkpoint {id} for client {current_user.client_id}: {e}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error updating checkpoint {id} for client {current_user.client_id}: {e}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return render_template('client_portal/checkpoints/add_edit.html',
                         title='Edit Checkpoint',
                         form=form,
                         checkpoint=checkpoint,
                         action='Edit')

@bp.route('/checkpoints/<int:id>/delete', methods=['POST'])
@login_required
def delete_checkpoint(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    checkpoint = Checkpoint.query.filter_by(id=id, client_id=current_user.client_id).first_or_404()
    
    try:
        # Check for dependent route associations
        if checkpoint.route_associations.first():
            flash(f"Error: Checkpoint '{checkpoint.name}' cannot be deleted because it is currently used in one or more routes. Please remove it from all routes first.", 'danger')
            current_app.logger.warning(f"Client {current_user.client_id} attempted to delete checkpoint {id} used in routes")
            return redirect(url_for('client_portal.list_checkpoints'))
        
        # Log the deletion attempt
        current_app.logger.info(f"Client {current_user.client_id} attempting to delete checkpoint: {checkpoint.name} (ID: {checkpoint.id})")
        
        # Delete the checkpoint
        db.session.delete(checkpoint)
        db.session.commit()
        
        flash('Checkpoint deleted successfully!', 'success')
        current_app.logger.info(f"Client {current_user.client_id} successfully deleted checkpoint: {checkpoint.name} (ID: {checkpoint.id})")
        return redirect(url_for('client_portal.list_checkpoints'))
        
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.error(f"IntegrityError deleting checkpoint {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('Error: Cannot delete checkpoint because it has associated records in the system.', 'danger')
        
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error deleting checkpoint {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('A database error occurred. Please try again.', 'danger')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.critical(f"Unexpected error deleting checkpoint {id} for client {current_user.client_id}: {e}", exc_info=True)
        flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return redirect(url_for('client_portal.list_checkpoints'))

@bp.route('/shifts/add', methods=['GET', 'POST'])
@login_required
def add_shift():
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    form = ShiftForm()
    
    # Populate form choices with only resources belonging to the current client
    form.device_id.choices = [(d.id, f"{d.name or 'Unnamed'} ({d.imei})") 
                             for d in Device.query.filter_by(client_id=current_user.client_id).order_by(Device.name).all()]
    form.route_id.choices = [(r.id, r.name) 
                            for r in Route.query.filter_by(client_id=current_user.client_id).order_by(Route.name).all()]
    form.site_id.choices = [(s.id, s.name) 
                           for s in Site.query.filter_by(client_id=current_user.client_id).order_by(Site.name).all()]
    
    if form.validate_on_submit():
        try:
            # Additional validation for device, route, and site ownership
            device = db.session.get(Device, form.device_id.data)
            route = db.session.get(Route, form.route_id.data)
            site = db.session.get(Site, form.site_id.data)
            
            if not device or device.client_id != current_user.client_id:
                flash('Invalid device selected.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to use invalid device {form.device_id.data}")
                return render_template('client_portal/shifts/add_edit.html',
                                    title='Add New Shift',
                                    form=form,
                                    action='Add')
            
            if not route or route.client_id != current_user.client_id:
                flash('Invalid route selected.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to use invalid route {form.route_id.data}")
                return render_template('client_portal/shifts/add_edit.html',
                                    title='Add New Shift',
                                    form=form,
                                    action='Add')
            
            if not site or site.client_id != current_user.client_id:
                flash('Invalid site selected.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to use invalid site {form.site_id.data}")
                return render_template('client_portal/shifts/add_edit.html',
                                    title='Add New Shift',
                                    form=form,
                                    action='Add')
            
            # Check for overlapping shifts for the same device
            start_datetime = datetime.combine(form.scheduled_date.data, form.scheduled_start_time.data)
            end_datetime = datetime.combine(form.scheduled_date.data, form.scheduled_end_time.data)
            
            overlapping_shift = Shift.query.filter(
                Shift.device_id == form.device_id.data,
                Shift.scheduled_date == form.scheduled_date.data,
                ((Shift.scheduled_start_time <= form.scheduled_start_time.data) & 
                 (Shift.scheduled_end_time > form.scheduled_start_time.data)) |
                ((Shift.scheduled_start_time < form.scheduled_end_time.data) & 
                 (Shift.scheduled_end_time >= form.scheduled_end_time.data))
            ).first()
            
            if overlapping_shift:
                flash(f'Error: Device is already scheduled for an overlapping shift on {form.scheduled_date.data}.', 'danger')
                current_app.logger.warning(f"Client {current_user.client_id} attempted to create overlapping shift for device {form.device_id.data}")
                return render_template('client_portal/shifts/add_edit.html',
                                    title='Add New Shift',
                                    form=form,
                                    action='Add')
            
            # Create the shift
            shift = Shift(
                device_id=form.device_id.data,
                route_id=form.route_id.data,
                site_id=form.site_id.data,
                scheduled_date=form.scheduled_date.data,
                scheduled_start_time=form.scheduled_start_time.data,
                scheduled_end_time=form.scheduled_end_time.data,
                shift_type=form.shift_type.data
            )
            db.session.add(shift)
            db.session.commit()
            
            flash('Shift added successfully!', 'success')
            current_app.logger.info(f"Client {current_user.client_id} added new shift: Device {device.imei} on Route '{route.name}' at Site '{site.name}' (ID: {shift.id})")
            return redirect(url_for('client_portal.list_shifts'))
            
        except IntegrityError as e:
            db.session.rollback()
            error_msg = str(e)
            if "UNIQUE constraint failed" in error_msg:
                flash('Error: A shift with these details already exists.', 'danger')
            else:
                flash('Error: A data conflict occurred. Please check your input and try again.', 'danger')
            current_app.logger.error(f"IntegrityError adding shift for client {current_user.client_id}: {error_msg}", exc_info=True)
            
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error adding shift for client {current_user.client_id}: {str(e)}", exc_info=True)
            flash('A database error occurred. Please try again.', 'danger')
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.critical(f"Unexpected error adding shift for client {current_user.client_id}: {str(e)}", exc_info=True)
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
    
    return render_template('client_portal/shifts/add_edit.html',
                         title='Add New Shift',
                         form=form,
                         action='Add')

@bp.route('/shifts/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_shift(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    shift = Shift.query.join(Device).filter(
        Shift.id == id,
        Device.client_id == current_user.client_id
    ).first_or_404()
    
    has_reports = shift.uploaded_reports.first() is not None
    if has_reports:
        flash('Warning: This shift has associated patrol reports. Changes may affect report validity.', 'warning')
    
    form = ShiftForm(obj=shift, editing_shift_id=id)
    
    # Populate form choices
    form.device_id.choices = [(d.id, f"{d.name or 'Unnamed'} ({d.imei})") 
                             for d in Device.query.filter_by(client_id=current_user.client_id).order_by(Device.name).all()]
    form.route_id.choices = [(r.id, r.name) 
                            for r in Route.query.filter_by(client_id=current_user.client_id).order_by(Route.name).all()]
    form.site_id.choices = [(s.id, s.name) 
                           for s in Site.query.filter_by(client_id=current_user.client_id).order_by(Site.name).all()]
    
    if form.validate_on_submit():
        try:
            # Validate resource ownership
            device = db.session.get(Device, form.device_id.data)
            route = db.session.get(Route, form.route_id.data)
            site = db.session.get(Site, form.site_id.data)
            
            if not all([device, route, site]) or any(r.client_id != current_user.client_id for r in [device, route, site]):
                flash('Invalid resource selected.', 'danger')
                return render_template('client_portal/shifts/add_edit.html',
                                    title='Edit Shift',
                                    form=form,
                                    shift=shift,
                                    action='Edit')
            
            # Check for critical changes if shift has reports
            if has_reports:
                critical_changes = (
                    shift.device_id != form.device_id.data or
                    shift.route_id != form.route_id.data or
                    shift.scheduled_date != form.scheduled_date.data or
                    shift.scheduled_start_time != form.scheduled_start_time.data or
                    shift.scheduled_end_time != form.scheduled_end_time.data
                )
                if critical_changes:
                    flash('Warning: You are changing critical fields of a shift with associated reports.', 'warning')
            
            # Update shift
            shift.device_id = form.device_id.data
            shift.route_id = form.route_id.data
            shift.site_id = form.site_id.data
            shift.scheduled_date = form.scheduled_date.data
            shift.scheduled_start_time = form.scheduled_start_time.data
            shift.scheduled_end_time = form.scheduled_end_time.data
            shift.shift_type = form.shift_type.data
            
            db.session.commit()
            flash('Shift updated successfully!', 'success')
            current_app.logger.info(f"Client {current_user.client_id} updated shift {id}")
            return redirect(url_for('client_portal.list_shifts'))
            
        except IntegrityError as e:
            db.session.rollback()
            flash('Error: A data conflict occurred. Please check your input and try again.', 'danger')
            current_app.logger.error(f"IntegrityError updating shift {id}: {str(e)}", exc_info=True)
            
        except SQLAlchemyError as e:
            db.session.rollback()
            flash('A database error occurred. Please try again.', 'danger')
            current_app.logger.error(f"Database error updating shift {id}: {str(e)}", exc_info=True)
            
        except Exception as e:
            db.session.rollback()
            flash('An unexpected error occurred. Please try again or contact support.', 'danger')
            current_app.logger.critical(f"Unexpected error updating shift {id}: {str(e)}", exc_info=True)
    
    return render_template('client_portal/shifts/add_edit.html',
                         title='Edit Shift',
                         form=form,
                         shift=shift,
                         action='Edit')

@bp.route('/shifts/<int:id>/delete', methods=['POST'])
@login_required
def delete_shift(id):
    if not current_user.is_client_user_type():
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login'))
    
    try:
        # Fetch the shift and verify ownership
        shift = Shift.query.join(Device).filter(
            Shift.id == id,
            Device.client_id == current_user.client_id
        ).first_or_404()
        
        # Check for associated reports
        if shift.uploaded_reports.first():
            flash('Cannot delete shift: It has associated patrol reports.', 'danger')
            current_app.logger.warning(f"Client {current_user.client_id} attempted to delete shift {id} with associated reports")
            return redirect(url_for('client_portal.list_shifts'))
        
        # Check for active patrols
        if shift.active_patrols.first():
            flash('Cannot delete shift: It has active patrols.', 'danger')
            current_app.logger.warning(f"Client {current_user.client_id} attempted to delete shift {id} with active patrols")
            return redirect(url_for('client_portal.list_shifts'))
        
        # Log the deletion attempt
        current_app.logger.info(f"Client {current_user.client_id} deleting shift {id} (Device: {shift.device.imei}, Route: {shift.route.name}, Site: {shift.site.name})")
        
        # Delete the shift
        db.session.delete(shift)
        db.session.commit()
        
        flash('Shift deleted successfully!', 'success')
        current_app.logger.info(f"Client {current_user.client_id} successfully deleted shift {id}")
        
    except IntegrityError as e:
        db.session.rollback()
        flash('Error: Cannot delete shift due to existing dependencies.', 'danger')
        current_app.logger.error(f"IntegrityError deleting shift {id} for client {current_user.client_id}: {str(e)}", exc_info=True)
        
    except SQLAlchemyError as e:
        db.session.rollback()
        flash('A database error occurred while deleting the shift.', 'danger')
        current_app.logger.error(f"Database error deleting shift {id} for client {current_user.client_id}: {str(e)}", exc_info=True)
        
    except Exception as e:
        db.session.rollback()
        flash('An unexpected error occurred while deleting the shift.', 'danger')
        current_app.logger.critical(f"Unexpected error deleting shift {id} for client {current_user.client_id}: {str(e)}", exc_info=True)
    
    return redirect(url_for('client_portal.list_shifts')) 