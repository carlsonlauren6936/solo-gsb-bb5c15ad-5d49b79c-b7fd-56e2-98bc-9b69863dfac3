"""AST 求值与量纲传播。

求值结果统一用 SI 内部值表示（:class:`Quantity`），从而不同但兼容的
单位（mm 与 in、kgf 与 N……）能自动换算后参与运算。

量纲运算规则（对应需求中的合法性约束）：

* ``+`` / ``-``：两边量纲必须完全相同，否则 DIMENSION_MISMATCH；
  仿射温标（℃、℉）只允许加减，不允许乘除。
* ``*``：量纲向量逐维相加；仿射温标参与乘法一律拒绝
  （20 ℃ × 3 没有物理意义，温度差应先转为 K）。
* ``/``：除数必须是无量纲标量（需求约束：不得除以带单位的量），
  商的量纲与被除数相同。
* 一元负号：仅取负，量纲不变；仿射温度取负无意义，拒绝。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import CalcError
from .parser import BinaryNode, Node, NumberNode, UnaryNode, VariableNode
from .units import DIM_ZERO, Dimension, UnitDef, UnitRegistry, describe_dim


@dataclass
class Quantity:
    """运算中间值：SI 数值 + 来源单位（提供量纲与符号）。"""

    si_value: float
    unit: UnitDef

    @property
    def dimension(self) -> Dimension:
        return self.unit.dimension

    @property
    def dimensionless(self) -> bool:
        return self.unit.dimension == DIM_ZERO


class Evaluator:
    def __init__(self, registry: UnitRegistry,
                 variables: dict[str, "VariableValue"]):
        self.reg = registry
        self.vars = variables

    def eval(self, node: Node) -> Quantity:
        if isinstance(node, NumberNode):
            return self._eval_number(node)
        if isinstance(node, VariableNode):
            return self._eval_variable(node)
        if isinstance(node, UnaryNode):
            return self._eval_unary(node)
        if isinstance(node, BinaryNode):
            return self._eval_binary(node)  # type: ignore[arg-type]
        raise CalcError("INTERNAL_ERROR", f"未知的语法节点: {type(node)!r}")

    # -- 字面量与变量 ---------------------------------------------------------
    def _eval_number(self, node: NumberNode) -> Quantity:
        try:
            value = float(node.raw)
        except ValueError:
            raise CalcError(
                "INVALID_NUMBER", f"无效的数字 {node.raw!r}", node.start,
                node.end - node.start,
            ) from None
        if not math.isfinite(value):
            raise CalcError(
                "INVALID_NUMBER", "数值必须为有限数", node.start,
                node.end - node.start,
            )
        if node.unit_name is None:
            # 裸数字 => 无量纲标量
            unit = self.reg.canonical_unit(DIM_ZERO)
            return Quantity(value, unit)

        unit = self.reg.require(node.unit_name, node.unit_start,
                                node.end - (node.unit_start or node.start))
        return Quantity(unit.to_si(value), unit)

    def _eval_variable(self, node: VariableNode) -> Quantity:
        var = self.vars.get(node.name)
        if var is None:
            raise CalcError(
                "UNKNOWN_VARIABLE",
                f"未定义的变量 '{node.name}'（请在请求的 variables 中提供，"
                "或检查单位拼写）",
                node.start,
                node.end - node.start,
            )
        unit = self.reg.require(var.unit, node.start, node.end - node.start)
        value = var.value
        if not math.isfinite(value):
            raise CalcError(
                "INVALID_VALUE",
                f"变量 '{node.name}' 的值必须为有限数",
                node.start,
                node.end - node.start,
            )
        return Quantity(unit.to_si(value), unit)

    # -- 运算 -----------------------------------------------------------------
    def _eval_unary(self, node: UnaryNode) -> Quantity:
        q = self.eval(node.operand)
        if node.op == "+":
            return q
        if node.op == "-":
            if q.unit.affine:
                raise CalcError(
                    "AFFINE_TEMPERATURE_OPERATION",
                    f"不能对仿射温度 '{q.unit.symbol}' 取负："
                    "请先换算为绝对温度 K（温度差请用 K 表示）",
                    node.start,
                )
            return Quantity(-q.si_value, q.unit)
        raise CalcError("INTERNAL_ERROR", f"未知一元运算符 {node.op!r}")

    def _eval_binary(self, node: BinaryNode) -> Quantity:
        left = self.eval(node.left)
        right = self.eval(node.right)

        if node.op in ("+", "-"):
            return self._add_sub(node, left, right)
        if node.op == "*":
            return self._multiply(node, left, right)
        if node.op == "/":
            return self._divide(node, left, right)
        raise CalcError("INTERNAL_ERROR", f"未知二元运算符 {node.op!r}")

    def _add_sub(self, node: BinaryNode, left: Quantity,
                 right: Quantity) -> Quantity:
        if left.dimension != right.dimension:
            raise CalcError(
                "DIMENSION_MISMATCH",
                "只能对相同量纲执行加减：左侧是 "
                f"'{describe_dim(left.dimension)}'，右侧是 "
                f"'{describe_dim(right.dimension)}'",
                node.op_start,
            )
        if left.unit.affine or right.unit.affine:
            if node.op == "+":
                # 点温 + 点温 / 点温 + 量 没有无歧义的物理含义
                raise CalcError(
                    "AFFINE_TEMPERATURE_OPERATION",
                    "仿射温度（℃/℉）不能相加：点温相加没有物理意义，"
                    "温度差请先用 K 表示",
                    node.op_start,
                )
            # 点温相减 => 温度差，统一以绝对温标 K 表达
            return Quantity(
                left.si_value - right.si_value,
                self.reg.canonical_unit(left.dimension),
            )
        if node.op == "+":
            value = left.si_value + right.si_value
        else:
            value = left.si_value - right.si_value
        # 结果保留左侧单位的语义（同量纲，SI 内部值已自动换算）
        return Quantity(value, left.unit)

    def _multiply(self, node: BinaryNode, left: Quantity,
                  right: Quantity) -> Quantity:
        if left.unit.affine or right.unit.affine:
            raise CalcError(
                "AFFINE_TEMPERATURE_OPERATION",
                "仿射温度（℃/℉）不能参与乘法：绝对温度乘法没有物理意义，"
                "温度差请改用 K",
                node.op_start,
            )
        dim_vec = tuple(a + b for a, b in zip(left.dimension,
                                              right.dimension))
        unit = self.reg.canonical_unit(dim_vec)  # type: ignore[arg-type]
        return Quantity(left.si_value * right.si_value, unit)

    def _divide(self, node: BinaryNode, left: Quantity,
                right: Quantity) -> Quantity:
        # 需求约束：除数必须是无量纲标量
        if not right.dimensionless:
            raise CalcError(
                "DIVISION_BY_DIMENSIONAL",
                "除数必须是无量纲标量，不能除以带单位的量 "
                f"'{right.unit.symbol}'（{describe_dim(right.dimension)}）。"
                "如需单位换算或求复合量，请使用相乘或改用标量除数",
                node.op_start,
            )
        if right.si_value == 0.0:
            raise CalcError(
                "DIVISION_BY_ZERO",
                "除数为零",
                node.right.start,
                node.right.end - node.right.start,
            )
        if left.unit.affine:
            raise CalcError(
                "AFFINE_TEMPERATURE_OPERATION",
                "仿射温度（℃/℉）不能与标量相除：请先换算为 K",
                node.op_start,
            )
        return Quantity(left.si_value / right.si_value, left.unit)


# 供 API 层传入的变量值（避免与 schemas.py 形成循环依赖）
@dataclass
class VariableValue:
    """最小变量结构：具名数值 + 单位（无量纲时 unit 为 'one'）。"""

    value: float
    unit: str
