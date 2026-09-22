"""FastAPI 入口：设备工程测量计算 API。

启动时（lifespan）初始化内置单位表并挂到 ``app.state.registry``。
默认监听 8000 端口（见 Dockerfile / compose，或 uvicorn 参数）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .calculator import calculate, dimension_dict
from .errors import CalcError
from .evaluator import VariableValue
from .schemas import (
    CalculateRequest,
    CalculateResponse,
    ErrorBody,
    UnitInfo,
    UnitsResponse,
)
from .units import init_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：初始化内置单位表
    app.state.registry = init_registry()
    yield


app = FastAPI(
    title="设备工程测量计算 API",
    description=(
        "提交带数值、单位与变量的四则运算算式；服务端解析表达式、"
        "传播单位量纲、自动换算兼容单位，并拒绝不同量纲相加、"
        "除以带单位量等非法操作。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# --- 业务异常 -> 400 -----------------------------------------------------------

def _line_column(text: str, pos: int) -> tuple[int, int]:
    """把 0 起点字符偏移换算为（1 起点）行号、列号。"""
    line = text.count("\n", 0, pos) + 1
    last_nl = text.rfind("\n", 0, pos)
    column = pos - last_nl if last_nl == -1 else pos - last_nl
    return line, column


@app.exception_handler(CalcError)
async def calc_error_handler(request: Request, exc: CalcError) -> JSONResponse:
    body = exc.to_dict()
    if body["position"] is not None:
        try:
            expression = (await request.json()).get("expression", "")
        except Exception:
            expression = ""
        line, column = _line_column(expression, body["position"])
        body["line"] = line
        body["column"] = column
    else:
        body["line"] = None
        body["column"] = None
    return JSONResponse(status_code=400, content=body)


# --- 路由 ----------------------------------------------------------------------

@app.get("/health", tags=["meta"], summary="健康检查")
async def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/api/units",
    response_model=UnitsResponse,
    tags=["units"],
    summary="列出内置单位表",
)
async def list_units(request: Request) -> UnitsResponse:
    reg = request.app.state.registry
    infos = [
        UnitInfo(
            symbol=u.symbol,
            name=next(iter(u.aliases), u.symbol),
            dimension=dimension_dict(u.dimension),
            si_factor=u.factor,
            affine=u.affine,
        )
        for u in reg.all_units()
    ]
    return UnitsResponse(count=len(infos), units=infos)


@app.post(
    "/api/calculate",
    response_model=CalculateResponse,
    tags=["calculate"],
    summary="计算带单位的算式",
    responses={400: {"model": ErrorBody, "description": "计算/量纲/语法错误"}},
)
async def calculate_endpoint(
    payload: CalculateRequest, request: Request
) -> CalculateResponse:
    reg = request.app.state.registry
    variables = {
        name: VariableValue(value=v.value, unit=v.unit)
        for name, v in payload.variables.items()
    }
    result = calculate(
        expression=payload.expression,
        registry=reg,
        variables=variables,
        result_unit=payload.result_unit,
    )
    return CalculateResponse(
        expression=payload.expression,
        value=result.value,
        unit=result.unit,
        dimension=dimension_dict(result.dimension),
        result_unit_requested=payload.result_unit,
    )
