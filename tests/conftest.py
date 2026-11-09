import pytest

from app import create_app, db


@pytest.fixture
def conn(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    c = db.connect(path)
    yield c
    c.close()


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "api.db"))
    app.testing = True
    return app.test_client()


@pytest.fixture
def projector(client):
    return client.post("/api/v1/equipment", json={"name": "Projector"}).get_json()
