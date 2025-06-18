from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed # For CSV upload
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, TextAreaField, HiddenField, DateTimeField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, ValidationError, Regexp
from app.models import User, Device, Client, Shift, Route, Site
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class LoginForm(FlaskForm):
    username_or_email = StringField('Username or Email', validators=[DataRequired(), Length(min=3, max=120)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class ClientForm(FlaskForm):
    name = StringField('Client Company Name', validators=[DataRequired(), Length(min=2, max=150)])
    contact_person = StringField('Contact Person', validators=[Optional(), Length(max=100)])
    contact_email = StringField('Contact Email', validators=[Optional(), Email(), Length(max=120)])
    contact_phone = StringField('Contact Phone', validators=[Optional(), Length(max=30)])
    is_active = BooleanField('Client is Active', default=True)
    submit = SubmitField('Save Client')

class ClientUserCreationForm(FlaskForm): # Used when creating a new Client
    # This form is specifically for creating the initial CLIENT_ADMIN user
    # It might be embedded or used alongside ClientForm
    username = StringField('Client Admin Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Client Admin Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Client Admin Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    # role will be set to 'CLIENT_ADMIN' automatically in the route
    # client_id will be linked automatically in the route
    submit_user = SubmitField('Create Client and Admin User') # Or handled by a single submit on a combined form

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is already taken. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email address is already registered. Please use a different one.')

class SystemUserForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=64),
        Regexp('^[A-Za-z][A-Za-z0-9_.]*$', 0,
               'Usernames must have only letters, numbers, dots or underscores and must start with a letter')
    ])
    email = StringField('Email', validators=[
        DataRequired(),
        Email(),
        Length(max=120)
    ])
    role = SelectField('Role', choices=[
        ('ULTRAGUARD_ADMIN', 'Ultraguard Admin'),
        ('CLIENT_ADMIN', 'Client Admin'),
        ('CLIENT_STAFF', 'Client Staff')
    ], validators=[DataRequired()])
    client_id = SelectField('Client', coerce=int, validators=[Optional()])
    is_active = BooleanField('Active')
    password = PasswordField('New Password (leave blank to keep current)', validators=[
        Optional(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        EqualTo('password', message='Passwords must match if new password is set.')
    ])
    submit = SubmitField('Save User')

    def __init__(self, *args, **kwargs):
        super(SystemUserForm, self).__init__(*args, **kwargs)
        # Set up client choices for the dropdown
        self.client_id.choices = [(0, 'Not Applicable')] + [
            (c.id, c.name) for c in Client.query.order_by(Client.name).all()
        ]
        # Store original values for edit validation
        if 'obj' in kwargs:
            self.obj = kwargs['obj']
            self.original_username = self.obj.username
            self.original_email = self.obj.email
            self.original_role = self.obj.role
            self.original_client_id = self.obj.client_id

    def validate_username(self, username):
        # Skip validation if username hasn't changed
        if hasattr(self, 'original_username') and self.original_username == username.data:
            return

        # Check username format
        if not username.data[0].isalpha():
            raise ValidationError('Username must start with a letter.')

        # Check for existing username
        query = User.query.filter_by(username=username.data)
        if hasattr(self, 'obj') and self.obj and self.obj.id:
            query = query.filter(User.id != self.obj.id)
        existing_user = query.first()
        if existing_user:
            raise ValidationError('That username is already taken by another user.')

    def validate_email(self, email):
        # Skip validation if email hasn't changed
        if hasattr(self, 'original_email') and self.original_email == email.data:
            return

        # Check for existing email
        query = User.query.filter_by(email=email.data.lower())
        if hasattr(self, 'obj') and self.obj and self.obj.id:
            query = query.filter(User.id != self.obj.id)
        existing_user = query.first()
        if existing_user:
            raise ValidationError('That email address is already registered by another user.')

        # Optional: Validate email domain
        domain = email.data.split('@')[-1].lower()
        if domain in ['example.com', 'test.com']:  # Add any restricted domains
            raise ValidationError('This email domain is not allowed.')

    def validate_client_id(self, client_id):
        if self.role.data != 'ULTRAGUARD_ADMIN':
            if not client_id.data or client_id.data == 0:
                raise ValidationError('Client must be selected for Client Admin and Client Staff roles.')
            # Verify client exists and is active
            client = db.session.get(Client, client_id.data)
            if not client:
                raise ValidationError('Selected client does not exist.')
            if not client.is_active:
                raise ValidationError('Selected client is not active.')
        else:
            # For Ultraguard Admins, ensure client_id is None or 0
            if client_id.data and client_id.data != 0:
                raise ValidationError('Ultraguard Admins cannot be associated with a client.')

    def validate_password(self, password):
        if not password.data:  # Skip validation if no password provided
            return

        # Password complexity requirements
        if len(password.data) < 8:
            raise ValidationError('Password must be at least 8 characters long.')
        if not any(c.isupper() for c in password.data):
            raise ValidationError('Password must contain at least one uppercase letter.')
        if not any(c.islower() for c in password.data):
            raise ValidationError('Password must contain at least one lowercase letter.')
        if not any(c.isdigit() for c in password.data):
            raise ValidationError('Password must contain at least one number.')
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password.data):
            raise ValidationError('Password must contain at least one special character.')

    def validate_is_active(self, is_active):
        # Prevent deactivating the last active Ultraguard Admin
        if hasattr(self, 'obj') and self.obj and self.obj.role == 'ULTRAGUARD_ADMIN':
            if not is_active.data:
                active_admin_count = User.query.filter_by(
                    role='ULTRAGUARD_ADMIN',
                    is_active=True
                ).count()
                if active_admin_count <= 1:
                    raise ValidationError('Cannot deactivate the last active Ultraguard Admin.')

    def validate_role(self, role):
        # Prevent changing role of the last active Ultraguard Admin
        if hasattr(self, 'obj') and self.obj and self.obj.role == 'ULTRAGUARD_ADMIN':
            if role.data != 'ULTRAGUARD_ADMIN':
                active_admin_count = User.query.filter_by(
                    role='ULTRAGUARD_ADMIN',
                    is_active=True
                ).count()
                if active_admin_count <= 1:
                    raise ValidationError('Cannot change role of the last active Ultraguard Admin.')

