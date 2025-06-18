from datetime import date, time, datetime, timedelta
from app import create_app, db
from app.models import Client, User, Device, Site, Checkpoint, Route, RouteCheckpoint, Shift

def create_full_test_client_setup(db_session, client_name="TestCorp Security", client_admin_username_prefix="testcorp_admin"):
    """
    Creates a comprehensive test setup for a client including:
    - Client
    - Client Admin User
    - Multiple Sites
    - Multiple Devices
    - Multiple Checkpoints per site (or globally for client)
    - Multiple Routes using these checkpoints
    - Multiple Shifts (some current, some past, some future)
    Returns a dictionary containing the created objects or their IDs.
    """
    created_data = {}

    # --- 1. Create Client ---
    client = db_session.query(Client).filter_by(name=client_name).first()
    if not client:
        client = Client(name=client_name, contact_person="John Doe", contact_email="john.doe@testcorp.com")
        db_session.add(client)
        db_session.flush()  # Get client.id
    created_data['client'] = client
    print(f"Client '{client.name}' (ID: {client.id}) ensured.")

    # --- 2. Create Client Admin User ---
    client_admin_username = f"{client_admin_username_prefix}_{client.id}"
    client_admin_email = f"{client_admin_username}@example.com"
    client_admin = db_session.query(User).filter_by(username=client_admin_username).first()
    if not client_admin:
        client_admin = User(
            username=client_admin_username,
            email=client_admin_email,
            role="CLIENT_ADMIN",  # Make sure this role matches your model
            client_id=client.id,
            is_active=True
        )
        client_admin.set_password("testpassword123")
        db_session.add(client_admin)
    created_data['client_admin'] = client_admin
    print(f"Client Admin '{client_admin.username}' (ID: {client_admin.id}) ensured.")

    # --- 3. Create Devices ---
    devices_data = [
        {"imei": f"TC_IMEI_001_{client.id}", "name": "Alpha Patrol Unit", "description": "Main gate vehicle"},
        {"imei": f"TC_IMEI_002_{client.id}", "name": "Bravo Handheld", "description": "Night shift guard handheld"},
        {"imei": f"TC_IMEI_003_{client.id}", "name": "Charlie Backup", "description": "Spare unit"},
    ]
    created_devices = []
    for dev_data in devices_data:
        device = db_session.query(Device).filter_by(imei=dev_data["imei"]).first()
        if not device:
            device = Device(client_id=client.id, **dev_data)
            db_session.add(device)
        created_devices.append(device)
    db_session.flush()
    created_data['devices'] = created_devices
    print(f"Created/ensured {len(created_devices)} devices for client {client.id}.")

    # --- 4. Create Sites ---
    sites_data = [
        {"name": "HQ Building", "address": "123 Main St, Anytown"},
        {"name": "Warehouse Complex A", "address": "456 Industrial Rd, Anytown"},
        {"name": "Retail Outlet Mall", "address": "789 Commerce Blvd, Anytown"},
    ]
    created_sites = []
    for site_data in sites_data:
        # Check if site with this name already exists for this client
        site = db_session.query(Site).filter_by(client_id=client.id, name=site_data["name"]).first()
        if not site:
            site = Site(client_id=client.id, **site_data)
            db_session.add(site)
        created_sites.append(site)
    db_session.flush()
    created_data['sites'] = created_sites
    print(f"Created/ensured {len(created_sites)} sites for client {client.id}.")

    # --- 5. Create Checkpoints ---
    # Group checkpoints by site for clarity, or make them generally available to the client
    checkpoints_hq = [
        {"name": "HQ Front Entrance", "latitude": 34.0522, "longitude": -118.2437, "radius": 30},
        {"name": "HQ Lobby Desk", "latitude": 34.0520, "longitude": -118.2435, "radius": 15},
        {"name": "HQ Server Room Door", "latitude": 34.0518, "longitude": -118.2439, "radius": 10},
        {"name": "HQ Parking Lot Gate East", "latitude": 34.0525, "longitude": -118.2430, "radius": 25},
    ]
    checkpoints_warehouse = [
        {"name": "Warehouse Gate A", "latitude": 33.9988, "longitude": -118.1255, "radius": 50},
        {"name": "Warehouse Loading Bay 1", "latitude": 33.9980, "longitude": -118.1250, "radius": 20},
        {"name": "Warehouse Office Entrance", "latitude": 33.9990, "longitude": -118.1245, "radius": 20},
    ]
    all_checkpoints_data = checkpoints_hq + checkpoints_warehouse
    created_checkpoints = []
    for cp_data in all_checkpoints_data:
        checkpoint = db_session.query(Checkpoint).filter_by(client_id=client.id, name=cp_data["name"]).first()
        if not checkpoint:
            checkpoint = Checkpoint(client_id=client.id, **cp_data)
            db_session.add(checkpoint)
        created_checkpoints.append(checkpoint)
    db_session.flush()
    created_data['checkpoints'] = created_checkpoints  # This is a flat list of all checkpoints
    created_data['checkpoints_hq'] = [cp for cp in created_checkpoints if cp.name.startswith("HQ")]
    created_data['checkpoints_warehouse'] = [cp for cp in created_checkpoints if cp.name.startswith("Warehouse")]
    print(f"Created/ensured {len(created_checkpoints)} checkpoints for client {client.id}.")

    # --- 6. Create Routes ---
    # Route 1: HQ Perimeter
    route_hq_perimeter = db_session.query(Route).filter_by(client_id=client.id, name="HQ Full Perimeter").first()
    if not route_hq_perimeter:
        route_hq_perimeter = Route(client_id=client.id, name="HQ Full Perimeter", description="Complete tour of HQ building exterior and interior key points.")
        db_session.add(route_hq_perimeter)
        db_session.flush()
        # Add checkpoints to HQ Perimeter route
        hq_route_cps_data = [
            (created_data['checkpoints_hq'][0], 1),  # HQ Front Entrance
            (created_data['checkpoints_hq'][1], 2),  # HQ Lobby Desk
            (created_data['checkpoints_hq'][2], 3),  # HQ Server Room
            (created_data['checkpoints_hq'][3], 4),  # HQ Parking Lot Gate East
            (created_data['checkpoints_hq'][0], 5),  # Return to HQ Front Entrance
        ]
        for cp, order in hq_route_cps_data:
            # Check if this exact RouteCheckpoint already exists
            rc_exists = db_session.query(RouteCheckpoint).filter_by(route_id=route_hq_perimeter.id, checkpoint_id=cp.id, sequence_order=order).first()
            if not rc_exists:
                db_session.add(RouteCheckpoint(route_id=route_hq_perimeter.id, checkpoint_id=cp.id, sequence_order=order))
    created_data['route_hq_perimeter'] = route_hq_perimeter
    print(f"Route '{route_hq_perimeter.name}' ensured for client {client.id}.")

    # Route 2: Warehouse Night Watch
    route_warehouse_night = db_session.query(Route).filter_by(client_id=client.id, name="Warehouse Night Watch").first()
    if not route_warehouse_night:
        route_warehouse_night = Route(client_id=client.id, name="Warehouse Night Watch", description="Secures all warehouse access points.")
        db_session.add(route_warehouse_night)
        db_session.flush()
        # Add checkpoints to Warehouse Night Watch route
        warehouse_route_cps_data = [
            (created_data['checkpoints_warehouse'][0], 1),  # Gate A
            (created_data['checkpoints_warehouse'][1], 2),  # Loading Bay 1
            (created_data['checkpoints_warehouse'][2], 3),  # Office Entrance
        ]
        for cp, order in warehouse_route_cps_data:
            rc_exists = db_session.query(RouteCheckpoint).filter_by(route_id=route_warehouse_night.id, checkpoint_id=cp.id, sequence_order=order).first()
            if not rc_exists:
                db_session.add(RouteCheckpoint(route_id=route_warehouse_night.id, checkpoint_id=cp.id, sequence_order=order))
    created_data['route_warehouse_night'] = route_warehouse_night
    print(f"Route '{route_warehouse_night.name}' ensured for client {client.id}.")

    # --- 7. Create Shifts ---
    today = date.today()
    created_shifts = []

    # Shift 1: Current Day Shift at HQ (Device 1, HQ Perimeter Route)
    shift1_start_time = time(8, 0, 0)
    shift1_end_time = time(16, 0, 0)
    # Check if this specific shift already exists (less likely for tests, but good practice)
    shift1 = db_session.query(Shift).filter_by(device_id=created_devices[0].id, route_id=route_hq_perimeter.id, site_id=created_sites[0].id, scheduled_date=today, scheduled_start_time=shift1_start_time).first()
    if not shift1:
        shift1 = Shift(device_id=created_devices[0].id, route_id=route_hq_perimeter.id, site_id=created_sites[0].id,  # HQ Site
                       scheduled_date=today, scheduled_start_time=shift1_start_time, scheduled_end_time=shift1_end_time, shift_type="Day")
        db_session.add(shift1)
    created_shifts.append(shift1)

    # Shift 2: Yesterday Night Shift at Warehouse (Device 2, Warehouse Night Route)
    yesterday = today - timedelta(days=1)
    shift2_start_time = time(22, 0, 0)  # Starts yesterday
    shift2_end_time = time(6, 0, 0)   # Ends today (crosses midnight)
    shift2 = db_session.query(Shift).filter_by(device_id=created_devices[1].id, route_id=route_warehouse_night.id, site_id=created_sites[1].id, scheduled_date=yesterday, scheduled_start_time=shift2_start_time).first()
    if not shift2:
        shift2 = Shift(device_id=created_devices[1].id, route_id=route_warehouse_night.id, site_id=created_sites[1].id,  # Warehouse Site
                       scheduled_date=yesterday, scheduled_start_time=shift2_start_time, scheduled_end_time=shift2_end_time, shift_type="Night")
        db_session.add(shift2)
    created_shifts.append(shift2)
    
    # Shift 3: Future Day Shift at HQ (Device 1, HQ Perimeter Route)
    tomorrow = today + timedelta(days=1)
    shift3_start_time = time(9, 0, 0)
    shift3_end_time = time(17, 0, 0)
    shift3 = db_session.query(Shift).filter_by(device_id=created_devices[0].id, route_id=route_hq_perimeter.id, site_id=created_sites[0].id, scheduled_date=tomorrow, scheduled_start_time=shift3_start_time).first()
    if not shift3:
        shift3 = Shift(device_id=created_devices[0].id, route_id=route_hq_perimeter.id, site_id=created_sites[0].id,  # HQ Site
                        scheduled_date=tomorrow, scheduled_start_time=shift3_start_time, scheduled_end_time=shift3_end_time, shift_type="Day")
        db_session.add(shift3)
    created_shifts.append(shift3)

    created_data['shifts'] = created_shifts
    print(f"Created/ensured {len(created_shifts)} shifts for client {client.id}.")

    try:
        db_session.commit()
        print("All test data committed successfully.")
    except Exception as e:
        db_session.rollback()
        print(f"Error committing test data: {e}")
        raise  # Re-raise the exception if you want the caller to know about it

    return created_data


