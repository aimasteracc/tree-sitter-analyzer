"""
Pattern learning - promotes LLM-resolved queries to fast path.

Analyzes successful LLM resolutions to extract patterns that can
be handled by deterministic tools (grep, ast-grep, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from tree_sitter_analyzer.search.query_cache import CacheEntry, QueryCache


@dataclass(frozen=True)
class PatternRule:
    """Learned pattern rule for fast path classification."""

    pattern: str
    tool_name: str
    confidence: float
    sample_queries: tuple[str, ...]
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "tool_name": self.tool_name,
            "confidence": self.confidence,
            "sample_queries": list(self.sample_queries),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatternRule:
        return cls(
            pattern=data["pattern"],
            tool_name=data["tool_name"],
            confidence=float(data["confidence"]),
            sample_queries=tuple(data.get("sample_queries", [])),
            created_at=data["created_at"],
        )


@dataclass
class PatternLearner:
    """Learns patterns from LLM-resolved queries.

    Analyzes query patterns that consistently resolve to specific tools
    and generates regex rules for fast path classification.
    """

    def __init__(
        self,
        cache: QueryCache,
        min_confidence: float = 0.8,
        min_samples: int = 3,
    ) -> None:
        """Initialize pattern learner.

        Args:
            cache: Query cache to analyze
            min_confidence: Minimum confidence score for pattern promotion
            min_samples: Minimum samples required to learn a pattern
        """
        self.cache = cache
        self.min_confidence = min_confidence
        self.min_samples = min_samples
        self._learned_rules: list[PatternRule] = []

    def extract_pattern(self, query: str) -> str | None:
        """Extract a generalized pattern from a specific query.

        Examples:
        - "find all functions with 'auth' in name" -> r"find all .* with '.*' in name"
        - "show methods that call foo" -> r"show .* that call .+"
        """
        # Strategy 1: Quote-based pattern extraction
        # Extract quoted strings and replace with wildcards
        quoted_pattern = r"(['\"])(.*?)\1"
        quoted_matches = list(re.finditer(quoted_pattern, query))
        if quoted_matches:
            pattern = query
            for match in reversed(quoted_matches):
                start, end = match.span()
                replacement = f"{match.group(1)}.*?{match.group(1)}"
                pattern = pattern[:start] + replacement + pattern[end:]
            return pattern

        # Strategy 2: Word-based generalization
        # Replace specific words with word-class wildcards
        words = query.split()
        generalized_words = []
        for word in words:
            # Keep structural words
            if word.lower() in {"find", "show", "all", "that", "with", "in", "where"}:
                generalized_words.append(word)
            # Replace specific terms with wildcards
            else:
                generalized_words.append(r"\w+")
        return " ".join(generalized_words)

    def calculate_confidence(
        self,
        tool_name: str,
        entries: list[CacheEntry],
    ) -> float:
        """Calculate confidence score for pattern promotion.

        Higher confidence when:
        - Same tool consistently handles similar queries
        - Multiple samples with similar structure
        - Low execution time (fast path is appropriate)
        """
        if not entries:
            return 0.0

        # Factor 1: Tool consistency (all use same tool)
        tool_consistency = sum(1 for e in entries if e.tool_used == tool_name) / len(entries)

        # Factor 2: Sample count (more samples = higher confidence)
        sample_factor = min(len(entries) / self.min_samples, 1.0)

        # Factor 3: Execution time (faster = better fast path candidate)
        avg_time = sum(e.execution_time_ms for e in entries) / len(entries)
        time_factor = max(0, 1 - (avg_time / 5000))  # 5s threshold

        return (tool_consistency * 0.5 + sample_factor * 0.3 + time_factor * 0.2)

    def learn_from_cache(self) -> list[PatternRule]:
        """Analyze cache and learn new patterns.

        Returns list of newly learned rules.
        """
        # Group cache entries by tool
        by_tool: dict[str, list[CacheEntry]] = {}
        for entry in self.cache._cache.values():
            if entry.tool_used not in by_tool:
                by_tool[entry.tool_used] = []
            by_tool[entry.tool_used].append(entry)

        new_rules = []

        for tool_name, entries in by_tool.items():
            if len(entries) < self.min_samples:
                continue

            # Analyze queries for this tool
            queries_by_pattern: dict[str, list[CacheEntry]] = {}

            for entry in entries:
                # Reconstruct query from cache key (we'd need to store this)
                # For now, use a simplified approach
                pattern = self.extract_pattern(str(entry.key.query_hash))
                if pattern is None:
                    continue
                if pattern not in queries_by_pattern:
                    queries_by_pattern[pattern] = []
                queries_by_pattern[pattern].append(entry)

            # Generate rules for high-confidence patterns
            for pattern, pattern_entries in queries_by_pattern.items():
                if len(pattern_entries) < self.min_samples:
                    continue

                confidence = self.calculate_confidence(tool_name, pattern_entries)
                if confidence >= self.min_confidence:
                    import time

                    rule = PatternRule(
                        pattern=pattern,
                        tool_name=tool_name,
                        confidence=confidence,
                        sample_queries=tuple(str(e.key.query_hash)[:16] for e in pattern_entries[:3]),
                        created_at=time.time(),
                    )
                    new_rules.append(rule)
                    self._learned_rules.append(rule)

        return new_rules

    def get_learned_rules(self) -> list[PatternRule]:
        """Get all learned pattern rules."""
        return self._learned_rules.copy()

    def classify_with_learned_rules(self, query: str) -> str | None:
        """Classify query using learned rules.

        Returns tool name if a rule matches, None otherwise.
        """
        for rule in self._learned_rules:
            try:
                if re.search(rule.pattern, query, re.IGNORECASE):
                    return rule.tool_name
            except re.error:
                # Invalid regex - skip this rule
                continue
        return None

    def save_rules(self, path: Path) -> None:
        """Save learned rules to file."""
        import json

        data = [rule.to_dict() for rule in self._learned_rules]
        path.write_text(json.dumps(data, indent=2))

    def load_rules(self, path: Path) -> None:
        """Load learned rules from file."""
        import json

        if not path.exists():
            return

        try:
            data = json.loads(path.read_text())
            self._learned_rules = [PatternRule.from_dict(d) for d in data]
        except (OSError, json.JSONDecodeError, KeyError):
            # Corrupt file - start fresh
            self._learned_rules.clear()


def update_classifier_with_learned_rules(
    rules: list[PatternRule],
    classifier_path: Path,
) -> None:
    """Update query classifier with learned rules.

    This would modify the classifier.py to include new patterns.
    For now, this is a placeholder for future integration.
    """
    # Future: Parse classifier.py and insert new rules
    # For now, rules can be stored separately and loaded at runtime
    pass
