#!/usr/bin/env python3
"""
Unit tests for Analysis Session recording and replay functionality.

Test Coverage:
- Session creation with all metadata fields
- File hash calculation (SHA256)
- Session serialization to JSON
- Session directory auto-creation (P1 gap fix)
- Session ID uniqueness (timestamp + uuid4)
- Git commit recording
- Token statistics tracking
- Multiple input files handling
- Session validation
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from tree_sitter_analyzer.core.analysis_session import AnalysisSession


class TestAnalysisSessionCreation:
    """测试 AnalysisSession 创建和基本属性"""

    def test_session_creation_with_minimal_params(self):
        """创建最小参数的 session"""
        session = AnalysisSession(
            input_files=["/path/to/file.py"],
            output_format="toon"
        )

        assert session.session_id is not None
        assert session.timestamp is not None
        assert session.input_files == ["/path/to/file.py"]
        assert session.output_format == "toon"
        assert session.tools_used == []
        assert session.git_commit is None

    def test_session_id_format_timestamp_plus_uuid(self):
        """Session ID 格式应为 timestamp-uuid4（防止同一秒内冲突）"""
        session = AnalysisSession(
            input_files=["/path/to/file.py"],
            output_format="json"
        )

        # Session ID 格式: YYYYMMDD-HHMMSS-<uuid4>
        parts = session.session_id.split('-')
        assert len(parts) >= 3  # 至少有 date-time-uuid

        # 第一部分是日期 YYYYMMDD
        assert len(parts[0]) == 8
        assert parts[0].isdigit()

        # 第二部分是时间 HHMMSS
        assert len(parts[1]) == 6
        assert parts[1].isdigit()

    def test_session_id_uniqueness_with_rapid_creation(self):
        """快速连续创建 session，ID 应该唯一（uuid4 保证）"""
        sessions = [
            AnalysisSession(input_files=[f"/file{i}.py"], output_format="toon")
            for i in range(10)
        ]

        session_ids = [s.session_id for s in sessions]
        assert len(session_ids) == len(set(session_ids))  # 所有 ID 唯一

    def test_session_with_all_optional_params(self):
        """创建包含所有可选参数的 session"""
        session = AnalysisSession(
            input_files=["/file1.py", "/file2.py"],
            output_format="json",
            git_commit="abc123def456",
            tools_used=["analyze_code_structure", "get_code_outline"],
            token_count_before=1000,
            token_count_after=450
        )

        assert session.git_commit == "abc123def456"
        assert session.tools_used == ["analyze_code_structure", "get_code_outline"]
        assert session.token_count_before == 1000
        assert session.token_count_after == 450
        assert session.token_savings_pct == 55.0  # (1000-450)/1000 * 100

    def test_token_savings_calculation(self):
        """Token 节省百分比计算正确"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon",
            token_count_before=1000,
            token_count_after=540
        )

        # (1000 - 540) / 1000 * 100 = 46%
        assert session.token_savings_pct == 46.0

    def test_token_savings_when_counts_not_provided(self):
        """Token counts 未提供时，savings_pct 应为 None"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon"
        )

        assert session.token_count_before is None
        assert session.token_count_after is None
        assert session.token_savings_pct is None


class TestFileHashCalculation:
    """测试文件 SHA256 hash 计算"""

    @patch("builtins.open", new_callable=mock_open, read_data=b"file content")
    @patch("pathlib.Path.exists", return_value=True)
    def test_file_hash_calculation_sha256(self, mock_exists, mock_file):
        """计算文件 SHA256 hash"""
        session = AnalysisSession(
            input_files=["/path/to/file.py"],
            output_format="toon"
        )

        # SHA256("file content") = 固定值
        expected_hash = "e0ac3601005dfa1864f5392aabaf7d898b1b5bab854f1acb4491bcd806b76b0c"
        assert session.file_hashes["/path/to/file.py"] == expected_hash

    @patch("pathlib.Path.exists", return_value=False)
    def test_file_hash_missing_file(self, mock_exists):
        """文件不存在时，hash 应为 None"""
        session = AnalysisSession(
            input_files=["/nonexistent/file.py"],
            output_format="toon"
        )

        assert session.file_hashes["/nonexistent/file.py"] is None

    @patch("builtins.open", new_callable=mock_open, read_data=b"content1")
    @patch("pathlib.Path.exists", return_value=True)
    def test_multiple_files_hash_calculation(self, mock_exists, mock_file):
        """多个文件的 hash 计算"""
        session = AnalysisSession(
            input_files=["/file1.py", "/file2.py"],
            output_format="toon"
        )

        assert len(session.file_hashes) == 2
        assert all(hash_val is not None for hash_val in session.file_hashes.values())


class TestSessionSerialization:
    """测试 Session 序列化到 JSON"""

    def test_to_dict_includes_all_fields(self):
        """to_dict() 应包含所有字段"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="json",
            git_commit="abc123",
            tools_used=["tool1"],
            token_count_before=100,
            token_count_after=50
        )

        data = session.to_dict()

        assert "session_id" in data
        assert "timestamp" in data
        assert "input_files" in data
        assert "file_hashes" in data
        assert "git_commit" in data
        assert "output_format" in data
        assert "tools_used" in data
        assert "token_count_before" in data
        assert "token_count_after" in data
        assert "token_savings_pct" in data

    def test_to_dict_serializable_to_json(self):
        """to_dict() 返回的数据应该可以序列化为 JSON"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon"
        )

        data = session.to_dict()
        json_str = json.dumps(data)  # 不应抛出异常

        assert isinstance(json_str, str)
        assert len(json_str) > 0


class TestSessionPersistence:
    """测试 Session 持久化到 ~/.tsa/sessions/"""

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.exists", return_value=False)
    @patch("builtins.open", new_callable=mock_open)
    def test_save_creates_session_directory_if_not_exists(
        self, mock_file, mock_exists, mock_mkdir
    ):
        """Session 目录不存在时自动创建（修复 P1 gap）"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon"
        )

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/mock/home")
            session.save_to_audit_log()

            # 应该调用 mkdir 创建 ~/.tsa/sessions/
            mock_mkdir.assert_called_once()

    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open)
    def test_save_skips_mkdir_if_directory_exists(
        self, mock_file, mock_exists, mock_mkdir
    ):
        """Session 目录存在时不重复创建"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon"
        )

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/mock/home")
            session.save_to_audit_log()

            # 不应该调用 mkdir
            mock_mkdir.assert_not_called()

    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_save_writes_json_to_correct_path(self, mock_exists, mock_file):
        """保存的 JSON 文件路径正确"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon"
        )

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/mock/home")
            result_path = session.save_to_audit_log()

            # 路径应该是 ~/.tsa/sessions/{session_id}.json
            expected_path = Path(f"/mock/home/.tsa/sessions/{session.session_id}.json")
            assert result_path == expected_path

    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.exists", return_value=True)
    def test_save_writes_valid_json_content(self, mock_exists, mock_file):
        """保存的 JSON 内容格式正确"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="json",
            git_commit="abc123"
        )

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/mock/home")
            session.save_to_audit_log()

            # 获取写入的内容
            handle = mock_file()
            written_content = "".join(
                call.args[0] for call in handle.write.call_args_list
            )

            # 应该是合法的 JSON
            data = json.loads(written_content)
            assert data["output_format"] == "json"
            assert data["git_commit"] == "abc123"


class TestSessionValidation:
    """测试 Session 数据验证"""

    def test_empty_input_files_raises_error(self):
        """input_files 为空应该抛出异常"""
        with pytest.raises(ValueError, match="input_files cannot be empty"):
            AnalysisSession(
                input_files=[],
                output_format="toon"
            )

    def test_invalid_output_format_raises_error(self):
        """无效的 output_format 应该抛出异常"""
        with pytest.raises(ValueError, match="Invalid output_format"):
            AnalysisSession(
                input_files=["/file.py"],
                output_format="invalid_format"
            )

    def test_valid_output_formats(self):
        """有效的 output_format 应该被接受"""
        valid_formats = ["toon", "json", "csv", "compact", "full"]

        for fmt in valid_formats:
            session = AnalysisSession(
                input_files=["/file.py"],
                output_format=fmt
            )
            assert session.output_format == fmt

    def test_negative_token_count_raises_error(self):
        """负数 token count 应该抛出异常"""
        with pytest.raises(ValueError, match="Token counts cannot be negative"):
            AnalysisSession(
                input_files=["/file.py"],
                output_format="toon",
                token_count_before=-100
            )

    def test_token_count_after_greater_than_before_warning(self):
        """token_count_after > before 应该警告（可能是统计错误）"""
        # 这个不抛出异常，但应该在 log 中警告
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon",
            token_count_before=100,
            token_count_after=200
        )

        # token_savings_pct 应该是负数
        assert session.token_savings_pct == -100.0


class TestGitIntegration:
    """测试 Git commit 记录功能"""

    @patch("subprocess.run")
    def test_auto_detect_git_commit(self, mock_run):
        """自动检测当前 git commit"""
        mock_run.return_value = MagicMock(
            stdout="abc123def456\n",
            returncode=0
        )

        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon",
            auto_detect_git_commit=True
        )

        assert session.git_commit == "abc123def456"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_auto_detect_git_commit_not_in_repo(self, mock_run):
        """不在 git repo 中时，git_commit 应为 None"""
        mock_run.return_value = MagicMock(
            stderr="not a git repository",
            returncode=128
        )

        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon",
            auto_detect_git_commit=True
        )

        assert session.git_commit is None

    def test_manual_git_commit_overrides_auto_detect(self):
        """手动提供的 git_commit 优先于自动检测"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="auto_detected_commit\n",
                returncode=0
            )

            session = AnalysisSession(
                input_files=["/file.py"],
                output_format="toon",
                git_commit="manual_commit",
                auto_detect_git_commit=True
            )

            assert session.git_commit == "manual_commit"
            # 不应该调用 git rev-parse
            mock_run.assert_not_called()


