from datetime import datetime, date, time, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from . import db

# --- Core Ultraguard and Client Management ---
class Client(db.Model):
    __tablename__ = 'client'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    contact_person = db.Column(db.String(100), nullable=True)
    contact_email = db.Column(db.String(120), nullable=True)
    contact_phone = db.Column(db.String(30), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    # 'client_users' backref defined in User model
    sites = db.relationship('Site', backref='client', lazy='dynamic', cascade="all, delete-orphan")
    devices = db.relationship('Device', backref='client', lazy='dynamic', cascade="all, delete-orphan")
    routes = db.relationship('Route', backref='client', lazy='dynamic', cascade="all, delete-orphan")
    checkpoints = db.relationship('Checkpoint', backref='client_owner', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Client {self.name}>'

class User(db.Model, UserMixin): # For both Ultraguard Admins and Client Users
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True) # Required by UserMixin
    username = db.Column(db.String(80), unique=True, nullable=False) # Login username
    password_hash = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False) # Email for login/notifications
    
    # ROLE DEFINITIONS
    role = db.Column(db.String(30), nullable=False, default='CLIENT_STAFF') # e.g., 'ULTRAGUARD_ADMIN', 'CLIENT_ADMIN', 'CLIENT_STAFF'
    is_active = db.Column(db.Boolean, default=True, nullable=False) # Required by UserMixin
    
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=True) # Null for Ultraguard Admins
    client = db.relationship('Client', backref=db.backref('client_users', lazy='dynamic'))

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Properties required by Flask-Login's UserMixin if not directly named 'is_authenticated', 'is_active', 'is_anonymous'
    # is_active is already a column.
    # UserMixin provides default implementations for is_authenticated and is_anonymous.
    # get_id() is also provided by UserMixin and will use self.id.

    def is_ultraguard_admin(self):
        return self.role == 'ULTRAGUARD_ADMIN'

    def is_client_admin(self):
        return self.role == 'CLIENT_ADMIN'
        
    def is_client_user_type(self): # General check for any client-associated role
        return self.client_id is not None and self.role in ['CLIENT_ADMIN', 'CLIENT_STAFF']

    def __repr__(self):
        client_info = f" ClientID:{self.client_id}" if self.client_id else " UG_Admin"
        return f'<User {self.username} ({self.role}){client_info}>'

class Device(db.Model):
    __tablename__ = 'device'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    imei = db.Column(db.String(15), unique=True, nullable=False)
    model = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), default='active')
    last_seen = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    
    # Explicitly define the relationship with Shift
    shifts = db.relationship(
        'Shift',
        foreign_keys='[Shift.device_id]',
        backref=db.backref('device', lazy=True),
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Device {self.name} (IMEI: {self.imei})>'

# --- Client-Managed Entities (Sites, Checkpoints, Routes, Shifts) ---
class Site(db.Model):
    __tablename__ = 'site'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # client relationship is defined via backref from Client model
    shifts = db.relationship('Shift', backref='site', lazy='dynamic')
    __table_args__ = (db.UniqueConstraint('client_id', 'name', name='_client_site_name_uc'),)

    def __repr__(self):
        return f'<Site {self.name} (Client ID: {self.client_id})>'

class Checkpoint(db.Model): # "Points"
    __tablename__ = 'checkpoint'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False) # Checkpoint belongs to a client
    name = db.Column(db.String(100), nullable=False) 
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    radius = db.Column(db.Float, nullable=False) # Verification radius in meters
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # client_owner relationship defined via backref from Client model
    # route_associations defined by RouteCheckpoint backref
    __table_args__ = (db.UniqueConstraint('client_id', 'name', name='_client_checkpoint_name_uc'),)

    def __repr__(self):
        return f'<Checkpoint {self.name} (Client ID: {self.client_id})>'

class Route(db.Model):
    __tablename__ = 'route'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # client relationship is defined via backref from Client model
    route_checkpoints = db.relationship('RouteCheckpoint', backref='route', lazy='dynamic', order_by='RouteCheckpoint.sequence_order', cascade="all, delete-orphan")
    shifts = db.relationship('Shift', backref='route', lazy='dynamic')
    __table_args__ = (db.UniqueConstraint('client_id', 'name', name='_client_route_name_uc'),)

    def __repr__(self):
        return f'<Route {self.name} (Client ID: {self.client_id})>'

