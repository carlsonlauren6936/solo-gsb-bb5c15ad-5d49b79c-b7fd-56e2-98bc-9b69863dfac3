"""计算过程中的业务错误。

所有错误都带可选的源码位置（基于字符的 0 起点偏移），
由 FastAPI 异常处理器统一转换为 400 响应体。
"""

from __future__ import annotations


class CalcError(Exception):
    """带错误码与出错位置的计算异常。"""

    def __init__(
        self,
        code: str,
        message: str,
        position: int | None = None,
        length: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        # position: 表达式中的字符偏移（0 起点，按 Unicode 字符计）
        self.position = position
        self.length = max(length, 1) if position is not None else None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "position": self.position,
            "length": self.length,
        }
