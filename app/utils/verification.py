from math import radians, sin, cos, sqrt, atan2
from datetime import datetime, time
from flask import current_app
from app.exceptions import VerificationLogicError

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    try:
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = 6371000 * c  # Radius of earth in meters
        
        return distance
    except Exception as e:
        current_app.logger.error(f"Error calculating distance: {str(e)}", exc_info=True)
        raise VerificationLogicError(f"Failed to calculate distance: {str(e)}")

def is_within_time_window(visit_time, window_start, window_end):
    """Check if a visit time falls within the expected time window."""
    try:
        if not window_start or not window_end:
            return True  # No time window specified, so any time is valid
        
        visit_time = visit_time.time()
        return window_start <= visit_time <= window_end
    except Exception as e:
        current_app.logger.error(f"Error checking time window: {str(e)}", exc_info=True)
        raise VerificationLogicError(f"Failed to check time window: {str(e)}")

def verify_checkpoint_visit(location, checkpoint, time_window_start=None, time_window_end=None):
    """
    Verify if a location point represents a valid visit to a checkpoint.
    
    Args:
        location: Dict containing 'latitude', 'longitude', and 'timestamp'
        checkpoint: Checkpoint object with 'latitude', 'longitude', and 'radius'
        time_window_start: Optional time object for start of expected window
        time_window_end: Optional time object for end of expected window
    
    Returns:
        bool: True if the location represents a valid visit to the checkpoint
    """
    try:
        # Calculate distance between location and checkpoint
        distance = calculate_distance(
            location['latitude'], location['longitude'],
            checkpoint.latitude, checkpoint.longitude
        )
        
        # Check if within radius
        if distance > checkpoint.radius:
            return False
        
        # Check time window if specified
        if time_window_start and time_window_end:
            if not is_within_time_window(location['timestamp'], time_window_start, time_window_end):
                return False
        
        return True
    except Exception as e:
        current_app.logger.error(f"Error verifying checkpoint visit: {str(e)}", exc_info=True)
        raise VerificationLogicError(f"Failed to verify checkpoint visit: {str(e)}")

def verify_patrol_report(report_id, shift, locations):
    """
    Verify a patrol report against the planned route checkpoints.
    
    Args:
        report_id: ID of the UploadedPatrolReport
        shift: Shift object containing the route
        locations: List of location dictionaries from the CSV
    
    Returns:
        tuple: (verified_visits, missed_checkpoints)
    """
    from app.models import VerifiedVisit, RouteCheckpoint, db
    
    try:
        # Validate inputs
        if not shift:
            raise VerificationLogicError("No shift provided for verification")
        if not locations:
            raise VerificationLogicError("No location data provided for verification")
        
        # Get all checkpoints for the route in sequence
        route_checkpoints = RouteCheckpoint.query\
            .filter_by(route_id=shift.route_id)\
            .order_by(RouteCheckpoint.sequence_order)\
            .all()
        
        if not route_checkpoints:
            raise VerificationLogicError(f"No checkpoints found for route {shift.route_id}")
        
        verified_visits = []
        missed_checkpoints = []
        unvisited_checkpoints = route_checkpoints.copy()
        
        # Process each location point
        for location in locations:
            # Check against remaining unvisited checkpoints
            for checkpoint in unvisited_checkpoints[:]:  # Copy to allow modification during iteration
                try:
                    if verify_checkpoint_visit(
                        location,
                        checkpoint.checkpoint,
                        checkpoint.expected_time_window_start,
                        checkpoint.expected_time_window_end
                    ):
                        # Create verified visit record
                        visit = VerifiedVisit(
                            report_id=report_id,
                            route_checkpoint_id=checkpoint.id,
                            visit_timestamp=location['timestamp'],
                            visit_latitude=location['latitude'],
                            visit_longitude=location['longitude']
                        )
                        verified_visits.append(visit)
                        unvisited_checkpoints.remove(checkpoint)
                        current_app.logger.info(f"Verified visit to checkpoint {checkpoint.checkpoint.name} at {location['timestamp']}")
                        break  # Move to next location after finding a match
                except Exception as e:
                    current_app.logger.error(f"Error processing checkpoint {checkpoint.id}: {str(e)}", exc_info=True)
                    # Continue with next checkpoint instead of failing the whole verification
        
        # Any remaining unvisited checkpoints are missed
        missed_checkpoints = unvisited_checkpoints
        if missed_checkpoints:
            current_app.logger.warning(f"Missed {len(missed_checkpoints)} checkpoints in report {report_id}")
        
        return verified_visits, missed_checkpoints
        
    except Exception as e:
        if isinstance(e, VerificationLogicError):
            raise
        current_app.logger.error(f"Error verifying patrol report: {str(e)}", exc_info=True)
        raise VerificationLogicError(f"Failed to verify patrol report: {str(e)}") 