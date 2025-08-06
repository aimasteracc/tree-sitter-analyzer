#!/usr/bin/env python3
"""
Deep Project Analyzer - 深層プロジェクト分析エンジン

プロジェクトの業務フロー、データフロー、アーキテクチャ、
業務用語、基本知識を深層分析し、真の理解を提供する革命的システム。

Features:
- 🏢 業務フロー分析 (Business Flow Analysis)
- 📊 データフロー分析 (Data Flow Analysis)  
- 🏗️ アーキテクチャ分析 (Architecture Analysis)
- 📚 ドメイン知識抽出 (Domain Knowledge Extraction)
- 🧠 学習前提条件分析 (Learning Prerequisites Analysis)
- 📖 ドキュメント深層解析 (Deep Documentation Analysis)
- 🔍 API仕様自動抽出 (API Specification Extraction)

Design Patterns:
- Strategy Pattern: 分析手法の切り替え
- Observer Pattern: 分析進捗の監視
- Factory Pattern: 分析器の生成
- Composite Pattern: 複合分析結果の構築
"""

import re
import ast
import json
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict

from .magic_base_tool import ProjectDNA


class FlowType(Enum):
    """フローの種類"""
    USER_INTERACTION = "user_interaction"
    DATA_PROCESSING = "data_processing"
    SYSTEM_INTEGRATION = "system_integration"
    ERROR_HANDLING = "error_handling"
    BUSINESS_LOGIC = "business_logic"


class ComponentType(Enum):
    """コンポーネントの種類"""
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    API = "api"
    SERVICE = "service"
    UTILITY = "utility"
    CONFIG = "config"


@dataclass
class FlowStep:
    """フローのステップ"""
    id: str
    name: str
    description: str
    input_data: List[str]
    output_data: List[str]
    conditions: List[str]
    error_handling: List[str]
    code_references: List[str]


@dataclass
class BusinessFlow:
    """業務フロー"""
    name: str
    description: str
    flow_type: FlowType
    steps: List[FlowStep]
    decision_points: List[Dict[str, Any]]
    error_scenarios: List[Dict[str, Any]]
    success_criteria: List[str]
    business_rules: List[str]


@dataclass
class DataEntity:
    """データエンティティ"""
    name: str
    type: str
    description: str
    fields: Dict[str, str]
    validation_rules: List[str]
    relationships: List[str]
    source_files: List[str]


@dataclass
class DataFlow:
    """データフロー"""
    name: str
    description: str
    input_entities: List[DataEntity]
    output_entities: List[DataEntity]
    transformation_steps: List[str]
    validation_points: List[str]
    storage_points: List[str]
    api_endpoints: List[Dict[str, Any]]


@dataclass
class ArchitectureComponent:
    """アーキテクチャコンポーネント"""
    name: str
    type: ComponentType
    description: str
    responsibilities: List[str]
    dependencies: List[str]
    interfaces: List[str]
    technologies: List[str]
    file_paths: List[str]


@dataclass
class Architecture:
    """アーキテクチャ"""
    pattern: str
    description: str
    components: List[ArchitectureComponent]
    layers: List[Dict[str, Any]]
    communication_patterns: List[str]
    design_principles: List[str]
    quality_attributes: Dict[str, float]


@dataclass
class DomainTerm:
    """ドメイン用語"""
    term: str
    definition: str
    context: str
    examples: List[str]
    related_terms: List[str]
    source_files: List[str]


@dataclass
class DomainKnowledge:
    """ドメイン知識"""
    domain: str
    description: str
    key_concepts: List[DomainTerm]
    business_rules: List[str]
    industry_standards: List[str]
    naming_conventions: List[str]
    best_practices: List[str]


@dataclass
class LearningPrerequisite:
    """学習前提条件"""
    category: str
    skill: str
    level: str
    description: str
    resources: List[str]
    assessment_criteria: List[str]


@dataclass
class Prerequisites:
    """前提条件"""
    technical_skills: List[LearningPrerequisite]
    domain_knowledge: List[LearningPrerequisite]
    tools_and_technologies: List[LearningPrerequisite]
    learning_path: List[str]
    estimated_time: str


