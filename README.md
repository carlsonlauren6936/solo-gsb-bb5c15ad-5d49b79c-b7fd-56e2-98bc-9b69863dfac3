# 设备工程测量计算 API

基于 Python + FastAPI 的工程测量计算服务：客户端提交**含数值、单位与变量的算式**
（支持 `+ - * /` 与括号），服务端解析表达式并**传播单位量纲**，对兼容单位
（如 mm 与 in、atm 与 bar、℃ 与 ℉）**自动换算**，并拒绝以下非法操作：

* 不同量纲相加 / 相减（如 `3 m + 2 kg`）；
* 除以带单位的量（如 `100 m / 10 s`），除数必须是无量纲标量；
* 仿射温标（℃/℉）参与乘法、加法或取负；
* 引用未定义的变量 / 单位，以及各类语法错误。

所有错误均返回**出错位置**（0 起点字符偏移 + 1 起点行列号 + 片段长度）。

## 目录结构

```
app/
  units.py       内置单位表、量纲向量、SI 仿射换算、单位规范化
  lexer.py       词法分析（数字 / 标识符 / 单位后缀 / 复合单位 m/s）
  parser.py      递归下降语法分析（四则运算、括号、一元负号）
  evaluator.py   AST 求值：量纲传播与合法性校验
  calculator.py  计算门面：解析→求值→规范化输出
  schemas.py     Pydantic 请求 / 响应模型
  main.py        FastAPI 入口、lifespan 启动初始化、异常处理
tests/           pytest 测试（37 个）
Dockerfile
docker-compose.yml
```

## 快速开始

### Docker Compose（默认端口 8000）

```bash
docker compose up --build
```

打开交互文档：<http://localhost:8000/docs>

### 本地运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

测试：

```bash
pip install -r requirements-dev.txt
pytest -q
```

## API

### `POST /api/calculate` — 计算带单位的算式

请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `expression` | string | 是 | 算式，数字后可直接跟单位，如 `12 mm + 1 in` |
| `variables` | object | 否 | 变量表：`{名字: {value, unit}}`，`unit` 省略表示无量纲纯数 |
| `result_unit` | string | 否 | 期望的结果单位；量纲不匹配会报错。缺省用规范（SI/导出）单位 |

#### 成功响应

```bash
curl -s -X POST http://localhost:8000/api/calculate \
  -H 'Content-Type: application/json' \
  -d '{"expression":"12 mm + 1 in","result_unit":"mm"}'
```

```json
{
  "expression": "12 mm + 1 in",
  "value": 37.4,
  "unit": "mm",
  "dimension": {"m": 1},
  "result_unit_requested": "mm"
}
```

`dimension` 是结果的量纲（基本单位指数，指数为 0 的维度省略），
例如牛顿为 `{"m":1,"kg":1,"s":-2}`，无量纲结果为 `{}`。

#### 量纲冲突（400，带出错位置）

```bash
curl -s -X POST http://localhost:8000/api/calculate \
  -H 'Content-Type: application/json' -d '{"expression":"3 m + 2 kg"}'
```

```json
{
  "code": "DIMENSION_MISMATCH",
  "message": "只能对相同量纲执行加减：左侧是 '长度'，右侧是 '质量'",
  "position": 4,
  "length": 1,
  "line": 1,
  "column": 5
}
```

#### 除以带单位的量（400）

```bash
curl -s -X POST http://localhost:8000/api/calculate \
  -H 'Content-Type: application/json' -d '{"expression":"100 m / 10 s"}'
```

```json
{
  "code": "DIVISION_BY_DIMENSIONAL",
  "message": "除数必须是无量纲标量，不能除以带单位的量 's'（时间）。如需单位换算或求复合量，请使用相乘或改用标量除数",
  "position": 6, "length": 1, "line": 1, "column": 7
}
```

#### 使用变量

```bash
curl -s -X POST http://localhost:8000/api/calculate \
  -H 'Content-Type: application/json' \
  -d '{
    "expression": "v * 2 h",
    "variables": {"v": {"value": 60, "unit": "km/h"}},
    "result_unit": "km"
  }'
# => {"value": 120.0, "unit": "km", "dimension": {"m": 1}, ...}
```

