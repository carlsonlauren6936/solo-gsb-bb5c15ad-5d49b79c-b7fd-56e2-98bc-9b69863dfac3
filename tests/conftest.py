"""pytest 共享夹具：启动 app（lifespan 会初始化内置单位表）。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def calc(client, expression, variables=None, result_unit=None):
    body = {"expression": expression}
    if variables is not None:
        body["variables"] = variables
    if result_unit is not None:
        body["result_unit"] = result_unit
    return client.post("/api/calculate", json=body)
