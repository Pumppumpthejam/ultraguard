from werkzeug.utils import secure_filename
from flask import current_app
from app import db
from app.models import UploadedPatrolReport, Shift
from app.exceptions import (
    FileUploadError, InvalidFileTypeError, CSVValidationError,
    DeviceIdentifierMismatchError, VerificationLogicError, DataTypeError, MissingHeaderError
)
from app.utils.file_handlers import save_uploaded_file, validate_and_read_csv_data
from app.utils.verification import verify_patrol_report
from datetime import datetime, timezone

# Status constants
REPORT_STATUS_PROCESSING = 'processing'
REPORT_STATUS_COMPLETED = 'completed'
REPORT_STATUS_COMPLETED_MISSED = 'completed_with_missed_checkpoints'
REPORT_STATUS_ERROR_UPLOAD = 'error_upload'
REPORT_STATUS_ERROR_VALIDATION = 'error_validation'
REPORT_STATUS_ERROR_DEVICE_MISMATCH = 'error_device_mismatch'
REPORT_STATUS_ERROR_VERIFICATION = 'error_verification'
REPORT_STATUS_ERROR_PROCESSING = 'error_processing'

def handle_report_submission_and_processing(shift_id: int, uploaded_file, current_user_id: int, client_id: int):
    """
    Handles the entire lifecycle of a patrol report submission and processing.
    Returns: tuple (success_bool, flash_category_str, flash_message_str, report_id_or_None)
    """
    report = None  # Initialize report variable
    shift = db.session.get(Shift, shift_id)

    try:
        # --- STEP 1: Create the report record with file_path as NULL ---
        report = UploadedPatrolReport(
            shift_id=shift.id,
            uploaded_by_user_id=current_user_id,
            filename=secure_filename(uploaded_file.filename),
            upload_timestamp=datetime.now(timezone.utc),
            processing_status=REPORT_STATUS_PROCESSING,
            file_path=None  # Initially NULL
        )
        db.session.add(report)
        db.session.flush()  # This assigns report.id and makes the object persistent in the session

        # --- STEP 2: Save the file using report.id, then update file_path ---
        try:
            file_path = save_uploaded_file(
                uploaded_file,
                client_id=client_id,
                report_id=report.id  # Now report.id is available
            )
            report.file_path = file_path  # Use the returned string directly
        except InvalidFileTypeError as e_filetype:
            db.session.rollback()
            current_app.logger.error(f"InvalidFileTypeError for client {client_id}: {str(e_filetype)}", exc_info=True)
            try:
                error_report = UploadedPatrolReport(
                    shift_id=shift.id,
                    uploaded_by_user_id=current_user_id,
                    filename=secure_filename(uploaded_file.filename) if uploaded_file else "Unknown Filename",
                    upload_timestamp=datetime.now(timezone.utc),
                    processing_status=REPORT_STATUS_ERROR_VALIDATION,
                    error_message=f"Invalid file type: {str(e_filetype)}",
                    file_path=None
                )
                db.session.add(error_report)
                db.session.commit()
                return (False, 'danger', f"Invalid file type: {str(e_filetype)}", error_report.id)
            except Exception as db_err_on_error_save:
                db.session.rollback()
                current_app.logger.error(f"Could not save error report after InvalidFileTypeError: {db_err_on_error_save}", exc_info=True)
                return (False, 'danger', f"Invalid file type: {str(e_filetype)}", None)

        # --- Continue with CSV validation, device check, verification ---
        reported_locations_data, device_id_from_csv = validate_and_read_csv_data(report.file_path)
        report.device_identifier_from_report = device_id_from_csv

        if not device_id_from_csv or device_id_from_csv.strip().lower() != shift.device.imei.strip().lower():
            raise DeviceIdentifierMismatchError(
                f"Device ID in report ('{device_id_from_csv or 'Not Found'}') "
                f"does not match expected device IMEI ('{shift.device.imei}') for the selected shift."
            )

        verification_successful, missed_checkpoints = verify_patrol_report(
            report.id, shift, reported_locations_data
        )

        if verification_successful:
            missed_count = len(missed_checkpoints)
            if missed_count > 0:
                report.processing_status = REPORT_STATUS_COMPLETED_MISSED
                db.session.commit()  # Commit everything: report creation, file_path update, verification results
                return (True, 'warning', f'Report processed. {missed_count} checkpoint(s) were missed.', report.id)
            else:
                report.processing_status = REPORT_STATUS_COMPLETED
                db.session.commit()
                return (True, 'success', 'Report uploaded and all checkpoints verified successfully!', report.id)
        else:
            report.processing_status = REPORT_STATUS_ERROR_PROCESSING
            db.session.commit()  # Commit the report with error status
            return (False, 'danger', f'Error during report verification: {report.error_message or "Unknown verification error."}', report.id)

    except FileUploadError as e:
        db.session.rollback()
        current_app.logger.error(f"FileUploadError for client {client_id}: {str(e)}", exc_info=True)
        try:
            error_report = UploadedPatrolReport(
                shift_id=shift.id,
                uploaded_by_user_id=current_user_id,
                filename=secure_filename(uploaded_file.filename) if uploaded_file else "Unknown Filename",
                upload_timestamp=datetime.now(timezone.utc),
                processing_status=REPORT_STATUS_ERROR_UPLOAD,
                error_message=f"File Upload Failed: {str(e)}",
                file_path=None
            )
            db.session.add(error_report)
            db.session.commit()
            return (False, 'danger', f"Upload Failed: {str(e)}", error_report.id)
        except Exception as db_err_on_error_save:
            db.session.rollback()
            current_app.logger.error(f"Could not save error report after FileUploadError: {db_err_on_error_save}", exc_info=True)
            return (False, 'danger', f"Upload Failed: {str(e)}", None)

    except (MissingHeaderError, DataTypeError, DeviceIdentifierMismatchError, CSVValidationError) as e:
        if report and report.id is not None:
            try:
                report.processing_status = REPORT_STATUS_ERROR_DEVICE_MISMATCH if isinstance(e, DeviceIdentifierMismatchError) else REPORT_STATUS_ERROR_VALIDATION
                report.error_message = str(e)
                db.session.commit()  # Commit the report with its file_path and error status
                report_id_for_return = report.id
            except Exception as db_err:
                db.session.rollback()
                current_app.logger.error(f"Error committing report status after CSV error: {db_err}", exc_info=True)
                report_id_for_return = None
        else:
            db.session.rollback()
            report_id_for_return = None

        current_app.logger.warning(f"CSV/Device Validation Error for client {client_id}, report ID {report_id_for_return or 'N/A'}: {str(e)}")
        return (False, 'danger', f"Invalid Report Data: {str(e)}", report_id_for_return)

    except VerificationLogicError as e:
        if report and report.id:
            try:
                report.processing_status = REPORT_STATUS_ERROR_PROCESSING
                report.error_message = f"Verification Error: {str(e)}"
                db.session.commit()
                report_id_for_return = report.id
            except Exception as db_err:
                db.session.rollback()
                current_app.logger.error(f"Error committing report status after verification error: {db_err}", exc_info=True)
                report_id_for_return = None
        else:
            db.session.rollback()
            report_id_for_return = None

        current_app.logger.error(f"VerificationLogicError for client {client_id}, report ID {report_id_for_return or 'N/A'}: {str(e)}", exc_info=True)
        return (False, 'danger', f"Verification Error: {str(e)}", report_id_for_return)

    except Exception as e:  # Catch-all for truly unexpected errors
        db.session.rollback()
        error_report_id = None
        try:
            final_error_report = UploadedPatrolReport(
                shift_id=shift.id,
                uploaded_by_user_id=current_user_id,
                filename=secure_filename(uploaded_file.filename) if uploaded_file else "Unknown Filename on Critical Error",
                upload_timestamp=datetime.now(timezone.utc),
                processing_status=REPORT_STATUS_ERROR_PROCESSING,
                error_message="A critical unexpected error occurred during processing.",
                file_path=report.file_path if report and report.file_path else None
            )
            db.session.add(final_error_report)
            db.session.commit()
            error_report_id = final_error_report.id
        except Exception as db_err_on_critical_save:
            db.session.rollback()
            current_app.logger.error(f"COULD NOT SAVE ERROR REPORT after critical failure: {db_err_on_critical_save}", exc_info=True)

        current_app.logger.critical(f"UNEXPECTED Exception for client {client_id}, original report attempt related to shift {shift.id}: {str(e)}", exc_info=True)
        return (False, 'danger', "A critical unexpected error occurred. Please contact support.", error_report_id) 