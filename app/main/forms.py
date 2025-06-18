from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, FloatField, TextAreaField, IntegerField, DateField, TimeField, FieldList, FormField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError
from app.models import User, Checkpoint, Route, Device, Site # Import Device and Site

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    role = SelectField('Role', choices=[('Admin', 'Admin'), ('Guard', 'Guard')], validators=[DataRequired()])
    submit = SubmitField('Save User')

class CheckpointForm(FlaskForm):
    name = StringField('Checkpoint Name', validators=[DataRequired(), Length(max=100)])
    latitude = FloatField('Latitude', validators=[DataRequired(), NumberRange(min=-90.0, max=90.0)])
    longitude = FloatField('Longitude', validators=[DataRequired(), NumberRange(min=-180.0, max=180.0)])
    radius = FloatField('Verification Radius (meters)', validators=[DataRequired(), NumberRange(min=1.0)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Save Checkpoint')

class RouteCheckpointEntryForm(FlaskForm):
    # This sub-form will be used in FieldList for RouteForm
    checkpoint_id = SelectField('Checkpoint', coerce=int, validators=[DataRequired()])
    # sequence_order will be handled by the order in FieldList or manually
    expected_time_window_start = TimeField('Expected Start (HH:MM)', format='%H:%M', validators=[Optional()])
    expected_time_window_end = TimeField('Expected End (HH:MM)', format='%H:%M', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate choices for checkpoint_id dynamically
        self.checkpoint_id.choices = [(c.id, c.name) for c in Checkpoint.query.order_by(Checkpoint.name).all()]
        # Add a default empty choice
        if not any(choice[0] == 0 for choice in self.checkpoint_id.choices): # Check if default already exists
            self.checkpoint_id.choices.insert(0, (0, '--- Select Checkpoint ---'))

class RouteForm(FlaskForm):
    name = StringField('Route Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    # Using FieldList to manage a dynamic list of checkpoints in the route
    # We'll manage checkpoints_in_route more directly in the template/routes for ordering
    submit = SubmitField('Save Route')
    # Note: Managing ordered RouteCheckpoint entries typically requires JavaScript on the frontend
    # or a simpler server-side handling. For MVP, we might start with a basic selection
    # and handle ordering as a separate step or simplify.

# Define the new ShiftForm
class ShiftForm(FlaskForm):
    device_id = SelectField('Device', coerce=int, validators=[DataRequired()])
    route_id = SelectField('Route', coerce=int, validators=[DataRequired()])
    site_id = SelectField('Site', coerce=int, validators=[DataRequired()])
    scheduled_date = DateField('Scheduled Date', format='%Y-%m-%d', validators=[DataRequired()])
    scheduled_start_time = TimeField('Scheduled Start Time (HH:MM)', format='%H:%M', validators=[DataRequired()])
    scheduled_end_time = TimeField('Scheduled End Time (HH:MM)', format='%H:%M', validators=[DataRequired()])
    # Optional: Add shift_type if needed in the form
    # shift_type = SelectField('Shift Type', choices=[('Day', 'Day'), ('Night', 'Night'), ('24Hour', '24 Hour'), ('Custom', 'Custom')], validators=[Optional()])
    submit = SubmitField('Save Shift')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate choices dynamically from models (ideally filtered by client)
        self.device_id.choices = [(d.id, f'{d.name} ({d.imei})') for d in Device.query.order_by(Device.name).all()]
        self.device_id.choices.insert(0, (0, '--- Select Device ---'))
        
        self.route_id.choices = [(r.id, r.name) for r in Route.query.order_by(Route.name).all()]
        self.route_id.choices.insert(0, (0, '--- Select Route ---'))

        self.site_id.choices = [(s.id, s.name) for s in Site.query.order_by(Site.name).all()]
        self.site_id.choices.insert(0, (0, '--- Select Site ---'))

    def validate_device_id(self, field):
        if field.data == 0:
            raise ValidationError('Please select a device.')

    def validate_route_id(self, field):
        if field.data == 0:
            raise ValidationError('Please select a route.')
            
    def validate_site_id(self, field):
        if field.data == 0:
            raise ValidationError('Please select a site.') 