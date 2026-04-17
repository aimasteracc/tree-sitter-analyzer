"""
LLM Integration Module

Handles semantic query understanding using LLMs (OpenAI, Anthropic, local).
Translates natural language queries into structured tool calls and ranks results.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    import anthropic  # type: ignore[import-not-found]
    import openai  # type: ignore[import-not-found]

# Set up logging
logger = setup_logger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    LLAMACPP = "llama-cpp"


@dataclass
class ToolCall:
    """Represents a tool call parsed from a query."""
    tool_name: str
    parameters: dict[str, Any]
    confidence: float
    reasoning: str | None = None


@dataclass
class LLMResult:
    """Result from LLM query processing."""
    tool_calls: list[ToolCall]
    raw_response: str
    provider_used: LLMProvider
    execution_time: float
    tokens_used: int = 0


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, model: str | None = None) -> None:
        """
        Initialize the LLM client.

        Args:
            model: Model name or identifier
        """
        self.model = model or self._default_model()
        self._available = self._check_available()

    @abstractmethod
    def _default_model(self) -> str:
        """Get the default model for this provider."""
        ...

    @abstractmethod
    def _check_available(self) -> bool:
        """Check if the LLM service is available."""
        ...

    @abstractmethod
    def parse_query(
        self,
        query: str,
        available_tools: list[str],
    ) -> LLMResult:
        """
        Parse a natural language query into tool calls.

        Args:
            query: User's natural language query
            available_tools: List of available tool names

        Returns:
            LLMResult with parsed tool calls
        """
        ...

    @abstractmethod
    def rank_results(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Rank search results by relevance to the query.

        Args:
            query: Original user query
            results: List of search results to rank

        Returns:
            Ranked list of results (highest relevance first)
        """
        ...

    def is_available(self) -> bool:
        """Check if this LLM client is available."""
        return self._available