class RouteCheckpoint(db.Model): # Association between Route and Checkpoint
    __tablename__ = 'route_checkpoint'
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('route.id'), nullable=False)
    checkpoint_id = db.Column(db.Integer, db.ForeignKey('checkpoint.id'), nullable=False)
    sequence_order = db.Column(db.Integer, nullable=False) # Defines the order of checkpoints in a route
    expected_time_window_start = db.Column(db.Time, nullable=True) # Optional
    expected_time_window_end = db.Column(db.Time, nullable=True) # Optional

    # route relationship defined via backref from Route model
    checkpoint = db.relationship('Checkpoint', backref=db.backref('route_associations', lazy=True))
    # verified_visits relationship will be defined by VerifiedVisit model

    __table_args__ = (
        db.UniqueConstraint('route_id', 'checkpoint_id', 'sequence_order', name='_route_checkpoint_sequence_uc'),
        db.UniqueConstraint('route_id', 'sequence_order', name='_route_sequence_order_uc')
    )

    def __repr__(self):
        return f'<RouteCheckpoint RouteID:{self.route_id} CP_ID:{self.checkpoint_id} Order:{self.sequence_order}>'

class Shift(db.Model):
    __tablename__ = 'shift'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=False)
    route_id = db.Column(db.Integer, db.ForeignKey('route.id'), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='active')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f'<Shift {self.id} at {self.start_time}>'

# --- Patrol Reporting and Verification ---
class UploadedPatrolReport(db.Model):
    __tablename__ = 'uploaded_patrol_report'
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=False)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # File handling fields
    filename = db.Column(db.String(255), nullable=False)  # Original filename
    file_path = db.Column(db.String(512), nullable=True)  # Allow NULL for file_path
    device_identifier_from_report = db.Column(db.String(50), nullable=True)  # Device ID from CSV
    
    # Status and timestamps
    upload_timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    processing_status = db.Column(db.String(50), default='processing')  # processing, completed, completed_with_missed_checkpoints, error_validation, error_processing, error_device_mismatch
    error_message = db.Column(db.Text, nullable=True)  # Detailed error message if any
    
    # Relationships
    shift = db.relationship('Shift', backref='patrol_reports')
    uploader = db.relationship('User', foreign_keys=[uploaded_by_user_id], backref='uploaded_reports')
    reported_locations = db.relationship('ReportedLocation', backref='report', lazy='dynamic', cascade='all, delete-orphan')
    verified_visits = db.relationship('VerifiedVisit', backref='report', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<UploadedPatrolReport {self.id} for Shift {self.shift_id}>'

class ReportedLocation(db.Model): # Data points from the uploaded CSV
    __tablename__ = 'reported_location'
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('uploaded_patrol_report.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False) # From the CSV
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    event_type = db.Column(db.String(100), nullable=True)
    event_details = db.Column(db.Text, nullable=True)

    # report relationship is defined via backref from UploadedPatrolReport model

    def __repr__(self):
        return f'<ReportedLocation ID:{self.id} ReportID:{self.report_id} @ {self.timestamp}>'

class VerifiedVisit(db.Model): # Records a successful visit to a planned checkpoint
    __tablename__ = 'verified_visit'
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('uploaded_patrol_report.id'), nullable=False)
    route_checkpoint_id = db.Column(db.Integer, db.ForeignKey('route_checkpoint.id'), nullable=False)
    reported_location_id = db.Column(db.Integer, db.ForeignKey('reported_location.id'), unique=True, nullable=False)
    
    visit_timestamp = db.Column(db.DateTime, nullable=False)
    visit_latitude = db.Column(db.Float, nullable=False)
    visit_longitude = db.Column(db.Float, nullable=False)

    # report relationship is defined via backref from UploadedPatrolReport model
    planned_checkpoint = db.relationship('RouteCheckpoint', backref=db.backref('verified_visits', lazy=True))
    verifying_location = db.relationship('ReportedLocation', backref=db.backref('verified_visit_record', uselist=False, lazy=True))

    __table_args__ = (db.UniqueConstraint('report_id', 'route_checkpoint_id', name='_report_planned_checkpoint_uc'),)

    def __repr__(self):
        return f'<VerifiedVisit ReportID:{self.report_id} RouteCheckpointID:{self.route_checkpoint_id}>' 