import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from app import create_app, db
from app.models import User, Client, Site, Device, Route, Checkpoint, Shift, UploadedPatrolReport, RouteCheckpoint
from datetime import datetime, timedelta, timezone
from config import TestingConfig
from sqlalchemy import select

@pytest.fixture
def app():
    app = create_app('testing')
    
    with app.app_context():
        db.create_all()
        
        # Create test client
        client = Client(name="Test Client Company")
        db.session.add(client)
        db.session.commit()
        
        # Create test users
        client_admin = User(
            username="clientadmin",
            email="admin@testclient.com",
            role="CLIENT_ADMIN",
            client_id=client.id,
            is_active=True
        )
        client_admin.set_password("testpass123")
        
        client_staff = User(
            username="clientstaff",
            email="staff@testclient.com",
            role="CLIENT_STAFF",
            client_id=client.id,
            is_active=True
        )
        client_staff.set_password("testpass123")
        
        non_client_user = User(
            username="nonclient",
            email="nonclient@example.com",
            role="ULTRAGUARD_ADMIN",
            is_active=True
        )
        non_client_user.set_password("testpass123")
        
        deactivated_user = User(
            username="deactivated",
            email="deactivated@testclient.com",
            role="CLIENT_STAFF",
            client_id=client.id,
            is_active=False
        )
        deactivated_user.set_password("testpass123")
        
        db.session.add_all([client_admin, client_staff, non_client_user, deactivated_user])
        db.session.commit()
        
        # Create test site
        site = Site(
            name="Test Site",
            address="123 Test Street",
            description="Test Site Description",
            client_id=client.id
        )
        db.session.add(site)
        db.session.commit()
        
        # Create test device
        device = Device(
            name="Test Device",
            imei="123456789012345",
            model="Test Model",
            client_id=client.id,
            status="active"
        )
        db.session.add(device)
        db.session.commit()
        
        # Create test route
        route = Route(
            name="Test Route",
            description="Test Route Description",
            client_id=client.id
        )
        db.session.add(route)
        db.session.commit()
        
        # Create test checkpoint
        checkpoint = Checkpoint(
            name="Test Checkpoint",
            description="Test Checkpoint Description",
            client_id=client.id,
            latitude=0.0,
            longitude=0.0,
            radius=10.0
        )
        db.session.add(checkpoint)
        db.session.commit()
        
        # Link checkpoint to route via RouteCheckpoint
        route_checkpoint = RouteCheckpoint(route_id=route.id, checkpoint_id=checkpoint.id, sequence_order=1)
        db.session.add(route_checkpoint)
        db.session.commit()
        
        # Create test shift
        now = datetime.now(timezone.utc)
        shift = Shift(
            device_id=device.id,
            route_id=route.id,
            site_id=site.id,
            start_time=now,
            end_time=now + timedelta(hours=8),
            status='active'
        )
        db.session.add(shift)
        db.session.commit()
        
        yield app
        
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def client_admin_user(app):
    with app.app_context():
        return db.session.execute(select(User).filter_by(username="clientadmin")).scalar_one_or_none()

@pytest.fixture
def client_staff_user(app):
    with app.app_context():
        return db.session.execute(select(User).filter_by(username="clientstaff")).scalar_one_or_none()

@pytest.fixture
def non_client_user(app):
    with app.app_context():
        return db.session.execute(select(User).filter_by(username="nonclient")).scalar_one_or_none()

@pytest.fixture
def deactivated_user(app):
    with app.app_context():
        return db.session.execute(select(User).filter_by(username="deactivated")).scalar_one_or_none() 