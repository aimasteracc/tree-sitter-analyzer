import argparse
import asyncio
import json
import os
from typing import Any

from ..output_manager import output_error, output_info, output_list
from ..query_loader import query_loader


class SpecialCommandHandler:
    """Handlers for special CLI commands that don't fit the standard command pattern."""

    @staticmethod
    def handle(args: argparse.Namespace) -> int | None:
        """
        Handle special commands based on arguments.

        Returns:
            Exit code (int) if a special command was handled, None otherwise.
        """
        handler = SpecialCommandHandler(args)
        return handler.process()

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args

    def process(self) -> int | None:
        # Batch partial read (unified with MCP tool arguments)
        if (
            hasattr(self.args, "partial_read")
            and self.args.partial_read
            and (
                getattr(self.args, "partial_read_requests_json", None)
                or getattr(self.args, "partial_read_requests_file", None)
            )
        ):
            return self._handle_batch_partial_read()

        # Batch metrics (unified with MCP tool arguments)
        if getattr(self.args, "metrics_only", False):
            return self._handle_batch_metrics()

        # Validate partial read options (single-range mode)
        if hasattr(self.args, "partial_read") and self.args.partial_read:
            validation_error = self._validate_partial_read_options()
            if validation_error:
                return validation_error

        # Query language commands
        if self.args.show_query_languages:
            return self._show_query_languages()

        if self.args.show_common_queries:
            return self._show_common_queries()

        # SQL Platform Compatibility Commands
        if self.args.sql_platform_info:
            return self._show_sql_platform_info()

        if self.args.record_sql_profile:
            return self._record_sql_profile()

        if self.args.compare_sql_profiles:
            return self._compare_sql_profiles()

        return None

    def _effective_output_format(self) -> str:
        # --format is an alias for json/toon; --output-format supports json/text/toon
        fmt = getattr(self.args, "format", None) or getattr(
            self.args, "output_format", "json"
        )
        return str(fmt)

    def _tool_output_format(self) -> str:
        # Tools only accept json/toon; map text -> toon for batch modes.
        fmt = self._effective_output_format()
        return "toon" if fmt in {"toon", "text"} else "json"

    def _load_requests_payload(self) -> list[dict[str, Any]]:
        # Local import avoids rare closure/scoping issues in some execution contexts.
        import json as _json

        if getattr(self.args, "partial_read_requests_json", None):
            raw = self.args.partial_read_requests_json
        elif getattr(self.args, "partial_read_requests_file", None):
            with open(self.args.partial_read_requests_file, encoding="utf-8") as f:
                raw = f.read()
        else:
            raise ValueError("No batch requests source provided")

        payload = _json.loads(raw)
        if isinstance(payload, dict) and "requests" in payload:
            reqs = payload["requests"]
        else:
            reqs = payload
        if not isinstance(reqs, list):
            raise ValueError(
                "Batch requests must be a list or {'requests': [...]} JSON"
            )
        return reqs

    def _load_file_paths(self) -> list[str]:
        paths: list[str] = []
        if getattr(self.args, "file_paths", None):
            paths.extend([str(p) for p in self.args.file_paths])
        if getattr(self.args, "files_from", None):
            with open(self.args.files_from, encoding="utf-8") as f:
                for line in f.read().splitlines():
                    s = line.strip()
                    if s:
                        paths.append(s)
        # De-dup while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for p in paths:
            if p not in seen:
                unique.append(p)
                seen.add(p)
        return unique

    def _handle_batch_partial_read(self) -> int:
        try:
            from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

            requests_list = self._load_requests_payload()
            project_root = getattr(self.args, "project_root", None) or os.getcwd()
            read_tool = ReadPartialTool(project_root=project_root)
            tool_args: dict[str, Any] = {
                "requests": requests_list,
                "output_format": self._tool_output_format(),
                "format": "text",
                "allow_truncate": bool(getattr(self.args, "allow_truncate", False)),
                "fail_fast": bool(getattr(self.args, "fail_fast", False)),
            }
            result = asyncio.run(read_tool.execute(tool_args))

            fmt = self._effective_output_format()
            if fmt == "toon":
                print(result.get("toon_content", ""))
            else:
                # json or text: print the returned dict as JSON (text is mapped for batch modes)
                from tree_sitter_analyzer.output_manager import output_json

                output_json(result)
            return 0 if result.get("success", False) else 1
        except Exception as e:
            output_error(f"Batch partial read failed: {e}")
            return 1

    def _handle_batch_metrics(self) -> int:
        file_paths = self._load_file_paths()
        if not file_paths:
            output_error("--metrics-only requires --file-paths or --files-from")
            return 1
        try:
            from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import (
                AnalyzeScaleTool,
            )

            project_root = getattr(self.args, "project_root", None) or os.getcwd()
            scale_tool = AnalyzeScaleTool(project_root=project_root)
            tool_args = {
                "file_paths": file_paths,
                "metrics_only": True,
                "output_format": self._tool_output_format(),
            }
            result = asyncio.run(scale_tool.execute(tool_args))

            fmt = self._effective_output_format()
            if fmt == "toon":
                print(result.get("toon_content", ""))
            else:
                from tree_sitter_analyzer.output_manager import output_json

                output_json(result)
            return 0 if result.get("success", False) else 1
        except Exception as e:
            output_error(f"Batch metrics failed: {e}")
            return 1

    def _validate_partial_read_options(self) -> int | None:
        if self.args.start_line is None:
            output_error("--start-line is required")
            return 1

        if self.args.start_line < 1:
            output_error("--start-line must be 1 or greater")
            return 1

        if self.args.end_line and self.args.end_line < self.args.start_line:
            output_error("--end-line must be greater than or equal to --start-line")
            return 1

        if self.args.start_column is not None and self.args.start_column < 0:
            output_error("--start-column must be 0 or greater")
            return 1

        if self.args.end_column is not None and self.args.end_column < 0:
            output_error("--end-column must be 0 or greater")
            return 1
        return None

    def _show_query_languages(self) -> int:
        output_list(["Languages with query support:"])
        for lang in query_loader.list_supported_languages():
            query_count = len(query_loader.list_queries_for_language(lang))
            output_list([f"  {lang:<15} ({query_count} queries)"])
        return 0

    def _show_common_queries(self) -> int:
        common_queries = query_loader.get_common_queries()
        if common_queries:
            output_list("Common queries across multiple languages:")
            for query in common_queries:
                output_list(f"  {query}")
        else:
            output_info("No common queries found.")
        return 0

    def _show_sql_platform_info(self) -> int:
        from tree_sitter_analyzer.platform_compat.detector import PlatformDetector
        from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile

        info = PlatformDetector.detect()
        output_list(
            [
                "SQL Platform Information:",
                f"  OS Name: {info.os_name}",
                f"  OS Version: {info.os_version}",
                f"  Python Version: {info.python_version}",
                f"  Platform Key: {info.platform_key}",
                "",
            ]
        )

        profile = BehaviorProfile.load(info.platform_key)
        if profile:
            output_list(
                [
                    f"Loaded Profile: {info.platform_key}",
                    f"  Schema Version: {profile.schema_version}",
                    f"  Behaviors Recorded: {len(profile.behaviors)}",
                    f"  Adaptation Rules: {', '.join(profile.adaptation_rules) if profile.adaptation_rules else 'None'}",
                ]
            )
        else:
            output_list(
                [
                    f"No profile found for {info.platform_key}",
                    "  Using default adaptation rules.",
                ]
            )
        return 0

    def _record_sql_profile(self) -> int:
        from pathlib import Path

        from tree_sitter_analyzer.platform_compat.recorder import BehaviorRecorder

        output_info("Starting SQL behavior recording...")
        try:
            recorder = BehaviorRecorder()
            profile = recorder.record_all()

            # Default output directory
            output_dir = Path("tests/platform_profiles")
            output_dir.mkdir(parents=True, exist_ok=True)

            profile.save(output_dir)
            output_info(f"Recorded profile for {profile.platform_key}")
            output_info(f"Saved to {output_dir}")
        except Exception as e:
            output_error(f"Failed to record profile: {e}")
            return 1
        return 0

    def _compare_sql_profiles(self) -> int:
        from pathlib import Path

        from tree_sitter_analyzer.platform_compat.compare import (
            compare_profiles,
            generate_diff_report,
        )
        from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile

        p1_path = Path(self.args.compare_sql_profiles[0])
        p2_path = Path(self.args.compare_sql_profiles[1])

        if not p1_path.exists():
            output_error(f"Profile not found: {p1_path}")
            return 1
        if not p2_path.exists():
            output_error(f"Profile not found: {p2_path}")
            return 1

        try:
            from tree_sitter_analyzer.platform_compat.profiles import (
                BehaviorProfile,
                ParsingBehavior,
            )

            def load_profile(path: Path) -> BehaviorProfile:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    # Manual deserialization of nested objects
                    behaviors: dict[str, ParsingBehavior] = {}
                    for key, b_data in data.get("behaviors", {}).items():
                        if isinstance(b_data, dict):
                            behaviors[key] = ParsingBehavior(**b_data)
                        # If b_data is not a dict, it's not a valid ParsingBehavior
                        # and should be skipped or an error raised.
                        # For now, we'll skip to avoid type errors.

                    return BehaviorProfile(
                        schema_version=data.get("schema_version", "1.0.0"),
                        platform_key=data["platform_key"],
                        behaviors=behaviors,
                        adaptation_rules=data.get("adaptation_rules", []),
                    )

            p1 = load_profile(p1_path)
            p2 = load_profile(p2_path)

            comparison = compare_profiles(p1, p2)
            report = generate_diff_report(comparison)
            print(report)
        except Exception as e:
            output_error(f"Error comparing profiles: {e}")
            return 1
        return 0
