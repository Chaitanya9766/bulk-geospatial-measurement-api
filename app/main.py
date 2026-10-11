from fastapi import FastAPI
from app.routes.files import router

app = FastAPI(
    title="Bulk Geospatial File Measurement API",
    description="Upload KML or zipped Shapefiles and calculate projected area/length measurements.",
    version="1.0.0",
)
app.include_router(router, prefix="/api")

@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "service": "Geospatial File Measurement API"}
