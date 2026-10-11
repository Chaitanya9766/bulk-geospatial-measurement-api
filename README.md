# Bulk Geospatial File Measurement API

A FastAPI backend that accepts KML files and ZIP archives containing a Shapefile, extracts features and attributes, and calculates polygon area and line length after transforming geometries into a suitable projected coordinate reference system (CRS).

## Features

- Upload a single `.kml` or `.zip` Shapefile: `POST /api/files/`
- Bulk upload multiple files: `POST /api/files/bulk/`
- Retrieve file metadata: `GET /api/files/{id}/`
- Retrieve feature geometry, attributes and measurements: `GET /api/files/{id}/measurements/`
- Projected measurements: polygon area in square metres; line length in metres
- Graceful status for points, empty geometries and unsupported geometry types
- File size limit and basic ZIP path validation
- Interactive API documentation at `/docs`

## Requirements

- Python 3.11 or later
- A compatible GDAL/Fiona installation with KML driver support for KML uploads

## Run locally (Windows)

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs>.

On some platforms, geospatial dependencies can require native GDAL libraries. Install GeoPandas using its recommended platform-specific instructions if pip cannot resolve the native dependencies.

## API

### 1. Upload one file

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -F "file=@survey.kml"
```

A zipped Shapefile should contain one `.shp` and its companion files, especially `.shx`, `.dbf`, and usually `.prj`.

Example response:

```json
{
  "id": "generated-file-id",
  "filename": "survey.kml",
  "feature_count": 120,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "status": "COMPLETED"
}
```

The values above are illustrative. The measurement CRS is selected for the uploaded dataset.

### 2. Bulk upload

```bash
curl -X POST "http://127.0.0.1:8000/api/files/bulk/" \
  -F "files=@survey.kml" \
  -F "files=@boundaries.zip"
```

Each file is processed independently. The response reports success or failure per file, so one invalid upload does not stop the other uploads.

### 3. Get file information

```bash
curl "http://127.0.0.1:8000/api/files/FILE_ID/"
```

### 4. Get measurements

```bash
curl "http://127.0.0.1:8000/api/files/FILE_ID/measurements/"
```

Each feature contains a zero-based `feature_id`, `geometry_type`, original geometry in GeoJSON-compatible form, source `crs`, properties, measurement value/unit when applicable, and a measurement status.

## Error behavior

- `400`: empty upload or missing bulk files
- `404`: unknown file ID
- `413`: file larger than 50 MiB
- `415`: unsupported extension
- `422`: unreadable geospatial data, malformed Shapefile ZIP, missing CRS or inability to choose a measurement CRS

Do not trust the filename or MIME type alone in a production deployment. Consider malware scanning, archive expansion limits, rate limits and authentication.

## Architecture

```text
Client / Postman
      |
      v
FastAPI routes (upload, bulk, metadata, measurements)
      |
      v
Validation + temporary file handling
      |
      v
GeoPandas / Fiona reads KML or zipped Shapefile
      |
      v
CRS selection + PyProj transformation
      |
      v
Shapely geometry measurements
      |
      v
JSON response + stored processed result
```

- `app/main.py`: creates the FastAPI app and registers routes.
- `app/routes/files.py`: upload, bulk upload, metadata and measurements endpoints.
- `app/services/geospatial.py`: reads data, chooses a projected CRS, extracts attributes and computes measurements.
- `app/storage.py`: in-memory record store for this demonstration.
- `tests/`: API behavior tests.

## File-processing flow

1. Validate extension, non-empty content and upload size.
2. Save upload to a temporary directory.
3. For ZIP input, check for unsafe archive paths and require exactly one Shapefile.
4. Read features using GeoPandas.
5. Validate CRS, select a measurement CRS and transform the geometries.
6. Calculate measurements, preserve original geometry and attributes, and store the result under a generated ID.
7. Return file metadata or measurement details through separate endpoints.

## CRS and measurement strategy

Area and length are not calculated directly from longitude/latitude degrees. If a dataset is already projected in metres, its CRS is reused. Otherwise, GeoPandas `estimate_utm_crs()` is used to select a local UTM CRS from dataset bounds, then `to_crs()` transforms the geometries before measurements are calculated.

Datasets without CRS metadata are rejected rather than assigned a guessed CRS. A single UTM zone is not appropriate for every global or multi-zone dataset; such datasets need a deliberate projection policy (for example, an equal-area CRS for area or geodesic methods for long-distance measurements).

## Design decisions and trade-offs

- **FastAPI:** lightweight, typed request handling and generated OpenAPI docs.
- **GeoPandas/Shapely/PyProj:** established vector-data, geometry and coordinate transformation tools rather than hand-written geometry math.
- **Temporary upload files:** keeps raw uploads out of permanent storage; processing results are retained in memory for this demo.
- **In-memory metadata:** simple to run locally, but records disappear on restart and are not shared between worker processes. Replace with a database and durable object storage for production.
- **Synchronous geospatial processing:** easy to understand for a small API. Large files should be queued to background workers.
- **Per-file bulk results:** one invalid file does not fail the entire batch.

## Run tests

```bash
pytest -q
```

These tests cover basic API behavior. Add integration tests using small real KML and zipped Shapefile fixtures before production use.

## Learning outcomes

This project provides practice with REST API design, multipart uploads, validation, vector geospatial formats, geometry types, projected CRS selection, measurement units, error handling and automated testing.

## Future scope

- Persist metadata in PostgreSQL/PostGIS and files in object storage.
- Background processing for large uploads.
- Authentication, authorization, rate limiting and audit logs.
- Configurable upload limits and archive expansion safeguards.
- Support GeoJSON and GeoPackage.
- Export measurements to CSV or downloadable GeoJSON.
- Add CI, Docker, structured logging and deployment monitoring.
- Improve projection selection for global, polar and multi-zone datasets.

## Limitations

This starter implementation uses in-memory storage and processes uploads synchronously. It is a foundation for a submission, not a fully hardened production deployment. KML driver availability varies by GDAL/Fiona installation. Always test the environment and sample datasets used by the evaluator.
