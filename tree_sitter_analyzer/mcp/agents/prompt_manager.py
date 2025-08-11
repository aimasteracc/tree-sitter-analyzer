#!/usr/bin/env python3
"""
Dynamic Prompt Management System for Educational Content Generation

This system generates context-aware, role-specific prompts for different AI agents
based on project characteristics, learning objectives, and target audience.
"""

import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from ...utils import setup_logger

logger = setup_logger(__name__)


class LearningLevel(Enum):
    """Learning levels for content generation."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ContentType(Enum):
    """Types of educational content."""
    OVERVIEW = "overview"
    TUTORIAL = "tutorial"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    PROJECT = "project"
    REFERENCE = "reference"


class AgentRole(Enum):
    """AI agent roles in the educational content generation system."""
    EDUCATOR = "educator"
    TECH_EXPERT = "tech_expert"
    CONTENT_ORGANIZER = "content_organizer"
    COURSE_DESIGNER = "course_designer"


@dataclass
class ProjectContext:
    """Context information about the project being analyzed."""
    language: str
    project_type: str
    complexity_score: float
    domain: str
    architecture_patterns: List[str]
    key_concepts: List[str]
    prerequisites: List[str]


@dataclass
class LearningContext:
    """Context information about the learning scenario."""
    target_level: LearningLevel
    content_type: ContentType
    learning_objectives: List[str]
    time_constraint: Optional[str] = None
    prior_knowledge: List[str] = None


class DynamicPromptManager:
    """
    Manages dynamic prompt generation for different AI agents and contexts.
    
    This system creates context-aware prompts that adapt to:
    - Project characteristics (language, complexity, domain)
    - Learning objectives and target audience
    - AI agent roles and responsibilities
    - Current learning phase and progress
    """

    def __init__(self):
        """Initialize the prompt manager with base templates."""
        self.base_templates = self._load_base_templates()
        self.context_modifiers = self._load_context_modifiers()
        self.role_specifications = self._load_role_specifications()
        logger.info("DynamicPromptManager initialized")

    def generate_prompt(
        self,
        agent_role: AgentRole,
        project_context: ProjectContext,
        learning_context: LearningContext,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a dynamic prompt for a specific agent and context.
        
        Args:
            agent_role: The role of the AI agent
            project_context: Information about the project
            learning_context: Information about the learning scenario
            additional_context: Any additional context information
            
        Returns:
            Generated prompt string
        """
        try:
            # Get base template for the agent role
            base_template = self.base_templates[agent_role.value]
            
            # Apply context-specific modifications
            context_prompt = self._apply_context_modifiers(
                base_template, project_context, learning_context
            )
            
            # Add role-specific instructions
            role_prompt = self._add_role_specifications(
                context_prompt, agent_role, project_context, learning_context
            )
            
            # Apply final customizations
            final_prompt = self._apply_final_customizations(
                role_prompt, additional_context or {}
            )
            
            logger.debug(f"Generated prompt for {agent_role.value}")
            return final_prompt
            
        except Exception as e:
            logger.error(f"Error generating prompt for {agent_role.value}: {e}")
            return self._get_fallback_prompt(agent_role)

    def _load_base_templates(self) -> Dict[str, str]:
        """Load base prompt templates for different agent roles."""
        return {
            "educator": """
You are an expert educational specialist with deep knowledge of learning theory and pedagogy.
Your role is to ensure that educational content follows sound pedagogical principles and is
optimized for effective learning.

CORE RESPONSIBILITIES:
- Apply learning theories (constructivism, scaffolding, active learning)
- Ensure appropriate cognitive load management
- Design effective learning progressions
- Recommend suitable assessment strategies
- Optimize content for knowledge retention

EDUCATIONAL PRINCIPLES TO FOLLOW:
- Start with prior knowledge and build incrementally
- Use multiple representation formats (visual, textual, practical)
- Provide immediate feedback and reinforcement
- Include active learning opportunities
- Consider different learning styles and preferences
""",
            
            "tech_expert": """
You are a senior technical expert with extensive experience in software development,
architecture, and best practices. Your role is to ensure technical accuracy and
provide authoritative guidance on implementation details.

CORE RESPONSIBILITIES:
- Verify technical accuracy of all content
- Identify and explain best practices
- Highlight common pitfalls and anti-patterns
- Provide context for technical decisions
- Ensure code examples are production-quality

TECHNICAL STANDARDS TO MAINTAIN:
- Code follows industry best practices
- Examples are realistic and practical
- Security considerations are addressed
- Performance implications are discussed
- Modern approaches and tools are emphasized
""",
            
            "content_organizer": """
You are an expert content strategist specializing in technical documentation and
educational material organization. Your role is to structure content for maximum
clarity and learning effectiveness.

CORE RESPONSIBILITIES:
- Organize content in logical, progressive sequences
- Create clear information hierarchies
- Ensure smooth transitions between topics
- Optimize readability and comprehension
- Design effective navigation and reference systems

CONTENT ORGANIZATION PRINCIPLES:
- Follow the inverted pyramid structure
- Use consistent formatting and style
- Provide clear headings and signposts
- Include summaries and key takeaways
- Create effective cross-references and links
""",
            
            "course_designer": """
You are a master course designer with expertise in curriculum development and
instructional design. Your role is to orchestrate the overall learning experience
and ensure all components work together effectively.

CORE RESPONSIBILITIES:
- Design comprehensive learning experiences
- Coordinate input from all specialist agents
- Ensure alignment with learning objectives
- Balance theoretical knowledge with practical skills
- Create cohesive, engaging course narratives

COURSE DESIGN PRINCIPLES:
- Align all content with clear learning outcomes
- Create engaging and motivating experiences
- Balance challenge with achievability
- Provide multiple pathways for different learners
- Include regular assessment and feedback loops
"""
        }

    def _load_context_modifiers(self) -> Dict[str, Dict[str, str]]:
        """Load context-specific prompt modifications."""
        return {
            "complexity_level": {
                "low": "Focus on clear, simple explanations. Avoid jargon and complex concepts.",
                "medium": "Balance simplicity with technical depth. Introduce concepts progressively.",
                "high": "Embrace technical complexity. Provide comprehensive, detailed explanations.",
                "very_high": "Address advanced concepts. Assume strong technical background."
            },
            "learning_level": {
                "beginner": "Assume no prior knowledge. Explain fundamental concepts thoroughly.",
                "intermediate": "Build on basic programming knowledge. Introduce new concepts clearly.",
                "advanced": "Assume solid foundation. Focus on advanced techniques and patterns.",
                "expert": "Address sophisticated concepts. Emphasize best practices and trade-offs."
            },
            "content_type": {
                "overview": "Provide high-level understanding. Focus on concepts and relationships.",
                "tutorial": "Create step-by-step instructions. Include practical examples.",
                "example": "Show concrete implementations. Explain the 'why' behind the 'how'.",
                "exercise": "Design hands-on activities. Include clear success criteria.",
                "project": "Create comprehensive challenges. Integrate multiple concepts.",
                "reference": "Provide detailed documentation. Focus on completeness and accuracy."
            },
            "domain": {
                "web_development": "Emphasize user experience and modern web standards.",
                "data_science": "Focus on data analysis workflows and statistical concepts.",
                "mobile_development": "Address platform-specific considerations and constraints.",
                "system_programming": "Emphasize performance, memory management, and low-level concepts.",
                "ai_ml": "Focus on algorithms, model training, and evaluation metrics.",
                "general": "Maintain broad applicability and universal principles."
            }
        }

    def _load_role_specifications(self) -> Dict[str, Dict[str, Any]]:
        """Load role-specific specifications and constraints."""
        return {
            "educator": {
                "focus_areas": ["learning_theory", "pedagogy", "assessment", "motivation"],
                "constraints": ["cognitive_load", "prerequisite_knowledge", "learning_styles"],
                "output_format": "educational_guidance"
            },
            "tech_expert": {
                "focus_areas": ["technical_accuracy", "best_practices", "implementation", "architecture"],
                "constraints": ["code_quality", "security", "performance", "maintainability"],
                "output_format": "technical_analysis"
            },
            "content_organizer": {
                "focus_areas": ["structure", "flow", "clarity", "accessibility"],
                "constraints": ["readability", "consistency", "navigation", "reference"],
                "output_format": "content_structure"
            },
            "course_designer": {
                "focus_areas": ["learning_outcomes", "experience_design", "engagement", "assessment"],
                "constraints": ["coherence", "progression", "motivation", "practical_application"],
                "output_format": "course_design"
            }
        }

    def _apply_context_modifiers(
        self,
        base_template: str,
        project_context: ProjectContext,
        learning_context: LearningContext
    ) -> str:
        """Apply context-specific modifications to the base template."""
        
        # Determine complexity modifier
        if project_context.complexity_score <= 3:
            complexity_mod = self.context_modifiers["complexity_level"]["low"]
        elif project_context.complexity_score <= 6:
            complexity_mod = self.context_modifiers["complexity_level"]["medium"]
        elif project_context.complexity_score <= 8:
            complexity_mod = self.context_modifiers["complexity_level"]["high"]
        else:
            complexity_mod = self.context_modifiers["complexity_level"]["very_high"]
        
        # Get learning level modifier
        level_mod = self.context_modifiers["learning_level"][learning_context.target_level.value]
        
        # Get content type modifier
        content_mod = self.context_modifiers["content_type"][learning_context.content_type.value]
        
        # Get domain modifier
        domain_mod = self.context_modifiers["domain"].get(
            project_context.domain, 
            self.context_modifiers["domain"]["general"]
        )
        
        # Combine modifiers
        context_additions = f"""

CONTEXT-SPECIFIC GUIDANCE:
Complexity Level: {complexity_mod}
Learning Level: {level_mod}
Content Type: {content_mod}
Domain Focus: {domain_mod}

PROJECT CONTEXT:
- Language: {project_context.language}
- Project Type: {project_context.project_type}
- Key Concepts: {', '.join(project_context.key_concepts)}
- Prerequisites: {', '.join(project_context.prerequisites)}

LEARNING OBJECTIVES:
{chr(10).join(f'- {obj}' for obj in learning_context.learning_objectives)}
"""
        
        return base_template + context_additions

    def _add_role_specifications(
        self,
        context_prompt: str,
        agent_role: AgentRole,
        project_context: ProjectContext,
        learning_context: LearningContext
    ) -> str:
        """Add role-specific specifications to the prompt."""
        
        role_spec = self.role_specifications[agent_role.value]
        
        role_additions = f"""

ROLE-SPECIFIC FOCUS:
Primary Areas: {', '.join(role_spec['focus_areas'])}
Key Constraints: {', '.join(role_spec['constraints'])}
Expected Output Format: {role_spec['output_format']}

COLLABORATION GUIDELINES:
- Coordinate with other specialist agents
- Provide clear rationale for recommendations
- Flag any conflicts or concerns
- Suggest alternative approaches when appropriate
"""
        
        return context_prompt + role_additions

    def _apply_final_customizations(
        self, role_prompt: str, additional_context: Dict[str, Any]
    ) -> str:
        """Apply final customizations based on additional context."""
        
        if not additional_context:
            return role_prompt
        
        customizations = "\nADDITIONAL CONTEXT:\n"
        for key, value in additional_context.items():
            customizations += f"- {key}: {value}\n"
        
        return role_prompt + customizations

    def _get_fallback_prompt(self, agent_role: AgentRole) -> str:
        """Get a fallback prompt if generation fails."""
        return f"""
You are a {agent_role.value.replace('_', ' ')} AI assistant helping with educational content generation.
Please provide helpful guidance based on your expertise and the given context.
"""

    def generate_collaborative_prompt(
        self,
        project_context: ProjectContext,
        learning_context: LearningContext,
        collaboration_phase: str = "initial"
    ) -> Dict[str, str]:
        """
        Generate prompts for all agents in a collaborative scenario.
        
        Args:
            project_context: Information about the project
            learning_context: Information about the learning scenario
            collaboration_phase: Current phase of collaboration
            
        Returns:
            Dictionary mapping agent roles to their prompts
        """
        
        collaborative_context = {
            "collaboration_phase": collaboration_phase,
            "coordination_instructions": self._get_coordination_instructions(collaboration_phase)
        }
        
        prompts = {}
        for role in AgentRole:
            prompts[role.value] = self.generate_prompt(
                role, project_context, learning_context, collaborative_context
            )
        
        return prompts

    def _get_coordination_instructions(self, phase: str) -> str:
        """Get coordination instructions for different collaboration phases."""
        instructions = {
            "initial": "Begin with individual analysis. Prepare to share findings with other agents.",
            "synthesis": "Integrate insights from other agents. Identify synergies and conflicts.",
            "refinement": "Refine recommendations based on collaborative feedback.",
            "finalization": "Prepare final deliverables with clear handoff instructions."
        }
        
        return instructions.get(phase, "Collaborate effectively with other specialist agents.")


# Global instance for easy access
prompt_manager = DynamicPromptManager()
