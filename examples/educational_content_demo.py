#!/usr/bin/env python3
"""
Educational Content Generation Demo

This script demonstrates how to use the tree-sitter-analyzer's educational
content generation capabilities to create comprehensive learning materials
for open source projects.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the project root to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from tree_sitter_analyzer.mcp.tools.learning_complexity_tool import LearningComplexityTool
from tree_sitter_analyzer.mcp.tools.educational_content_generator import EducationalContentGenerator
from tree_sitter_analyzer.mcp.agents.multi_agent_coordinator import (
    MultiAgentCoordinator,
    ProjectContext,
    LearningContext,
    LearningLevel,
    ContentType
)


async def demo_learning_complexity_analysis():
    """Demonstrate learning complexity analysis."""
    print("🔍 DEMO: Learning Complexity Analysis")
    print("=" * 50)
    
    # Initialize the learning complexity tool
    complexity_tool = LearningComplexityTool()
    
    # Analyze a sample Java file
    sample_file = Path(__file__).parent / "Sample.java"
    if not sample_file.exists():
        print(f"⚠️  Sample file not found: {sample_file}")
        return
    
    # Test different analysis depths and target audiences
    test_cases = [
        {"target_audience": "beginner", "analysis_depth": "basic"},
        {"target_audience": "intermediate", "analysis_depth": "detailed"},
        {"target_audience": "advanced", "analysis_depth": "comprehensive"},
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📊 Test Case {i}: {test_case['target_audience'].title()} Level")
        print("-" * 30)
        
        try:
            arguments = {
                "file_path": str(sample_file),
                "analysis_depth": test_case["analysis_depth"],
                "target_audience": test_case["target_audience"],
                "include_recommendations": True
            }
            
            result = await complexity_tool.execute(arguments)
            
            # Display key results
            print(f"Difficulty Level: {result['learning_difficulty']['difficulty_level']}")
            print(f"Complexity Score: {result['learning_difficulty']['adjusted_score']:.1f}/10")
            print(f"Confidence: {result['learning_difficulty']['confidence']:.1%}")
            
            if result['recommendations']['prerequisite_topics']:
                print(f"Prerequisites: {', '.join(result['recommendations']['prerequisite_topics'][:3])}")
            
            print(f"Suggested Approach: {result['recommendations']['suggested_approach']}")
            
        except Exception as e:
            print(f"❌ Error in test case {i}: {e}")


async def demo_educational_content_generation():
    """Demonstrate comprehensive educational content generation."""
    print("\n\n🚀 DEMO: Educational Content Generation")
    print("=" * 50)
    
    # Initialize the educational content generator
    content_generator = EducationalContentGenerator()
    
    # Test different content types and audiences
    sample_file = Path(__file__).parent / "Sample.java"
    if not sample_file.exists():
        print(f"⚠️  Sample file not found: {sample_file}")
        return
    
    test_scenarios = [
        {
            "name": "Beginner Tutorial",
            "target_audience": "beginner",
            "content_type": "tutorial",
            "learning_objectives": [
                "Understand basic Java class structure",
                "Learn about methods and fields",
                "Practice reading and understanding code"
            ]
        },
        {
            "name": "Advanced Reference",
            "target_audience": "advanced",
            "content_type": "reference",
            "learning_objectives": [
                "Master advanced Java patterns",
                "Understand architectural decisions",
                "Apply best practices in similar projects"
            ]
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n📚 Scenario {i}: {scenario['name']}")
        print("-" * 30)
        
        try:
            arguments = {
                "project_path": str(sample_file),
                "target_audience": scenario["target_audience"],
                "content_type": scenario["content_type"],
                "learning_objectives": scenario["learning_objectives"],
                "content_depth": "detailed",
                "include_exercises": True,
                "include_assessments": True,
                "output_format": "structured"
            }
            
            result = await content_generator.execute(arguments)
            
            if result["success"]:
                print("✅ Content generation successful!")
                print(f"Quality Score: {result['metadata']['quality_score']:.1%}")
                print(f"Content Type: {result['content_type']}")
                print(f"Target Audience: {result['target_audience']}")
                
                # Display some key recommendations
                if result['metadata']['recommendations']:
                    print(f"Key Recommendations:")
                    for rec in result['metadata']['recommendations'][:3]:
                        print(f"  • {rec}")
                
                # Show content structure
                content = result['generated_content']['content']
                if isinstance(content, dict):
                    print(f"Generated Components:")
                    for component in content.keys():
                        print(f"  • {component}")
                
            else:
                print(f"❌ Content generation failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"❌ Error in scenario {i}: {e}")


async def demo_multi_agent_collaboration():
    """Demonstrate multi-agent collaboration."""
    print("\n\n🤝 DEMO: Multi-Agent Collaboration")
    print("=" * 50)
    
    # Initialize the multi-agent coordinator
    coordinator = MultiAgentCoordinator()
    
    # Create sample project and learning contexts
    project_context = ProjectContext(
        language="java",
        project_type="Object-Oriented Application",
        complexity_score=6.5,
        domain="general",
        architecture_patterns=["Object-Oriented Design", "Encapsulation"],
        key_concepts=["Classes", "Methods", "Inheritance"],
        prerequisites=["Basic Programming", "Object-Oriented Concepts"]
    )
    
    learning_context = LearningContext(
        target_level=LearningLevel.INTERMEDIATE,
        content_type=ContentType.TUTORIAL,
        learning_objectives=[
            "Understand the project architecture",
            "Learn implementation patterns",
            "Practice code analysis skills"
        ]
    )
    
    try:
        print("🔄 Starting multi-agent collaboration...")
        
        # Generate educational content through collaboration
        collaboration_result = await coordinator.generate_educational_content(
            project_context, learning_context
        )
        
        print("✅ Collaboration completed successfully!")
        print(f"Quality Score: {collaboration_result.quality_score:.1%}")
        print(f"Participating Agents: {len(collaboration_result.agent_responses)}")
        
        # Show agent contributions
        print("\n👥 Agent Contributions:")
        for role, response in collaboration_result.agent_responses.items():
            print(f"  • {role.replace('_', ' ').title()}: {response.confidence:.1%} confidence")
            if response.recommendations:
                print(f"    Recommendations: {len(response.recommendations)}")
        
        # Show final recommendations
        if collaboration_result.recommendations:
            print(f"\n💡 Final Recommendations:")
            for rec in collaboration_result.recommendations[:5]:
                print(f"  • {rec}")
        
        # Show next steps
        if collaboration_result.next_steps:
            print(f"\n📋 Next Steps:")
            for step in collaboration_result.next_steps[:3]:
                print(f"  1. {step}")
                
    except Exception as e:
        print(f"❌ Multi-agent collaboration failed: {e}")


async def main():
    """Run all demos."""
    print("🎓 Tree-sitter Analyzer Educational Content Generation Demo")
    print("=" * 60)
    print("This demo showcases the intelligent educational content generation")
    print("capabilities built on top of tree-sitter code analysis.")
    print()
    
    try:
        # Run individual demos
        await demo_learning_complexity_analysis()
        await demo_educational_content_generation()
        await demo_multi_agent_collaboration()
        
        print("\n\n🎉 Demo completed successfully!")
        print("\nTo use these features in your own projects:")
        print("1. Install tree-sitter-analyzer with MCP support")
        print("2. Configure Claude Desktop with the MCP server")
        print("3. Use the educational tools in your AI assistant")
        print("\nFor more information, see the README.md file.")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the demo
    asyncio.run(main())
