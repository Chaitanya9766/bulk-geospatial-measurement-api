from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rejects_unsupported_extension():
    response = client.post(
        "/api/files/",
        files={"file": ("notes.txt", b"not geospatial data", "text/plain")},
    )
    assert response.status_code == 415


def test_unknown_file_id_returns_404():
    response = client.get("/api/files/does-not-exist/")
    assert response.status_code == 404
