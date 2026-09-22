"""设备工程测量计算 API。

- units:      内置单位表与量纲（SI 基本量纲向量）
- lexer/parser: 算式词法/语法解析（四则运算、括号、单位后缀）
- evaluator:  求值并传播量纲、自动换算、校验非法运算
- calculator: 对外的计算门面，负责结果规范化
- main:       FastAPI 路由与启动初始化
"""

__version__ = "1.0.0"
