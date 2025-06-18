import pytest
from datetime import datetime, timezone
from io import BytesIO
from werkzeug.datastructures import FileStorage
from app import create_app, db
from app.models import User, Client, Device, Shift, Route, Site, UploadedPatrolReport, Checkpoint, RouteCheckpoint
from app.utils.report_processing import handle_report_submission_and_processing

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client_user(app):
    with app.app_context():
        # Create a client
        client = Client(name='Test Client')
        db.session.add(client)
        db.session.flush()
        
        # Create a client user
        user = User(
            username='client@test.com',
            email='client@test.com',
            role='CLIENT_STAFF',
            client_id=client.id
        )
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        
        # Return the user ID and client ID instead of the user object
        return {'user_id': user.id, 'client_id': client.id}

@pytest.fixture
def test_device(app, client_user):
    with app.app_context():
        device = Device(
            imei='123456789012345',
            name='Test Device',
            client_id=client_user['client_id']
        )
        db.session.add(device)
        db.session.commit()
        return {'device_id': device.id, 'client_id': device.client_id}

@pytest.fixture
def test_shift(app, test_device, client_user):
    with app.app_context():
        device = db.session.get(Device, test_device['device_id'])
        site = Site(name='Test Site', client_id=test_device['client_id'])
        db.session.add(site)
        db.session.flush()
        route = Route(name='Test Route', client_id=test_device['client_id'])
        db.session.add(route)
        db.session.flush()
        
        # Create checkpoints and associate them with the route
        checkpoint1 = Checkpoint(
            name='Test Checkpoint 1',
            latitude=51.5074,
            longitude=-0.1278,
            radius=10.0,
            client_id=test_device['client_id']
        )
        checkpoint2 = Checkpoint(
            name='Test Checkpoint 2',
            latitude=51.5075,
            longitude=-0.1279,
            radius=10.0,
            client_id=test_device['client_id']
        )
        db.session.add_all([checkpoint1, checkpoint2])
        db.session.flush()
        
        # Associate checkpoints with route
        route_checkpoint1 = RouteCheckpoint(
            route_id=route.id,
            checkpoint_id=checkpoint1.id,
            sequence_order=1
        )
        route_checkpoint2 = RouteCheckpoint(
            route_id=route.id,
            checkpoint_id=checkpoint2.id,
            sequence_order=2
        )
        db.session.add_all([route_checkpoint1, route_checkpoint2])
        
        shift = Shift(
            device_id=device.id,
            route_id=route.id,
            site_id=site.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc)
        )
        db.session.add(shift)
        db.session.commit()
        return {'shift_id': shift.id, 'device_id': device.id}

def create_test_csv_file(device_imei):
    """Helper function to create a test CSV file with location data"""
    csv_content = f"""Device_IMEI,Timestamp,Latitude,Longitude
{device_imei},{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')},51.5074,-0.1278
{device_imei},{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')},51.5075,-0.1279"""
    return FileStorage(
        stream=BytesIO(csv_content.encode()),
        filename='test_report.csv',
        content_type='text/csv'
    )

def test_successful_report_processing(app, client_user, test_shift):
    """Test successful report processing with valid data"""
    with app.app_context():
        shift = db.session.get(Shift, test_shift['shift_id'])
        device = db.session.get(Device, test_shift['device_id'])
        # Create a test CSV file with matching device IMEI
        test_file = create_test_csv_file(device.imei)
        
        # Process the report
        success, msg_category, msg_text, report_id = handle_report_submission_and_processing(
            shift_id=shift.id,
            uploaded_file=test_file,
            current_user_id=client_user['user_id'],
            client_id=client_user['client_id']
        )
        
        # Verify the results
        assert success is True
        assert msg_category == 'success'
        assert 'successfully' in msg_text.lower()
        assert report_id is not None
        
        # Verify the report was created in the database
        report = db.session.get(UploadedPatrolReport, report_id)
        assert report is not None
        assert report.processing_status == 'completed'
        assert report.device_identifier_from_report == device.imei

def test_device_mismatch(app, client_user, test_shift):
    """Test report processing with mismatched device IMEI"""
    with app.app_context():
        shift = db.session.get(Shift, test_shift['shift_id'])
        device = db.session.get(Device, test_shift['device_id'])
        # Create a test CSV file with different device IMEI
        test_file = create_test_csv_file('999999999999999')
        
        # Process the report
        success, msg_category, msg_text, report_id = handle_report_submission_and_processing(
            shift_id=shift.id,
            uploaded_file=test_file,
            current_user_id=client_user['user_id'],
            client_id=client_user['client_id']
        )
        
        # Verify the results
        assert success is False
        assert msg_category == 'danger'
        assert 'device id' in msg_text.lower()
        assert report_id is not None
        
        # Verify the report was created with error status
        report = db.session.get(UploadedPatrolReport, report_id)
        assert report is not None
        assert report.processing_status == 'error_device_mismatch'
        assert report.device_identifier_from_report == '999999999999999'

def test_invalid_file_type(app, client_user, test_shift):
    """Test report processing with invalid file type"""
    with app.app_context():
        shift = db.session.get(Shift, test_shift['shift_id'])
        device = db.session.get(Device, test_shift['device_id'])
        # Create an invalid file (not CSV)
        invalid_file = FileStorage(
            stream=BytesIO(b'invalid content'),
            filename='test.txt',
            content_type='text/plain'
        )
        
        # Process the report
        success, msg_category, msg_text, report_id = handle_report_submission_and_processing(
            shift_id=shift.id,
            uploaded_file=invalid_file,
            current_user_id=client_user['user_id'],
            client_id=client_user['client_id']
        )
        
        # Verify the results
        assert success is False
        assert msg_category == 'danger'
        assert 'invalid file type' in msg_text.lower()
        assert report_id is not None
        
        # Verify the report was created with error status
        report = db.session.get(UploadedPatrolReport, report_id)
        assert report is not None
        assert report.processing_status == 'error_validation'

def test_empty_csv(app, client_user, test_shift):
    """Test report processing with empty CSV file"""
    with app.app_context():
        shift = db.session.get(Shift, test_shift['shift_id'])
        device = db.session.get(Device, test_shift['device_id'])
        # Create an empty CSV file
        empty_file = FileStorage(
            stream=BytesIO(b''),
            filename='empty.csv',
            content_type='text/csv'
        )
        
        # Process the report
        success, msg_category, msg_text, report_id = handle_report_submission_and_processing(
            shift_id=shift.id,
            uploaded_file=empty_file,
            current_user_id=client_user['user_id'],
            client_id=client_user['client_id']
        )
        
        # Verify the results
        assert success is False
        assert msg_category == 'danger'
        assert 'csv file' in msg_text.lower()
        assert report_id is not None
        
        # Verify the report was created with error status
        report = db.session.get(UploadedPatrolReport, report_id)
        assert report is not None
        assert report.processing_status == 'error_validation' 