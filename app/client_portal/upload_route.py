from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.urls import url_parse
from app import db
from app.models import Shift, Device, UploadedPatrolReport
from app.client_portal.forms import PatrolReportUploadForm
from datetime import datetime, timezone
from app.exceptions import (
    FileUploadError, InvalidFileTypeError, CSVValidationError,
    DeviceIdentifierMismatchError, VerificationLogicError
)
from app.utils.file_handlers import save_uploaded_file, validate_csv_structure, read_csv_data
from app.utils.verification import verify_patrol_report

def handle_upload_patrol_report(form):
    """Handle the patrol report upload process with comprehensive error handling."""
    if not (hasattr(current_user, 'is_client_user_type') and current_user.is_client_user_type()):
        flash('Please log in to access the client portal.', 'warning')
        return redirect(url_for('client_portal.login')), None
    
    report = None
    try:
        # Get the selected shift
        shift = db.session.get(Shift, form.shift_id.data)
        if shift is None:
            flash('Selected shift not found.', 'danger')
            return redirect(url_for('client_portal.upload_patrol_report'))
        
        # Verify shift belongs to client
        if shift.device.client_id != current_user.client_id:
            flash('Invalid shift selected.', 'danger')
            return redirect(url_for('client_portal.upload_patrol_report')), None
        
        # Create the report record with initial status
        report = UploadedPatrolReport(
            shift_id=shift.id,
            uploaded_by_user_id=current_user.id,
            processing_status='processing',
            upload_timestamp=datetime.now(timezone.utc)
        )
        db.session.add(report)
        db.session.flush()  # Get the report ID without committing
        
        try:
            # Save the uploaded file
            file_path = save_uploaded_file(form.report_file.data, current_user.client_id, report.id)
            
            # Update report with file info
            report.filename = form.report_file.data.filename
            report.file_path = file_path
            
            # Validate CSV structure
            validate_csv_structure(file_path)
            
            # Read and process the CSV data
            locations = read_csv_data(file_path)
            
            # Validate device identifier from CSV matches shift's device
            if not locations:
                raise CSVValidationError("No location data found in CSV file")
            
            device_identifier = locations[0]['device_identifier']
            report.device_identifier_from_report = device_identifier
            
            if device_identifier != shift.device.imei:
                raise DeviceIdentifierMismatchError(
                    f"Device identifier in report ({device_identifier}) does not match shift's device ({shift.device.imei})"
                )
            
            # Verify the patrol report
            verified_visits, missed_checkpoints = verify_patrol_report(report.id, shift, locations)
            
            # Update report status based on verification results
            if missed_checkpoints:
                report.processing_status = 'completed_with_missed_checkpoints'
                report.error_message = f"Missed {len(missed_checkpoints)} checkpoints: {', '.join(cp.checkpoint.name for cp in missed_checkpoints)}"
            else:
                report.processing_status = 'completed'
            
            # Save all changes
            db.session.add_all(verified_visits)
            db.session.commit()
            
            flash('Report uploaded and processed successfully!', 'success')
            return redirect(url_for('client_portal.list_uploaded_reports')), report
            
        except FileUploadError as e:
            report.processing_status = 'error_upload'
            report.error_message = str(e)
            db.session.commit()
            flash(f'File upload error: {str(e)}', 'danger')
            current_app.logger.error(f"FileUploadError in report {report.id}: {str(e)}", exc_info=True)
            
        except InvalidFileTypeError as e:
            report.processing_status = 'error_validation'
            report.error_message = str(e)
            db.session.commit()
            flash(f'Invalid file type: {str(e)}', 'danger')
            current_app.logger.warning(f"InvalidFileTypeError in report {report.id}: {str(e)}")
            
        except CSVValidationError as e:
            report.processing_status = 'error_validation'
            report.error_message = str(e)
            db.session.commit()
            flash(f'CSV validation error: {str(e)}', 'danger')
            current_app.logger.warning(f"CSVValidationError in report {report.id}: {str(e)}")
            
        except DeviceIdentifierMismatchError as e:
            report.processing_status = 'error_device_mismatch'
            report.error_message = str(e)
            db.session.commit()
            flash(f'Device mismatch error: {str(e)}', 'danger')
            current_app.logger.warning(f"DeviceIdentifierMismatchError in report {report.id}: {str(e)}")
            
        except VerificationLogicError as e:
            report.processing_status = 'error_verification'
            report.error_message = str(e)
            db.session.commit()
            flash(f'Verification error: {str(e)}', 'danger')
            current_app.logger.error(f"VerificationLogicError in report {report.id}: {str(e)}", exc_info=True)
            
        except Exception as e:
            report.processing_status = 'error_processing'
            report.error_message = str(e)
            db.session.commit()
            flash('An unexpected error occurred while processing the report.', 'danger')
            current_app.logger.error(f"Unexpected error in report {report.id}: {str(e)}", exc_info=True)
            
        return redirect(url_for('client_portal.upload_patrol_report')), report
        
    except Exception as e:
        if report:
            db.session.rollback()
        flash('An unexpected error occurred while processing the report.', 'danger')
        current_app.logger.error(f"Error processing patrol report: {str(e)}", exc_info=True)
        return redirect(url_for('client_portal.upload_patrol_report')), None 