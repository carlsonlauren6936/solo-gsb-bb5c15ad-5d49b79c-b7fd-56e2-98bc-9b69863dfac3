"""合法计算路径：四则运算、括号、自动换算、量纲传播、结果规范化。"""

import pytest

from conftest import calc


def test_plain_arithmetics(client):
    r = calc(client, "(2 + 3) * 4 - 10 / 2")
    assert r.status_code == 200
    data = r.json()
    assert data["value"] == 15.0
    assert data["unit"] == "1"
    assert data["dimension"] == {}


def test_compatible_units_auto_conversion(client):
    # 12 mm + 1 in = 12 + 25.4 = 37.4 mm
    r = calc(client, "12 mm + 1 in", result_unit="mm")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["value"] == pytest.approx(37.4)
    assert data["unit"] == "mm"
    assert data["dimension"] == {"m": 1}


def test_length_addition_canonical_output(client):
    # 规范结果单位为 SI 基本单位 m
    r = calc(client, "2 mm + 3 cm")
    assert r.status_code == 200
    data = r.json()
    assert data["value"] == pytest.approx(0.032)
    assert data["unit"] == "m"


def test_multiply_dimensions_compose(client):
    # 10 N * 2 m = 20 J
    r = calc(client, "10 N * 2 m")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["value"] == pytest.approx(20.0)
    assert data["unit"] == "J"
    assert data["dimension"] == {"m": 2, "kg": 1, "s": -2}


def test_divide_by_scalar(client):
    # 18 km / 3 = 6 km；换算规范单位 m => 6000 m
    r = calc(client, "18 km / 3")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["value"] == pytest.approx(6000.0)
    assert data["unit"] == "m"


def test_divide_by_dimensionless_variable(client):
    r = calc(client, "100 km / factor",
             variables={"factor": {"value": 4, "unit": "one"}})
    assert r.status_code == 200
    assert r.json()["value"] == pytest.approx(25000.0)


def test_variable_with_unit(client):
    # v = 60 km/h, 2 h => 120 km
    r = calc(client, "v * 2 h",
             variables={"v": {"value": 60, "unit": "km/h"}},
             result_unit="km")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["value"] == pytest.approx(120.0)
    assert data["unit"] == "km"


def test_pressure_units_convert(client):
    r = calc(client, "1 atm + 1 bar", result_unit="kPa")
    assert r.status_code == 200
    assert r.json()["value"] == pytest.approx(201.325)


def test_unary_minus_and_parens(client):
    r = calc(client, "-(5 mm) + 10 mm", result_unit="mm")
    assert r.status_code == 200
    assert r.json()["value"] == pytest.approx(5.0)


def test_force_from_scalar_times_acceleration(client):
    # F = m * a，结果 10 N
    r = calc(client, "2 kg * 5 m/s2")
    assert r.status_code == 200
    data = r.json()
    assert data["value"] == pytest.approx(10.0)
    assert data["unit"] == "N"


def test_temperature_subtraction_is_delta(client):
    # 100 ℃ - 20 ℃ = 80 K 的温差
    r = calc(client, "100 degC - 20 degC")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["value"] == pytest.approx(80.0)
    assert data["unit"] == "K"


def test_fahrenheit_celsius_mix(client):
    # 32 ℉ = 0 ℃；32 ℉ - 0 ℃ => 0 K
    r = calc(client, "32 degF - 0 degC")
    assert r.status_code == 200
    assert r.json()["value"] == pytest.approx(0.0, abs=1e-9)


def test_percent_scalar(client):
    r = calc(client, "200 * 50 %")
    assert r.status_code == 200
    # 50% = 0.5，无量纲结果规范为 "1"
    data = r.json()
    assert data["value"] == pytest.approx(100.0)
    assert data["unit"] == "1"


def test_result_unit_dimension_mismatch_rejected(client):
    r = calc(client, "10 m", result_unit="kg")
    assert r.status_code == 400
    err = r.json()
    assert err["code"] == "DIMENSION_MISMATCH"


def test_chinese_unit_alias(client):
    r = calc(client, "1 公里 + 500 米", result_unit="km")
    assert r.status_code == 200, r.text
    assert r.json()["value"] == pytest.approx(1.5)


def test_pressure_via_reciprocal_unit(client):
    # 受“不得除以带单位量”约束，压强用 F * 1/m² 构造
    r = calc(
        client, "F * invA",
        variables={"F": {"value": 1000, "unit": "N"},
                   "invA": {"value": 10, "unit": "1/m2"}},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["value"] == pytest.approx(10000.0)
    assert data["unit"] == "Pa"


def test_per_minute_normalizes_to_hertz(client):
    r = calc(client, "120 1/min")
    assert r.status_code == 200
    assert r.json()["unit"] == "Hz"
    assert r.json()["value"] == pytest.approx(2.0)