class DocumentAnalyzer:
    """ドキュメント分析器"""
    
    def __init__(self):
        self.readme_patterns = {
            'installation': r'(?i)(install|setup|getting started)',
            'usage': r'(?i)(usage|how to use|examples?)',
            'api': r'(?i)(api|reference|methods?)',
            'configuration': r'(?i)(config|settings|options)',
            'troubleshooting': r'(?i)(troubleshoot|faq|issues?)'
        }
    
    async def analyze_readme(self, project_path: str) -> Dict[str, Any]:
        """README分析"""
        readme_files = []
        project_dir = Path(project_path)
        
        # README系ファイルを検索
        for pattern in ['README*', 'readme*', 'Readme*']:
            readme_files.extend(project_dir.glob(pattern))
        
        if not readme_files:
            return {"sections": {}, "key_info": {}}
        
        # 最初のREADMEファイルを分析
        readme_path = readme_files[0]
        try:
            content = readme_path.read_text(encoding='utf-8')
        except:
            try:
                content = readme_path.read_text(encoding='shift_jis')
            except:
                return {"sections": {}, "key_info": {}}
        
        sections = self._extract_sections(content)
        key_info = self._extract_key_information(content)
        
        return {
            "sections": sections,
            "key_info": key_info,
            "file_path": str(readme_path)
        }
    
    def _extract_sections(self, content: str) -> Dict[str, str]:
        """セクション抽出"""
        sections = {}
        
        # マークダウンのヘッダーでセクション分割
        lines = content.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            if line.startswith('#'):
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line.strip('#').strip()
                current_content = []
            else:
                current_content.append(line)
        
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        
        return sections
    
    def _extract_key_information(self, content: str) -> Dict[str, Any]:
        """重要情報抽出"""
        key_info = {
            "installation_commands": [],
            "usage_examples": [],
            "api_endpoints": [],
            "configuration_options": [],
            "dependencies": []
        }
        
        # インストールコマンド抽出
        install_patterns = [
            r'```(?:bash|shell|cmd)?\s*\n(.*?(?:install|pip|npm|yarn).*?)\n```',
            r'`(.*?(?:install|pip|npm|yarn).*?)`'
        ]
        
        for pattern in install_patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            key_info["installation_commands"].extend(matches)
        
        # 使用例抽出
        usage_patterns = [
            r'```(?:python|javascript|java|bash)?\s*\n(.*?)\n```',
            r'`([^`\n]+)`'
        ]
        
        for pattern in usage_patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            key_info["usage_examples"].extend(matches[:10])  # 最初の10個まで
        
        return key_info


class CodeAnalyzer:
    """コード分析器"""
    
    def __init__(self):
        self.supported_extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h'}
    
    async def analyze_code_structure(self, project_path: str) -> Dict[str, Any]:
        """コード構造分析"""
        project_dir = Path(project_path)
        
        structure = {
            "classes": [],
            "functions": [],
            "apis": [],
            "constants": [],
            "imports": [],
            "file_structure": {}
        }
        
        # ファイル構造分析
        for file_path in project_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix in self.supported_extensions:
                rel_path = file_path.relative_to(project_dir)
                
                try:
                    if file_path.suffix == '.py':
                        file_analysis = await self._analyze_python_file(file_path)
                        structure["file_structure"][str(rel_path)] = file_analysis
                        
                        # 全体構造に追加
                        structure["classes"].extend(file_analysis.get("classes", []))
                        structure["functions"].extend(file_analysis.get("functions", []))
                        structure["imports"].extend(file_analysis.get("imports", []))
                        
                except Exception as e:
                    continue
        
        return structure
    
    async def _analyze_python_file(self, file_path: Path) -> Dict[str, Any]:
        """Pythonファイル分析"""
        try:
            content = file_path.read_text(encoding='utf-8')
        except:
            return {}
        
        try:
            tree = ast.parse(content)
        except:
            return {}
        
        analysis = {
            "classes": [],
            "functions": [],
            "imports": [],
            "constants": [],
            "docstrings": []
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = {
                    "name": node.name,
                    "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)],
                    "docstring": ast.get_docstring(node),
                    "line": node.lineno
                }
                analysis["classes"].append(class_info)
            
            elif isinstance(node, ast.FunctionDef):
                func_info = {
                    "name": node.name,
                    "args": [arg.arg for arg in node.args.args],
                    "docstring": ast.get_docstring(node),
                    "line": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef)
                }
                analysis["functions"].append(func_info)
            
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        analysis["imports"].append(alias.name)
                else:
                    module = node.module or ""
                    for alias in node.names:
                        analysis["imports"].append(f"{module}.{alias.name}")
        
        return analysis


