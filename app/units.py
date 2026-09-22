"""内置单位表与量纲系统。

量纲使用 8 维指数向量表示，前 7 维对应 SI 基本量纲，
最后一维是「平面角」伪量纲——在 SI 中角度无量纲，但工程测量里
弧度与纯数字不能互相混用，这里将其独立成维（工程惯例，类似 Boost.Units
的 angle 建模方式）。

    (长度 L, 质量 M, 时间 T, 电流 I, 热力学温度 Θ,
     物质的量 N, 发光强度 J, 平面角 A)

单位到 SI 的换算采用仿射模型：``si = value * factor + offset``，
其中 ``offset`` 仅用于摄氏度、华氏度这类平移温标。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from .errors import CalcError

# --- 量纲向量各维对应的基本单位符号，顺序即向量索引 -------------------------
BASE_SYMBOLS = ("m", "kg", "s", "A", "K", "mol", "cd", "rad")

# 量纲各维的中文名（用于错误信息）
DIM_NAMES = (
    "长度",
    "质量",
    "时间",
    "电流",
    "温度",
    "物质的量",
    "发光强度",
    "平面角",
)

Dimension = tuple[int, ...]
DIM_ZERO: Dimension = (0, 0, 0, 0, 0, 0, 0, 0)


def dim(**kw: int) -> Dimension:
    """按名称构造量纲向量，如 ``dim(L=1, T=-2)``。"""
    names = ("L", "M", "T", "I", "Theta", "N", "J", "A")
    vec = [0] * 8
    for key, value in kw.items():
        try:
            vec[names.index(key)] = value
        except ValueError:
            raise ValueError(f"未知量纲名: {key}") from None
    return tuple(vec)  # type: ignore[return-value]


@dataclass(frozen=True)
class UnitDef:
    """一个单位的定义。

    symbol:   规范符号，也是注册表的主键
    aliases:  可接受的别名（中文、全称等）
    dimension:量纲向量
    factor:   线性换算系数（到 SI）
    offset:   仿射平移项（到 SI），仅温标使用
    affine:   是否为仿射（平移）单位
    canonical:该量纲是否优先用此单位表达结果
    """

    symbol: str
    dimension: Dimension
    factor: float = 1.0
    aliases: frozenset[str] = frozenset()
    offset: float = 0.0
    affine: bool = False
    canonical: bool = False

    def to_si(self, value: float) -> float:
        return value * self.factor + self.offset

    def from_si(self, value: float) -> float:
        return (value - self.offset) / self.factor


@dataclass
class UnitRegistry:
    """单位注册表：应用启动时初始化内置单位表，运行期只读。"""

    _by_name: dict[str, UnitDef] = field(default_factory=dict)

    # -- 注册与查询 -----------------------------------------------------------
    def add(
        self,
        symbol: str,
        dimension: Dimension,
        factor: float = 1.0,
        aliases: tuple[str, ...] = (),
        offset: float = 0.0,
        affine: bool = False,
        canonical: bool = False,
    ) -> None:
        unit = UnitDef(
            symbol=symbol,
            dimension=dimension,
            factor=factor,
            aliases=frozenset(aliases),
            offset=offset,
            affine=affine,
            canonical=canonical,
        )
        for name in (symbol, *aliases):
            self._by_name[name] = unit

    def get(self, name: str) -> UnitDef | None:
        return self._by_name.get(name)

    def require(self, name: str, position: int | None = None,
                length: int = 1) -> UnitDef:
        """查询单位，不存在则抛 UNKNOWN_UNIT（带最近匹配建议）。"""
        unit = self._by_name.get(name)
        if unit is not None:
            return unit
        suggestion = self._suggest(name)
        hint = f"，是否想用 '{suggestion}'？" if suggestion else ""
        raise CalcError(
            "UNKNOWN_UNIT",
            f"未知单位 '{name}'{hint}",
            position,
            length,
        )

    def _suggest(self, name: str) -> str | None:
        """简单的最近匹配：公共前缀最长或编辑距离最小的符号。"""
        symbols = sorted({u.symbol for u in self._by_name.values()})
        best: str | None = None
        best_score = -1
        for sym in symbols:
            score = _common_prefix_len(name, sym)
            if score > best_score and score >= max(1, min(len(name), 2)):
                best, best_score = sym, score
        return best

    def all_units(self) -> list[UnitDef]:
        """去重后的全部单位（按符号排序）。"""
        seen: set[str] = set()
        result: list[UnitDef] = []
        for unit in self._by_name.values():
            if unit.symbol not in seen:
                seen.add(unit.symbol)
                result.append(unit)
        return sorted(result, key=lambda u: u.symbol)

    # -- 量纲换算与表达 -------------------------------------------------------
    def convert(
        self,
        value: float,
        src: UnitDef,
        dst: UnitDef,
        position: int | None = None,
    ) -> float:
        """把数值从 src 换算到 dst；量纲不兼容时抛错。"""
        if src.dimension != dst.dimension:
            raise CalcError(
                "DIMENSION_MISMATCH",
                f"单位不兼容：'{src.symbol}'（{format_dim(src.dimension)}）"
                f"无法换算为 '{dst.symbol}'（{format_dim(dst.dimension)}）",
                position,
            )
        si = src.to_si(value)
        return dst.from_si(si)

    def canonical_unit(self, dimension: Dimension) -> UnitDef:
        """返回该量纲用于规范化表达的单位。

        优先取标记为 canonical 的命名单位（如 N、Pa、m/s），
        否则由基本单位符号组合而成（合成单位无需注册）。
        """
        for unit in self._by_name.values():
            if unit.dimension == dimension and unit.canonical:
                return unit
        symbol = format_dim(dimension) or "1"
        return UnitDef(symbol=symbol, dimension=dimension)


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


# --- 量纲格式化 ---------------------------------------------------------------

# 优先使用的导出单位（比纯基本单位组合更工程化）
_PREFERRED_DERIVED: dict[Dimension, str] = {}


def _fractions_gcd(a: int, b: int) -> int:  # 指数恒为整数，留作扩展
    return math.gcd(a, b)


# Unicode 上标，用于把 m^2 表达为 m²
_SUPERSCRIPTS = {
    "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
}


def _sup(n: int) -> str:
    if n == 1:
        return ""
    return "".join(_SUPERSCRIPTS[ch] for ch in str(n))


def format_dim(dimension: Dimension) -> str:
    """把量纲向量格式化为工程单位符号，如 m·kg·s⁻²。"""
    # 1) 命名导出单位优先
    if dimension in _PREFERRED_DERIVED:
        return _PREFERRED_DERIVED[dimension]
    # 2) 基本单位幂连乘
    positive, negative = [], []
    for symbol, exp in zip(BASE_SYMBOLS, dimension):
        if exp > 0:
            positive.append(symbol + _sup(exp))
        elif exp < 0:
            negative.append(symbol + _sup(-exp))
    if positive and negative:
        return "·".join(positive) + "/" + "·".join(negative)
    if positive:
        return "·".join(positive)
    if negative:
        # 无正幂时以 1 作分子，如 1/s（频率回退场景）
        return "1/" + "·".join(negative)
    return "1"


def describe_dim(dimension: Dimension) -> str:
    """把量纲向量格式化为中文描述，用于错误信息，如「长度/时间」。"""
    positive, negative = [], []
    for name, exp in zip(DIM_NAMES, dimension):
        if exp > 0:
            positive.append(name if exp == 1 else f"{name}^{exp}")
        elif exp < 0:
            negative.append(name if exp == -1 else f"{name}^{-exp}")
    if positive and negative:
        return "·".join(positive) + "/" + "·".join(negative)
    if positive:
        return "·".join(positive)
    if negative:
        return "1/" + "·".join(negative)
    return "无量纲"


# --- 内置单位表（应用启动时调用） ---------------------------------------------

def init_registry() -> UnitRegistry:
    """构造并初始化内置单位表。

    覆盖工程测量常用单位：SI 基本单位、词头倍数、英制、
    温标、角度，以及力/压/能/电/光等导出单位与少量复合单位。
    """
    reg = UnitRegistry()

    # ===== 长度 L =====
    reg.add("m", dim(L=1), 1.0, ("米", "公尺", "meter", "metre"), canonical=True)
    reg.add("mm", dim(L=1), 1e-3, ("毫米", "公厘"))
    reg.add("cm", dim(L=1), 1e-2, ("厘米", "公分", "centimetre"))
    reg.add("dm", dim(L=1), 1e-1, ("分米",))
    reg.add("km", dim(L=1), 1e3, ("千米", "公里", "kilometer"))
    reg.add("um", dim(L=1), 1e-6, ("微米", "μm", "micrometre"))
    reg.add("nm", dim(L=1), 1e-9, ("纳米", "nanometre"))
    reg.add("in", dim(L=1), 0.0254, ("英寸", "inch", "inches", '"'))
    reg.add("ft", dim(L=1), 0.3048, ("英尺", "foot", "feet", "'"))
    reg.add("yd", dim(L=1), 0.9144, ("码", "yard"))
    reg.add("mi", dim(L=1), 1609.344, ("英里", "mile"))
    reg.add("nmi", dim(L=1), 1852.0, ("海里", "nautical mile"))
    reg.add("mil", dim(L=1), 2.54e-5, ("密耳", "thou"))

    # ===== 面积 L² / 体积 L³ =====
    reg.add("m2", dim(L=2), 1.0, ("m²", "平方米", "sq m"), canonical=True)
    reg.add("cm2", dim(L=2), 1e-4, ("cm²", "平方厘米", "sq cm"))
    reg.add("mm2", dim(L=2), 1e-6, ("mm²", "平方毫米"))
    reg.add("km2", dim(L=2), 1e6, ("km²", "平方千米", "平方公里"))
    reg.add("ha", dim(L=2), 1e4, ("公顷", "hectare"))
    reg.add("acre", dim(L=2), 4046.8564224, ("英亩",))

    reg.add("L", dim(L=3), 1e-3, ("升", "litre", "liter"))
    reg.add("l", dim(L=3), 1e-3, ("公升",))
    reg.add("mL", dim(L=3), 1e-6, ("毫升", "ml", "cm³", "cc"))
    reg.add("m3", dim(L=3), 1.0, ("m³", "立方米", "立方"), canonical=True)
    reg.add("cm3", dim(L=3), 1e-6, ("cm³", "立方厘米"))
    reg.add("mm3", dim(L=3), 1e-9, ("mm³", "立方毫米"))
    reg.add("gal", dim(L=3), 0.003785411784, ("加仑", "美制加仑", "gallon"))

    # ===== 质量 M =====
    reg.add("kg", dim(M=1), 1.0, ("千克", "公斤", "kilogram"), canonical=True)
    reg.add("g", dim(M=1), 1e-3, ("克", "gram", "gramme"))
    reg.add("mg", dim(M=1), 1e-6, ("毫克", "milligram"))
    reg.add("t", dim(M=1), 1e3, ("吨", "公吨", "tonne", "metric ton"))
    reg.add("lb", dim(M=1), 0.45359237, ("磅", "pound", "lbs"))
    reg.add("oz", dim(M=1), 0.028349523125, ("盎司", "ounce"))
    reg.add("grain", dim(M=1), 6.479891e-5, ("格令", "gr"))

    # ===== 时间 T =====
    reg.add("s", dim(T=1), 1.0, ("秒", "sec", "second"), canonical=True)
    reg.add("ms", dim(T=1), 1e-3, ("毫秒", "millisecond"))
    reg.add("us", dim(T=1), 1e-6, ("微秒", "μs", "microsecond"))
    reg.add("min", dim(T=1), 60.0, ("分", "分钟", "minute"))
    reg.add("h", dim(T=1), 3600.0, ("小时", "时", "hour", "hr"))
    reg.add("day", dim(T=1), 86400.0, ("天", "日", "d"))
    reg.add("week", dim(T=1), 604800.0, ("周", "星期"))

    # ===== 电流 I =====
    reg.add("A", dim(I=1), 1.0, ("安", "安培", "amp", "ampere"), canonical=True)
    reg.add("mA", dim(I=1), 1e-3, ("毫安",))
    reg.add("uA", dim(I=1), 1e-6, ("微安", "μA"))
    reg.add("kA", dim(I=1), 1e3, ("千安",))

    # ===== 温度 Θ（仿射温标） =====
    reg.add("K", dim(Theta=1), 1.0, ("开尔文", "kelvin"), canonical=True)
    reg.add("degC", dim(Theta=1), 1.0, ("°C", "C", "摄氏度", "celsius"),
            offset=273.15, affine=True)
    reg.add("degF", dim(Theta=1), 5.0 / 9.0, ("°F", "F", "华氏度",
            "fahrenheit"), offset=459.67 * 5.0 / 9.0, affine=True)
    reg.add("degR", dim(Theta=1), 5.0 / 9.0, ("兰氏度", "°R", "rankine"))

    # ===== 物质的量 N / 发光强度 J =====
    reg.add("mol", dim(N=1), 1.0, ("摩尔", "mole"), canonical=True)
    reg.add("mmol", dim(N=1), 1e-3, ("毫摩尔",))
    reg.add("kmol", dim(N=1), 1e3, ("千摩尔",))
    reg.add("cd", dim(J=1), 1.0, ("坎德拉", "烛光", "candela"), canonical=True)

    # ===== 平面角（伪量纲 A） =====
    reg.add("rad", dim(A=1), 1.0, ("弧度", "radian"), canonical=True)
    reg.add("deg", dim(A=1), math.pi / 180.0, ("°", "度", "角度", "degree"))
    reg.add("arcmin", dim(A=1), math.pi / 10800.0, ("角分", "'", "′"))
    reg.add("arcsec", dim(A=1), math.pi / 648000.0, ("角秒", '"', "″"))
    reg.add("turn", dim(A=1), 2 * math.pi, ("转", "圈", "周", "revolution"))

    # ===== 无量纲 =====
    reg.add("1", DIM_ZERO, 1.0, ("one", "纯数", "无量纲"), canonical=True)
    reg.add("%", DIM_ZERO, 0.01, ("percent", "pct", "百分比"))
    reg.add("ppm", DIM_ZERO, 1e-6, ("百万分率",))

    # ===== 力 L M T⁻² =====
    reg.add("N", dim(L=1, M=1, T=-2), 1.0,
            ("牛", "牛顿", "newton"), canonical=True)
    reg.add("kN", dim(L=1, M=1, T=-2), 1e3, ("千牛",))
    reg.add("lbf", dim(L=1, M=1, T=-2), 4.4482216152605, ("磅力",))
    reg.add("kgf", dim(L=1, M=1, T=-2), 9.80665, ("千克力", "公斤力"))
    reg.add("dyn", dim(L=1, M=1, T=-2), 1e-5, ("达因", "dyne"))

    # ===== 压力 M L⁻¹ T⁻² =====
    reg.add("Pa", dim(M=1, L=-1, T=-2), 1.0, ("帕", "帕斯卡", "pascal"),
            canonical=True)
    reg.add("kPa", dim(M=1, L=-1, T=-2), 1e3, ("千帕",))
    reg.add("MPa", dim(M=1, L=-1, T=-2), 1e6, ("兆帕",))
    reg.add("GPa", dim(M=1, L=-1, T=-2), 1e9, ("吉帕",))
    reg.add("bar", dim(M=1, L=-1, T=-2), 1e5, ("巴",))
    reg.add("mbar", dim(M=1, L=-1, T=-2), 1e2, ("毫巴",))
    reg.add("atm", dim(M=1, L=-1, T=-2), 101325.0, ("标准大气压",))
    reg.add("mmHg", dim(M=1, L=-1, T=-2), 133.322387415, ("毫米汞柱", "托", "torr"))
    reg.add("psi", dim(M=1, L=-1, T=-2), 6894.757293168, ("磅每平方英寸",))

    # ===== 能量 M L² T⁻² =====
    reg.add("J", dim(M=1, L=2, T=-2), 1.0, ("焦", "焦耳", "joule"),
            canonical=True)
    reg.add("kJ", dim(M=1, L=2, T=-2), 1e3, ("千焦",))
    reg.add("MJ", dim(M=1, L=2, T=-2), 1e6, ("兆焦",))
    reg.add("Wh", dim(M=1, L=2, T=-2), 3600.0, ("瓦时",))
    reg.add("kWh", dim(M=1, L=2, T=-2), 3.6e6, ("千瓦时", "度电", "度"))
    reg.add("cal", dim(M=1, L=2, T=-2), 4.184, ("卡", "卡路里", "calorie"))
    reg.add("kcal", dim(M=1, L=2, T=-2), 4184.0, ("千卡", "大卡"))
    reg.add("BTU", dim(M=1, L=2, T=-2), 1055.05585262, ("英热单位",))
    reg.add("eV", dim(M=1, L=2, T=-2), 1.602176634e-19, ("电子伏",))

    # ===== 功率 M L² T⁻³ =====
    reg.add("W", dim(M=1, L=2, T=-3), 1.0, ("瓦", "瓦特", "watt"),
            canonical=True)
    reg.add("kW", dim(M=1, L=2, T=-3), 1e3, ("千瓦",))
    reg.add("MW", dim(M=1, L=2, T=-3), 1e6, ("兆瓦",))
    reg.add("mW", dim(M=1, L=2, T=-3), 1e-3, ("毫瓦",))
    reg.add("hp", dim(M=1, L=2, T=-3), 745.6998715822702, ("马力", "英制马力"))
    reg.add("PS", dim(M=1, L=2, T=-3), 735.49875, ("公制马力", "米制马力"))

    # ===== 频率 T⁻¹ / 角速度 A T⁻¹ =====
    reg.add("Hz", dim(T=-1), 1.0, ("赫", "赫兹", "hertz"), canonical=True)
    reg.add("kHz", dim(T=-1), 1e3, ("千赫",))
    reg.add("MHz", dim(T=-1), 1e6, ("兆赫",))
    reg.add("rpm", dim(A=1, T=-1), 2 * math.pi / 60.0,
            ("转每分", "r/min", "rev/min"), canonical=True)
    reg.add("rad/s", dim(A=1, T=-1), 1.0, ("弧度每秒",), canonical=False)

    # ===== 电学 =====
    reg.add("V", dim(M=1, L=2, T=-3, I=-1), 1.0,
            ("伏", "伏特", "volt"), canonical=True)
    reg.add("mV", dim(M=1, L=2, T=-3, I=-1), 1e-3, ("毫伏",))
    reg.add("kV", dim(M=1, L=2, T=-3, I=-1), 1e3, ("千伏",))
    reg.add("Ohm", dim(M=1, L=2, T=-3, I=-2), 1.0,
            ("Ω", "欧", "欧姆", "ohm"), canonical=True)
    reg.add("kOhm", dim(M=1, L=2, T=-3, I=-2), 1e3, ("kΩ", "千欧"))
    reg.add("MOhm", dim(M=1, L=2, T=-3, I=-2), 1e6, ("MΩ", "兆欧"))
    reg.add("F", dim(M=-1, L=-2, T=4, I=2), 1.0,
            ("法", "法拉", "farad"), canonical=True)
    reg.add("uF", dim(M=-1, L=-2, T=4, I=2), 1e-6, ("μF", "微法"))
    reg.add("nF", dim(M=-1, L=-2, T=4, I=2), 1e-9, ("纳法",))
    reg.add("pF", dim(M=-1, L=-2, T=4, I=2), 1e-12, ("皮法",))
    reg.add("C", dim(T=1, I=1), 1.0, ("库", "库仑", "coulomb"), canonical=True)
    reg.add("H", dim(M=1, L=2, T=-2, I=-2), 1.0,
            ("亨", "亨利", "henry"), canonical=True)
    reg.add("Wb", dim(M=1, L=2, T=-2, I=-1), 1.0,
            ("韦伯", "weber"), canonical=True)
    reg.add("Tmag", dim(M=1, T=-2, I=-1), 1.0,
            ("T", "特斯拉", "tesla"), canonical=True)

    # ===== 光 =====
    reg.add("lm", dim(J=1, A=1), 1.0, ("流明", "lumen"), canonical=True)
    reg.add("lx", dim(J=1, A=1, L=-2), 1.0, ("勒克斯", "lux"), canonical=True)

    # ===== 速度 L T⁻¹ / 加速度 L T⁻²（常用复合单位） =====
    reg.add("m/s", dim(L=1, T=-1), 1.0, ("米每秒", "米/秒"), canonical=True)
    reg.add("km/h", dim(L=1, T=-1), 1000.0 / 3600.0, ("千米每小时", "公里每小时"))
    reg.add("mph", dim(L=1, T=-1), 1609.344 / 3600.0, ("英里每小时",))
    reg.add("kn", dim(L=1, T=-1), 1852.0 / 3600.0, ("节", "knot"))
    reg.add("ft/s", dim(L=1, T=-1), 0.3048, ("英尺每秒",))
    reg.add("m/s2", dim(L=1, T=-2), 1.0, ("m/s²", "米每平方秒"),
            canonical=True)
    reg.add("g0", dim(L=1, T=-2), 9.80665, ("标准重力加速度",))

    # ===== 常用倒数 / 每单位（配合乘法构造复合量） =====
    reg.add("1/m", dim(L=-1), 1.0, ("每米", "per metre", "per meter"))
    reg.add("1/m2", dim(L=-2), 1.0, ("1/m²", "每平方米", "per square metre"))
    reg.add("1/m3", dim(L=-3), 1.0, ("1/m³", "每立方米"))
    reg.add("1/s", dim(T=-1), 1.0, ("每秒", "per second"))
    reg.add("1/min", dim(T=-1), 1.0 / 60.0, ("每分", "每分钟", "per minute"))
    reg.add("1/h", dim(T=-1), 1.0 / 3600.0, ("每小时", "per hour"))
    reg.add("1/kg", dim(M=-1), 1.0, ("每千克", "per kilogram"))
    reg.add("1/K", dim(Theta=-1), 1.0, ("每开尔文", "per kelvin"))
    reg.add("1/A", dim(I=-1), 1.0, ("每安培", "per ampere"))

    # 让量纲格式化优先使用命名导出单位
    preferred = (
        "N", "Pa", "J", "W", "Hz", "V", "Ohm", "F", "C", "H", "Wb",
        "Tmag", "lm", "lx", "m/s", "m/s2", "m2", "m3", "rpm",
    )
    _PREFERRED_DERIVED.clear()
    for sym in preferred:
        unit = reg.require(sym)
        _PREFERRED_DERIVED.setdefault(unit.dimension, unit.symbol)

    return reg
