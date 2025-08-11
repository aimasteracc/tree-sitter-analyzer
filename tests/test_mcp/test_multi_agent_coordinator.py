#!/usr/bin/env python3
"""
Test suite for Multi-Agent Coordinator

This module contains comprehensive tests for the multi-agent coordination system,
including collaboration phases, agent responses, and content synthesis.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from tree_sitter_analyzer.mcp.agents.multi_agent_coordinator import (
    MultiAgentCoordinator,
    CollaborationPhase,
    AgentResponse,
    CollaborationResult
)
from tree_sitter_analyzer.mcp.agents.prompt_manager import (
    ProjectContext,
    LearningContext,
    LearningLevel,
    ContentType,
    AgentRole
)


class TestMultiAgentCoordinator:
    """Test suite for MultiAgentCoordinator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.coordinator = MultiAgentCoordinator()
        
        self.sample_project_context = ProjectContext(
            language="python",
            project_type="Web Application",
            complexity_score=6.5,
            domain="web_development",
            architecture_patterns=["MVC", "RESTful API"],
            key_concepts=["Flask", "Database", "Authentication"],
            prerequisites=["Python Basics", "Web Fundamentals"]
        )
        
        self.sample_learning_context = LearningContext(
            target_level=LearningLevel.INTERMEDIATE,
            content_type=ContentType.TUTORIAL,
            learning_objectives=[
                "Understand web application architecture",
                "Learn Flask framework basics",
                "Implement user authentication"
            ]
        )

    def test_coordinator_initialization(self):
        """Test coordinator initialization."""
        coordinator = MultiAgentCoordinator()
        
        assert hasattr(coordinator, 'prompt_manager')
        assert hasattr(coordinator, 'collaboration_history')
        assert isinstance(coordinator.collaboration_history, list)

    def test_agent_response_creation(self):
        """Test AgentResponse dataclass creation."""
        response = AgentResponse(
            agent_role="educator",
            phase="analysis",
            content="Test content",
            confidence=0.85,
            recommendations=["Rec 1", "Rec 2"],
            concerns=["Concern 1"],
            metadata={"test": "data"}
        )
        
        assert response.agent_role == "educator"
        assert response.confidence == 0.85
        assert len(response.recommendations) == 2
        assert len(response.concerns) == 1

    def test_collaboration_result_creation(self):
        """Test CollaborationResult dataclass creation."""
        agent_responses = {
            "educator": AgentResponse("educator", "analysis", "content", 0.9, [], [], {})
        }
        
        result = CollaborationResult(
            project_context=self.sample_project_context,
            learning_context=self.sample_learning_context,
            agent_responses=agent_responses,
            synthesized_content="Synthesized content",
            quality_score=0.85,
            recommendations=["Recommendation"],
            next_steps=["Next step"]
        )
        
        assert result.quality_score == 0.85
        assert len(result.recommendations) == 1
        assert len(result.next_steps) == 1

    @pytest.mark.asyncio
    async def test_educational_content_generation(self):
        """Test complete educational content generation workflow."""
        result = await self.coordinator.generate_educational_content(
            self.sample_project_context,
            self.sample_learning_context
        )
        
        assert isinstance(result, CollaborationResult)
        assert result.project_context == self.sample_project_context
        assert result.learning_context == self.sample_learning_context
        assert len(result.agent_responses) == 4  # All agent roles
        assert 0 <= result.quality_score <= 1
        assert isinstance(result.synthesized_content, str)
        assert isinstance(result.recommendations, list)
        assert isinstance(result.next_steps, list)

    @pytest.mark.asyncio
    async def test_analysis_phase(self):
        """Test analysis phase execution."""
        analysis_results = await self.coordinator._run_analysis_phase(
            self.sample_project_context,
            self.sample_learning_context
        )
        
        assert len(analysis_results) == 4  # All agent roles
        
        for role_name, response in analysis_results.items():
            assert isinstance(response, AgentResponse)
            assert response.agent_role == role_name
            assert response.phase == CollaborationPhase.ANALYSIS.value
            assert isinstance(response.content, str)
            assert 0 <= response.confidence <= 1
            assert isinstance(response.recommendations, list)
            assert isinstance(response.concerns, list)

    @pytest.mark.asyncio
    async def test_planning_phase(self):
        """Test planning phase execution."""
        # First run analysis phase
        analysis_results = await self.coordinator._run_analysis_phase(
            self.sample_project_context,
            self.sample_learning_context
        )
        
        # Then run planning phase
        planning_results = await self.coordinator._run_planning_phase(
            self.sample_project_context,
            self.sample_learning_context,
            analysis_results
        )
        
        assert len(planning_results) == 4  # All agent roles
        
        for role_name, response in planning_results.items():
            assert response.phase == CollaborationPhase.PLANNING.value
            assert len(response.content) > 0

    @pytest.mark.asyncio
    async def test_content_generation_phase(self):
        """Test content generation phase execution."""
        # Setup previous phases
        analysis_results = await self.coordinator._run_analysis_phase(
            self.sample_project_context,
            self.sample_learning_context
        )
        
        planning_results = await self.coordinator._run_planning_phase(
            self.sample_project_context,
            self.sample_learning_context,
            analysis_results
        )
        
        # Run content generation phase
        content_requirements = {
            "include_exercises": True,
            "include_assessments": True,
            "output_format": "structured"
        }
        
        content_results = await self.coordinator._run_content_generation_phase(
            self.sample_project_context,
            self.sample_learning_context,
            planning_results,
            content_requirements
        )
        
        assert len(content_results) == 4  # All agent roles
        
        for role_name, response in content_results.items():
            assert response.phase == CollaborationPhase.CONTENT_GENERATION.value
            assert len(response.content) > 0

    @pytest.mark.asyncio
    async def test_review_phase(self):
        """Test review and refinement phase execution."""
        # Setup previous phases
        analysis_results = await self.coordinator._run_analysis_phase(
            self.sample_project_context,
            self.sample_learning_context
        )
        
        planning_results = await self.coordinator._run_planning_phase(
            self.sample_project_context,
            self.sample_learning_context,
            analysis_results
        )
        
        content_results = await self.coordinator._run_content_generation_phase(
            self.sample_project_context,
            self.sample_learning_context,
            planning_results,
            {}
        )
        
        # Run review phase
        review_results = await self.coordinator._run_review_phase(
            self.sample_project_context,
            self.sample_learning_context,
            content_results
        )
        
        assert len(review_results) == 4  # All agent roles
        
        for role_name, response in review_results.items():
            assert response.phase == CollaborationPhase.REVIEW.value
            assert len(response.content) > 0

    def test_synthesis_methods(self):
        """Test content synthesis methods."""
        sample_responses = {
            "educator": AgentResponse(
                "educator", "analysis", "Educational analysis content", 0.9,
                ["Use scaffolding", "Provide examples"], ["Cognitive overload"], {}
            ),
            "tech_expert": AgentResponse(
                "tech_expert", "analysis", "Technical analysis content", 0.85,
                ["Follow best practices", "Include error handling"], ["Code complexity"], {}
            )
        }
        
        # Test analysis synthesis
        synthesis = self.coordinator._synthesize_analysis_results(sample_responses)
        assert isinstance(synthesis, str)
        assert "EDUCATOR" in synthesis
        assert "TECH_EXPERT" in synthesis
        assert "scaffolding" in synthesis.lower()
        
        # Test content synthesis
        content = self.coordinator._synthesize_content(sample_responses)
        assert isinstance(content, str)
        assert "Educational" in content
        assert "Technical" in content

    def test_quality_score_calculation(self):
        """Test quality score calculation."""
        sample_responses = {
            "educator": AgentResponse("educator", "review", "content", 0.9, [], [], {}),
            "tech_expert": AgentResponse("tech_expert", "review", "content", 0.8, [], [], {}),
            "content_organizer": AgentResponse("content_organizer", "review", "content", 0.85, [], [], {}),
            "course_designer": AgentResponse("course_designer", "review", "content", 0.95, [], [], {})
        }
        
        quality_score = self.coordinator._calculate_quality_score(sample_responses)
        
        expected_score = (0.9 + 0.8 + 0.85 + 0.95) / 4
        assert abs(quality_score - expected_score) < 0.01

    def test_recommendations_extraction(self):
        """Test recommendations extraction from agent responses."""
        sample_responses = {
            "educator": AgentResponse("educator", "review", "content", 0.9, 
                                    ["Use active learning", "Provide feedback"], [], {}),
            "tech_expert": AgentResponse("tech_expert", "review", "content", 0.8,
                                       ["Follow coding standards", "Use active learning"], [], {})
        }
        
        recommendations = self.coordinator._extract_recommendations(sample_responses)
        
        assert isinstance(recommendations, list)
        assert "Use active learning" in recommendations
        assert "Provide feedback" in recommendations
        assert "Follow coding standards" in recommendations
        # Should remove duplicates
        assert recommendations.count("Use active learning") == 1

    def test_next_steps_generation(self):
        """Test next steps generation."""
        sample_responses = {
            "educator": AgentResponse("educator", "review", "content", 0.9, [], [], {}),
            "tech_expert": AgentResponse("tech_expert", "review", "content", 0.8, [], [], {})
        }
        
        next_steps = self.coordinator._generate_next_steps(sample_responses)
        
        assert isinstance(next_steps, list)
        assert len(next_steps) > 0
        assert any("review" in step.lower() for step in next_steps)

    @pytest.mark.asyncio
    async def test_agent_response_simulation(self):
        """Test agent response simulation."""
        response = await self.coordinator._simulate_agent_response(
            "educator",
            CollaborationPhase.ANALYSIS,
            "Test prompt",
            self.sample_project_context,
            self.sample_learning_context
        )
        
        assert isinstance(response, AgentResponse)
        assert response.agent_role == "educator"
        assert response.phase == CollaborationPhase.ANALYSIS.value
        assert isinstance(response.content, str)
        assert len(response.content) > 0
        assert 0 <= response.confidence <= 1
        assert isinstance(response.recommendations, list)
        assert isinstance(response.concerns, list)
        assert isinstance(response.metadata, dict)

    @pytest.mark.asyncio
    async def test_different_agent_role_responses(self):
        """Test that different agent roles produce different responses."""
        responses = {}
        
        for role in ["educator", "tech_expert", "content_organizer", "course_designer"]:
            response = await self.coordinator._simulate_agent_response(
                role,
                CollaborationPhase.ANALYSIS,
                "Test prompt",
                self.sample_project_context,
                self.sample_learning_context
            )
            responses[role] = response
        
        # Each role should have different content
        contents = [response.content for response in responses.values()]
        assert len(set(contents)) == 4  # All different
        
        # Check role-specific keywords
        assert "educational" in responses["educator"].content.lower()
        assert "technical" in responses["tech_expert"].content.lower()
        assert "content" in responses["content_organizer"].content.lower()
        assert "course" in responses["course_designer"].content.lower()

    @pytest.mark.asyncio
    async def test_collaboration_history_tracking(self):
        """Test collaboration history tracking."""
        initial_history_length = len(self.coordinator.collaboration_history)
        
        await self.coordinator.generate_educational_content(
            self.sample_project_context,
            self.sample_learning_context
        )
        
        assert len(self.coordinator.collaboration_history) == initial_history_length + 1
        
        latest_result = self.coordinator.collaboration_history[-1]
        assert isinstance(latest_result, CollaborationResult)

    @pytest.mark.asyncio
    async def test_content_requirements_integration(self):
        """Test integration of content requirements."""
        content_requirements = {
            "include_exercises": True,
            "include_assessments": False,
            "output_format": "markdown",
            "custom_requirement": "accessibility focus"
        }
        
        result = await self.coordinator.generate_educational_content(
            self.sample_project_context,
            self.sample_learning_context,
            content_requirements
        )
        
        # Requirements should be reflected in the result
        assert isinstance(result, CollaborationResult)
        # The specific integration would depend on implementation details

    @pytest.mark.asyncio
    async def test_error_handling_in_collaboration(self):
        """Test error handling during collaboration."""
        # Test with invalid project context
        invalid_context = Mock()
        invalid_context.language = None
        
        with pytest.raises(Exception):
            await self.coordinator.generate_educational_content(
                invalid_context,
                self.sample_learning_context
            )

    def test_collaboration_phases_enum(self):
        """Test CollaborationPhase enum."""
        phases = list(CollaborationPhase)
        
        expected_phases = ["ANALYSIS", "PLANNING", "CONTENT_GENERATION", "REVIEW", "REFINEMENT", "FINALIZATION"]
        
        for expected in expected_phases:
            assert any(phase.name == expected for phase in phases)

    @pytest.mark.asyncio
    async def test_concurrent_collaboration(self):
        """Test concurrent collaboration sessions."""
        import asyncio
        
        # Run multiple collaboration sessions concurrently
        tasks = []
        for i in range(3):
            task = self.coordinator.generate_educational_content(
                self.sample_project_context,
                self.sample_learning_context
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        for result in results:
            assert isinstance(result, CollaborationResult)
            assert result.quality_score > 0

    def test_empty_responses_handling(self):
        """Test handling of empty agent responses."""
        empty_responses = {}
        
        quality_score = self.coordinator._calculate_quality_score(empty_responses)
        assert quality_score == 0.0
        
        recommendations = self.coordinator._extract_recommendations(empty_responses)
        assert recommendations == []


if __name__ == "__main__":
    pytest.main([__file__])