class DeviceForm(FlaskForm):
    client_id = HiddenField() 
    name = StringField('Device Name', validators=[Optional(), Length(max=100)])
    imei = StringField('IMEI', validators=[DataRequired(), Length(max=50)])
    model = StringField('Device Model', validators=[DataRequired(), Length(max=50)])
    status = SelectField('Status', choices=[
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ], validators=[DataRequired()])
    last_seen = DateTimeField('Last Seen', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Save Device')

    def validate_imei(self, imei):
        device = Device.query.filter_by(imei=imei.data).first()
        if device and (not hasattr(self, 'obj') or self.obj is None or device.id != self.obj.id):
            raise ValidationError('This IMEI is already registered to another device.')

class DeviceCSVUploadForm(FlaskForm):
    client_id = HiddenField(validators=[DataRequired()]) # To ensure we know which client to associate with
    csv_file = FileField('Upload Devices CSV', validators=[
        FileRequired(),
        FileAllowed(['csv'], 'CSV files only!')
    ])
    submit_csv = SubmitField('Upload CSV')

class DeleteDeviceForm(FlaskForm):
    """Form for confirming device deletion."""
    submit = SubmitField('Delete Device')

class DeleteForm(FlaskForm):
    """Generic form for confirming deletion."""
    submit_delete = SubmitField('Delete')

class PatrolReportUploadForm(FlaskForm):
    shift_id = SelectField('Select Shift to Associate Report With', coerce=int, validators=[DataRequired()])
    report_file = FileField('Patrol Report CSV File', validators=[
        FileRequired(),
        FileAllowed(['csv'], 'CSV files only!')
    ])
    source_system = StringField('Source System (e.g., italk ptt)', default='italk ptt', validators=[Optional(), Length(max=50)])
    submit_report = SubmitField('Upload and Process Report')

    def __init__(self, *args, **kwargs):
        super(PatrolReportUploadForm, self).__init__(*args, **kwargs)
        # Populate shift_id choices dynamically
        # This query can be quite complex to display nicely.
        # We want to show shifts that might still need a report.
        # Order by most recent, and perhaps only show shifts from the last X days or 'Pending'.
        
        # A more descriptive choice label:
        # "Shift ID X: Device IMEI (Site Name) on Route Y (Date @ Time)"
        shifts = Shift.query.join(Device).join(Client).join(Route).join(Site)\
            .order_by(Shift.scheduled_date.desc(), Shift.scheduled_start_time.desc()).limit(100).all() # Limit for performance in dropdown

        self.shift_id.choices = [(0, '--- Select a Shift ---')] + \
                                [(s.id, f"ID {s.id}: {s.device.imei} ({s.device.name or ''}) for {s.site.client.name} / {s.site.name} on Route '{s.route.name}' - {s.scheduled_date.strftime('%Y-%m-%d')} {s.scheduled_start_time.strftime('%H:%M')}") 
                                 for s in shifts]
     
    def validate_shift_id(self, field):
        if field.data == 0:
            raise ValidationError('Please select a valid shift.')