from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import mapping


SUPPORTED_EXTENSIONS = {".kml", ".zip"}


class GeospatialProcessingError(ValueError):
    """Raised when an upload cannot be read as supported geospatial data."""


def _read_geodataframe(path: Path, original_name: str) -> gpd.GeoDataFrame:
    suffix = Path(original_name).suffix.lower()
    try:
        if suffix == ".kml":
            # KML support depends on the installed GDAL/Fiona driver.
            return gpd.read_file(path, driver="KML")
        if suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                # Reject path traversal and unexpected archive entries.
                if any(Path(n).is_absolute() or ".." in Path(n).parts for n in names):
                    raise GeospatialProcessingError("ZIP contains unsafe file paths.")
                shp_names = [n for n in names if n.lower().endswith(".shp")]
                if len(shp_names) != 1:
                    raise GeospatialProcessingError(
                        "ZIP must contain exactly one .shp file and its companion files."
                    )
            # GeoPandas can read a zipped Shapefile through /vsizip on GDAL builds.
            try:
                return gpd.read_file(f"zip://{path.resolve()}!{shp_names[0]}")
            except Exception:
                # Fallback: extract only after validating archive paths.
                with tempfile.TemporaryDirectory(prefix="geo_upload_") as tmp:
                    with zipfile.ZipFile(path) as archive:
                        archive.extractall(tmp)
                    shp_path = Path(tmp) / shp_names[0]
                    if not shp_path.exists():
                        raise GeospatialProcessingError("Shapefile could not be located in ZIP.")
                    return gpd.read_file(shp_path)
        raise GeospatialProcessingError("Only .kml and .zip uploads are supported.")
    except GeospatialProcessingError:
        raise
    except Exception as exc:
        raise GeospatialProcessingError(
            "Could not read geospatial file. Check that it is valid and includes required files."
        ) from exc


def _choose_measurement_crs(gdf: gpd.GeoDataFrame):
    if gdf.crs is None:
        raise GeospatialProcessingError(
            "The file has no CRS metadata. Add a valid CRS before measuring."
        )
    try:
        crs = gdf.crs
        if crs.is_projected:
            # Use an existing projected CRS only when its axis units are metres.
            axis_units = [axis.unit_name.lower() for axis in crs.axis_info if axis.unit_name]
            if axis_units and all("metre" in unit or "meter" in unit for unit in axis_units):
                return crs
        estimated = gdf.estimate_utm_crs()
        if estimated is not None:
            return estimated
        # For non-local/global data, require an explicit projection choice rather
        # than silently measuring degrees or selecting a misleading projection.
        raise GeospatialProcessingError(
            "Could not estimate a suitable local projected CRS for this dataset."
        )
    except GeospatialProcessingError:
        raise
    except Exception as exc:
        raise GeospatialProcessingError("Unable to determine measurement CRS.") from exc


def process_file(path: Path, original_name: str) -> dict[str, Any]:
    gdf = _read_geodataframe(path, original_name)
    if gdf.empty:
        raise GeospatialProcessingError("The uploaded file contains no features.")

    source_crs = gdf.crs
    if source_crs is None:
        raise GeospatialProcessingError(
            "The file has no CRS metadata. Add a valid CRS before measuring."
        )
    measurement_crs = _choose_measurement_crs(gdf)
    projected = gdf.to_crs(measurement_crs)

    features = []
    for index, (_, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        props = {}
        for key, value in row.drop(labels=[gdf.geometry.name]).items():
            if value is None:
                props[str(key)] = None
            else:
                try:
                    # Convert numpy scalar values to JSON-friendly Python values.
                    props[str(key)] = value.item() if hasattr(value, "item") else value
                    json.dumps(props[str(key)])
                except (TypeError, ValueError):
                    props[str(key)] = str(value)

        feature: dict[str, Any] = {
            "feature_id": index,
            "geometry_type": geom.geom_type if geom is not None else None,
            "geometry": mapping(geom) if geom is not None and not geom.is_empty else None,
            "crs": source_crs.to_string(),
            "properties": props,
            "measurement": None,
            "measurement_unit": None,
            "measurement_status": "NOT_REQUIRED",
        }

        projected_geom = projected.geometry.iloc[index]
        if geom is None or geom.is_empty:
            feature["measurement_status"] = "SKIPPED_EMPTY_GEOMETRY"
        elif geom.geom_type == "Polygon" or geom.geom_type == "MultiPolygon":
            feature["measurement"] = float(projected_geom.area)
            feature["measurement_unit"] = "square_meters"
            feature["measurement_type"] = "area"
            feature["measurement_status"] = "COMPLETED"
        elif geom.geom_type == "LineString" or geom.geom_type == "MultiLineString":
            feature["measurement"] = float(projected_geom.length)
            feature["measurement_unit"] = "meters"
            feature["measurement_type"] = "length"
            feature["measurement_status"] = "COMPLETED"
        elif geom.geom_type in {"Point", "MultiPoint"}:
            feature["measurement_status"] = "NOT_REQUIRED"
        else:
            feature["measurement_status"] = "UNSUPPORTED_GEOMETRY"
        features.append(feature)

    return {
        "feature_count": len(features),
        "crs": source_crs.to_string(),
        "measurement_crs": measurement_crs.to_string(),
        "features": features,
    }
