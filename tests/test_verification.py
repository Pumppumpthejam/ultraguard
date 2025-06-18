import pytest
from datetime import datetime, timedelta
from app import create_app, db
from app.models import Client, Device, Site, Route, Checkpoint, RouteCheckpoint, Shift, UploadedPatrolReport
from app.utils.verification import verify_patrol_report, VerificationLogicError

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def setup_route_with_checkpoints(app):
    with app.app_context():
        client = Client(name='Test Client')
        db.session.add(client)
        db.session.flush()
        device = Device(imei='123456789012345', name='Test Device', client_id=client.id)
        db.session.add(device)
        db.session.flush()
        site = Site(name='Test Site', client_id=client.id)
        db.session.add(site)
        db.session.flush()
        route = Route(name='Test Route', client_id=client.id)
        db.session.add(route)
        db.session.flush()
        # Create two checkpoints
        cp1 = Checkpoint(name='CP1', latitude=10.0, longitude=20.0, radius=50, client_id=client.id)
        cp2 = Checkpoint(name='CP2', latitude=11.0, longitude=21.0, radius=50, client_id=client.id)
        db.session.add_all([cp1, cp2])
        db.session.flush()
        rc1 = RouteCheckpoint(route_id=route.id, checkpoint_id=cp1.id, sequence_order=1)
        rc2 = RouteCheckpoint(route_id=route.id, checkpoint_id=cp2.id, sequence_order=2)
        db.session.add_all([rc1, rc2])
        db.session.flush()
        shift = Shift(device_id=device.id, route_id=route.id, site_id=site.id, start_time=datetime.now(), end_time=datetime.now()+timedelta(hours=1))
        db.session.add(shift)
        db.session.flush()
        report = UploadedPatrolReport(shift_id=shift.id, filename='test.csv', processing_status='processing')
        db.session.add(report)
        db.session.commit()
        return {
            'client_id': client.id,
            'device_id': device.id,
            'site_id': site.id,
            'route_id': route.id,
            'checkpoint_ids': [cp1.id, cp2.id],
            'route_checkpoint_ids': [rc1.id, rc2.id],
            'shift_id': shift.id,
            'report_id': report.id
        }

def test_all_checkpoints_visited(app, setup_route_with_checkpoints):
    with app.app_context():
        data = setup_route_with_checkpoints
        # Re-query objects within this session context
        report = db.session.get(UploadedPatrolReport, data['report_id'])
        shift = db.session.get(Shift, data['shift_id'])
        
        # Both points within radius
        locations = [
            {'timestamp': datetime.now(), 'latitude': 10.0, 'longitude': 20.0},
            {'timestamp': datetime.now(), 'latitude': 11.0, 'longitude': 21.0}
        ]
        verified, missed = verify_patrol_report(report.id, shift, locations)
        assert len(verified) == 2
        assert len(missed) == 0

def test_some_checkpoints_missed(app, setup_route_with_checkpoints):
    with app.app_context():
        data = setup_route_with_checkpoints
        # Re-query objects within this session context
        report = db.session.get(UploadedPatrolReport, data['report_id'])
        shift = db.session.get(Shift, data['shift_id'])
        
        # Only one point within radius
        locations = [
            {'timestamp': datetime.now(), 'latitude': 10.0, 'longitude': 20.0}
        ]
        verified, missed = verify_patrol_report(report.id, shift, locations)
        assert len(verified) == 1
        assert len(missed) == 1

def test_all_checkpoints_missed(app, setup_route_with_checkpoints):
    with app.app_context():
        data = setup_route_with_checkpoints
        # Re-query objects within this session context
        report = db.session.get(UploadedPatrolReport, data['report_id'])
        shift = db.session.get(Shift, data['shift_id'])
        
        # Points far from both checkpoints
        locations = [
            {'timestamp': datetime.now(), 'latitude': 0.0, 'longitude': 0.0}
        ]
        verified, missed = verify_patrol_report(report.id, shift, locations)
        assert len(verified) == 0
        assert len(missed) == 2

def test_points_outside_radius(app, setup_route_with_checkpoints):
    with app.app_context():
        data = setup_route_with_checkpoints
        # Re-query objects within this session context
        report = db.session.get(UploadedPatrolReport, data['report_id'])
        shift = db.session.get(Shift, data['shift_id'])
        
        # Points just outside the radius
        locations = [
            {'timestamp': datetime.now(), 'latitude': 10.5, 'longitude': 20.5},
            {'timestamp': datetime.now(), 'latitude': 11.5, 'longitude': 21.5}
        ]
        verified, missed = verify_patrol_report(report.id, shift, locations)
        assert len(verified) == 0
        assert len(missed) == 2

def test_no_checkpoints_in_route(app):
    with app.app_context():
        # Setup with no checkpoints
        client = Client(name='NoCPClient')
        db.session.add(client)
        db.session.flush()
        device = Device(imei='999999999999999', name='NoCPDevice', client_id=client.id)
        db.session.add(device)
        db.session.flush()
        site = Site(name='NoCPSite', client_id=client.id)
        db.session.add(site)
        db.session.flush()
        route = Route(name='NoCPRoute', client_id=client.id)
        db.session.add(route)
        db.session.flush()
        shift = Shift(device_id=device.id, route_id=route.id, site_id=site.id, start_time=datetime.now(), end_time=datetime.now()+timedelta(hours=1))
        db.session.add(shift)
        db.session.flush()
        report = UploadedPatrolReport(shift_id=shift.id, filename='nocp.csv', processing_status='processing')
        db.session.add(report)
        db.session.commit()
        locations = [
            {'timestamp': datetime.now(), 'latitude': 0.0, 'longitude': 0.0}
        ]
        with pytest.raises(VerificationLogicError):
            verify_patrol_report(report.id, shift, locations)

def test_empty_reported_locations(app, setup_route_with_checkpoints):
    with app.app_context():
        data = setup_route_with_checkpoints
        # Re-query objects within this session context
        report = db.session.get(UploadedPatrolReport, data['report_id'])
        shift = db.session.get(Shift, data['shift_id'])
        
        locations = []
        with pytest.raises(VerificationLogicError):
            verify_patrol_report(report.id, shift, locations)

def test_duplicate_verification_attempts(app, setup_route_with_checkpoints):
    with app.app_context():
        data = setup_route_with_checkpoints
        # Re-query objects within this session context
        report = db.session.get(UploadedPatrolReport, data['report_id'])
        shift = db.session.get(Shift, data['shift_id'])
        
        # Two points at the same checkpoint
        locations = [
            {'timestamp': datetime.now(), 'latitude': 10.0, 'longitude': 20.0},
            {'timestamp': datetime.now(), 'latitude': 10.0, 'longitude': 20.0}
        ]
        verified, missed = verify_patrol_report(report.id, shift, locations)
        # Only one should be counted for the checkpoint
        assert len(verified) == 1
        assert len(missed) == 1 