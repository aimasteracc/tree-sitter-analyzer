"""
Refactoring Safety Tool - 一次调用获取完整影响分析

让Agent在修改代码前,瞬间判断重构的安全性
"""

from pathlib import Path
from typing import Any, Dict

from tree_sitter_analyzer_v2.features.project_knowledge import (
    ProjectKnowledgeEngine,
    get_function_safety,
)
from tree_sitter_analyzer_v2.mcp.tools.base import BaseTool


class CheckRefactoringSafetyTool(BaseTool):
    """
    检查重构安全性 - 一次调用获取全部信息
    
    提供:
    - 调用者列表 (谁会受影响)
    - 调用目标列表 (依赖哪些函数)
    - 影响等级 (high/medium/low)
    - 安全建议 (可以安全重构 / 需要谨慎)
    
    Token消耗: <200 tokens
    """
    
    def get_name(self) -> str:
        return "check_refactoring_safety"
    
    def get_description(self) -> str:
        return """检查函数重构的安全性,一次调用获取完整影响分析。

**快速决策工具**: 在修改代码前,瞬间判断是否安全

**输入**:
- function_name: 要重构的函数名 (支持 "file::func" 或 "func")
- project_root: 项目根目录 (可选,默认使用当前项目)

**输出**:
- function: 函数名
- file: 所在文件
- impact_level: 影响等级 (high/medium/low)
- impact_score: 影响分数
- called_by: 调用者列表 (谁会受影响)
- calls: 调用目标列表 (依赖哪些函数)
- affected_files: 受影响的文件数
- safe_to_refactor: 是否安全重构 (bool)
- recommendation: 具体建议

**示例**:
```json
{
  "function_name": "build_from_file"
}
```

**返回**:
```json
{
  "function": "build_from_file",
  "file": "builder.py",
  "impact_level": "high",
  "impact_score": 25,
  "called_by": ["analyze_directory", "main"],
  "calls": ["_extract_module", "_extract_class"],
  "affected_files": 2,
  "safe_to_refactor": false,
  "recommendation": "⚠️  需要谨慎: 高影响函数,可能影响多个模块"
}
```

**使用场景**:
- 重构函数前评估风险
- 识别关键函数 (高影响)
- 规划代码改动顺序
"""
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "function_name": {
                    "type": "string",
                    "description": "要检查的函数名 (支持 'file::func' 或 'func')"
                },
                "project_root": {
                    "type": "string",
                    "description": "项目根目录 (可选,默认使用当前项目)"
                }
            },
            "required": ["function_name"]
        }
    
    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行重构安全性检查
        
        Args:
            arguments: 包含 function_name 和可选的 project_root
        
        Returns:
            安全性分析结果
        """
        function_name = arguments.get("function_name")
        project_root = arguments.get("project_root")
        
        if not function_name:
            return {
                "error": "Missing required parameter: function_name",
                "success": False
            }
        
        # 使用当前项目根目录或指定的目录
        if project_root:
            root_path = Path(project_root)
        else:
            # 默认使用MCP服务器的项目根目录
            root_path = Path.cwd()
        
        try:
            # 获取函数安全性信息
            safety_info = get_function_safety(root_path, function_name)
            
            if not safety_info:
                return {
                    "error": f"Function '{function_name}' not found in project",
                    "success": False,
                    "suggestion": "Check function name spelling or ensure project snapshot is up to date"
                }
            
            return {
                "success": True,
                **safety_info
            }
        
        except Exception as e:
            return {
                "error": f"Failed to check refactoring safety: {str(e)}",
                "success": False
            }


class ProjectKnowledgeTool(BaseTool):
    """
    项目知识查询工具
    
    快速访问项目知识快照和热点函数
    """
    
    def get_name(self) -> str:
        return "query_project_knowledge"
    
    def get_description(self) -> str:
        return """查询项目知识快照和热点函数。

**功能**:
- snapshot: 获取项目整体快照 (<500 tokens)
- hotspots: 获取热点函数 (Top N)
- stats: 获取项目统计信息

**输入**:
- query_type: 查询类型 ("snapshot" | "hotspots" | "stats")
- top_n: 热点函数数量 (仅hotspots类型,默认20)
- max_functions: 快照最大函数数 (仅snapshot类型,默认50)

**示例**:
```json
{
  "query_type": "snapshot",
  "max_functions": 30
}
```

**使用场景**:
- 快速了解项目整体结构
- 识别核心/热点函数
- 评估项目规模和复杂度
"""
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["snapshot", "hotspots", "stats"],
                    "description": "查询类型"
                },
                "top_n": {
                    "type": "integer",
                    "description": "热点函数数量 (仅hotspots类型)",
                    "default": 20
                },
                "max_functions": {
                    "type": "integer",
                    "description": "快照最大函数数 (仅snapshot类型)",
                    "default": 50
                },
                "project_root": {
                    "type": "string",
                    "description": "项目根目录 (可选)"
                }
            },
            "required": ["query_type"]
        }
    
    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行项目知识查询"""
        query_type = arguments.get("query_type")
        project_root = arguments.get("project_root", Path.cwd())
        
        if not query_type:
            return {
                "error": "Missing required parameter: query_type",
                "success": False
            }
        
        try:
            engine = ProjectKnowledgeEngine(Path(project_root))
            
            if query_type == "snapshot":
                max_functions = arguments.get("max_functions", 50)
                content = engine.load_snapshot(max_functions=max_functions)
                return {
                    "success": True,
                    "query_type": "snapshot",
                    "content": content
                }
            
            elif query_type == "hotspots":
                top_n = arguments.get("top_n", 20)
                hotspots = engine.get_hotspots(top_n=top_n)
                return {
                    "success": True,
                    "query_type": "hotspots",
                    "hotspots": hotspots
                }
            
            elif query_type == "stats":
                if not engine.snapshot:
                    engine._load_from_cache()
                
                if not engine.snapshot:
                    return {
                        "error": "No snapshot available. Build snapshot first.",
                        "success": False
                    }
                
                snapshot = engine.snapshot
                high_count = sum(1 for f in snapshot.functions.values() if f.impact_level == "high")
                medium_count = sum(1 for f in snapshot.functions.values() if f.impact_level == "medium")
                low_count = sum(1 for f in snapshot.functions.values() if f.impact_level == "low")
                
                return {
                    "success": True,
                    "query_type": "stats",
                    "total_files": snapshot.total_files,
                    "total_functions": snapshot.total_functions,
                    "timestamp": snapshot.timestamp,
                    "impact_distribution": {
                        "high": high_count,
                        "medium": medium_count,
                        "low": low_count
                    }
                }
            
            else:
                return {
                    "error": f"Unknown query_type: {query_type}",
                    "success": False
                }
        
        except Exception as e:
            return {
                "error": f"Failed to query project knowledge: {str(e)}",
                "success": False
            }
