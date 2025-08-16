# Language Guidelines for Tree-sitter Analyzer

This document establishes language consistency guidelines for all project documentation.

## 📋 Language Standards

### Primary Language: English
- All main documentation should be in English
- Code comments should be in English
- API documentation should be in English
- Error messages should be in English

### Localized Documentation
- `README_zh.md` - Chinese (Simplified)
- `README_ja.md` - Japanese (if exists)

## 📁 File Language Mapping

### English Files
- `README.md` - Main English documentation
- `CONTRIBUTING.md` - English contribution guide
- `DEPLOYMENT_GUIDE.md` - English deployment guide
- `CODE_STYLE_GUIDE.md` - English code style guide
- All files in `.kiro/steering/` - English steering rules
- All Python scripts in `scripts/` - English comments
- All GitHub workflows - English
- All configuration files - English comments

### Chinese Files
- `README_zh.md` - Chinese README

### Mixed Language (Acceptable)
- None - All files should use consistent language

## 🔍 Common Issues to Avoid

### ❌ Don't Mix Languages
```markdown
# Bad Example
## Installation 安装
This is an English section with 中文 mixed in.
```

### ✅ Use Consistent Language
```markdown
# Good Example - English File
## Installation
This section explains how to install the package.

# Good Example - Chinese File
## 安装
本节说明如何安装软件包。
```

## 🛠️ Maintenance Guidelines

### When Adding New Documentation
1. **Determine target audience**
   - International developers → English
   - Chinese developers → Chinese
   - Japanese developers → Japanese

2. **Choose appropriate file**
   - Main docs → English files
   - Localized docs → Language-specific files

3. **Keep language consistent**
   - Don't mix languages within a file
   - Use appropriate technical terms

### When Updating Existing Files
1. **Check current language**
2. **Maintain consistency**
3. **Update all language versions if needed**

## 🔧 Automated Checks

### Pre-commit Hooks
- Check for language consistency
- Validate file naming conventions
- Ensure proper encoding (UTF-8)

### CI/CD Validation
- Automated language detection
- Consistency checks across files
- Documentation completeness validation

## 📊 Current File Status

### ✅ Correctly Configured
- `README.md` - English ✓
- `README_zh.md` - Chinese ✓
- `CONTRIBUTING.md` - English ✓
- `DEPLOYMENT_GUIDE.md` - English ✓
- `.kiro/steering/*.md` - English ✓
- `scripts/*.py` - English comments ✓

### 🎯 Special Cases
- None - All files now use consistent language

## 🌍 Localization Strategy

### Priority Order
1. **English** - Primary, always up-to-date
2. **Chinese** - Secondary, for Chinese developers
3. **Japanese** - Tertiary, if community demand exists

### Update Process
1. Update English version first
2. Update Chinese version within 1 week
3. Update other language versions as needed

## 📝 Writing Guidelines

### English Documentation
- Use clear, concise language
- Follow technical writing best practices
- Use consistent terminology
- Include code examples with English comments

### Chinese Documentation
- Use simplified Chinese characters
- Maintain technical accuracy
- Keep formatting consistent with English version
- Use appropriate technical terms in Chinese

### Code Comments
```python
# English - Preferred
def analyze_file(file_path: str) -> AnalysisResult:
    """Analyze a code file and return results."""
    # Parse the file content
    content = read_file(file_path)
    return parse_content(content)

# Chinese - Avoid in main codebase
def analyze_file(file_path: str) -> AnalysisResult:
    """分析代码文件并返回结果。"""  # ❌ Don't do this
    # 解析文件内容  # ❌ Don't do this
    content = read_file(file_path)
    return parse_content(content)
```

## 🚨 Quality Assurance

### Review Checklist
- [ ] Language consistency within file
- [ ] Appropriate file for target audience
- [ ] Technical accuracy maintained
- [ ] Formatting consistency
- [ ] No mixed languages

### Tools
- Language detection scripts
- Automated consistency checks
- Translation validation (for localized versions)

---

**Remember: Consistent language usage improves project professionalism and accessibility!** 🌟
