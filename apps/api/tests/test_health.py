from grantlens_api import create_app
from grantlens_api.config import TestConfig


def test_health_ok():
    client = create_app(TestConfig).test_client()
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok", "db": True}
