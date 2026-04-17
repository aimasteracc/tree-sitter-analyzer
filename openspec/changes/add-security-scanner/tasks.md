# Security Scanner MCP Tool

## Goal
Add a security-focused MCP tool that detects common security vulnerabilities using AST pattern matching.一句话定义：**AST-based security vulnerability scanner for multi-language codebases.**

## MVP Scope

### Sprint 1: Core Detection Engine (Python focus)
**Goal**: Implement core security pattern detection engine with Python support

**Tasks**:
1. Create `analysis/security_scan.py` module
   - Security pattern registry (vulnerability type → AST pattern)
   - Pattern matcher engine using tree-sitter queries
   - Finding severity classification (CRITICAL/HIGH/MEDIUM/LOW)

2. Implement 5 core security patterns for Python:
   - **Hardcoded secrets**: API keys, passwords, tokens in string literals
   - **SQL injection**: String concatenation in SQL queries
   - **Command injection**: Subprocess calls with untrusted input
   - **Unsafe deserialization**: pickle/yaml loads with user data
   - **Weak crypto**: MD5, SHA1 usage

3. Add unit tests (20+ tests)
   - Pattern detection tests for each vulnerability type
   - False positive tests
   - Severity classification tests

**Success Criteria**:
- 20+ unit tests pass
- Detects all 5 vulnerability types in Python code
- < 10% false positive rate

---

### Sprint 2: Multi-Language Support
**Goal**: Extend detection to JavaScript, Java, Go

**Tasks**:
1. Add JavaScript security patterns:
   - XSS: unsafe innerHTML, eval()
   - SQL injection: template literals in queries
   - Command injection: child_process.exec()
   - Hardcoded secrets: string literals

2. Add Java security patterns:
   - SQL injection: string concatenation in JDBC
   - Command injection: Runtime.exec()
   - Deserialization: ObjectInputStream, unsafe XMLDecoder
   - Path traversal: File() with user input

3. Add Go security patterns:
   - SQL injection: fmt.Sprintf in queries
   - Command injection: exec.Command with user input
   - Path traversal: os.Open with user input

4. Add integration tests (15+ tests)
   - Real code samples with vulnerabilities
   - Multi-language project scanning

**Success Criteria**:
- 15+ integration tests pass
- Supports Python, JavaScript, Java, Go
- Each language has 4+ security patterns

---

### Sprint 3: MCP Integration & CI Output
**Goal**: Create MCP tool wrapper with SARIF output

**Tasks**:
1. Create `mcp/tools/security_scan_tool.py`
   - Register to ToolRegistry (safety toolset)
   - Add schema with language/filter options
   - Implement TOON format output

2. Add SARIF format output
   - SARIF 2.1.0 JSON schema compliance
   - Severity levels map to SARIF levels
   - CI-friendly output format

3. Add security report tool
   - Aggregates findings across multiple files
   - Provides remediation suggestions
   - Generates executive summary

4. Add documentation and tests (10+ tests)
   - MCP tool integration tests
   - SARIF validation tests
   - Update README/ARCHITECTURE/CHANGELOG

**Success Criteria**:
- 10+ tests pass
- SARIF output validates against schema
- Tool registered and discoverable via tools/list
- Total: 45+ tests (20+15+10)

## Technical Approach

### Core Components

```
security_scan.py
├── SecurityPattern (dataclass)
│   ├── name: str
│   ├── severity: SeverityLevel
│   ├── description: str
│   ├── remediation: str
│   └── query: tree-sitter query
│
├── SecurityScanner (class)
│   ├── register_pattern(pattern)
│   ├── scan_file(path, language)
│   └── scan_project(path)
│
└── SecurityFinding (dataclass)
    ├── rule_id: str
    ├── severity: SeverityLevel
    ├── message: str
    ├── location: (line, col)
    └── remediation: str
```

### Dependencies
- `tree_sitter_analyzer/analysis/` — Core analysis utilities
- Existing tree-sitter language parsers
- `sarif_om` Python library for SARIF output

### Integration Points
- ToolRegistry → safety toolset
- CI/CD pipeline → SARIF output for GitHub Security tab
- Existing security_reviewer skill (ECC) — complementary

## Exit Criteria
- [x] Sprint 1: Core engine + Python patterns (20+ tests)
- [x] Sprint 2: Multi-language support (15+ tests)
- [x] Sprint 3: MCP integration (10+ tests)
- [x] Total: 45+ tests pass
- [x] Tool registered and discoverable
- [x] Documentation updated
- [x] CHANGELOG.md updated
