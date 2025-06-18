class UltraguardError(Exception):
    """Base exception for Ultraguard application."""
    pass

class FileUploadError(UltraguardError):
    """Related to file upload issues."""
    pass

class InvalidFileTypeError(FileUploadError):
    """For incorrect file types."""
    pass

class CSVValidationError(UltraguardError):
    """Base for CSV validation issues."""
    pass

class MissingHeaderError(CSVValidationError):
    def __init__(self, missing_headers, message="Missing required CSV headers."):
        self.missing_headers = missing_headers
        super().__init__(f"{message} Missing: {', '.join(missing_headers)}")

class DataTypeError(CSVValidationError):
    def __init__(self, column, expected_type, row_num=None, message="Incorrect data type in CSV."):
        self.column = column
        self.expected_type = expected_type
        self.row_num = row_num
        details = f"Column '{column}' (expected {expected_type})"
        if row_num:
            details += f" at row {row_num}"
        super().__init__(f"{message} {details}")

class DeviceIdentifierMismatchError(CSVValidationError):
    """When device ID in report doesn't match expected."""
    pass

class VerificationLogicError(UltraguardError):
    """Errors specific to the patrol verification logic."""
    pass 