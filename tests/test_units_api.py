"""单位表与元信息接口。"""

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_units_listing(client):
    r = client.get("/api/units")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] > 40
    symbols = {u["symbol"] for u in data["units"]}
    assert {"m", "kg", "s", "N", "Pa", "degC", "km/h"} <= symbols


def test_unit_dimensions(client):
    r = client.get("/api/units")
    units = {u["symbol"]: u for u in r.json()["units"]}
    assert units["N"]["dimension"] == {"m": 1, "kg": 1, "s": -2}
    assert units["degC"]["affine"] is True
    assert units["K"]["affine"] is False
