"""
MCP Resources Provider - 将项目知识暴露为MCP Resources

让Agent无需调用tool,直接读取项目知识快照
"""

from pathlib import Path
from typing import Any, Dict, List

from tree_sitter_analyzer_v2.features.project_knowledge import ProjectKnowledgeEngine


class KnowledgeResourceProvider:
    """
    知识资源提供者
    
    将项目知识图谱暴露为MCP Resources:
    - knowledge://project/snapshot - 完整项目快照 (<500 tokens)
    - knowledge://project/hotspots - 热点函数 (Top 20)
    - knowledge://function/{name}/impact - 函数影响范围
    """
    
    def __init__(self, engine: ProjectKnowledgeEngine):
        """
        初始化资源提供者
        
        Args:
            engine: 项目知识引擎
        """
        self.engine = engine
    
    def list_resources(self) -> List[Dict[str, Any]]:
        """
        列出所有可用的知识资源
        
        Returns:
            资源列表
        """
        return [
            {
                "uri": "knowledge://project/snapshot",
                "name": "项目知识快照 (Ultra-Compact)",
                "description": "完整项目调用关系,<500 tokens",
                "mimeType": "text/plain"
            },
            {
                "uri": "knowledge://project/hotspots",
                "name": "核心热点函数 (Top 20)",
                "description": "最常被调用的20个函数,<100 tokens",
                "mimeType": "text/plain"
            },
            {
                "uri": "knowledge://project/stats",
                "name": "项目统计信息",
                "description": "文件数、函数数等统计",
                "mimeType": "text/plain"
            }
        ]
    
    def read_resource(self, uri: str) -> str:
        """
        读取指定资源 (极快,从缓存读取)
        
        Args:
            uri: 资源URI
        
        Returns:
            资源内容
        """
        if uri == "knowledge://project/snapshot":
            return self._read_snapshot()
        elif uri == "knowledge://project/hotspots":
            return self._read_hotspots()
        elif uri == "knowledge://project/stats":
            return self._read_stats()
        elif uri.startswith("knowledge://function/"):
            # 提取函数名: knowledge://function/{name}/impact
            parts = uri.split("/")
            if len(parts) >= 4:
                func_name = parts[3]
                return self._read_function_impact(func_name)
        
        return f"Unknown resource: {uri}"
    
    def _read_snapshot(self) -> str:
        """读取项目快照"""
        snapshot = self.engine.load_snapshot(max_functions=50)
        
        # 添加使用说明
        header = """# 项目知识快照 - 超压缩格式

## 如何阅读
- 格式: FILE::FUNC → CALLS[...] ← CALLED_BY[...] | I:level
- → : 该函数调用哪些函数
- ← : 哪些函数调用该函数
- I: 影响等级 (high/medium/low)

## 数据
"""
        return header + "\n" + snapshot
    
    def _read_hotspots(self) -> str:
        """读取热点函数"""
        hotspots = self.engine.get_hotspots(top_n=20)
        
        lines = ["# 热点函数 (Top 20)", ""]
        lines.append("Rank | Function | File | Impact | Called By | Calls")
        lines.append("-----|----------|------|--------|-----------|------")
        
        for i, hotspot in enumerate(hotspots, 1):
            lines.append(
                f"{i:2d}   | {hotspot['function']:30s} | "
                f"{hotspot['file']:20s} | {hotspot['impact_level']:6s} | "
                f"{hotspot['called_by_count']:9d} | {hotspot['calls_count']:5d}"
            )
        
        return "\n".join(lines)
    
    def _read_stats(self) -> str:
        """读取项目统计"""
        if not self.engine.snapshot:
            self.engine._load_from_cache()
        
        if not self.engine.snapshot:
            return "No snapshot available"
        
        snapshot = self.engine.snapshot
        
        # 统计影响等级分布
        high_count = sum(1 for f in snapshot.functions.values() if f.impact_level == "high")
        medium_count = sum(1 for f in snapshot.functions.values() if f.impact_level == "medium")
        low_count = sum(1 for f in snapshot.functions.values() if f.impact_level == "low")
        
        return f"""# 项目统计信息

## 基本信息
- 总文件数: {snapshot.total_files}
- 总函数数: {snapshot.total_functions}
- 最后更新: {snapshot.timestamp}

## 影响等级分布
- 高影响函数: {high_count} ({high_count/snapshot.total_functions*100:.1f}%)
- 中影响函数: {medium_count} ({medium_count/snapshot.total_functions*100:.1f}%)
- 低影响函数: {low_count} ({low_count/snapshot.total_functions*100:.1f}%)

## 建议
- 修改高影响函数需要特别谨慎
- 优先重构低影响函数
- 定期更新知识快照以保持准确性
"""
    
    def _read_function_impact(self, function_name: str) -> str:
        """读取函数影响范围"""
        impact = self.engine.get_function_impact(function_name)
        
        if not impact:
            return f"Function '{function_name}' not found"
        
        # 格式化输出
        lines = [
            f"# 函数影响分析: {impact['function']}",
            "",
            f"**文件**: {impact['file']}",
            f"**影响等级**: {impact['impact_level'].upper()}",
            f"**影响分数**: {impact['impact_score']}",
            "",
            "## 谁调用了它 (Called By)",
            ""
        ]
        
        if impact['callers']:
            for caller in impact['callers'][:10]:
                lines.append(f"- {caller}")
            if len(impact['callers']) > 10:
                lines.append(f"- ... 还有 {len(impact['callers']) - 10} 个")
        else:
            lines.append("- (无调用者)")
        
        lines.extend([
            "",
            "## 它调用了谁 (Calls)",
            ""
        ])
        
        if impact['callees']:
            for callee in impact['callees'][:10]:
                lines.append(f"- {callee}")
            if len(impact['callees']) > 10:
                lines.append(f"- ... 还有 {len(impact['callees']) - 10} 个")
        else:
            lines.append("- (不调用其他函数)")
        
        lines.extend([
            "",
            "## 影响范围",
            "",
            f"- 受影响文件数: {impact['affected_files']}",
            f"- 受影响文件: {', '.join(impact['files_list'][:5])}"
        ])
        
        if len(impact['files_list']) > 5:
            lines.append(f"  ... 还有 {len(impact['files_list']) - 5} 个文件")
        
        return "\n".join(lines)