def generate_test_csv_data(target_shift, scenario="perfect"):
    """
    Generate CSV data for a specific shift based on different scenarios.
    
    Args:
        target_shift: Shift object with associated route and checkpoints
        scenario: "perfect", "missed_checkpoint", "out_of_order", "extra_points"
    
    Returns:
        List of dictionaries representing CSV rows
    """
    csv_data_rows = []
    target_device_imei = target_shift.device.imei
    
    # Get route checkpoints in order
    route_checkpoints = db.session.query(RouteCheckpoint).filter_by(route_id=target_shift.route_id).order_by(RouteCheckpoint.sequence_order).all()
    
    print(f"\n--- Generating CSV data for Shift ID: {target_shift.id} (Device: {target_device_imei}) ---")
    print(f"Route: {target_shift.route.name} with {len(route_checkpoints)} planned checkpoints.")
    print(f"Scenario: {scenario}")
    
    base_timestamp = datetime.combine(target_shift.scheduled_date, target_shift.scheduled_start_time)
    current_time = base_timestamp + timedelta(minutes=10)  # Start 10 mins into shift
    
    if scenario == "perfect":
        # Visit all checkpoints in order
        for i, rc in enumerate(route_checkpoints):
            checkpoint = rc.checkpoint
            csv_data_rows.append({
                'Device_IMEI': target_device_imei,
                'Timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Latitude': checkpoint.latitude,
                'Longitude': checkpoint.longitude,
                'Event_Type': 'Checkpoint Visit',
                'Event_Details': f'Arrived at {checkpoint.name}'
            })
            print(f"  Added visit for {checkpoint.name} at {current_time.strftime('%H:%M:%S')} ({checkpoint.latitude}, {checkpoint.longitude})")
            
            # Add a point between checkpoints if not the last one
            if i < len(route_checkpoints) - 1:
                current_time += timedelta(minutes=5)  # Travel time
                next_checkpoint = route_checkpoints[i+1].checkpoint
                # Mid-point (very simplistic)
                mid_lat = (checkpoint.latitude + next_checkpoint.latitude) / 2
                mid_lon = (checkpoint.longitude + next_checkpoint.longitude) / 2
                csv_data_rows.append({
                    'Device_IMEI': target_device_imei,
                    'Timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'Latitude': round(mid_lat, 6),
                    'Longitude': round(mid_lon, 6),
                    'Event_Type': 'En Route',
                    'Event_Details': f'Traveling to {next_checkpoint.name}'
                })
                print(f"  Added en-route point at {current_time.strftime('%H:%M:%S')} ({mid_lat}, {mid_lon})")
            current_time += timedelta(minutes=10)  # Time spent at checkpoint + travel to next
    
    elif scenario == "missed_checkpoint":
        # Skip one checkpoint (middle one)
        skip_index = len(route_checkpoints) // 2
        for i, rc in enumerate(route_checkpoints):
            if i == skip_index:
                print(f"  Skipping checkpoint: {rc.checkpoint.name}")
                continue
                
            checkpoint = rc.checkpoint
            csv_data_rows.append({
                'Device_IMEI': target_device_imei,
                'Timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Latitude': checkpoint.latitude,
                'Longitude': checkpoint.longitude,
                'Event_Type': 'Checkpoint Visit',
                'Event_Details': f'Arrived at {checkpoint.name}'
            })
            print(f"  Added visit for {checkpoint.name} at {current_time.strftime('%H:%M:%S')} ({checkpoint.latitude}, {checkpoint.longitude})")
            current_time += timedelta(minutes=15)
    
    elif scenario == "out_of_order":
        # Visit checkpoints in reverse order
        for i, rc in enumerate(reversed(route_checkpoints)):
            checkpoint = rc.checkpoint
            csv_data_rows.append({
                'Device_IMEI': target_device_imei,
                'Timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Latitude': checkpoint.latitude,
                'Longitude': checkpoint.longitude,
                'Event_Type': 'Checkpoint Visit',
                'Event_Details': f'Arrived at {checkpoint.name}'
            })
            print(f"  Added visit for {checkpoint.name} at {current_time.strftime('%H:%M:%S')} ({checkpoint.latitude}, {checkpoint.longitude})")
            current_time += timedelta(minutes=15)
    
    elif scenario == "extra_points":
        # Visit all checkpoints plus some extra points
        for i, rc in enumerate(route_checkpoints):
            checkpoint = rc.checkpoint
            csv_data_rows.append({
                'Device_IMEI': target_device_imei,
                'Timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Latitude': checkpoint.latitude,
                'Longitude': checkpoint.longitude,
                'Event_Type': 'Checkpoint Visit',
                'Event_Details': f'Arrived at {checkpoint.name}'
            })
            print(f"  Added visit for {checkpoint.name} at {current_time.strftime('%H:%M:%S')} ({checkpoint.latitude}, {checkpoint.longitude})")
            current_time += timedelta(minutes=10)
            
            # Add extra point near checkpoint
            current_time += timedelta(minutes=2)
            csv_data_rows.append({
                'Device_IMEI': target_device_imei,
                'Timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Latitude': checkpoint.latitude + 0.0001,
                'Longitude': checkpoint.longitude + 0.0001,
                'Event_Type': 'Extra Point',
                'Event_Details': f'Near {checkpoint.name}'
            })
            print(f"  Added extra point near {checkpoint.name}")
            current_time += timedelta(minutes=8)
    
    return csv_data_rows


