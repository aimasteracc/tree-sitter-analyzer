# Security Review Report - TOON Format Changes

**Files Reviewed:**
- tree_sitter_analyzer/mcp/utils/format_helper.py
- tree_sitter_analyzer/formatters/toon_formatter.py
- tree_sitter_analyzer/formatters/toon_encoder.py
- All MCP tools using TOON formatting functions

**Reviewed:** 2026-02-13
**Reviewer:** security-reviewer agent
**Risk Level:** 🟢 LOW

## Summary

- **Critical Issues:** 0
- **High Issues:** 0
- **Medium Issues:** 2
- **Low Issues:** 3
- **Risk Level:** 🟢 LOW

The bug fix addressing field duplication and token explosion has been implemented securely. The whitelist approach in `apply_toon_format_to_response` effectively prevents data duplication and token explosion without introducing new vulnerabilities.

## Positive Security Findings

### 1. Whitelist-Based Field Filtering (SECURE)
**Location:** `format_helper.py:180-209`

The implementation uses a strict whitelist (`_METADATA_WHITELIST`) to control which fields are preserved alongside `toon_content`. This approach:
- ✅ Prevents token explosion by excluding all data-bearing fields
- ✅ Only preserves small scalar metadata fields
- ✅ Explicitly excludes dict and list types even if field names match whitelist
- ✅ Cannot be bypassed through field name manipulation

### 2. Circular Reference Detection (SECURE)
**Location:** `toon_encoder.py:232-236, 303-309`

Strong protection against circular references:
- ✅ Tracks object IDs during traversal
- ✅ Raises `ToonEncodeError` on circular reference detection
- ✅ Properly cleans up `seen_ids` set after processing
- ✅ Prevents infinite loops and memory exhaustion

### 3. Maximum Depth Limiting (SECURE)
**Location:** `toon_encoder.py:187-191`

Effective DoS prevention:
- ✅ Enforces MAX_DEPTH limit (default 100) without using recursion
- ✅ Uses iterative approach with explicit stack
- ✅ Cannot cause Python stack overflow
- ✅ Configurable limit for different security requirements

### 4. Path Traversal Protection (SECURE)
**Location:** `validator.py:96-200`

Multi-layer defense:
- ✅ Null byte injection check
- ✅ Path traversal sequence detection
- ✅ Symbolic link and junction detection
- ✅ Project boundary enforcement
- ✅ Windows reparse point detection

---

## Medium Issues (Fix When Possible)

### 1. String Escaping Edge Cases
**Severity:** MEDIUM
**Category:** Input Validation
**Location:** `toon_encoder.py:543-593`

**Issue:**
The `_encode_string` method escapes special characters but may not handle all edge cases:
- Escapes: `\`, `"`, `\n`, `\r`, `\t`
- Missing: Other control characters (0x00-0x1F)
- Missing: Unicode direction override characters (U+202A-U+202E)

**Impact:**
- Could lead to malformed TOON output if control characters are present
- Potential for format confusion attacks using Unicode bidirectional characters

**Proof of Concept:**
```python
# Control character injection
malicious_data = {"field": "value\x00\x01\x02"}  # Null and control chars
toon_output = format_as_toon(malicious_data)
# May produce malformed output

# Unicode bidi override
rtl_override = {"name": "\u202Emalicious"}  # Right-to-left override
# Could cause visual confusion in logs
```

**Remediation:**
```python
def _encode_string(self, s: str) -> str:
    # Filter or escape all control characters
    import unicodedata

    # Remove control characters except tab, newline, carriage return
    filtered = "".join(
        ch for ch in s
        if ch in '\t\n\r' or unicodedata.category(ch)[0] != 'C'
    )

    # Remove bidirectional override characters
    bidi_chars = '\u202A\u202B\u202C\u202D\u202E\u2066\u2067\u2068\u2069'
    filtered = filtered.translate(str.maketrans('', '', bidi_chars))

    # Continue with existing escaping...
```

### 2. ReDoS Risk in Path Normalization
**Severity:** MEDIUM
**Category:** Denial of Service
**Location:** `toon_encoder.py:624-628`

**Issue:**
Complex regex patterns for Windows path detection could be vulnerable to ReDoS:
```python
re.match(r"^[A-Za-z]:\\[A-Za-z0-9_\-\.\\/]+", s)
```

