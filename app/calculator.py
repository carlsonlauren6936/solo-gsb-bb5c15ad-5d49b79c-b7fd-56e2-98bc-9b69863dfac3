"""计算门面：解析 -> 求值 -> 规范化结果。

规范化结果默认用 SI/导出单位表达（``canonical_unit``）；
客户端可通过 ``result_unit`` 指定希望的输出单位，此时会再次做
量纲兼容检查并换算。
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import CalcError
from .evaluator import Evaluator, Quantity, VariableValue
from .parser import parse
from .units import DIM_ZERO, UnitRegistry, describe_dim, format_dim

# 浮点清理阈值：小于该相对量的尾巴视为二进制浮点噪声
_EPS = 1e-12


def tidy_number(x: float) -> float:
    """清理二进制浮点误差并限制输出有效位数（12 位）。"""
    if x == 0.0:
        return 0.0
    ax = abs(x)
    # 极接近整数（相对误差 < EPS）直接取整
    rounded = round(x)
    if rounded != 0 and abs(x - rounded) / ax < _EPS:
        return float(rounded)
    # 限制 12 位有效数字，去掉 0.30000000000000004 之类的尾巴
    from math import floor, log10
    digits = 12 - int(floor(log10(ax))) - 1
    quant = 10 ** digits
    y = round(x * quant) / quant
    if abs(y - x) / ax < 1e-10:
        return y
    return x


def dimension_dict(dimension: tuple[int, ...]) -> dict[str, int]:
    """把量纲向量转成 {基本单位符号: 指数}，省略 0 指数。"""
    return {
        sym: exp for sym, exp in
        zip(("m", "kg", "s", "A", "K", "mol", "cd", "rad"), dimension)
        if exp != 0
    }


@dataclass
class CalculationResult:
    value: float
    unit: str
    dimension: tuple[int, ...]


def calculate(
    expression: str,
    registry: UnitRegistry,
    variables: dict[str, VariableValue] | None = None,
    result_unit: str | None = None,
) -> CalculationResult:
    if not expression or not expression.strip():
        raise CalcError("EMPTY_EXPRESSION", "表达式为空", 0, 0)

    ast = parse(expression, registry)
    quantity = Evaluator(registry, variables or {}).eval(ast)

    # 默认规范化：量纲对应的规范单位
    out_unit = registry.canonical_unit(quantity.dimension)

    if result_unit is not None:
        target = registry.require(result_unit)
        if target.dimension != quantity.dimension:
            raise CalcError(
                "DIMENSION_MISMATCH",
                f"结果量纲为 '{describe_dim(quantity.dimension)}'，"
                f"无法以单位 '{result_unit}'"
                f"（{describe_dim(target.dimension)}）表示",
            )
        out_unit = target

    value = out_unit.from_si(quantity.si_value)
    value = tidy_number(value)
    return CalculationResult(
        value=value,
        unit=out_unit.symbol,
        dimension=quantity.dimension,
    )
