# Hardcoded IP Address Detector

## Goal
Detect hardcoded IP addresses and port numbers in source code that should be in configuration.

## MVP Scope
- [ ] Core analyzer: hardcoded_ip.py (inherits BaseAnalyzer)
- [ ] Detect: hardcoded_ip, hardcoded_port
- [ ] Languages: Python, JavaScript/TypeScript, Java, Go
- [ ] MCP tool: hardcoded_ip_tool.py registered in tool_registration.py
- [ ] Tests: 35+ tests covering all issue types and languages

## Technical Approach
- Pure AST traversal — find string literal and integer literal nodes
- Regex on string content for IPv4 patterns
- Port detection: integer literals in port range (1-65535) assigned to port-related variables
- Skip: loopback (127.x), broadcast, common test IPs (0.0.0.0)
- Skip: strings inside comments

## Dependencies
- BaseAnalyzer (analysis/base.py)
- LanguageLoader (language_loader.py)
- tool_registration.py for MCP registration
