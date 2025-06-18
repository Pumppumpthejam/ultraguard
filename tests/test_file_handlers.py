import pytest
import io
import csv
import os
from datetime import datetime
from app import create_app
from app.utils.file_handlers import validate_and_read_csv_data, EXPECTED_HEADERS, DEVICE_ID_COLUMN_NAME, TIMESTAMP_COLUMN_NAME, LATITUDE_COLUMN_NAME, LONGITUDE_COLUMN_NAME, TIMESTAMP_FORMAT
from app.exceptions import MissingHeaderError, DataTypeError, CSVValidationError

@pytest.fixture(scope="module")
def app_context():
    app = create_app('testing')
    ctx = app.app_context()
    ctx.push()
    yield app
    ctx.pop()

def create_csv_content(headers, rows_list_of_dicts):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for row in rows_list_of_dicts:
        writer.writerow(row)
    return output.getvalue()

def test_validate_read_valid_csv(tmp_path, app_context):
    file_content = create_csv_content(
        EXPECTED_HEADERS,
        [{DEVICE_ID_COLUMN_NAME: "IMEI123", TIMESTAMP_COLUMN_NAME: "2023-01-01 10:00:00", LATITUDE_COLUMN_NAME: "34.0", LONGITUDE_COLUMN_NAME: "-118.0"}]
    )
    p = tmp_path / "valid.csv"
    p.write_text(file_content, encoding="utf-8")
    locations, device_id = validate_and_read_csv_data(str(p))
    assert device_id == "IMEI123"
    assert len(locations) == 1
    assert locations[0]['latitude'] == 34.0
    assert locations[0]['longitude'] == -118.0

def test_validate_read_missing_header(tmp_path, app_context):
    invalid_headers = [h for h in EXPECTED_HEADERS if h != LATITUDE_COLUMN_NAME]
    file_content = create_csv_content(
        invalid_headers,
        [{DEVICE_ID_COLUMN_NAME: "IMEI123", TIMESTAMP_COLUMN_NAME: "2023-01-01 10:00:00", LONGITUDE_COLUMN_NAME: "-118.0"}]
    )
    p = tmp_path / "missing_header.csv"
    p.write_text(file_content)
    with pytest.raises(MissingHeaderError):
        validate_and_read_csv_data(str(p))

def test_validate_read_incorrect_data_type(tmp_path, app_context):
    file_content = create_csv_content(
        EXPECTED_HEADERS,
        [{DEVICE_ID_COLUMN_NAME: "IMEI123", TIMESTAMP_COLUMN_NAME: "not-a-date", LATITUDE_COLUMN_NAME: "not-a-float", LONGITUDE_COLUMN_NAME: "-118.0"}]
    )
    p = tmp_path / "badtype.csv"
    p.write_text(file_content)
    with pytest.raises(DataTypeError):
        validate_and_read_csv_data(str(p))

def test_validate_read_missing_critical_data(tmp_path, app_context):
    file_content = create_csv_content(
        EXPECTED_HEADERS,
        [{DEVICE_ID_COLUMN_NAME: "", TIMESTAMP_COLUMN_NAME: "2023-01-01 10:00:00", LATITUDE_COLUMN_NAME: "34.0", LONGITUDE_COLUMN_NAME: "-118.0"}]
    )
    p = tmp_path / "missing_device.csv"
    p.write_text(file_content)
    with pytest.raises(DataTypeError):
        validate_and_read_csv_data(str(p))

def test_validate_read_latitude_out_of_range(tmp_path, app_context):
    file_content = create_csv_content(
        EXPECTED_HEADERS,
        [{DEVICE_ID_COLUMN_NAME: "IMEI123", TIMESTAMP_COLUMN_NAME: "2023-01-01 10:00:00", LATITUDE_COLUMN_NAME: "100.0", LONGITUDE_COLUMN_NAME: "-118.0"}]
    )
    p = tmp_path / "lat_out_of_range.csv"
    p.write_text(file_content)
    with pytest.raises(DataTypeError):
        validate_and_read_csv_data(str(p))

def test_validate_read_empty_csv(tmp_path, app_context):
    p = tmp_path / "empty.csv"
    p.write_text("")
    with pytest.raises(CSVValidationError):
        validate_and_read_csv_data(str(p))

def test_validate_read_only_headers(tmp_path, app_context):
    file_content = create_csv_content(EXPECTED_HEADERS, [])
    p = tmp_path / "headers_only.csv"
    p.write_text(file_content)
    with pytest.raises(CSVValidationError):
        validate_and_read_csv_data(str(p))

def test_validate_read_multiple_device_ids_warns(tmp_path, app_context, caplog):
    # This test assumes your implementation logs a warning but does not raise if multiple device IDs are found
    file_content = create_csv_content(
        EXPECTED_HEADERS,
        [
            {DEVICE_ID_COLUMN_NAME: "IMEI123", TIMESTAMP_COLUMN_NAME: "2023-01-01 10:00:00", LATITUDE_COLUMN_NAME: "34.0", LONGITUDE_COLUMN_NAME: "-118.0"},
            {DEVICE_ID_COLUMN_NAME: "IMEI456", TIMESTAMP_COLUMN_NAME: "2023-01-01 10:10:00", LATITUDE_COLUMN_NAME: "35.0", LONGITUDE_COLUMN_NAME: "-119.0"}
        ]
    )
    p = tmp_path / "multi_device.csv"
    p.write_text(file_content)
    locations, device_id = validate_and_read_csv_data(str(p))
    assert device_id in ["IMEI123", "IMEI456"]
    assert len(locations) == 2
    assert any("multiple device ids" in r.lower() for r in caplog.text.splitlines())

def test_validate_read_file_not_found(app_context):
    with pytest.raises(FileNotFoundError):
        validate_and_read_csv_data("/nonexistent/path/to/file.csv")

def test_validate_read_csv_with_bom(tmp_path, app_context):
    file_content = create_csv_content(EXPECTED_HEADERS, [
        {DEVICE_ID_COLUMN_NAME: "IMEI123", TIMESTAMP_COLUMN_NAME: "2023-01-01 10:00:00", LATITUDE_COLUMN_NAME: "34.0", LONGITUDE_COLUMN_NAME: "-118.0"}
    ])
    p = tmp_path / "bom.csv"
    p.write_text(file_content, encoding="utf-8-sig")
    locations, device_id = validate_and_read_csv_data(str(p))
    assert device_id == "IMEI123"
    assert len(locations) == 1 