class OpenAIClient(LLMClient):
    """OpenAI GPT-based LLM client."""

    def _default_model(self) -> str:
        return "gpt-4o-mini"

    def _check_available(self) -> bool:
        """Check if OpenAI API is available."""
        try:
            import openai
            return hasattr(openai, "OpenAI")
        except ImportError:
            return False

    def parse_query(
        self,
        query: str,
        available_tools: list[str],
    ) -> LLMResult:
        """
        Parse query using OpenAI GPT.

        Args:
            query: User's natural language query
            available_tools: List of available tool names

        Returns:
            LLMResult with parsed tool calls
        """
        import time

        if not self.is_available():
            return LLMResult(
                tool_calls=[],
                raw_response="OpenAI client not available",
                provider_used=LLMProvider.OPENAI,
                execution_time=0.0,
            )

        try:
            import openai
        except ImportError:
            return LLMResult(
                tool_calls=[],
                raw_response="OpenAI package not installed",
                provider_used=LLMProvider.OPENAI,
                execution_time=0.0,
            )

        start_time = time.time()

        try:
            client = openai.OpenAI()
            tools_list = "\n".join(f"- {tool}" for tool in available_tools)

            system_prompt = f"""You are a code search assistant. Given a user query,
identify which tools to call and extract parameters.

Available tools:
{tools_list}

Respond in JSON format:
{{
    "tool_calls": [
        {{
            "tool_name": "tool_name",
            "parameters": {{"param": "value"}},
            "confidence": 0.9,
            "reasoning": "explanation"
        }}
    ]
}}"""

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                response_format={"type": "json_object"},
            )

            raw_response = response.choices[0].message.content or "{}"
            execution_time = time.time() - start_time
            tokens_used = response.usage.total_tokens if response.usage else 0

            parsed = json.loads(raw_response)
            tool_calls = [
                ToolCall(
                    tool_name=tc["tool_name"],
                    parameters=tc["parameters"],
                    confidence=tc.get("confidence", 0.5),
                    reasoning=tc.get("reasoning"),
                )
                for tc in parsed.get("tool_calls", [])
            ]

            return LLMResult(
                tool_calls=tool_calls,
                raw_response=raw_response,
                provider_used=LLMProvider.OPENAI,
                execution_time=execution_time,
                tokens_used=tokens_used,
            )

        except Exception as e:
            logger.exception(f"OpenAI API error: {e}")
            return LLMResult(
                tool_calls=[],
                raw_response=f"Error: {e}",
                provider_used=LLMProvider.OPENAI,
                execution_time=time.time() - start_time,
            )

    def rank_results(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rank results by relevance using OpenAI."""
        # For now, return results as-is (re-ranking can be added later)
        return results


class AnthropicClient(LLMClient):
    """Anthropic Claude-based LLM client."""

    def _default_model(self) -> str:
        return "claude-3-5-haiku-20241022"

    def _check_available(self) -> bool:
        """Check if Anthropic API is available."""
        try:
            import anthropic
            return hasattr(anthropic, "Anthropic")
        except ImportError:
            return False

    def parse_query(
        self,
        query: str,
        available_tools: list[str],
    ) -> LLMResult:
        """
        Parse query using Anthropic Claude.

        Args:
            query: User's natural language query
            available_tools: List of available tool names

        Returns:
            LLMResult with parsed tool calls
        """
        import time

        if not self.is_available():
            return LLMResult(
                tool_calls=[],
                raw_response="Anthropic client not available",
                provider_used=LLMProvider.ANTHROPIC,
                execution_time=0.0,
            )

        try:
            import anthropic
        except ImportError:
            return LLMResult(
                tool_calls=[],
                raw_response="Anthropic package not installed",
                provider_used=LLMProvider.ANTHROPIC,
                execution_time=0.0,
            )

        start_time = time.time()

        try:
            client = anthropic.Anthropic()
            tools_list = "\n".join(f"- {tool}" for tool in available_tools)

            system_prompt = f"""You are a code search assistant. Given a user query,
identify which tools to call and extract parameters.

Available tools:
{tools_list}

Respond in JSON format:
{{
    "tool_calls": [
        {{
            "tool_name": "tool_name",
            "parameters": {{"param": "value"}},
            "confidence": 0.9,
            "reasoning": "explanation"
        }}
    ]
}}"""

            message = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": query},
                ],
            )

            raw_response = message.content[0].text
            execution_time = time.time() - start_time
            tokens_used = message.usage.input_tokens + message.usage.output_tokens

            # Extract JSON from response (Claude might wrap in markdown)
            import re

            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                raw_response = json_match.group(0)

            parsed = json.loads(raw_response)
            tool_calls = [
                ToolCall(
                    tool_name=tc["tool_name"],
                    parameters=tc["parameters"],
                    confidence=tc.get("confidence", 0.5),
                    reasoning=tc.get("reasoning"),
                )
                for tc in parsed.get("tool_calls", [])
            ]

            return LLMResult(
                tool_calls=tool_calls,
                raw_response=raw_response,
                provider_used=LLMProvider.ANTHROPIC,
                execution_time=execution_time,
                tokens_used=tokens_used,
            )

        except Exception as e:
            logger.exception(f"Anthropic API error: {e}")
            return LLMResult(
                tool_calls=[],
                raw_response=f"Error: {e}",
                provider_used=LLMProvider.ANTHROPIC,
                execution_time=time.time() - start_time,
            )

    def rank_results(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Rank results by relevance using Anthropic."""
        return results


class LLMIntegration:
    """
    Main LLM integration manager.

    Manages multiple LLM providers and provides fallback logic.
    """

    def __init__(
        self,
        preferred_provider: LLMProvider = LLMProvider.ANTHROPIC,
        model: str | None = None,
    ) -> None:
        """
        Initialize LLM integration.

        Args:
            preferred_provider: Preferred LLM provider
            model: Optional model override
        """
        self.preferred_provider = preferred_provider
        self._clients: dict[LLMProvider, LLMClient] = {}
        self._initialize_clients(model)

    def _initialize_clients(self, model: str | None) -> None:
        """Initialize available LLM clients."""
        self._clients[LLMProvider.OPENAI] = OpenAIClient(model)
        self._clients[LLMProvider.ANTHROPIC] = AnthropicClient(model)
        # Ollama and llama-cpp clients can be added here

    def get_available_providers(self) -> list[LLMProvider]:
        """Get list of available LLM providers."""
        return [
            provider
            for provider, client in self._clients.items()
            if client.is_available()
        ]

    def parse_query(
        self,
        query: str,
        available_tools: list[str],
        provider: LLMProvider | None = None,
    ) -> LLMResult:
        """
        Parse a query using LLM.

        Args:
            query: User's natural language query
            available_tools: List of available tool names
            provider: Optional provider override

        Returns:
            LLMResult with parsed tool calls
        """
        # Use specified provider or fall back to preferred
        target_provider = provider or self.preferred_provider

        # Try preferred provider first
        if target_provider in self._clients:
            client = self._clients[target_provider]
            if client.is_available():
                result = client.parse_query(query, available_tools)
                if result.tool_calls:
                    return result

        # Fallback to any available provider
        for provider, client in self._clients.items():
            if provider != target_provider and client.is_available():
                result = client.parse_query(query, available_tools)
                if result.tool_calls:
                    return result

        # No provider available or no tool calls returned
        return LLMResult(
            tool_calls=[],
            raw_response="No LLM provider available or query could not be parsed",
            provider_used=target_provider,
            execution_time=0.0,
        )

    def rank_results(
        self,
        query: str,
        results: list[dict[str, Any]],
        provider: LLMProvider | None = None,
    ) -> list[dict[str, Any]]:
        """
        Rank search results by relevance.

        Args:
            query: Original user query
            results: List of search results to rank
            provider: Optional provider override

        Returns:
            Ranked list of results
        """
        target_provider = provider or self.preferred_provider

        if target_provider in self._clients:
            client = self._clients[target_provider]
            if client.is_available():
                return client.rank_results(query, results)

        return results