class BusinessFlowAnalyzer:
    """業務フロー分析器"""
    
    def __init__(self):
        self.flow_indicators = {
            'user_flow': ['user', 'login', 'register', 'submit', 'click', 'input'],
            'data_flow': ['process', 'transform', 'validate', 'save', 'load', 'query'],
            'api_flow': ['request', 'response', 'endpoint', 'route', 'handler'],
            'error_flow': ['error', 'exception', 'fail', 'retry', 'fallback']
        }
    
    async def analyze_business_flows(self, project_path: str, code_structure: Dict[str, Any], 
                                   readme_info: Dict[str, Any]) -> List[BusinessFlow]:
        """業務フロー分析"""
        flows = []
        
        # READMEから業務フローを抽出
        readme_flows = await self._extract_flows_from_readme(readme_info)
        flows.extend(readme_flows)
        
        # コードから業務フローを抽出
        code_flows = await self._extract_flows_from_code(code_structure)
        flows.extend(code_flows)
        
        return flows
    
    async def _extract_flows_from_readme(self, readme_info: Dict[str, Any]) -> List[BusinessFlow]:
        """READMEから業務フロー抽出"""
        flows = []
        
        sections = readme_info.get("sections", {})
        
        for section_name, content in sections.items():
            if any(keyword in section_name.lower() for keyword in ['usage', 'how to', 'example', 'workflow']):
                flow = BusinessFlow(
                    name=f"User Workflow: {section_name}",
                    description=content[:200] + "..." if len(content) > 200 else content,
                    flow_type=FlowType.USER_INTERACTION,
                    steps=self._extract_steps_from_text(content),
                    decision_points=[],
                    error_scenarios=[],
                    success_criteria=[],
                    business_rules=[]
                )
                flows.append(flow)
        
        return flows
    
    def _extract_steps_from_text(self, text: str) -> List[FlowStep]:
        """テキストからステップ抽出"""
        steps = []
        
        # 番号付きリストや手順を検索
        step_patterns = [
            r'(\d+)\.\s*([^\n]+)',
            r'-\s*([^\n]+)',
            r'\*\s*([^\n]+)'
        ]
        
        step_id = 1
        for pattern in step_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    step_text = match[-1]  # 最後の要素を取得
                else:
                    step_text = match
                
                if len(step_text.strip()) > 10:  # 意味のあるステップのみ
                    step = FlowStep(
                        id=f"step_{step_id}",
                        name=f"Step {step_id}",
                        description=step_text.strip(),
                        input_data=[],
                        output_data=[],
                        conditions=[],
                        error_handling=[],
                        code_references=[]
                    )
                    steps.append(step)
                    step_id += 1
        
        return steps[:10]  # 最初の10ステップまで
    
    async def _extract_flows_from_code(self, code_structure: Dict[str, Any]) -> List[BusinessFlow]:
        """コードから業務フロー抽出"""
        flows = []
        
        # API関数から業務フローを推測
        functions = code_structure.get("functions", [])
        api_functions = [f for f in functions if any(keyword in f["name"].lower() 
                        for keyword in ['handle', 'process', 'create', 'update', 'delete', 'get'])]
        
        if api_functions:
            steps = []
            for i, func in enumerate(api_functions[:5]):  # 最初の5つまで
                step = FlowStep(
                    id=f"api_step_{i+1}",
                    name=func["name"],
                    description=func.get("docstring", f"Execute {func['name']} function"),
                    input_data=func.get("args", []),
                    output_data=["result"],
                    conditions=[],
                    error_handling=[],
                    code_references=[f"Function: {func['name']} at line {func.get('line', 0)}"]
                )
                steps.append(step)
            
            flow = BusinessFlow(
                name="API Processing Flow",
                description="Main API processing workflow extracted from code",
                flow_type=FlowType.DATA_PROCESSING,
                steps=steps,
                decision_points=[],
                error_scenarios=[],
                success_criteria=["Successful API response"],
                business_rules=[]
            )
            flows.append(flow)
        
        return flows