class TestSessionRetention:
    """测试 Session 保留策略"""

    def test_default_retention_90_days(self):
        """默认保留策略应为 90 天"""
        _ = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon"
        )

        # 这个属性在类级别定义
        assert AnalysisSession.DEFAULT_RETENTION_DAYS == 90

    @patch.dict("os.environ", {"TSA_SESSION_RETENTION_DAYS": "30"})
    def test_custom_retention_from_env_var(self):
        """从环境变量读取自定义保留天数"""
        # 这个功能在后续实现 session cleanup 时测试
        # 现在只验证常量存在
        assert hasattr(AnalysisSession, "DEFAULT_RETENTION_DAYS")


class TestSessionMetadataFields:
    """测试 Session metadata 字段的正确性"""

    def test_timestamp_format_iso8601(self):
        """Timestamp 应为 ISO 8601 格式"""
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon"
        )

        # 应该能解析为 datetime (handle 'Z' suffix for UTC)
        timestamp_str = session.timestamp.replace('Z', '+00:00')
        dt = datetime.fromisoformat(timestamp_str)
        assert isinstance(dt, datetime)

    def test_tools_used_preserves_order(self):
        """tools_used 应保持调用顺序"""
        tools = ["tool_a", "tool_b", "tool_c"]
        session = AnalysisSession(
            input_files=["/file.py"],
            output_format="toon",
            tools_used=tools
        )

        assert session.tools_used == tools

    def test_multiple_input_files_preserved(self):
        """多个 input files 应该完整保存"""
        files = ["/file1.py", "/file2.py", "/dir/file3.py"]
        session = AnalysisSession(
            input_files=files,
            output_format="toon"
        )

        assert session.input_files == files
        assert len(session.file_hashes) == 3
