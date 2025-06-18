import pytest
from flask import url_for
from app.models import User, Site, Device, Route, Checkpoint, Shift, UploadedPatrolReport

def test_login_page(client):
    """Test the login page loads correctly"""
    response = client.get('/portal/login')
    assert response.status_code == 200
    assert b'Client Portal Login' in response.data

def test_login_success(client, client_admin_user):
    """Test successful login"""
    response = client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Welcome back' in response.data

def test_login_invalid_credentials(client):
    """Test login with invalid credentials"""
    response = client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'wrongpass',
        'remember_me': False
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid username/email or password' in response.data

def test_login_deactivated_account(client, deactivated_user):
    """Test login with deactivated account"""
    response = client.post('/portal/login', data={
        'username_or_email': 'deactivated',
        'password': 'testpass123',
        'remember_me': False
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Your account has been deactivated' in response.data

def test_login_non_client_user(client, non_client_user):
    """Test login with non-client user"""
    response = client.post('/portal/login', data={
        'username_or_email': 'nonclient',
        'password': 'testpass123',
        'remember_me': False
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'You do not have permission to access the client portal' in response.data

def test_dashboard_access_authenticated(client, client_admin_user):
    """Test dashboard access for authenticated client user"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.get('/portal/dashboard')
    assert response.status_code == 200
    assert b'Test Client Company Dashboard' in response.data
    assert b'My Sites' in response.data
    assert b'My Devices' in response.data
    assert b'My Routes' in response.data

def test_dashboard_access_unauthenticated(client):
    """Test dashboard access for unauthenticated user"""
    response = client.get('/portal/dashboard', follow_redirects=True)
    assert response.status_code == 200
    assert b'Please log in to access the client portal' in response.data

def test_site_listing(client, client_admin_user):
    """Test site listing page"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.get('/portal/sites')
    assert response.status_code == 200
    assert b'My Sites' in response.data
    assert b'Test Site' in response.data

def test_add_site(client, client_admin_user):
    """Test adding a new site"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.post('/portal/sites/add', data={
        'name': 'New Test Site',
        'address': '456 New Test Street',
        'description': 'New Test Site Description',
        'submit': True
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Site added successfully' in response.data
    assert b'New Test Site' in response.data

def test_edit_site(client, client_admin_user):
    """Test editing an existing site"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    # Get the first site's ID
    with client.application.app_context():
        site = Site.query.filter_by(name='Test Site').first()
        site_id = site.id
    
    response = client.post(f'/portal/sites/{site_id}/edit', data={
        'name': 'Updated Test Site',
        'address': 'Updated Test Address',
        'description': 'Updated Test Description',
        'submit': True
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Site updated successfully' in response.data
    assert b'Updated Test Site' in response.data

def test_checkpoint_listing(client, client_admin_user):
    """Test checkpoint listing page"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.get('/portal/checkpoints')
    assert response.status_code == 200
    assert b'My Checkpoints' in response.data
    assert b'Test Checkpoint' in response.data

def test_route_listing(client, client_admin_user):
    """Test route listing page"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.get('/portal/routes')
    assert response.status_code == 200
    assert b'My Routes' in response.data
    assert b'Test Route' in response.data

def test_shift_listing(client, client_admin_user):
    """Test shift listing page"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.get('/portal/shifts')
    assert response.status_code == 200
    assert b'My Shifts' in response.data

def test_device_listing(client, client_admin_user):
    """Test device listing page"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.get('/portal/devices')
    assert response.status_code == 200
    assert b'My Devices' in response.data
    assert b'Test Device' in response.data

def test_report_listing(client, client_admin_user):
    """Test report listing page"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.get('/portal/reports')
    assert response.status_code == 200
    assert b'My Patrol Reports' in response.data

def test_logout(client, client_admin_user):
    """Test logout functionality"""
    # Login first
    client.post('/portal/login', data={
        'username_or_email': 'clientadmin',
        'password': 'testpass123',
        'remember_me': False
    })
    
    response = client.get('/portal/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b'You have been successfully logged out' in response.data
    
    # Try accessing dashboard after logout
    response = client.get('/portal/dashboard', follow_redirects=True)
    assert response.status_code == 200
    assert b'Please log in to access the client portal' in response.data 