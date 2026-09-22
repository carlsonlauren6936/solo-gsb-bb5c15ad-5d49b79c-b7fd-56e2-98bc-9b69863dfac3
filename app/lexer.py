"""表达式词法分析器。

Token 类型：
    NUMBER  数值字面量（整数 / 小数 / 科学计数法）
    IDENT   标识符（变量名或单位符号，支持中文、希腊字母，以及
            m/s、km/h、r/min 这类含 '/' 的已注册复合单位）
    + - * / ( )
    EOF

分两阶段：
1) 扫描出基础 token，'/' 永远先当作运算符；
2) 合并阶段把相邻的 IDENT '/' IDENT( '/' IDENT) 序列，
   若整体在单位表中已注册（如 m/s、km/h、r/min），则合并为一个单位 token。
   其余 '/' 保持为除法运算符。

所有 token 都带 start/end，按 Unicode 字符偏移（0 起点）计，
便于把出错位置精确返回给客户端。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import CalcError
from .units import UnitRegistry

# 标识符首字符：字母（含希腊/中文等）、下划线，以及工程常用符号
_IDENT_START = re.compile(
    r"[A-Za-z°Ωμ_]"
    r"|[㐀-䶿一-鿿]"  # CJK 统一表意文字
)
# 标识符后续字符：上者再加数字、百分号、上标 ²³ 等
_IDENT_PART = re.compile(
    r"[A-Za-z0-9°Ωμ_%²³_']"
    r"|[㐀-䶿一-鿿]"
)
_NUMBER = re.compile(
    r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?"
)


@dataclass
class Token:
    kind: str          # NUMBER / IDENT / + / - / * / / / ( / ) / EOF
    value: str
    start: int         # 起始字符偏移（含）
    end: int           # 结束字符偏移（不含）


class Lexer:
    def __init__(self, text: str, registry: UnitRegistry):
        self.text = text
        self.reg = registry
        self.pos = 0
        self.n = len(text)
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        while self.pos < self.n:
            ch = self.text[self.pos]
            if ch in " \t\r\n":
                self.pos += 1
            elif ch in "+-*/()":
                self.tokens.append(Token(ch, ch, self.pos, self.pos + 1))
                self.pos += 1
            elif ch.isdigit() or ch == ".":
                self._read_number()
            elif _IDENT_START.match(ch) or ch == "%":
                self._read_ident()
            else:
                raise CalcError(
                    "INVALID_CHARACTER",
                    f"无法识别的字符 {ch!r}",
                    self.pos,
                )
        self.tokens.append(Token("EOF", "", self.pos, self.pos))
        self._merge_compound_units()
        return self.tokens

    # -- 基础 token -----------------------------------------------------------
    def _read_number(self) -> None:
        start = self.pos
        m = _NUMBER.match(self.text, self.pos)
        if m is None or m.group(0) == ".":
            raise CalcError(
                "INVALID_NUMBER",
                f"无效的数字（位置 {start} 附近）",
                start,
            )
        self.pos = m.end()
        self.tokens.append(Token("NUMBER", m.group(0), start, self.pos))

    def _read_ident(self) -> None:
        start = self.pos
        self.pos += 1
        while self.pos < self.n and _IDENT_PART.match(self.text[self.pos]):
            self.pos += 1
        self.tokens.append(
            Token("IDENT", self.text[start:self.pos], start, self.pos)
        )

    # -- 复合单位合并 ---------------------------------------------------------
    def _merge_compound_units(self) -> None:
        """合并形如 ``a/b(/c)`` 的已注册复合单位。

        两种起点：
        * IDENT '/' IDENT  —— m/s、km/h、r/min；
        * NUMBER '/' IDENT —— 1/s、1/m2 这类以数字开头的“每单位”，
          合并后整体作为一个单位标识符（其前面通常是数值字面量）。
        合并从左向右反复吸收 "/ IDENT" 段，只吞真正属于某单位符号的 '/'。
        """
        out: list[Token] = []
        i = 0
        toks = self.tokens
        while i < len(toks):
            tok = toks[i]
            can_start = tok.kind in ("IDENT", "NUMBER") and tok.kind != "EOF"
            if can_start and i + 2 < len(toks) \
                    and toks[i + 1].kind == "/" \
                    and toks[i + 2].kind == "IDENT":
                j = i
                merged = tok
                while (
                    j + 2 < len(toks)
                    and toks[j + 1].kind == "/"
                    and toks[j + 2].kind == "IDENT"
                ):
                    candidate = merged.value + "/" + toks[j + 2].value
                    if self.reg.get(candidate) is not None:
                        merged = Token(
                            "IDENT", candidate, merged.start, toks[j + 2].end
                        )
                        j += 2
                    else:
                        break
                if j > i:  # 确实发生了合并
                    out.append(merged)
                    i = j + 1
                    continue
            out.append(tok)
            i += 1
        self.tokens = out


def tokenize(text: str, registry: UnitRegistry) -> list[Token]:
    return Lexer(text, registry).tokenize()
