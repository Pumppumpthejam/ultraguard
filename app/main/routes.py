from flask import render_template, redirect, url_for, flash, request, abort
from app import db
from app.main import bp
from app.models import User, Checkpoint, Route, RouteCheckpoint, Shift, Device, Site # Import Device and Site
from app.main.forms import UserForm, CheckpointForm, RouteForm, ShiftForm # Import ShiftForm instead of PatrolAssignmentForm
from datetime import datetime

# --- Dashboard ---
@bp.route('/')
@bp.route('/index')
def index():
    # For now, just a simple dashboard
    # Later, we can query some stats:
    # num_guards = User.query.filter_by(role='Guard').count()
    # num_routes = Route.query.count()
    # etc.
    return render_template('main/index.html', title='Dashboard')

# --- User Management ---
@bp.route('/users')
def list_users():
    users = User.query.order_by(User.username).all()
    return render_template('main/users.html', users=users, title='Manage Users')

@bp.route('/user/add', methods=['GET', 'POST'])
def add_user():
    form = UserForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
        else:
            user = User(username=form.username.data, email='placeholder@example.com', role=form.role.data, is_active=True)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f'User {user.username} added successfully!', 'success')
            return redirect(url_for('main.list_users'))
    return render_template('main/add_edit_form.html', form=form, title='Add New User', form_title='Add New User')

# --- Checkpoint Management ---
@bp.route('/checkpoints')
def list_checkpoints():
    checkpoints = Checkpoint.query.order_by(Checkpoint.name).all()
    return render_template('main/checkpoints.html', checkpoints=checkpoints, title='Manage Checkpoints')

@bp.route('/checkpoint/add', methods=['GET', 'POST'])
def add_checkpoint():
    form = CheckpointForm()
    if form.validate_on_submit():
        checkpoint = Checkpoint(
            name=form.name.data,
            latitude=form.latitude.data,
            longitude=form.longitude.data,
            radius=form.radius.data,
            description=form.description.data
        )
        db.session.add(checkpoint)
        db.session.commit()
        flash(f'Checkpoint {checkpoint.name} added successfully!', 'success')
        return redirect(url_for('main.list_checkpoints'))
    return render_template('main/add_edit_form.html', form=form, title='Add New Checkpoint', form_title='Add New Checkpoint')

@bp.route('/checkpoint/edit/<int:checkpoint_id>', methods=['GET', 'POST'])
def edit_checkpoint(checkpoint_id):
    checkpoint = db.session.get(Checkpoint, checkpoint_id)
    if checkpoint is None:
        abort(404, description="Checkpoint with ID {checkpoint_id} not found.")
    form = CheckpointForm(obj=checkpoint)
    if form.validate_on_submit():
        checkpoint.name = form.name.data
        checkpoint.latitude = form.latitude.data
        checkpoint.longitude = form.longitude.data
        checkpoint.radius = form.radius.data
        checkpoint.description = form.description.data
        db.session.commit()
        flash(f'Checkpoint {checkpoint.name} updated successfully!', 'success')
        return redirect(url_for('main.list_checkpoints'))
    return render_template('main/add_edit_form.html', form=form, title=f'Edit Checkpoint: {checkpoint.name}', form_title=f'Edit Checkpoint: {checkpoint.name}')

# --- Route Management ---
@bp.route('/routes')
def list_routes():
    routes = Route.query.order_by(Route.name).all()
    return render_template('main/routes.html', routes=routes, title='Manage Routes')

@bp.route('/route/add', methods=['GET', 'POST'])
def add_route():
    form = RouteForm()
    if form.validate_on_submit():
        route = Route(name=form.name.data, description=form.description.data)
        db.session.add(route)
        db.session.commit()
        # For MVP, adding checkpoints to the route will be a separate step on the route detail/edit page.
        flash(f'Route {route.name} added. Now add checkpoints to it.', 'success')
        return redirect(url_for('main.edit_route', route_id=route.id)) # Redirect to edit page to add checkpoints
    return render_template('main/add_edit_form.html', form=form, title='Add New Route', form_title='Add New Route')

@bp.route('/route/edit/<int:route_id>', methods=['GET', 'POST'])
def edit_route(route_id):
    route = db.session.get(Route, route_id)
    if route is None:
        abort(404, description="Route with ID {route_id} not found.")
    form = RouteForm(obj=route)
    # For managing checkpoints within a route (RouteCheckpoint instances)
    # This will be more complex and might involve dynamic form handling or separate forms.
    # Let's list current checkpoints and provide a way to add new ones.
    
    # Get all available checkpoints to choose from
    available_checkpoints = Checkpoint.query.order_by(Checkpoint.name).all()
    # Get existing RouteCheckpoint entries for this route, ordered
    assigned_route_checkpoints = RouteCheckpoint.query.filter_by(route_id=route.id).order_by(RouteCheckpoint.sequence_order).all()

    if form.validate_on_submit(): # This part is for updating route's name/description
        route.name = form.name.data
        route.description = form.description.data
        db.session.commit()
        flash(f'Route {route.name} details updated!', 'success')
        # The page will re-render, no redirect needed just for name/desc update
        # return redirect(url_for('main.edit_route', route_id=route.id))

    return render_template('main/manage_route_checkpoints.html', 
                           form=form, route=route, 
                           assigned_route_checkpoints=assigned_route_checkpoints,
                           available_checkpoints=available_checkpoints,
                           title=f'Edit Route: {route.name}',
                           form_title=f'Edit Route: {route.name}')