# --- How to use it (example standalone script or in a test fixture) ---
if __name__ == '__main__':
    # This part is for standalone execution to populate your dev DB
    app = create_app('development')
    
    print(f"Connecting to DB: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    with app.app_context():
        db.create_all()  # Ensure all tables exist (idempotent)
        
        test_data_objects = create_full_test_client_setup(db.session)
        
        # You can now access the created objects:
        print("\n--- Created Data Summary ---")
        print(f"Client: {test_data_objects['client'].name}")
        print(f"Client Admin: {test_data_objects['client_admin'].username}")
        print(f"Devices: {[d.name for d in test_data_objects['devices']]}")
        print(f"Sites: {[s.name for s in test_data_objects['sites']]}")
        print(f"HQ Checkpoints: {[cp.name for cp in test_data_objects['checkpoints_hq']]}")
        print(f"Shifts created: {len(test_data_objects['shifts'])}")
        if test_data_objects['shifts']:
            print(f"  Example Shift 1 (ID: {test_data_objects['shifts'][0].id}): Device {test_data_objects['shifts'][0].device.name} on Route '{test_data_objects['shifts'][0].route.name}' at Site '{test_data_objects['shifts'][0].site.name}'")
        
        # Generate test CSV data for the first shift
        if test_data_objects['shifts']:
            target_shift = test_data_objects['shifts'][0]
            csv_data = generate_test_csv_data(target_shift, scenario="perfect")
            print(f"\nGenerated {len(csv_data)} CSV rows for perfect patrol scenario")
            
            # Show first few rows
            print("\nFirst 3 CSV rows:")
            for i, row in enumerate(csv_data[:3]):
                print(f"  Row {i+1}: {row}") 