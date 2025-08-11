#!/usr/bin/env python3
"""
Multi-Agent System for Educational Content Generation

This package contains the multi-agent coordination system that enables
collaborative educational content generation using specialized AI agents.
"""

from .prompt_manager import (
    DynamicPromptManager,
    ProjectContext,
    LearningContext,
    LearningLevel,
    ContentType,
    AgentRole,
    prompt_manager
)

from .multi_agent_coordinator import (
    MultiAgentCoordinator,
    CollaborationPhase,
    AgentResponse,
    CollaborationResult,
    multi_agent_coordinator
)

__version__ = "1.0.0"

__all__ = [
    # Prompt Management
    "DynamicPromptManager",
    "ProjectContext", 
    "LearningContext",
    "LearningLevel",
    "ContentType",
    "AgentRole",
    "prompt_manager",
    
    # Multi-Agent Coordination
    "MultiAgentCoordinator",
    "CollaborationPhase",
    "AgentResponse", 
    "CollaborationResult",
    "multi_agent_coordinator",
]

# Package metadata
AGENTS_INFO = {
    "name": "tree-sitter-analyzer-agents",
    "version": __version__,
    "description": "Multi-agent system for educational content generation",
    "capabilities": {
        "prompt_management": {
            "dynamic_generation": True,
            "context_awareness": True,
            "role_specialization": True,
            "collaboration_support": True
        },
        "multi_agent_coordination": {
            "specialist_agents": ["educator", "tech_expert", "content_organizer", "course_designer"],
            "collaboration_phases": ["analysis", "planning", "content_generation", "review", "refinement"],
            "quality_assurance": True,
            "adaptive_strategies": True
        }
    }
}