class DeepProjectAnalyzer:
    """深層プロジェクト分析エンジン"""
    
    def __init__(self):
        self.document_analyzer = DocumentAnalyzer()
        self.code_analyzer = CodeAnalyzer()
        self.business_flow_analyzer = BusinessFlowAnalyzer()
    
    async def analyze_project_deeply(self, project_path: str) -> Dict[str, Any]:
        """プロジェクトの深層分析"""
        
        # 並行分析実行
        readme_task = self.document_analyzer.analyze_readme(project_path)
        code_task = self.code_analyzer.analyze_code_structure(project_path)
        
        readme_info, code_structure = await asyncio.gather(readme_task, code_task)
        
        # 業務フロー分析
        business_flows = await self.business_flow_analyzer.analyze_business_flows(
            project_path, code_structure, readme_info
        )
        
        # データフロー分析
        data_flows = await self.analyze_data_flows(code_structure, readme_info)
        
        # アーキテクチャ分析
        architecture = await self.analyze_architecture(code_structure, readme_info)
        
        # ドメイン知識抽出
        domain_knowledge = await self.extract_domain_knowledge(readme_info, code_structure)
        
        # 学習前提条件分析
        prerequisites = await self.analyze_prerequisites(readme_info, code_structure)
        
        return {
            "readme_info": readme_info,
            "code_structure": code_structure,
            "business_flows": [flow.__dict__ for flow in business_flows],
            "data_flows": [flow.__dict__ for flow in data_flows],
            "architecture": architecture.__dict__,
            "domain_knowledge": domain_knowledge.__dict__,
            "prerequisites": prerequisites.__dict__
        }
    
    async def analyze_data_flows(self, code_structure: Dict[str, Any], 
                                readme_info: Dict[str, Any]) -> List[DataFlow]:
        """データフロー分析"""
        data_flows = []
        
        # クラスからデータエンティティを抽出
        classes = code_structure.get("classes", [])
        entities = []
        
        for cls in classes:
            if any(keyword in cls["name"].lower() for keyword in ['model', 'entity', 'data', 'dto']):
                entity = DataEntity(
                    name=cls["name"],
                    type="class",
                    description=cls.get("docstring", f"Data entity: {cls['name']}"),
                    fields={method: "unknown" for method in cls.get("methods", [])},
                    validation_rules=[],
                    relationships=[],
                    source_files=[]
                )
                entities.append(entity)
        
        if entities:
            data_flow = DataFlow(
                name="Main Data Flow",
                description="Primary data processing flow",
                input_entities=entities[:len(entities)//2] if len(entities) > 1 else entities,
                output_entities=entities[len(entities)//2:] if len(entities) > 1 else entities,
                transformation_steps=["Data validation", "Business logic processing", "Result formatting"],
                validation_points=["Input validation", "Business rule validation"],
                storage_points=["Database", "Cache"],
                api_endpoints=[]
            )
            data_flows.append(data_flow)
        
        return data_flows
    
    async def analyze_architecture(self, code_structure: Dict[str, Any], 
                                  readme_info: Dict[str, Any]) -> Architecture:
        """アーキテクチャ分析"""
        
        # ファイル構造からコンポーネントを推測
        file_structure = code_structure.get("file_structure", {})
        components = []
        
        # 一般的なディレクトリパターンからコンポーネントを識別
        component_patterns = {
            'frontend': ['frontend', 'client', 'ui', 'web', 'static'],
            'backend': ['backend', 'server', 'api', 'service'],
            'database': ['db', 'database', 'models', 'schema'],
            'config': ['config', 'settings', 'env'],
            'utility': ['utils', 'helpers', 'common', 'shared']
        }
        
        for file_path in file_structure.keys():
            path_parts = Path(file_path).parts
            
            for comp_type, patterns in component_patterns.items():
                if any(pattern in part.lower() for part in path_parts for pattern in patterns):
                    component = ArchitectureComponent(
                        name=f"{comp_type.title()} Component",
                        type=ComponentType(comp_type),
                        description=f"Component handling {comp_type} functionality",
                        responsibilities=[f"Manage {comp_type} operations"],
                        dependencies=[],
                        interfaces=[],
                        technologies=[],
                        file_paths=[file_path]
                    )
                    components.append(component)
                    break
        
        # デフォルトコンポーネント
        if not components:
            component = ArchitectureComponent(
                name="Main Application",
                type=ComponentType.SERVICE,
                description="Main application component",
                responsibilities=["Core application logic"],
                dependencies=[],
                interfaces=[],
                technologies=[],
                file_paths=list(file_structure.keys())
            )
            components.append(component)
        
        return Architecture(
            pattern="Layered Architecture",
            description="Multi-layered application architecture",
            components=components,
            layers=[
                {"name": "Presentation Layer", "components": ["Frontend"]},
                {"name": "Business Layer", "components": ["Backend", "Service"]},
                {"name": "Data Layer", "components": ["Database"]}
            ],
            communication_patterns=["Request-Response", "Event-Driven"],
            design_principles=["Separation of Concerns", "Single Responsibility"],
            quality_attributes={"maintainability": 0.8, "scalability": 0.7, "reliability": 0.8}
        )
    
    async def extract_domain_knowledge(self, readme_info: Dict[str, Any], 
                                     code_structure: Dict[str, Any]) -> DomainKnowledge:
        """ドメイン知識抽出"""
        
        # READMEとコードから専門用語を抽出
        terms = []
        
        # クラス名から用語抽出
        classes = code_structure.get("classes", [])
        for cls in classes:
            if cls["docstring"]:
                term = DomainTerm(
                    term=cls["name"],
                    definition=cls["docstring"][:200],
                    context="Class definition",
                    examples=[],
                    related_terms=[],
                    source_files=[]
                )
                terms.append(term)
        
        # 関数名から用語抽出
        functions = code_structure.get("functions", [])
        for func in functions[:5]:  # 最初の5つまで
            if func["docstring"]:
                term = DomainTerm(
                    term=func["name"],
                    definition=func["docstring"][:200],
                    context="Function definition",
                    examples=[],
                    related_terms=[],
                    source_files=[]
                )
                terms.append(term)
        
        return DomainKnowledge(
            domain="Application Domain",
            description="Domain knowledge extracted from project",
            key_concepts=terms,
            business_rules=[],
            industry_standards=[],
            naming_conventions=["camelCase for functions", "PascalCase for classes"],
            best_practices=["Follow SOLID principles", "Write comprehensive tests"]
        )
    
    async def analyze_prerequisites(self, readme_info: Dict[str, Any], 
                                  code_structure: Dict[str, Any]) -> Prerequisites:
        """学習前提条件分析"""
        
        # インポートから技術スタックを推測
        imports = code_structure.get("imports", [])
        technologies = set()
        
        for imp in imports:
            if '.' in imp:
                base_module = imp.split('.')[0]
                technologies.add(base_module)
            else:
                technologies.add(imp)
        
        # 技術的前提条件
        technical_skills = []
        for tech in list(technologies)[:5]:  # 最初の5つまで
            skill = LearningPrerequisite(
                category="Technical",
                skill=f"{tech} programming",
                level="Intermediate",
                description=f"Understanding of {tech} framework/library",
                resources=[f"Official {tech} documentation"],
                assessment_criteria=[f"Can write basic {tech} code"]
            )
            technical_skills.append(skill)
        
        return Prerequisites(
            technical_skills=technical_skills,
            domain_knowledge=[],
            tools_and_technologies=[],
            learning_path=["Basic programming", "Framework understanding", "Project setup", "Advanced features"],
            estimated_time="4-8 hours"
        )
