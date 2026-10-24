"""#1632：调用边给出的非 ``complete`` 答案必须带机器可读的原因码。

RFC-0028 §1.1 要求非 ``complete`` 的答案点名缺口。#1632 之前，调用边这一层
（未解析入边、声明文件守卫、仅同名入边、模块级调用点、空证据基）降级时
``completeness_reason`` 一律为 ``null``，调用方只能读 prose 猜原因。

设计：``completeness_reason`` 保持单个字符串（主因，向后兼容），另加
``completeness_reasons`` 列出全部成立的原因（主因在首位，顺序固定）。只给主因
会让调用方修好一个缺口后误以为已是普查；只给列表会破坏既有按字符串分支的调用方。
"""

from __future__ import annotations

from .callers_absence import (
    ACCESSOR_REASON,
    ACCESSOR_UNCHECKED_REASON,
    NON_CALL_REASON,
)
from .callers_absence import UNCHECKED_REASON as NON_CALL_UNCHECKED_REASON
from .callers_decorators import DECORATED_REASON
from .callers_excluded import EXCLUDED_REASON
from .callers_target import NOT_DEFINED_REASON
from .callers_target import UNCHECKED_REASON as TARGET_UNCHECKED_REASON
from .relation_freshness import (
    MISSING_REASON,
    STALE_REASON,
    UNKNOWN_REASON,
)
from .unindexed_sources import UNCHECKED_REASON as UNINDEXED_UNCHECKED_REASON
from .unindexed_sources import UNINDEXED_REASON

#: 未解析入边计数或声明文件守卫无法读取：读取失败不是不存在的证据。
UNCHECKED_REASON = "UNRESOLVED_INBOUND_UNCHECKED"
#: 存在名字指向目标、但未解析到定义的入边。
UNRESOLVED_INBOUND_REASON = "UNRESOLVED_INBOUND"
#: 声明目标的文件里有可能点名目标的未解析调用点（§1.2 守卫）。
DECLARING_FILE_REASON = "UNRESOLVED_IN_DECLARING_FILE"
#: 仅凭同名匹配、无法绑定到目标的入边（#1578）。
NAME_ONLY_REASON = "NAME_ONLY_INBOUND"
#: 模块级调用点只计数不列出（#638）：目标确实被调用，只是答不出被谁调用，
#: 因此列出 0 个也不是普查。
UNATTRIBUTED_REASON = "UNATTRIBUTED_CALL_SITES"
#: RFC-0040：同名入边检查未能运行（例如同名方法的定义无法从调用图读取）。
NAME_ONLY_UNCHECKED_REASON = "NAME_ONLY_INBOUND_UNCHECKED"
#: RFC-0040：模块级调用点无法计数。
UNATTRIBUTED_UNCHECKED_REASON = "UNATTRIBUTED_CALL_SITES_UNCHECKED"
#: 调用图不含任何调用边，0 无法区分“无人调用”与“从未填充”；图里别处有边时
#: 0 才是关于本符号的事实。
EMPTY_EVIDENCE_REASON = "EMPTY_EVIDENCE_BASE"

#: 调用边层的全部原因码，按主因优先级排列。
EDGE_REASONS = (
    UNCHECKED_REASON,
    NAME_ONLY_UNCHECKED_REASON,
    UNATTRIBUTED_UNCHECKED_REASON,
    UNRESOLVED_INBOUND_REASON,
    DECLARING_FILE_REASON,
    NAME_ONLY_REASON,
    UNATTRIBUTED_REASON,
    EMPTY_EVIDENCE_REASON,
)

#: ``nav action=callers`` 可能给出的全部原因码（闭集）：调用边层加上复核门。
COMPLETENESS_REASONS = frozenset(
    {
        *EDGE_REASONS,
        STALE_REASON,
        UNKNOWN_REASON,
        MISSING_REASON,
        NOT_DEFINED_REASON,
        EXCLUDED_REASON,
        TARGET_UNCHECKED_REASON,
        UNINDEXED_REASON,
        UNINDEXED_UNCHECKED_REASON,
        NON_CALL_REASON,
        NON_CALL_UNCHECKED_REASON,
        ACCESSOR_REASON,
        ACCESSOR_UNCHECKED_REASON,
        DECORATED_REASON,
    }
)
