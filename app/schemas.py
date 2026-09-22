"""请求 / 响应的 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Variable(BaseModel):
    """客户端提交的一个具名测量值。"""

    value: float = Field(..., description="数值")
    unit: str = Field("one", description="单位符号（缺省视为无量纲纯数）")

    @field_validator("unit")
    @classmethod
    def _unit_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("单位不能为空字符串（无量纲请用 'one'）")
        return v.strip()


class CalculateRequest(BaseModel):
    expression: str = Field(
        ...,
        min_length=1,
        description="含数值、单位与变量的算式，如 '(12 mm + 1 in) * x'",
        examples=["2 mm + 3 cm", "60 km/h * 2", "force / 9.8"],
    )
    variables: dict[str, Variable] = Field(
        default_factory=dict,
        description="算式中引用的变量及其数值、单位",
    )
    result_unit: str | None = Field(
        default=None,
        description="期望的结果单位（量纲必须与结果一致）；缺省用规范单位",
    )


class ErrorBody(BaseModel):
    code: str = Field(..., description="错误码，如 DIMENSION_MISMATCH")
    message: str
    position: int | None = Field(
        None, description="出错起始字符偏移（0 起点），无法定位时为 null"
    )
    length: int | None = Field(None, description="出错片段长度（字符数）")
    line: int | None = Field(None, description="行号（1 起点）")
    column: int | None = Field(None, description="列号（1 起点）")


class CalculateResponse(BaseModel):
    expression: str
    value: float = Field(..., description="规范化后的数值")
    unit: str = Field(..., description="规范化后的单位符号")
    dimension: dict[str, int] = Field(
        ..., description="量纲：{基本单位符号: 指数}"
    )
    result_unit_requested: str | None = Field(
        None, description="客户端请求的结果单位（若有）"
    )


class UnitInfo(BaseModel):
    symbol: str
    name: str
    dimension: dict[str, int]
    si_factor: float
    affine: bool


class UnitsResponse(BaseModel):
    count: int
    units: list[UnitInfo]
