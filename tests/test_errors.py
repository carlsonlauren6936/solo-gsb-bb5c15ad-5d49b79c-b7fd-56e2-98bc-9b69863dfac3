"""非法操作与错误定位：量纲冲突、除以带单位量、语法错误等。"""

from conftest import calc


def test_add_different_dimensions(client):
    r = calc(client, "3 m + 2 kg")
    assert r.status_code == 400
    err = r.json()
    assert err["code"] == "DIMENSION_MISMATCH"
    # '+' 在 "3 m + 2 kg" 中的偏移为 4（0 起点）
    assert err["position"] == 4
    assert err["length"] == 1
    assert err["line"] == 1
    assert err["column"] == 5


def test_subtract_different_dimensions(client):
    r = calc(client, "10 s - 5 A")
    assert r.status_code == 400
    assert r.json()["code"] == "DIMENSION_MISMATCH"


def test_divide_by_dimensional_variable_rejected(client):
    r = calc(client, "100 m / 10 s")
    assert r.status_code == 400
    err = r.json()
    assert err["code"] == "DIVISION_BY_DIMENSIONAL"
    # 位置指向除号
    assert err["position"] == 6


def test_divide_by_dimensional_variable_2(client):
    r = calc(client, "distance / t",
             variables={"distance": {"value": 100, "unit": "m"},
                        "t": {"value": 10, "unit": "s"}})
    assert r.status_code == 400
    assert r.json()["code"] == "DIVISION_BY_DIMENSIONAL"


def test_division_by_zero(client):
    r = calc(client, "10 m / 0")
    assert r.status_code == 400
    assert r.json()["code"] == "DIVISION_BY_ZERO"


def test_unknown_variable(client):
    r = calc(client, "2 * xyz")
    assert r.status_code == 400
    err = r.json()
    assert err["code"] == "UNKNOWN_VARIABLE"
    assert err["position"] == 4
    assert "xyz" in err["message"]


def test_unknown_unit(client):
    r = calc(client, "10 parsec")
    assert r.status_code == 400
    err = r.json()
    assert err["code"] == "UNKNOWN_UNIT"
    # 位置指向单位片段
    assert err["position"] == 3
    assert "parsec" in err["message"]


def test_unknown_unit_suggestion(client):
    r = calc(client, "10 mete")
    assert r.status_code == 400
    err = r.json()
    assert err["code"] == "UNKNOWN_UNIT"
    assert "m" in err["message"]  # 最近匹配建议


def test_syntax_error_unbalanced_paren(client):
    r = calc(client, "(2 + 3")
    assert r.status_code == 400
    assert r.json()["code"] == "SYNTAX_ERROR"


def test_syntax_error_double_operator(client):
    r = calc(client, "2 * * 3")
    assert r.status_code == 400
    assert r.json()["code"] == "SYNTAX_ERROR"


def test_syntax_error_trailing_operator(client):
    r = calc(client, "2 +")
    assert r.status_code == 400
    assert r.json()["code"] == "SYNTAX_ERROR"


def test_invalid_character(client):
    r = calc(client, "2 m @ 3")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_CHARACTER"
    assert r.json()["position"] == 4


def test_temperature_multiply_rejected(client):
    r = calc(client, "20 degC * 3")
    assert r.status_code == 400
    assert r.json()["code"] == "AFFINE_TEMPERATURE_OPERATION"


def test_temperature_add_rejected(client):
    r = calc(client, "20 degC + 10 degC")
    assert r.status_code == 400
    assert r.json()["code"] == "AFFINE_TEMPERATURE_OPERATION"


def test_empty_expression(client):
    r = client.post("/api/calculate", json={"expression": "   "})
    assert r.status_code == 400
    assert r.json()["code"] == "EMPTY_EXPRESSION"


def test_missing_expression_body(client):
    r = client.post("/api/calculate", json={})
    # 请求体结构错误由 FastAPI/Pydantic 返回 422
    assert r.status_code == 422


def test_multiline_position_reports_line_column(client):
    expr = "(1 m\n + 2 kg)"
    r = calc(client, expr)
    assert r.status_code == 400
    err = r.json()
    assert err["code"] == "DIMENSION_MISMATCH"
    assert err["line"] == 2
