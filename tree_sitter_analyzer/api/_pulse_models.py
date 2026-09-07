"""Pulse 的冻结数据模型；供查询与序列化共用，不依赖业务入口。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SymbolInfo:
    """符号的定义身份与文档信息。"""

    name: str
    kind: str
    file: str
    line: int
    end_line: int
    language: str
    class_name: str | None = None
    docstring: str | None = None  # 文档的前 200 个字符


@dataclass(frozen=True)
class CallerRef:
    """调用目标符号的定义及其近期修改次数。"""

    name: str
    file: str
    line: int
    hot30: int  # 近 30 天修改次数，对应 mod_count_30d


@dataclass(frozen=True)
class CalleeRef:
    """目标符号调用的定义及其解析状态。"""

    name: str
    file: str | None = None
    line: int | None = None
    resolution: str = "unresolved"  # 解析器原始状态，不改写协议枚举


@dataclass(frozen=True)
class ImportRef:
    """目标文件中的模块导入。"""

    module: str
    file: str | None = None


@dataclass(frozen=True)
class GitHeat:
    """符号的提交信息与各时间窗口修改统计。"""

    commit: str | None = None
    commit_msg: str | None = None
    at: int | None = None  # Unix 时间戳，单位为秒
    mod_30d: int = 0
    mod_90d: int = 0
    mod_all: int = 0
    state: str = "tracked"


@dataclass(frozen=True)
class SiblingRef:
    """同一文件内的其他符号。"""

    name: str
    kind: str
    line: int


@dataclass(frozen=True)
class CommentRef:
    """目标附近的行内或块注释。"""

    line: int
    text: str  # 去除标记后的前 80 个字符
    kind: str  # 注释类型：inline 或 block


@dataclass(frozen=True)
class BranchContext:
    """调用点所在分支的条件与嵌套信息。"""

    kind: str
    condition_text: str | None = None
    nesting_depth: int = 0


@dataclass(frozen=True)
class PulseResponse:
    """单次请求返回的快照绑定符号上下文。"""

    symbol: SymbolInfo
    token_estimate: int = 0
    truncated_fields: tuple[str, ...] = field(default_factory=tuple)
    call_graph_available: bool = True
    call_graph_reason: str = ""
    callers: tuple[CallerRef, ...] = field(default_factory=tuple)
    callees: tuple[CalleeRef, ...] = field(default_factory=tuple)
    git_heat: GitHeat | None = None
    imports: tuple[ImportRef, ...] = field(default_factory=tuple)
    imported_by: tuple[str, ...] = field(default_factory=tuple)
    siblings: tuple[SiblingRef, ...] = field(default_factory=tuple)
    comments: tuple[CommentRef, ...] = field(default_factory=tuple)


# 保留公开限定名及既有 pickle 路径；这里只设置类型元数据，不反向导入 pulse。
for _model in (
    SymbolInfo,
    CallerRef,
    CalleeRef,
    ImportRef,
    GitHeat,
    SiblingRef,
    CommentRef,
    BranchContext,
    PulseResponse,
):
    _model.__module__ = "tree_sitter_analyzer.api.pulse"