**Impact:**
- Carefully crafted input with many backslashes could cause performance degradation
- Not critical as it's bounded by MAX_DEPTH and string length limits

**Remediation:**
```python
def _normalize_path_string(self, s: str) -> str:
    if "\\" not in s:
        return s

    # Use simpler, non-regex approach
    if len(s) >= 3 and s[1:3] == ':\\' and s[0].isalpha():
        # Windows absolute path
        return s.replace("\\", "/")
    elif s.startswith('\\\\') and len(s) > 2:
        # UNC path
        return s.replace("\\", "/")
    elif s.startswith('.\\') or s.startswith('..\\'):
        # Relative path
        return s.replace("\\", "/")

    return s
```

---

## Low Issues (Consider Fixing)

### 1. Inconsistent Error Handling
**Severity:** LOW
**Category:** Error Handling
**Location:** Multiple locations

**Issue:**
Some errors fall back to JSON silently without proper logging context:
- `format_helper.py:63`: Logs warning but doesn't include original error details
- `format_helper.py:224`: Generic error message without stack trace

**Impact:**
- Debugging difficulties
- Potential information disclosure if errors contain sensitive data

**Remediation:**
```python
except Exception as e:
    logger.warning(
        f"TOON formatting failed: {type(e).__name__}",
        exc_info=False  # Don't log full traceback to avoid info disclosure
    )
    return format_as_json(data)
```

### 2. Incomplete Input Type Validation
**Severity:** LOW
**Category:** Input Validation
**Location:** `toon_encoder.py:511-541`

**Issue:**
The `encode_value` method uses `str()` fallback for unknown types without validation:
```python
else:
    return str(value)
```

**Impact:**
- Objects with malicious `__str__` implementations could inject unexpected content
- Custom objects might leak internal state

**Remediation:**
```python
else:
    # Whitelist approach for unknown types
    type_name = type(value).__name__
    if type_name in ['datetime', 'date', 'time', 'UUID']:
        return str(value)
    else:
        return f"<{type_name} object>"
```

### 3. Missing Rate Limiting for Format Operations
**Severity:** LOW
**Category:** Denial of Service
**Location:** All formatting operations

**Issue:**
No rate limiting on formatting operations that could be CPU-intensive for large data structures.

**Impact:**
- Potential for resource exhaustion with many concurrent formatting requests
- Already mitigated by MAX_DEPTH and general API rate limiting

**Remediation:**
Consider implementing operation-level rate limiting or CPU time limits for formatting operations.

---

## Security Checklist

- ✅ No hardcoded secrets
- ✅ Input validation present (path validation, type checking)
- ✅ No SQL injection risks (no database operations)
- ✅ XSS prevention (string escaping implemented)
- ✅ Path traversal prevention (comprehensive validation)
- ✅ Denial of Service protection (depth limits, circular reference detection)
- ✅ No authentication bypass risks (no auth in formatter)
- ⚠️ Rate limiting (relies on API-level limiting)
- ✅ Error messages sanitized (no sensitive data in errors)
- ✅ No vulnerable dependencies identified

## Recommendations

1. **Priority 1 - Medium Issues:**
   - Enhance string escaping to handle all control characters
   - Simplify Windows path detection to avoid ReDoS

2. **Priority 2 - Low Issues:**
   - Improve error logging consistency
   - Add type whitelist for unknown object types

3. **Security Enhancements:**
   - Consider adding configurable limits for:
     - Maximum string length
     - Maximum array size
     - Maximum object key count
   - Add metrics/monitoring for formatting operations
   - Document security considerations in API documentation

## Conclusion

The TOON format bug fix has been implemented with strong security controls. The whitelist approach effectively prevents the token explosion issue without introducing significant vulnerabilities. The identified issues are mostly edge cases with LOW to MEDIUM severity that should be addressed but do not pose immediate security risks.

**Recommendation:** APPROVE WITH MINOR FIXES

The implementation is secure for production use. The medium-severity issues should be addressed in a follow-up PR to further harden the system against edge cases.

---

**Security review performed by Claude Code security-reviewer agent**
For questions, see security documentation or consult the security team.