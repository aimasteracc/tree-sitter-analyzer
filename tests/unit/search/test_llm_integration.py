"""
Unit tests for LLM Integration.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.search.llm_integration import (
    AnthropicClient,
    LLMClient,
    LLMIntegration,
    LLMProvider,
    LLMResult,
    OpenAIClient,
    ToolCall,
)


class TestToolCall:
    """Test ToolCall dataclass."""

    def test_init(self) -> None:
        """Test ToolCall initialization."""
        tool_call = ToolCall(
            tool_name="test_tool",
            parameters={"param1": "value1"},
            confidence=0.9,
            reasoning="Test reasoning",
        )

        assert tool_call.tool_name == "test_tool"
        assert tool_call.parameters == {"param1": "value1"}
        assert tool_call.confidence == 0.9
        assert tool_call.reasoning == "Test reasoning"


class TestLLMResult:
    """Test LLMResult dataclass."""

    def test_init(self) -> None:
        """Test LLMResult initialization."""
        result = LLMResult(
            tool_calls=[
                ToolCall(
                    tool_name="test_tool",
                    parameters={},
                    confidence=0.8,
                )
            ],
            raw_response="Test response",
            provider_used=LLMProvider.OPENAI,
            execution_time=1.5,
            tokens_used=100,
        )

        assert len(result.tool_calls) == 1
        assert result.raw_response == "Test response"
        assert result.provider_used == LLMProvider.OPENAI
        assert result.execution_time == 1.5
        assert result.tokens_used == 100


class TestLLMProvider:
    """Test LLMProvider enum."""

    def test_values(self) -> None:
        """Test enum values."""
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.ANTHROPIC.value == "anthropic"
        assert LLMProvider.OLLAMA.value == "ollama"
        assert LLMProvider.LLAMACPP.value == "llama-cpp"


class TestOpenAIClient:
    """Test OpenAIClient class."""

    @pytest.fixture
    def client(self) -> OpenAIClient:
        """Get OpenAIClient instance."""
        return OpenAIClient()

    def test_init(self, client: OpenAIClient) -> None:
        """Test OpenAIClient initialization."""
        assert client.model == "gpt-4o-mini"
        assert isinstance(client.is_available(), bool)

    def test_default_model(self) -> None:
        """Test default model."""
        client = OpenAIClient(model="gpt-4")
        assert client.model == "gpt-4"

    def test_parse_query_not_available(self, client: OpenAIClient) -> None:
        """Test parse_query when OpenAI is not available."""
        with patch.object(client, "is_available", return_value=False):
            result = client.parse_query("test query", ["tool1", "tool2"])

            assert result.tool_calls == []
            assert "not available" in result.raw_response
            assert result.provider_used == LLMProvider.OPENAI

    def test_rank_results(self, client: OpenAIClient) -> None:
        """Test rank_results returns results as-is."""
        results = [
            {"file": "test.py", "line": 10},
            {"file": "main.py", "line": 5},
        ]

        ranked = client.rank_results("test query", results)

        assert ranked == results


class TestAnthropicClient:
    """Test AnthropicClient class."""

    @pytest.fixture
    def client(self) -> AnthropicClient:
        """Get AnthropicClient instance."""
        return AnthropicClient()

    def test_init(self, client: AnthropicClient) -> None:
        """Test AnthropicClient initialization."""
        assert client.model == "claude-3-5-haiku-20241022"
        assert isinstance(client.is_available(), bool)

    def test_default_model(self) -> None:
        """Test default model override."""
        client = AnthropicClient(model="claude-3-opus-20240229")
        assert client.model == "claude-3-opus-20240229"

    def test_parse_query_not_available(self, client: AnthropicClient) -> None:
        """Test parse_query when Anthropic is not available."""
        with patch.object(client, "is_available", return_value=False):
            result = client.parse_query("test query", ["tool1", "tool2"])

            assert result.tool_calls == []
            assert "not available" in result.raw_response
            assert result.provider_used == LLMProvider.ANTHROPIC

    def test_rank_results(self, client: AnthropicClient) -> None:
        """Test rank_results returns results as-is."""
        results = [
            {"file": "test.py", "line": 10},
            {"file": "main.py", "line": 5},
        ]

        ranked = client.rank_results("test query", results)

        assert ranked == results


class TestLLMIntegration:
    """Test LLMIntegration class."""

    @pytest.fixture
    def integration(self) -> LLMIntegration:
        """Get LLMIntegration instance."""
        return LLMIntegration()

    def test_init(self, integration: LLMIntegration) -> None:
        """Test LLMIntegration initialization."""
        assert integration.preferred_provider == LLMProvider.ANTHROPIC
        assert len(integration._clients) == 2  # OPENAI and ANTHROPIC

    def test_init_with_provider(self) -> None:
        """Test initialization with preferred provider."""
        integration = LLMIntegration(
            preferred_provider=LLMProvider.OPENAI
        )

        assert integration.preferred_provider == LLMProvider.OPENAI

    def test_get_available_providers(self, integration: LLMIntegration) -> None:
        """Test getting available providers."""
        providers = integration.get_available_providers()

        assert isinstance(providers, list)
        # All providers in the list should be LLMProvider enum values
        for provider in providers:
            assert isinstance(provider, LLMProvider)

    def test_parse_query_fallback(self, integration: LLMIntegration) -> None:
        """Test parse_query falls back to available provider."""
        # Mock all clients as unavailable
        for client in integration._clients.values():
            client._available = False

        result = integration.parse_query("test query", ["tool1"])

        assert result.tool_calls == []
        assert "No LLM provider available" in result.raw_response

    def test_rank_results(self, integration: LLMIntegration) -> None:
        """Test rank_results."""
        results = [
            {"file": "test.py", "line": 10},
        ]

        ranked = integration.rank_results("test query", results)

        assert ranked == results


class TestLLMClientAbstract:
    """Test LLMClient abstract base class."""

    def test_cannot_instantiate(self) -> None:
        """Test that LLMClient cannot be instantiated directly."""
        with pytest.raises(TypeError):
            LLMClient()  # type: ignore


class TestLLMIntegrationWithMock:
    """Test LLMIntegration with mocked clients."""

    def test_parse_query_uses_preferred_provider(self) -> None:
        """Test that preferred provider is used first."""
        integration = LLMIntegration(
            preferred_provider=LLMProvider.ANTHROPIC
        )

        # Mock preferred provider as unavailable
        anthropic_client = integration._clients[LLMProvider.ANTHROPIC]
        anthropic_client._available = False

        # Mock fallback provider
        openai_client = integration._clients[LLMProvider.OPENAI]
        openai_client._available = True

        with patch.object(
            openai_client,
            "parse_query",
            return_value=LLMResult(
                tool_calls=[
                    ToolCall(
                        tool_name="test_tool",
                        parameters={},
                        confidence=0.8,
                    )
                ],
                raw_response="success",
                provider_used=LLMProvider.OPENAI,
                execution_time=0.5,
            ),
        ):
            result = integration.parse_query("test query", ["tool1"])

            assert len(result.tool_calls) == 1
            assert result.tool_calls[0].tool_name == "test_tool"
            assert result.provider_used == LLMProvider.OPENAI
