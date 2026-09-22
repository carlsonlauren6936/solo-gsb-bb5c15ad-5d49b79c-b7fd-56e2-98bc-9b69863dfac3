"""递归下降语法分析器。

文法（带单位后缀的数字字面量是最小因子）：

    expression := term   (('+' | '-') term)*
    term       := factor (('*' | '/') factor)*
    factor     := NUMBER [IDENT]      # 数字后紧跟标识符 => 单位后缀，如 12 mm
                | IDENT               # 变量引用
                | '(' expression ')'
                | ('+' | '-') factor  # 一元正负号

语法错误统一报 SYNTAX_ERROR，并携带期望/实际 token 的位置。
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import CalcError
from .lexer import Token, tokenize
from .units import UnitRegistry


# --- AST 节点 -----------------------------------------------------------------

@dataclass
class Node:
    start: int
    end: int


@dataclass
class NumberNode(Node):
    raw: str                  # 原始数字文本
    unit_name: str | None     # 紧跟的单位后缀（可能为 None）
    unit_start: int | None


@dataclass
class VariableNode(Node):
    name: str


@dataclass
class UnaryNode(Node):
    op: str                   # '+' / '-'
    operand: Node


@dataclass
class BinaryNode(Node):
    op: str                   # '+' / '-' / '*' / '/'
    left: Node
    right: Node
    op_start: int


# --- 解析器 -------------------------------------------------------------------

class Parser:
    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.i = 0

    @property
    def cur(self) -> Token:
        return self.toks[self.i]

    def advance(self) -> Token:
        tok = self.toks[self.i]
        if self.i < len(self.toks) - 1:
            self.i += 1
        return tok

    def parse(self) -> Node:
        node = self.expression()
        if self.cur.kind != "EOF":
            tok = self.cur
            raise CalcError(
                "SYNTAX_ERROR",
                f"语法错误：意外的 token '{tok.value}'，"
                "此处应为运算符或表达式结束",
                tok.start,
                tok.end - tok.start,
            )
        return node

    def expression(self) -> Node:
        node = self.term()
        while self.cur.kind in ("+", "-"):
            op = self.advance()
            right = self.term()
            node = BinaryNode(node.start, right.end, op.value, node, right,
                              op.start)
        return node

    def term(self) -> Node:
        node = self.factor()
        while self.cur.kind in ("*", "/"):
            op = self.advance()
            right = self.factor()
            node = BinaryNode(node.start, right.end, op.value, node, right,
                              op.start)
        return node

    def factor(self) -> Node:
        tok = self.cur

        if tok.kind in ("+", "-"):
            self.advance()
            operand = self.factor()
            return UnaryNode(tok.start, operand.end, tok.value, operand)

        if tok.kind == "(":
            self.advance()
            inner = self.expression()
            if self.cur.kind != ")":
                t = self.cur
                raise CalcError(
                    "SYNTAX_ERROR",
                    "语法错误：缺少右括号 ')'",
                    t.start,
                    max(t.end - t.start, 1),
                )
            close = self.advance()
            # 括号仅改变结合性；位置用括号整体，便于上层定位
            inner.start, inner.end = tok.start, close.end
            return inner

        if tok.kind == "NUMBER":
            self.advance()
            # 数字后紧跟标识符 => 单位后缀
            if self.cur.kind == "IDENT":
                unit_tok = self.advance()
                return NumberNode(tok.start, unit_tok.end, tok.value,
                                  unit_tok.value, unit_tok.start)
            return NumberNode(tok.start, tok.end, tok.value, None, None)

        if tok.kind == "IDENT":
            self.advance()
            return VariableNode(tok.start, tok.end, tok.value)

        if tok.kind == "EOF":
            raise CalcError(
                "SYNTAX_ERROR",
                "语法错误：表达式不完整，此处应有数字、变量或括号表达式",
                tok.start,
            )
        raise CalcError(
            "SYNTAX_ERROR",
            f"语法错误：意外的 token '{tok.value}'",
            tok.start,
            max(tok.end - tok.start, 1),
        )


def parse(text: str, registry: UnitRegistry) -> Node:
    return Parser(tokenize(text, registry)).parse()
