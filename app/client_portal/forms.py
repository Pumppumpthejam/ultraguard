from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, SelectField, SelectMultipleField, DateField, TimeField, HiddenField
from wtforms.validators import DataRequired, Length, Optional, ValidationError
from app.models import Checkpoint, Device, Route, Site, Shift
from datetime import datetime, time, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import current_user

db = SQLAlchemy()

class ClientLoginForm(FlaskForm):
    username_or_email = StringField('Username or Email', validators=[DataRequired(), Length(min=3, max=120)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class SiteForm(FlaskForm):
    name = StringField('Site Name', validators=[DataRequired(), Length(min=3, max=150)])
    address = TextAreaField('Address', validators=[Optional(), Length(max=500)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Save Site')

    def __init__(self, original_name=None, client_id=None, *args, **kwargs):
        super(SiteForm, self).__init__(*args, **kwargs)
        self.original_name = original_name # For edit mode, to check if name changed
        self.client_id = client_id # To scope uniqueness check

    def validate_name(self, name):
        # If name hasn't changed during an edit, no need to check for uniqueness against itself
        if self.original_name and self.original_name == name.data:
            return
        
        # Check if site name is unique for the current client
        query_client_id = self.client_id or (current_user.is_authenticated and current_user.client_id)
        if not query_client_id:
            # This should ideally not happen if form is used correctly in client portal
            raise ValidationError("Client association is missing for validation.")

        existing_site = Site.query.filter_by(client_id=query_client_id, name=name.data).first()
        if existing_site:
            raise ValidationError('A site with this name already exists for your client. Please use a different name.')

class CheckpointForm(FlaskForm):
    name = StringField('Checkpoint Name', validators=[DataRequired(), Length(min=2, max=100)])
    latitude = StringField('Latitude', validators=[DataRequired()])
    longitude = StringField('Longitude', validators=[DataRequired()])
    radius = StringField('Verification Radius (meters)', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Save Checkpoint')

    def __init__(self, original_name=None, client_id=None, *args, **kwargs):
        super(CheckpointForm, self).__init__(*args, **kwargs)
        self.original_name = original_name
        self.client_id = client_id

    def validate_name(self, name):
        if self.original_name and self.original_name == name.data:
            return
        
        query_client_id = self.client_id or (current_user.is_authenticated and current_user.client_id)
        if not query_client_id:
            raise ValidationError("Client association is missing for validation.")

        existing_checkpoint = Checkpoint.query.filter_by(client_id=query_client_id, name=name.data).first()
        if existing_checkpoint:
            raise ValidationError('A checkpoint with this name already exists for your client. Please use a different name.')

    def validate_latitude(self, field):
        try:
            lat = float(field.data)
            if not -90 <= lat <= 90:
                raise ValidationError('Latitude must be between -90 and 90 degrees.')
        except ValueError:
            raise ValidationError('Please enter a valid number for latitude.')

    def validate_longitude(self, field):
        try:
            lon = float(field.data)
            if not -180 <= lon <= 180:
                raise ValidationError('Longitude must be between -180 and 180 degrees.')
        except ValueError:
            raise ValidationError('Please enter a valid number for longitude.')

    def validate_radius(self, field):
        try:
            radius = float(field.data)
            if radius <= 0:
                raise ValidationError('Radius must be greater than 0 meters.')
            if radius > 1000:  # Optional: Set a reasonable maximum radius
                raise ValidationError('Radius cannot exceed 1000 meters.')
        except ValueError:
            raise ValidationError('Please enter a valid number for radius.')

class PatrolReportUploadForm(FlaskForm):
    shift_id = SelectField('Select Shift to Associate Report With', coerce=int, validators=[DataRequired()])
    report_file = FileField('iTalk Geo Fence Report File', validators=[
        FileRequired(),
        FileAllowed(['csv', 'xlsx'], 'CSV or XLSX files only!')
    ])
    source_system = StringField('Source System (e.g., italk ptt)', default='italk ptt', validators=[Optional(), Length(max=50)])
    submit_report = SubmitField('Upload iTalk Geo Fence report')

    def __init__(self, *args, **kwargs):
        super(PatrolReportUploadForm, self).__init__(*args, **kwargs)
        # The choices for shift_id will be populated by the route function
        # So this __init__ might not need to fetch all shifts globally,
        # the route function will scope it to the current client's shifts.
        # For now, we can leave the choices empty or add a placeholder.
        # The route will override choices.
        self.shift_id.choices = [(0, '--- Select a Shift ---')]
    
    def validate_shift_id(self, field):
        if field.data == 0: # Assuming 0 is the placeholder for "--- Select a Shift ---"
            raise ValidationError('Please select a valid shift.')

class RouteForm(FlaskForm):
    name = StringField('Route Name', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    checkpoints = SelectMultipleField('Checkpoints', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Save Route')

    def __init__(self, *args, **kwargs):
        self.original_name = kwargs.pop('original_name', None)
        self.client_id = kwargs.pop('client_id', None)
        super(RouteForm, self).__init__(*args, **kwargs)
        # The choices for checkpoints will be populated by the route function
        # to scope it to the current client's checkpoints
        self.checkpoints.choices = []

    def validate_name(self, name):
        if self.original_name and self.original_name == name.data:
            return
        
        query_client_id = self.client_id or (current_user.is_authenticated and current_user.client_id)
        if not query_client_id:
            raise ValidationError("Client association is missing for validation.")

        existing_route = Route.query.filter_by(client_id=query_client_id, name=name.data).first()
        if existing_route:
            raise ValidationError('A route with this name already exists for your client. Please use a different name.')

    def validate_checkpoints(self, field):
        if not field.data:
            raise ValidationError('Please select at least one checkpoint.')
        
        # Validate that all selected checkpoints exist and belong to the current client
        from flask_login import current_user
        invalid_checkpoints = []
        for checkpoint_id in field.data:
            checkpoint = db.session.get(Checkpoint, checkpoint_id)
            if not checkpoint or checkpoint.client_id != current_user.client_id:
                invalid_checkpoints.append(checkpoint_id)
        
        if invalid_checkpoints:
            raise ValidationError('One or more selected checkpoints do not belong to your client.')

class ShiftForm(FlaskForm):
    device_id = SelectField('Device', coerce=int, validators=[DataRequired()])
    route_id = SelectField('Route', coerce=int, validators=[DataRequired()])
    site_id = SelectField('Site', coerce=int, validators=[DataRequired()])
    scheduled_date = DateField('Date', validators=[DataRequired()])
    scheduled_start_time = TimeField('Start Time', validators=[DataRequired()])
    scheduled_end_time = TimeField('End Time', validators=[DataRequired()])
    shift_type = SelectField('Shift Type', choices=[
        ('day', 'Day'),
        ('night', 'Night'),
        ('24hour', '24 Hour'),
        ('custom', 'Custom')
    ], validators=[DataRequired()])
    editing_shift_id = HiddenField('Editing Shift ID')  # For edit mode
    submit = SubmitField('Save Shift')

    def __init__(self, *args, **kwargs):
        self.editing_shift_id = kwargs.pop('editing_shift_id', None)
        self.client_id = kwargs.pop('client_id', None)  # For consistency with other forms
        super(ShiftForm, self).__init__(*args, **kwargs)
        # The choices for device_id, route_id, and site_id will be populated by the route function
        # to scope them to the current client's resources
        self.device_id.choices = []
        self.route_id.choices = []
        self.site_id.choices = []

    def validate_scheduled_end_time(self, field):
        if self.scheduled_start_time.data and field.data:
            if field.data <= self.scheduled_start_time.data:
                raise ValidationError('End time must be after start time.')

    def validate_device_id(self, field):
        from flask_login import current_user
        device = db.session.get(Device, field.data)
        if not device or device.client_id != current_user.client_id:
            raise ValidationError('Invalid device selected.')

    def validate_route_id(self, field):
        from flask_login import current_user
        route = db.session.get(Route, field.data)
        if not route or route.client_id != current_user.client_id:
            raise ValidationError('Invalid route selected.')

    def validate_site_id(self, field):
        from flask_login import current_user
        site = db.session.get(Site, field.data)
        if not site or site.client_id != current_user.client_id:
            raise ValidationError('Invalid site selected.')

    def validate_scheduled_date(self, field):
        if field.data < datetime.now().date():
            raise ValidationError('Cannot schedule shifts in the past.')

    def validate_shift_type(self, field):
        if field.data not in ['day', 'night', '24hour', 'custom']:
            raise ValidationError('Invalid shift type selected.')

    def validate(self):
        if not super().validate():
            return False

        # Shift type-specific time constraints
        if self.shift_type.data == 'day':
            if not (time(6, 0) <= self.scheduled_start_time.data <= time(18, 0)):
                self.scheduled_start_time.errors.append('Day shifts must start between 06:00 and 18:00.')
                return False
            if not (time(6, 0) <= self.scheduled_end_time.data <= time(18, 0)):
                self.scheduled_end_time.errors.append('Day shifts must end between 06:00 and 18:00.')
                return False
        elif self.shift_type.data == 'night':
            # Night shifts can span midnight
            if not (time(18, 0) <= self.scheduled_start_time.data <= time(23, 59) or 
                   time(0, 0) <= self.scheduled_start_time.data <= time(6, 0)):
                self.scheduled_start_time.errors.append('Night shifts must start between 18:00 and 06:00.')
                return False
            if not (time(18, 0) <= self.scheduled_end_time.data <= time(23, 59) or 
                   time(0, 0) <= self.scheduled_end_time.data <= time(6, 0)):
                self.scheduled_end_time.errors.append('Night shifts must end between 18:00 and 06:00.')
                return False
        elif self.shift_type.data == '24hour':
            # 24-hour shifts must be exactly 24 hours
            start_datetime = datetime.combine(self.scheduled_date.data, self.scheduled_start_time.data)
            end_datetime = datetime.combine(self.scheduled_date.data, self.scheduled_end_time.data)
            if end_datetime < start_datetime:
                end_datetime += timedelta(days=1)
            if (end_datetime - start_datetime).total_seconds() != 86400:  # 24 hours in seconds
                self.scheduled_end_time.errors.append('24-hour shifts must be exactly 24 hours long.')
                return False

        # Check for overlapping shifts
        from flask_login import current_user
        start_datetime = datetime.combine(self.scheduled_date.data, self.scheduled_start_time.data)
        end_datetime = datetime.combine(self.scheduled_date.data, self.scheduled_end_time.data)
        if end_datetime < start_datetime:
            end_datetime += timedelta(days=1)

        # Query for overlapping shifts, excluding the current shift if in edit mode
        query = Shift.query.filter(
            Shift.device_id == self.device_id.data,
            ((Shift.scheduled_date == self.scheduled_date.data) |
             (Shift.scheduled_date == self.scheduled_date.data + timedelta(days=1))),
            ((Shift.scheduled_start_time <= self.scheduled_start_time.data) & 
             (Shift.scheduled_end_time > self.scheduled_start_time.data)) |
            ((Shift.scheduled_start_time < self.scheduled_end_time.data) & 
             (Shift.scheduled_end_time >= self.scheduled_end_time.data))
        )

        if self.editing_shift_id:
            query = query.filter(Shift.id != self.editing_shift_id)

        if query.first():
            self.scheduled_start_time.errors.append('This shift overlaps with an existing shift for the selected device.')
            return False

        return True 