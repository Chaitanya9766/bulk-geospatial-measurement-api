"""Small in-memory metadata store for the demo.

For production, replace this with a database and durable object storage.
Processed GeoJSON-like results are stored so later GET requests work.
"""
from typing import Any

FILES: dict[str, dict[str, Any]] = {}
