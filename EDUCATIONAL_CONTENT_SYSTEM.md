# 🎓 智能教育内容生成系统

基于tree-sitter-analyzer的MCP功能，这是一个能够自动为开源项目生成Udemy级别教程的智能系统。

## 🌟 系统特色

### 🎯 核心价值主张
- **解决问题**: 开源项目学习门槛高，缺乏系统性、分层次的教育资料
- **解决方案**: 基于代码结构智能分析，自动生成适合不同学习阶段的高质量教程

### 🚀 创新特性
1. **因地制宜的智能分析** - 基于tree-sitter的深度代码分析，自动识别项目特点
2. **因材施教的个性化生成** - 根据学习者水平动态调整内容深度和教学策略
3. **多角色协作的质量保证** - 四个专业AI代理协同工作，确保内容质量

## 🏗️ 系统架构

```
输入层 → 智能分析层 → 多角色AI协作层 → 内容生成层 → 输出层
  ↓           ↓              ↓             ↓         ↓
项目仓库   特征识别      教育专家AI      理论讲解    初级教程
代码分析   难度分级      技术专家AI      实践案例    中级教程  
复杂度评估 内容策略      内容组织者AI    练习题目    高级教程
关键提取   学习路径      课程设计师AI    项目实战    专家教程
```

## 🛠️ 核心组件

### 1. 智能分析工具

#### `analyze_learning_complexity` - 学习复杂度分析
```python
# 分析项目的学习难度和复杂度
arguments = {
    "file_path": "path/to/project/main.py",
    "analysis_depth": "detailed",  # basic, detailed, comprehensive
    "target_audience": "intermediate",  # beginner, intermediate, advanced, expert
    "include_recommendations": True
}
```

**分析维度**:
- 结构复杂度 (类、方法、继承关系)
- 认知负荷 (条件语句、循环、异常处理)
- 依赖复杂度 (导入、外部调用)
- 模式复杂度 (设计模式识别)
- 概念密度 (编程概念集中度)

#### `generate_educational_content` - 教育内容生成
```python
# 生成完整的教育内容
arguments = {
    "project_path": "path/to/project",
    "target_audience": "intermediate",
    "content_type": "tutorial",  # overview, tutorial, example, exercise, project, reference
    "learning_objectives": [
        "理解项目架构",
        "掌握核心概念", 
        "实践编程技能"
    ],
    "content_depth": "detailed",
    "include_exercises": True,
    "include_assessments": True,
    "output_format": "structured"
}
```

### 2. 多角色AI代理系统

#### 🎓 教育专家AI (Educator Agent)
- **职责**: 教学法、学习理论、课程设计
- **确保**: 内容符合教育学原理，学习路径科学合理
- **输出**: 教学策略建议、学习进度规划、评估方法

#### 🔧 技术专家AI (Technical Expert Agent)  
- **职责**: 技术准确性、最佳实践、代码质量
- **确保**: 技术内容专业准确，代码示例生产级质量
- **输出**: 技术分析、最佳实践指导、常见陷阱提醒

#### 📝 内容组织者AI (Content Organizer Agent)
- **职责**: 内容结构、逻辑流程、可读性优化
- **确保**: 内容组织清晰，易于理解和导航
- **输出**: 内容结构设计、信息层次规划、导航系统

#### 🎨 课程设计师AI (Course Designer Agent)
- **职责**: 整体学习体验、协调统筹、质量控制
- **确保**: 各组件协调一致，学习体验连贯engaging
- **输出**: 课程大纲、学习体验设计、质量评估

### 3. 动态提示词管理系统

#### 上下文感知提示生成
```python
# 根据项目特点和学习目标动态生成提示词
project_context = ProjectContext(
    language="python",
    project_type="Web Application", 
    complexity_score=7.2,
    domain="web_development",
    architecture_patterns=["MVC", "RESTful API"],
    key_concepts=["Flask", "Database", "Authentication"],
    prerequisites=["Python Basics", "Web Fundamentals"]
)

learning_context = LearningContext(
    target_level=LearningLevel.INTERMEDIATE,
    content_type=ContentType.TUTORIAL,
    learning_objectives=["Build web applications", "Understand MVC pattern"]
)
```

#### 角色专用提示模板
- 每个AI代理都有专门的提示词模板
- 根据项目特点和学习目标动态调整
- 支持多阶段协作的提示策略

## 📋 使用工作流

### 基础代码分析工作流 (现有功能)
1. `check_code_scale` - 检查代码规模和复杂度
2. `analyze_code_structure` - 生成详细结构表格
3. `extract_code_section` - 提取特定代码段

