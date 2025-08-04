# Project Root Configuration Guide

**Quick reference for configuring project root in tree-sitter-analyzer**

## 🎯 Recommended Configuration (Most Users)

### MCP Server (Claude Desktop)

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

### CLI Usage

```bash
# Auto-detect project root (recommended)
tree-sitter-analyzer src/main.py --table=full

# Explicit project root (when needed)
tree-sitter-analyzer src/main.py --project-root /path/to/project --table=full
```

## 🔧 How It Works

### Auto-Detection Process

1. **Searches for project markers** (in priority order):
   - Version control: `.git`, `.hg`, `.svn`
   - Python: `pyproject.toml`, `setup.py`, `requirements.txt`
   - JavaScript: `package.json`, `yarn.lock`, `node_modules`
   - Java: `pom.xml`, `build.gradle`, `gradlew`
   - And 20+ more project types

2. **Traverses upward** from file location
3. **Selects best match** based on marker priority and count
4. **Falls back** to file directory if no markers found

### Security Benefits

- ✅ **File access control**: Only files within project boundaries
- ✅ **Path traversal protection**: Blocks `../../../etc/passwd` attacks
- ✅ **Symlink safety**: Prevents symlink-based boundary bypass
- ✅ **Audit logging**: Records all security events

## 📋 Configuration Options

### Priority Order (Highest to Lowest)

| Priority | Method | CLI | MCP | Use Case |
|----------|--------|-----|-----|----------|
| 🥇 **1st** | Command line argument | `--project-root /path` | `"args": [..., "--project-root", "/path"]` | Fixed paths, overrides |
| 🥈 **2nd** | Environment variable | `TREE_SITTER_PROJECT_ROOT=/path` | `"env": {"TREE_SITTER_PROJECT_ROOT": "/path"}` | Dynamic, workspace integration |
| 🥉 **3rd** | Auto-detection | *(default)* | *(default)* | Zero configuration |

### When to Use Each Method

#### Environment Variable (Recommended)
```json
"env": {"TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"}
```
- ✅ **Best for**: Most users, IDE integration
- ✅ **Benefits**: Automatic workspace adaptation, flexible
- ✅ **Works with**: VS Code, most IDEs

#### Command Line Argument
```bash
--project-root /specific/path
```
- ✅ **Best for**: Fixed paths, CI/CD, overrides
- ✅ **Benefits**: Explicit control, highest priority
- ✅ **Works with**: Scripts, automation

#### Auto-Detection
```bash
# No configuration needed
```
- ✅ **Best for**: Development, quick testing
- ✅ **Benefits**: Zero configuration, intelligent
- ✅ **Works with**: Standard project structures

## 🚨 Common Issues & Solutions

### Issue: "Absolute path must be within project directory"

**Cause**: File is outside detected project boundary

**Solutions:**
1. Use explicit project root: `--project-root /correct/path`
2. Check project markers exist in expected location
3. Verify file is actually within intended project

### Issue: "No project root detected"

**Cause**: No project markers found

**Solutions:**
1. Add a project marker file (`.git`, `pyproject.toml`, etc.)
2. Use explicit project root: `--project-root .`
3. Check current working directory

### Issue: Wrong project root detected

**Cause**: Multiple nested projects or unexpected markers

**Solutions:**
1. Use explicit project root to override
2. Remove unwanted project markers
3. Check marker priority (`.git` > `pyproject.toml` > `README.md`)

## 🧪 Testing Your Configuration

### Test Auto-Detection
```bash
cd /your/project
python -c "
from tree_sitter_analyzer.project_detector import detect_project_root
print('Detected:', detect_project_root())
"
```

### Test MCP Server
```bash
# Test with your configuration
python -m tree_sitter_analyzer.mcp.server --help
# Check logs for "MCP server starting with project root: ..."
```

### Test Security Boundaries
```bash
# Should work (file within project)
tree-sitter-analyzer src/main.py --table=compact

# Should fail (file outside project)
tree-sitter-analyzer ../outside.py --table=compact
```

## 📖 Examples by Project Type

### Python Project
```
my-python-project/
├── pyproject.toml          # ← Detected as project root
├── src/
│   └── mypackage/
│       └── main.py         # ← Analyze this file
└── tests/
```

### JavaScript Project
```
my-js-project/
├── package.json            # ← Detected as project root
├── src/
│   └── index.js           # ← Analyze this file
└── node_modules/
```

### Java Project
```
my-java-project/
├── pom.xml                 # ← Detected as project root
├── src/
│   └── main/
│       └── java/
│           └── Main.java   # ← Analyze this file
└── target/
```

### Git Repository
```
any-project/
├── .git/                   # ← Detected as project root (highest priority)
├── src/
│   └── code.ext           # ← Analyze this file
└── docs/
```

## 🎯 Best Practices

1. **Use environment variable for MCP**: `${workspaceFolder}` adapts automatically
2. **Let auto-detection work**: Most projects have standard markers
3. **Override when needed**: Use command line for special cases
4. **Test your setup**: Verify project root detection works as expected
5. **Keep it simple**: Start with recommended configuration, customize only if needed

---

**Need help?** Check the full setup guides:
- [MCP Setup for Users](MCP_SETUP_USERS.md)
- [MCP Setup for Developers](MCP_SETUP_DEVELOPERS.md)