### `GET /api/units` — 内置单位表

返回全部可用单位及其量纲与 SI 换算系数，可用于客户端构造单位选择器。

### `GET /health` — 健康检查

## 计算规则

**量纲模型**：内部采用 8 维指数向量 —— 7 个 SI 基本量纲
（长度 m、质量 kg、时间 s、电流 A、温度 K、物质的量 mol、发光强度 cd）
外加一个「平面角 rad」伪量纲（工程惯例：弧度不与纯数字混用）。

**换算模型**：`si = value × factor + offset`。`offset` 仅用于摄氏度、
华氏度等平移温标。运算一律先转 SI 值，再按结果单位转回。

| 运算 | 规则 |
| --- | --- |
| `+` / `-` | 两边量纲必须相同（兼容单位自动换算后相加减） |
| `*` | 量纲指数逐维相加，结果取命名导出单位（如 N·m → J）或基本单位组合 |
| `/` | **除数必须无量纲**（`%`、`ppm`、纯数及无量纲变量）；除零返回 `DIVISION_BY_ZERO` |
| 一元 `-` | 量纲不变取负；仿射温度取负被拒绝 |

仿射温标的特殊处理：

* `100 degC - 20 degC` 是**温度差**，结果为 `80 K`；
* `20 degC + 30 degC`（点温相加）被拒绝——无唯一物理含义；
* 温度差参与乘法时请直接用 K（如 `80 K * 2`）。

> 为什么不允许除以带单位的量？
> 这是本服务（面向设备工程参数校验）的明确约束：除以带单位量会在一条
> 表达式里隐式引入任意复合量纲，容易掩盖量纲误用。需要复合量时请用
> 乘法 + 倒数单位表达，例如压强 `F * invA`（`invA` 单位 `1/m2`）：
>
> ```bash
> curl -s -X POST http://localhost:8000/api/calculate \
>   -H 'Content-Type: application/json' \
>   -d '{"expression":"F * invA",
>        "variables":{"F":{"value":1000,"unit":"N"},
>                     "invA":{"value":10,"unit":"1/m2"}}}'
> # => {"value": 10000.0, "unit": "Pa", ...}
> ```

## 单位书写

* 数字后紧跟单位：`2 mm`、`1 in`、`100 degC`、`50 %`；
* 变量：在 `variables` 中声明，支持英文名与中文名（如 `"长度"`）；
* 复合单位整体书写：`60 km/h`、`3000 rpm`、`120 1/min`；
* 别名丰富：`米/公尺/meter`、`公斤/kg`、`℃/摄氏度/celsius`、
  `公里/千米/km`、`Ω/欧姆/ohm` 等均可识别，拼错时会返回最近匹配建议。

内置单位覆盖长度、面积/体积、质量、时间、电流、温度、角度、力、
压力、能量、功率、频率、电压/电阻/电容/电荷/电感/磁通/特斯拉、
光通量/照度、速度/加速度等类别（共 100+ 符号与别名），完整列表见
`GET /api/units`。

## 错误码

| code | 触发场景 |
| --- | --- |
| `SYNTAX_ERROR` | 括号不匹配、运算符残缺、多余 token 等 |
| `INVALID_CHARACTER` / `INVALID_NUMBER` | 非法字符 / 非法数字字面量 |
| `UNKNOWN_VARIABLE` | 表达式引用了未在 `variables` 中提供的名字 |
| `UNKNOWN_UNIT` | 单位未注册（附带最近拼写建议） |
| `DIMENSION_MISMATCH` | 加减两边量纲不一致，或结果单位量纲不符 |
| `DIVISION_BY_DIMENSIONAL` | 除数带单位 |
| `DIVISION_BY_ZERO` | 标量除数为 0 |
| `AFFINE_TEMPERATURE_OPERATION` | ℃/℉ 被取负、相加或参与乘除 |
| `EMPTY_EXPRESSION` | 表达式为空串 |

请求体自身的结构校验（缺少 `expression`、类型错误等）由 FastAPI 返回 `422`。

## 端口配置

容器内固定监听 8000 端口（Dockerfile `EXPOSE 8000`、compose 端口映射
`8000:8000`）。宿主机映射可在 `docker-compose.yml` 的 `ports` 中调整。
