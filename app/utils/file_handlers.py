import os
import csv
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app
from app.exceptions import (
    FileUploadError, InvalidFileTypeError, CSVValidationError,
    MissingHeaderError, DataTypeError, DeviceIdentifierMismatchError
)

def get_upload_path(client_id, report_id):
    """Generate a secure path for storing uploaded files."""
    try:
        # Create a path structure: uploads/client_{id}/reports/report_{id}/
        base_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f'client_{client_id}', 'reports', f'report_{report_id}')
        os.makedirs(base_path, exist_ok=True)
        return base_path
    except OSError as e:
        current_app.logger.error(f"Error creating upload directory: {str(e)}", exc_info=True)
        raise FileUploadError(f"Failed to create upload directory: {str(e)}")

def save_uploaded_file(file, client_id, report_id):
    """Save an uploaded file securely and return its path."""
    if not file:
        raise FileUploadError("No file provided")
    
    # Check file extension
    allowed_extensions = {'csv'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        raise InvalidFileTypeError(f"Invalid file type. Only CSV files are allowed.")
    
    try:
        # Generate secure filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(f"{timestamp}_{file.filename}")
        
        # Get the upload path and save the file
        upload_path = get_upload_path(client_id, report_id)
        file_path = os.path.join(upload_path, filename)
        
        file.save(file_path)
        current_app.logger.info(f"File saved successfully: {file_path}")
        return file_path
    except Exception as e:
        current_app.logger.error(f"Error saving uploaded file: {str(e)}", exc_info=True)
        raise FileUploadError(f"Failed to save uploaded file: {str(e)}")

def validate_csv_structure(file_path):
    """Validate the structure of the uploaded CSV file."""
    required_columns = {'Device_Identifier', 'Timestamp', 'Latitude', 'Longitude'}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = set(reader.fieldnames or [])
            
            # Check for required columns
            missing_columns = required_columns - headers
            if missing_columns:
                raise MissingHeaderError(missing_columns)
            
            # Validate first row for data types
            try:
                first_row = next(reader)
                try:
                    float(first_row['Latitude'])
                except ValueError:
                    raise DataTypeError('Latitude', 'float')
                
                try:
                    float(first_row['Longitude'])
                except ValueError:
                    raise DataTypeError('Longitude', 'float')
                
                try:
                    datetime.strptime(first_row['Timestamp'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    raise DataTypeError('Timestamp', 'datetime (YYYY-MM-DD HH:MM:SS)')
                
            except StopIteration:
                raise CSVValidationError("CSV file is empty (no data rows)")
            
            return True
    except UnicodeDecodeError:
        raise CSVValidationError("Invalid file encoding. Please ensure the file is UTF-8 encoded.")
    except Exception as e:
        if isinstance(e, CSVValidationError):
            raise
        current_app.logger.error(f"Error validating CSV file: {str(e)}", exc_info=True)
        raise CSVValidationError(f"Error validating CSV file: {str(e)}")

def read_csv_data(file_path):
    """Read and parse the CSV file data."""
    locations = []
    errors = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):  # Start from 2 to account for header row
                try:
                    location = {
                        'device_identifier': row['Device_Identifier'],
                        'timestamp': datetime.strptime(row['Timestamp'], '%Y-%m-%d %H:%M:%S'),
                        'latitude': float(row['Latitude']),
                        'longitude': float(row['Longitude']),
                        'event_type': row.get('Event_Type', ''),
                        'event_details': row.get('Event_Details', '')
                    }
                    locations.append(location)
                except ValueError as e:
                    error_msg = f"Error in row {row_num}: {str(e)}"
                    errors.append(error_msg)
                    current_app.logger.warning(error_msg)
                except KeyError as e:
                    error_msg = f"Missing required column in row {row_num}: {str(e)}"
                    errors.append(error_msg)
                    current_app.logger.warning(error_msg)
        
        if not locations:
            raise CSVValidationError("No valid location data found in CSV file")
        
        if errors:
            current_app.logger.warning(f"Found {len(errors)} errors while reading CSV file")
        
        return locations
    except Exception as e:
        if isinstance(e, CSVValidationError):
            raise
        current_app.logger.error(f"Error reading CSV data: {str(e)}", exc_info=True)
        raise CSVValidationError(f"Error reading CSV data: {str(e)}")

# --- Expected CSV Structure ---
EXPECTED_HEADERS = ['Device_IMEI', 'Timestamp', 'Latitude', 'Longitude']
DEVICE_ID_COLUMN_NAME = 'Device_IMEI'
TIMESTAMP_COLUMN_NAME = 'Timestamp'
LATITUDE_COLUMN_NAME = 'Latitude'
LONGITUDE_COLUMN_NAME = 'Longitude'
EVENT_TYPE_COLUMN_NAME = 'Event_Type'
EVENT_DETAILS_COLUMN_NAME = 'Event_Details'

TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'

def validate_and_read_csv_data(file_path: str):
    """
    Validates CSV structure, reads data, extracts device ID, and converts to appropriate types.
    Args:
        file_path (str): The full path to the CSV file.
    Returns:
        tuple: (list_of_location_data_dicts, device_id_from_csv_str)
    Raises:
        FileNotFoundError: If the file_path does not exist.
        MissingHeaderError: If required headers are not found.
        DataTypeError: If data in critical columns cannot be converted.
        CSVValidationError: For other general CSV issues (e.g., empty file after headers).
    """
    locations_data = []
    device_ids_found = set()

    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)

            # 1. Validate Headers
            headers = reader.fieldnames
            if not headers:
                raise CSVValidationError("CSV file is empty or headers could not be read.")

            missing_headers = [h for h in EXPECTED_HEADERS if h not in headers]
            if missing_headers:
                raise MissingHeaderError(missing_headers=missing_headers)

            # 2. Read and Process Rows
            for i, row in enumerate(reader):
                row_num = i + 2  # For user-friendly error messages (1 for header, 1 for 0-indexed)

                # Extract Device ID
                current_row_device_id = row.get(DEVICE_ID_COLUMN_NAME, '').strip()
                if not current_row_device_id:
                    raise DataTypeError(column=DEVICE_ID_COLUMN_NAME, expected_type="Non-empty string", row_num=row_num,
                                        message="Device identifier is missing or empty in a row.")
                device_ids_found.add(current_row_device_id)

                # Extract and Validate Timestamp
                timestamp_str = row.get(TIMESTAMP_COLUMN_NAME)
                if not timestamp_str:
                    raise DataTypeError(column=TIMESTAMP_COLUMN_NAME, expected_type="Valid timestamp string", row_num=row_num,
                                        message="Timestamp is missing.")
                try:
                    timestamp = datetime.strptime(timestamp_str, TIMESTAMP_FORMAT)
                except ValueError:
                    raise DataTypeError(column=TIMESTAMP_COLUMN_NAME, expected_type=f"Format '{TIMESTAMP_FORMAT}'", row_num=row_num,
                                        message="Timestamp format is incorrect.")

                # Extract and Validate Latitude
                lat_str = row.get(LATITUDE_COLUMN_NAME)
                if not lat_str:
                    raise DataTypeError(column=LATITUDE_COLUMN_NAME, expected_type="Numeric value", row_num=row_num,
                                        message="Latitude is missing.")
                try:
                    latitude = float(lat_str)
                    if not (-90 <= latitude <= 90):
                        raise ValueError("Latitude out of range")
                except ValueError:
                    raise DataTypeError(column=LATITUDE_COLUMN_NAME, expected_type="Float between -90 and 90", row_num=row_num,
                                        message="Latitude is invalid or out of range.")

                # Extract and Validate Longitude
                lon_str = row.get(LONGITUDE_COLUMN_NAME)
                if not lon_str:
                    raise DataTypeError(column=LONGITUDE_COLUMN_NAME, expected_type="Numeric value", row_num=row_num,
                                        message="Longitude is missing.")
                try:
                    longitude = float(lon_str)
                    if not (-180 <= longitude <= 180):
                        raise ValueError("Longitude out of range")
                except ValueError:
                    raise DataTypeError(column=LONGITUDE_COLUMN_NAME, expected_type="Float between -180 and 180", row_num=row_num,
                                        message="Longitude is invalid or out of range.")

                # Optional fields
                event_type = row.get(EVENT_TYPE_COLUMN_NAME)
                event_details = row.get(EVENT_DETAILS_COLUMN_NAME)

                locations_data.append({
                    'timestamp': timestamp,
                    'latitude': latitude,
                    'longitude': longitude,
                    'event_type': event_type,
                    'event_details': event_details,
                    'original_device_id': current_row_device_id
                })

            if not locations_data:
                raise CSVValidationError("CSV file contains no data rows after the header.")

            # Determine the primary device ID for the report
            if len(device_ids_found) > 1:
                current_app.logger.warning(f"Multiple device IDs found in CSV '{file_path}': {device_ids_found}. Using the first one encountered.")
                # For simplicity, we'll use the first device ID found.
                # A stricter approach might raise an error here.

            primary_device_id_from_csv = locations_data[0]['original_device_id'] if locations_data else None
            if not primary_device_id_from_csv and device_ids_found:
                primary_device_id_from_csv = list(device_ids_found)[0]

            return locations_data, primary_device_id_from_csv

    except FileNotFoundError:
        current_app.logger.error(f"CSV file not found at path: {file_path}")
        raise
    except CSVValidationError as e:
        current_app.logger.warning(f"CSV Validation Error for '{file_path}': {str(e)}")
        raise
    except MissingHeaderError as e:
        current_app.logger.warning(f"Missing Headers in CSV '{file_path}': {str(e)}")
        raise
    except DataTypeError as e:
        current_app.logger.warning(f"Data Type Error in CSV '{file_path}': {str(e)}")
        raise
    except Exception as e:
        current_app.logger.error(f"Unexpected error reading CSV '{file_path}': {str(e)}", exc_info=True)
        raise CSVValidationError(f"An unexpected error occurred while reading the CSV file: {str(e)}") 