### 教育内容生成工作流 (新增功能)
4. `analyze_learning_complexity` - 评估学习复杂度
5. `generate_educational_content` - 生成完整教育材料

### 完整示例
```python
# 1. 首先分析项目复杂度
complexity_result = await analyze_learning_complexity({
    "file_path": "examples/Sample.java",
    "target_audience": "intermediate",
    "analysis_depth": "detailed"
})

# 2. 基于复杂度分析生成教育内容
content_result = await generate_educational_content({
    "project_path": "examples/Sample.java", 
    "target_audience": "intermediate",
    "content_type": "tutorial",
    "learning_objectives": [
        "理解Java类结构",
        "掌握面向对象编程",
        "学会代码分析方法"
    ]
})
```

## 🎯 输出内容结构

### 结构化输出格式
```json
{
  "course_outline": {
    "title": "Learning Java Programming",
    "modules": [
      {"title": "项目概览", "duration": "30分钟"},
      {"title": "核心概念", "duration": "60分钟"}, 
      {"title": "实现细节", "duration": "90分钟"},
      {"title": "实践练习", "duration": "120分钟"}
    ]
  },
  "learning_materials": {
    "content": "详细的教学内容...",
    "examples": ["基础用法示例", "高级模式示例"],
    "resources": ["官方文档", "社区教程", "最佳实践指南"]
  },
  "exercises": [
    {
      "title": "代码阅读练习",
      "description": "分析主要组件并解释其用途",
      "difficulty": "beginner",
      "estimated_time": "20分钟"
    }
  ],
  "assessments": [
    {
      "type": "知识检查",
      "questions": ["系统的主要组件是什么？", "不同部分如何交互？"]
    }
  ],
  "quality_metrics": {
    "overall_score": 0.87,
    "agent_confidence": {"educator": 0.9, "tech_expert": 0.85},
    "content_completeness": 0.92
  }
}
```

## 🚀 快速开始

### 1. 安装和配置
```bash
# 安装带有MCP支持的tree-sitter-analyzer
uv add "tree-sitter-analyzer[mcp]"

# 配置Claude Desktop (添加到claude_desktop_config.json)
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {"TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"}
    }
  }
}
```

### 2. 运行演示
```bash
# 运行教育内容生成演示
python examples/educational_content_demo.py
```

### 3. 在Claude Desktop中使用
```
# 分析学习复杂度
使用工具: analyze_learning_complexity
参数: {"file_path": "src/main.py", "target_audience": "intermediate"}

# 生成教育内容  
使用工具: generate_educational_content
参数: {
  "project_path": "src/main.py",
  "target_audience": "intermediate", 
  "content_type": "tutorial"
}
```

## 🎓 教学策略适配

### 不同水平的教学策略

#### 初学者 (Beginner)
- **策略**: 概念优先，大量解释和示例
- **内容**: 基础概念、逐步指导、详细注释
- **评估**: 理解检查、简单练习

#### 中级 (Intermediate)  
- **策略**: 平衡理论与实践，渐进式学习
- **内容**: 模式识别、最佳实践、项目练习
- **评估**: 实现挑战、代码审查

#### 高级 (Advanced)
- **策略**: 深度分析，架构思维
- **内容**: 设计决策、性能优化、扩展性
- **评估**: 架构设计、优化挑战

#### 专家 (Expert)
- **策略**: 前沿技术，创新应用
- **内容**: 高级模式、领域特定知识
- **评估**: 创新项目、技术领导

## 🔮 未来发展方向

### 短期目标 (1-3个月)
- [ ] 完善多语言支持 (Python, JavaScript, TypeScript, Go, Rust)
- [ ] 增强设计模式识别能力
- [ ] 优化多代理协作效率

### 中期目标 (3-6个月)  
- [ ] 集成更多教学理论 (建构主义、认知负荷理论)
- [ ] 支持交互式学习内容生成
- [ ] 添加学习进度跟踪和适应性调整

### 长期目标 (6-12个月)
- [ ] 构建完整的在线学习平台集成
- [ ] 支持多模态内容生成 (视频、图表、交互式演示)
- [ ] 建立学习效果评估和反馈循环

## 🤝 贡献指南

我们欢迎社区贡献！请参考以下方式参与：

1. **代码贡献**: 提交PR改进算法和功能
2. **内容贡献**: 分享教学策略和最佳实践
3. **测试贡献**: 在不同项目上测试并反馈
4. **文档贡献**: 改进文档和示例

## 📞 联系我们

- **项目主页**: [tree-sitter-analyzer](https://github.com/aimasteracc/tree-sitter-analyzer)
- **问题反馈**: GitHub Issues
- **功能建议**: GitHub Discussions

---

**让每个开源项目都有最好的学习资料！** 🚀
