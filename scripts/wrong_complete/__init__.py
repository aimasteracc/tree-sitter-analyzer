"""错误 ``complete`` 的独立判定器（oracle）与真实仓库扫描。

本包**不导入** ``tree_sitter_analyzer``：判定器只用 Python ``ast`` 与纯文本
token 扫描得出“哪些调用点可能调用目标”，再由 ``scorer`` 把 TSA 的
``nav action=callers`` 回答与之比对。这样 TSA 的解析缺陷不会同时污染答案与
标准答案（RFC-0028 §1 的诚实性不变量，REA 对比建议 #2）。

模块：

* ``sites``：目标、调用点与判定结果的数据结构；
* ``py_model`` / ``py_oracle``：Python ``ast`` 判定器；
* ``token_oracle``：Java / TypeScript / JavaScript 的 token 扫描判定器；
* ``scorer``：把一次回答与判定器结果比对，给出错误 ``complete``；
* ``sweep``：夜间真实仓库扫描的命令行入口。
"""