@bp.route('/route/<int:route_id>/add_checkpoint_to_route', methods=['POST'])
def add_checkpoint_to_route(route_id):
    route = db.session.get(Route, route_id)
    if route is None:
        abort(404, description="Route with ID {route_id} not found.")
    checkpoint_id = request.form.get('checkpoint_id', type=int)
    # Determine next sequence order
    last_rc = RouteCheckpoint.query.filter_by(route_id=route_id).order_by(RouteCheckpoint.sequence_order.desc()).first()
    next_sequence = (last_rc.sequence_order + 1) if last_rc else 1

    if checkpoint_id:
        # Check if this checkpoint is already in the route (optional: allow duplicates if sequence is different)
        exists = RouteCheckpoint.query.filter_by(route_id=route_id, checkpoint_id=checkpoint_id, sequence_order=next_sequence).first() # More robust check needed if allowing same checkpoint multiple times
        if not exists:
            rc = RouteCheckpoint(route_id=route_id, checkpoint_id=checkpoint_id, sequence_order=next_sequence)
            # Add time window if submitted
            start_time_str = request.form.get('expected_time_window_start')
            end_time_str = request.form.get('expected_time_window_end')
            if start_time_str:
                rc.expected_time_window_start = datetime.strptime(start_time_str, '%H:%M').time()
            if end_time_str:
                rc.expected_time_window_end = datetime.strptime(end_time_str, '%H:%M').time()

            db.session.add(rc)
            db.session.commit()
            flash('Checkpoint added to route.', 'success')
        else:
            flash('Checkpoint already in this sequence or issue with sequence.', 'warning')
    else:
        flash('No checkpoint selected.', 'danger')
    return redirect(url_for('main.edit_route', route_id=route_id))

@bp.route('/route_checkpoint/remove/<int:rc_id>', methods=['POST']) # Should be POST or DELETE
def remove_checkpoint_from_route(rc_id):
    rc_to_remove = db.session.get(RouteCheckpoint, rc_id)
    if rc_to_remove is None:
        abort(404, description=f"RouteCheckpoint with ID {rc_id} not found.")
    route_id = rc_to_remove.route_id
    db.session.delete(rc_to_remove)
    # Important: Re-sequence remaining checkpoints for this route
    remaining_rcs = RouteCheckpoint.query.filter_by(route_id=route_id).order_by(RouteCheckpoint.sequence_order).all()
    for i, rc_item in enumerate(remaining_rcs):
        rc_item.sequence_order = i + 1
    db.session.commit()
    flash('Checkpoint removed from route and sequence updated.', 'success')
    return redirect(url_for('main.edit_route', route_id=route_id))

# --- Shift Management (Updated from Patrol Assignment) ---
@bp.route('/shifts')
def list_shifts():
    shifts = Shift.query.order_by(Shift.scheduled_date.desc(), Shift.scheduled_start_time.desc()).all()
    return render_template('main/assignments.html', assignments=shifts, title='Manage Shifts')

@bp.route('/shift/add', methods=['GET', 'POST'])
def add_shift():
    form = ShiftForm()
    if form.validate_on_submit():
        # Get related objects
        device = db.session.get(Device, form.device_id.data)
        if device is None:
            flash('Selected device not found.', 'danger')
            return redirect(url_for('main.index'))
            
        route = db.session.get(Route, form.route_id.data)
        if route is None:
            flash('Selected route not found.', 'danger')
            return redirect(url_for('main.index'))
            
        site = db.session.get(Site, form.site_id.data)
        if site is None:
            flash('Selected site not found.', 'danger')
            return redirect(url_for('main.index'))

        shift = Shift(
            device_id=form.device_id.data,
            route_id=form.route_id.data,
            site_id=form.site_id.data,
            scheduled_date=form.scheduled_date.data,
            scheduled_start_time=form.scheduled_start_time.data,
            scheduled_end_time=form.scheduled_end_time.data,
            shift_type='Custom'
        )
        db.session.add(shift)
        db.session.commit()
        flash('Shift created successfully!', 'success')
        return redirect(url_for('main.list_shifts'))
    
    return render_template('main/add_edit_form.html', form=form, title='Add New Shift', form_title='Add New Shift')

# --- Upload Report (Placeholder for Step 4) ---
@bp.route('/upload_report', methods=['GET'])
def upload_report_form():
    shifts = Shift.query.order_by(Shift.scheduled_date.desc()).all()
    return render_template('main/upload_report_page.html', assignments=shifts, title="Upload Patrol Report")

# Generic form template (can be used for add/edit of simple objects)
# We'll create more specific templates for list views and complex forms like route checkpoint management. 