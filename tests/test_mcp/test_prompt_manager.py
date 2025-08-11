#!/usr/bin/env python3
"""
Test suite for Dynamic Prompt Manager

This module contains comprehensive tests for the dynamic prompt management system,
including context-aware prompt generation and multi-agent collaboration.
"""

import pytest
from unittest.mock import Mock, patch

from tree_sitter_analyzer.mcp.agents.prompt_manager import (
    DynamicPromptManager,
    ProjectContext,
    LearningContext,
    LearningLevel,
    ContentType,
    AgentRole
)


class TestDynamicPromptManager:
    """Test suite for DynamicPromptManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DynamicPromptManager()
        
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

    def test_manager_initialization(self):
        """Test prompt manager initialization."""
        manager = DynamicPromptManager()
        
        assert hasattr(manager, 'base_templates')
        assert hasattr(manager, 'context_modifiers')
        assert hasattr(manager, 'role_specifications')
        
        # Check that all agent roles have templates
        for role in AgentRole:
            assert role.value in manager.base_templates

    def test_project_context_creation(self):
        """Test ProjectContext creation and validation."""
        context = ProjectContext(
            language="java",
            project_type="Enterprise Application",
            complexity_score=8.2,
            domain="enterprise",
            architecture_patterns=["Microservices", "Event-Driven"],
            key_concepts=["Spring Boot", "Kafka", "Docker"],
            prerequisites=["Java", "Spring Framework"]
        )
        
        assert context.language == "java"
        assert context.complexity_score == 8.2
        assert "Microservices" in context.architecture_patterns
        assert "Spring Boot" in context.key_concepts

    def test_learning_context_creation(self):
        """Test LearningContext creation and validation."""
        context = LearningContext(
            target_level=LearningLevel.ADVANCED,
            content_type=ContentType.PROJECT,
            learning_objectives=["Build microservices", "Implement CI/CD"]
        )
        
        assert context.target_level == LearningLevel.ADVANCED
        assert context.content_type == ContentType.PROJECT
        assert len(context.learning_objectives) == 2

    def test_prompt_generation_for_all_roles(self):
        """Test prompt generation for all agent roles."""
        for role in AgentRole:
            prompt = self.manager.generate_prompt(
                role, self.sample_project_context, self.sample_learning_context
            )
            
            assert isinstance(prompt, str)
            assert len(prompt) > 100  # Should be substantial
            assert self.sample_project_context.language in prompt.lower()
            
            # Check role-specific content
            if role == AgentRole.EDUCATOR:
                assert "educational" in prompt.lower() or "pedagogy" in prompt.lower()
            elif role == AgentRole.TECH_EXPERT:
                assert "technical" in prompt.lower() or "accuracy" in prompt.lower()
            elif role == AgentRole.CONTENT_ORGANIZER:
                assert "content" in prompt.lower() or "structure" in prompt.lower()
            elif role == AgentRole.COURSE_DESIGNER:
                assert "course" in prompt.lower() or "design" in prompt.lower()

    def test_context_modifiers_application(self):
        """Test context-specific modifications."""
        # Test with different complexity levels
        high_complexity_context = ProjectContext(
            language="rust",
            project_type="System Programming",
            complexity_score=9.5,
            domain="systems",
            architecture_patterns=["Zero-Copy", "Lock-Free"],
            key_concepts=["Memory Management", "Concurrency"],
            prerequisites=["Systems Programming", "Computer Architecture"]
        )
        
        prompt = self.manager.generate_prompt(
            AgentRole.TECH_EXPERT, high_complexity_context, self.sample_learning_context
        )
        
        assert "complex" in prompt.lower() or "advanced" in prompt.lower()
        assert "rust" in prompt.lower()

    def test_learning_level_adaptation(self):
        """Test prompt adaptation for different learning levels."""
        for level in LearningLevel:
            learning_context = LearningContext(
                target_level=level,
                content_type=ContentType.TUTORIAL,
                learning_objectives=["Learn the basics"]
            )
            
            prompt = self.manager.generate_prompt(
                AgentRole.EDUCATOR, self.sample_project_context, learning_context
            )
            
            if level == LearningLevel.BEGINNER:
                assert "basic" in prompt.lower() or "fundamental" in prompt.lower()
            elif level == LearningLevel.EXPERT:
                assert "advanced" in prompt.lower() or "sophisticated" in prompt.lower()

    def test_content_type_adaptation(self):
        """Test prompt adaptation for different content types."""
        for content_type in ContentType:
            learning_context = LearningContext(
                target_level=LearningLevel.INTERMEDIATE,
                content_type=content_type,
                learning_objectives=["Learn effectively"]
            )
            
            prompt = self.manager.generate_prompt(
                AgentRole.CONTENT_ORGANIZER, self.sample_project_context, learning_context
            )
            
            if content_type == ContentType.TUTORIAL:
                assert "step-by-step" in prompt.lower() or "tutorial" in prompt.lower()
            elif content_type == ContentType.EXERCISE:
                assert "hands-on" in prompt.lower() or "exercise" in prompt.lower()
            elif content_type == ContentType.PROJECT:
                assert "comprehensive" in prompt.lower() or "project" in prompt.lower()

    def test_domain_specific_modifications(self):
        """Test domain-specific prompt modifications."""
        domains = ["web_development", "data_science", "mobile_development", "general"]
        
        for domain in domains:
            domain_context = ProjectContext(
                language="python",
                project_type="Application",
                complexity_score=5.0,
                domain=domain,
                architecture_patterns=["Standard"],
                key_concepts=["Core Concepts"],
                prerequisites=["Basics"]
            )
            
            prompt = self.manager.generate_prompt(
                AgentRole.TECH_EXPERT, domain_context, self.sample_learning_context
            )
            
            if domain == "web_development":
                assert "web" in prompt.lower() or "user experience" in prompt.lower()
            elif domain == "data_science":
                assert "data" in prompt.lower() or "statistical" in prompt.lower()

    def test_collaborative_prompt_generation(self):
        """Test collaborative prompt generation for all agents."""
        prompts = self.manager.generate_collaborative_prompt(
            self.sample_project_context,
            self.sample_learning_context,
            "initial"
        )
        
        assert len(prompts) == len(AgentRole)
        
        for role in AgentRole:
            assert role.value in prompts
            assert isinstance(prompts[role.value], str)
            assert len(prompts[role.value]) > 100

    def test_collaboration_phases(self):
        """Test different collaboration phases."""
        phases = ["initial", "synthesis", "refinement", "finalization"]
        
        for phase in phases:
            prompts = self.manager.generate_collaborative_prompt(
                self.sample_project_context,
                self.sample_learning_context,
                phase
            )
            
            # All prompts should contain phase-specific instructions
            for prompt in prompts.values():
                assert phase in prompt.lower() or "collaboration" in prompt.lower()

    def test_additional_context_integration(self):
        """Test integration of additional context."""
        additional_context = {
            "deadline": "2 weeks",
            "target_platform": "web",
            "special_requirements": "accessibility compliance"
        }
        
        prompt = self.manager.generate_prompt(
            AgentRole.COURSE_DESIGNER,
            self.sample_project_context,
            self.sample_learning_context,
            additional_context
        )
        
        assert "deadline" in prompt.lower()
        assert "web" in prompt.lower()
        assert "accessibility" in prompt.lower()

    def test_fallback_prompt_generation(self):
        """Test fallback prompt generation on errors."""
        # Mock an error in prompt generation
        with patch.object(self.manager, '_apply_context_modifiers', side_effect=Exception("Test error")):
            prompt = self.manager.generate_prompt(
                AgentRole.EDUCATOR,
                self.sample_project_context,
                self.sample_learning_context
            )
            
            # Should return fallback prompt
            assert isinstance(prompt, str)
            assert "educator" in prompt.lower()

    def test_role_specifications_loading(self):
        """Test role specifications loading and structure."""
        specs = self.manager._load_role_specifications()
        
        for role in AgentRole:
            assert role.value in specs
            role_spec = specs[role.value]
            
            assert "focus_areas" in role_spec
            assert "constraints" in role_spec
            assert "output_format" in role_spec
            assert isinstance(role_spec["focus_areas"], list)
            assert isinstance(role_spec["constraints"], list)

    def test_context_modifiers_loading(self):
        """Test context modifiers loading and structure."""
        modifiers = self.manager._load_context_modifiers()
        
        expected_categories = ["complexity_level", "learning_level", "content_type", "domain"]
        
        for category in expected_categories:
            assert category in modifiers
            assert isinstance(modifiers[category], dict)

    def test_base_templates_loading(self):
        """Test base templates loading and completeness."""
        templates = self.manager._load_base_templates()
        
        for role in AgentRole:
            assert role.value in templates
            template = templates[role.value]
            
            assert isinstance(template, str)
            assert len(template) > 50  # Should be substantial
            assert "RESPONSIBILITIES" in template or "role" in template.lower()

    def test_prompt_consistency(self):
        """Test prompt generation consistency."""
        # Generate same prompt multiple times
        prompts = []
        for _ in range(3):
            prompt = self.manager.generate_prompt(
                AgentRole.EDUCATOR,
                self.sample_project_context,
                self.sample_learning_context
            )
            prompts.append(prompt)
        
        # All prompts should be identical (deterministic)
        assert all(prompt == prompts[0] for prompt in prompts)

    def test_prompt_length_validation(self):
        """Test that generated prompts have appropriate length."""
        for role in AgentRole:
            prompt = self.manager.generate_prompt(
                role, self.sample_project_context, self.sample_learning_context
            )
            
            # Prompts should be substantial but not excessive
            assert 500 <= len(prompt) <= 5000

    def test_learning_objectives_integration(self):
        """Test integration of learning objectives into prompts."""
        specific_objectives = [
            "Master advanced Python decorators",
            "Implement design patterns effectively",
            "Optimize code for performance"
        ]
        
        learning_context = LearningContext(
            target_level=LearningLevel.ADVANCED,
            content_type=ContentType.TUTORIAL,
            learning_objectives=specific_objectives
        )
        
        prompt = self.manager.generate_prompt(
            AgentRole.EDUCATOR, self.sample_project_context, learning_context
        )
        
        for objective in specific_objectives:
            # At least part of each objective should appear in the prompt
            assert any(word in prompt.lower() for word in objective.lower().split())

    def test_error_handling_in_prompt_generation(self):
        """Test error handling in various prompt generation scenarios."""
        # Test with None contexts
        with pytest.raises(AttributeError):
            self.manager.generate_prompt(AgentRole.EDUCATOR, None, self.sample_learning_context)
        
        # Test with invalid role
        with pytest.raises(KeyError):
            invalid_role = Mock()
            invalid_role.value = "invalid_role"
            self.manager.generate_prompt(invalid_role, self.sample_project_context, self.sample_learning_context)


if __name__ == "__main__":
    pytest.main([__file__])
