from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.geospatial import GeospatialProcessingError, process_file
from app.storage import FILES

router = APIRouter(tags=["Geospatial files"])
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MiB
ALLOWED_EXTENSIONS = {".kml", ".zip"}


async def _process_upload(upload: UploadFile) -> dict:
    filename = Path(upload.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a .kml file or a .zip containing a Shapefile.",
        )

    content = await upload.read(MAX_FILE_SIZE + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 50 MiB upload limit.")

    file_id = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="geospatial_api_") as tmp:
        path = Path(tmp) / filename
        path.write_bytes(content)
        try:
            result = process_file(path, filename)
        except GeospatialProcessingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = {
        "id": file_id,
        "filename": filename,
        "feature_count": result["feature_count"],
        "crs": result["crs"],
        "measurement_crs": result["measurement_crs"],
        "status": "COMPLETED",
        "features": result["features"],
    }
    FILES[file_id] = record
    return record


@router.post("/files/", status_code=status.HTTP_201_CREATED)
async def upload_file(file: Annotated[UploadFile, File(...)]):
    """Upload one .kml or zipped Shapefile."""
    record = await _process_upload(file)
    return {
        "id": record["id"],
        "filename": record["filename"],
        "feature_count": record["feature_count"],
        "crs": record["crs"],
        "measurement_crs": record["measurement_crs"],
        "status": record["status"],
    }


@router.post("/files/bulk/", status_code=status.HTTP_207_MULTI_STATUS)
async def bulk_upload_files(files: Annotated[list[UploadFile], File(...)]):
    """Process multiple files independently; one invalid file does not stop the batch."""
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one file.")
    results = []
    for upload in files:
        try:
            record = await _process_upload(upload)
            results.append({
                "filename": record["filename"],
                "id": record["id"],
                "status": "COMPLETED",
                "feature_count": record["feature_count"],
                "crs": record["crs"],
                "measurement_crs": record["measurement_crs"],
            })
        except HTTPException as exc:
            results.append({
                "filename": Path(upload.filename or "").name,
                "status": "FAILED",
                "error": exc.detail,
                "http_status": exc.status_code,
            })
    return {"total_files": len(files), "results": results}


@router.get("/files/{file_id}/")
def get_file_info(file_id: str):
    record = FILES.get(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File ID not found.")
    return {
        "id": record["id"],
        "filename": record["filename"],
        "feature_count": record["feature_count"],
        "crs": record["crs"],
        "measurement_crs": record["measurement_crs"],
        "status": record["status"],
    }


@router.get("/files/{file_id}/measurements/")
def get_measurements(file_id: str):
    record = FILES.get(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File ID not found.")
    return {
        "file_id": file_id,
        "filename": record["filename"],
        "source_crs": record["crs"],
        "measurement_crs": record["measurement_crs"],
        "feature_count": record["feature_count"],
        "features": record["features"],
    }
