#!/usr/bin/env python3
"""
Language Info Tool for MCP

This tool provides information about supported languages and file extensions
through the MCP protocol, allowing clients to discover available analysis capabilities.
"""

import json
from typing import Any

from ...language_detector import detector
from ...plugins.manager import PluginManager
from ...utils import setup_logger
from .base_tool import BaseMCPTool

# Set up logging
logger = setup_logger(__name__)


class LanguageInfoTool(BaseMCPTool):
    """
    MCP Tool for retrieving language and extension support information.
    
    This tool provides clients with information about:
    - Supported programming languages
    - File extensions for each language
    - Available plugins and their capabilities
    """

    def __init__(self, project_root: str = None) -> None:
        """Initialize the language info tool."""
        super().__init__(project_root)
        self.plugin_manager = PluginManager()
        self.logger = logger
        
        # Load plugins to get current support information
        try:
            self.plugin_manager.load_plugins()
            logger.info("LanguageInfoTool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize LanguageInfoTool: {e}")
            raise

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the tool definition for MCP registration."""
        return {
            "name": "get_language_info",
            "description": "Get information about supported languages and file extensions for code analysis",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "info_type": {
                        "type": "string",
                        "enum": ["languages", "extensions", "plugins", "all"],
                        "default": "all",
                        "description": "Type of information to retrieve: languages (supported languages), extensions (file extensions), plugins (plugin details), or all",
                    },
                    "language": {
                        "type": "string",
                        "description": "Specific language to get detailed information for (optional)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "text"],
                        "default": "json", 
                        "description": "Output format: json (structured data) or text (human-readable)",
                    }
                },
                "additionalProperties": False,
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        """Execute the language info tool."""
        try:
            info_type = arguments.get("info_type", "all")
            specific_language = arguments.get("language")
            output_format = arguments.get("format", "json")
            
            logger.info(f"Getting language info: type={info_type}, language={specific_language}, format={output_format}")
            
            if specific_language:
                return self._get_language_specific_info(specific_language, output_format)
            
            result = {}
            
            if info_type in ["languages", "all"]:
                result["languages"] = self._get_supported_languages()
            
            if info_type in ["extensions", "all"]:
                result["extensions"] = self._get_supported_extensions()
            
            if info_type in ["plugins", "all"]:
                result["plugins"] = self._get_plugin_info()
            
            if info_type == "all":
                result["summary"] = self._get_summary_info()
            
            if output_format == "text":
                return self._format_as_text(result, info_type)
            else:
                return json.dumps(result, indent=2)
            
        except Exception as e:
            error_msg = f"Error retrieving language information: {e}"
            logger.error(error_msg)
            if arguments.get("format", "json") == "json":
                return json.dumps({"error": error_msg})
            else:
                return f"ERROR: {error_msg}"

    def _get_supported_languages(self) -> dict[str, Any]:
        """Get information about supported languages."""
        languages = {}
        
        try:
            # Get languages from detector
            for language in detector.get_supported_languages():
                info = detector.get_language_info(language)
                languages[language] = {
                    "extensions": info.get("extensions", []),
                    "confidence_patterns": len(info.get("patterns", [])),
                    "description": f"{language.title()} programming language"
                }
            
            # Add plugin-specific languages
            plugins = self.plugin_manager.get_all_plugins()
            for lang, plugin in plugins.items():
                if lang not in languages:
                    languages[lang] = {
                        "extensions": plugin.get_file_extensions(),
                        "confidence_patterns": 0,
                        "description": f"{lang.title()} language (via plugin)"
                    }
                else:
                    # Update with plugin information
                    plugin_extensions = plugin.get_file_extensions()
                    existing_extensions = set(languages[lang]["extensions"])
                    all_extensions = list(existing_extensions.union(set(plugin_extensions)))
                    languages[lang]["extensions"] = sorted(all_extensions)
                    
        except Exception as e:
            logger.error(f"Error getting supported languages: {e}")
            
        return languages

    def _get_supported_extensions(self) -> dict[str, str]:
        """Get mapping of file extensions to languages."""
        extensions = {}
        
        try:
            supported_exts = detector.get_supported_extensions()
            for ext in supported_exts:
                # Use the detector to find the primary language for this extension
                try:
                    # Create a dummy file path to test extension mapping
                    test_file = f"test{ext}"
                    language = detector.detect_language(test_file)
                    extensions[ext] = language
                except Exception:
                    # Fallback for extensions that might not be directly mappable
                    extensions[ext] = "unknown"
                    
        except Exception as e:
            logger.error(f"Error getting supported extensions: {e}")
            
        return extensions

    def _get_plugin_info(self) -> dict[str, Any]:
        """Get detailed information about loaded plugins."""
        plugins = {}
        
        try:
            loaded_plugins = self.plugin_manager.get_all_plugins()
            
            for language, plugin in loaded_plugins.items():
                plugins[language] = {
                    "class_name": plugin.__class__.__name__,
                    "module": plugin.__class__.__module__,
                    "extensions": plugin.get_file_extensions(),
                    "has_extractor": hasattr(plugin, "create_extractor"),
                    "has_analyzer": hasattr(plugin, "analyze_file"),
                }
                
        except Exception as e:
            logger.error(f"Error getting plugin info: {e}")
            
        return plugins

    def _get_language_specific_info(self, language: str, output_format: str) -> str:
        """Get detailed information for a specific language."""
        try:
            info = {
                "language": language,
                "supported": False,
                "extensions": [],
                "plugin_info": None,
                "detector_info": None
            }
            
            # Check detector support
            if language in detector.get_supported_languages():
                info["supported"] = True
                detector_info = detector.get_language_info(language)
                info["detector_info"] = detector_info
                info["extensions"].extend(detector_info.get("extensions", []))
            
            # Check plugin support
            plugin = self.plugin_manager.get_plugin(language)
            if plugin:
                info["supported"] = True
                info["plugin_info"] = {
                    "class_name": plugin.__class__.__name__,
                    "module": plugin.__class__.__module__,
                    "extensions": plugin.get_file_extensions(),
                    "methods": [method for method in dir(plugin) if not method.startswith("_")]
                }
                # Add plugin extensions to the list
                plugin_exts = plugin.get_file_extensions()
                info["extensions"].extend([ext for ext in plugin_exts if ext not in info["extensions"]])
            
            # Remove duplicates and sort
            info["extensions"] = sorted(list(set(info["extensions"])))
            
            if not info["supported"]:
                info["error"] = f"Language '{language}' is not supported"
            
            if output_format == "text":
                return self._format_language_info_as_text(info)
            else:
                return json.dumps(info, indent=2)
                
        except Exception as e:
            error_msg = f"Error getting info for language '{language}': {e}"
            logger.error(error_msg)
            if output_format == "json":
                return json.dumps({"error": error_msg})
            else:
                return f"ERROR: {error_msg}"

    def _get_summary_info(self) -> dict[str, Any]:
        """Get summary statistics about language support."""
        try:
            languages = self._get_supported_languages()
            extensions = self._get_supported_extensions()
            plugins = self._get_plugin_info()
            
            # Calculate total extensions
            total_extensions = len(extensions)
            
            # Group extensions by language
            extensions_by_language = {}
            for ext, lang in extensions.items():
                if lang not in extensions_by_language:
                    extensions_by_language[lang] = []
                extensions_by_language[lang].append(ext)
            
            return {
                "total_languages": len(languages),
                "total_extensions": total_extensions,
                "total_plugins": len(plugins),
                "languages_with_plugins": len([lang for lang in languages if lang in plugins]),
                "most_extensions": max(extensions_by_language.items(), key=lambda x: len(x[1])) if extensions_by_language else None,
            }
            
        except Exception as e:
            logger.error(f"Error getting summary info: {e}")
            return {"error": str(e)}

    def _format_as_text(self, data: dict[str, Any], info_type: str) -> str:
        """Format the result data as human-readable text."""
        lines = []
        
        if "languages" in data:
            lines.append("SUPPORTED LANGUAGES:")
            lines.append("=" * 50)
            for lang, info in sorted(data["languages"].items()):
                extensions = ", ".join(info["extensions"][:5])
                if len(info["extensions"]) > 5:
                    extensions += f" (and {len(info['extensions'])-5} more)"
                lines.append(f"  {lang:<12} - Extensions: {extensions}")
            lines.append("")
        
        if "extensions" in data:
            lines.append("SUPPORTED FILE EXTENSIONS:")
            lines.append("=" * 50)
            # Group extensions by language
            by_language = {}
            for ext, lang in data["extensions"].items():
                if lang not in by_language:
                    by_language[lang] = []
                by_language[lang].append(ext)
            
            for lang in sorted(by_language.keys()):
                exts = sorted(by_language[lang])
                lines.append(f"  {lang:<12}: {', '.join(exts)}")
            lines.append("")
        
        if "plugins" in data:
            lines.append("LOADED PLUGINS:")
            lines.append("=" * 50)
            for lang, plugin_info in sorted(data["plugins"].items()):
                lines.append(f"  {lang:<12} - {plugin_info['class_name']}")
                lines.append(f"               Extensions: {', '.join(plugin_info['extensions'])}")
            lines.append("")
        
        if "summary" in data:
            summary = data["summary"]
            lines.append("SUMMARY:")
            lines.append("=" * 50)
            lines.append(f"Total Languages: {summary.get('total_languages', 0)}")
            lines.append(f"Total Extensions: {summary.get('total_extensions', 0)}")
            lines.append(f"Total Plugins: {summary.get('total_plugins', 0)}")
            lines.append(f"Languages with Plugins: {summary.get('languages_with_plugins', 0)}")
            
            most_ext = summary.get('most_extensions')
            if most_ext:
                lines.append(f"Language with Most Extensions: {most_ext[0]} ({len(most_ext[1])} extensions)")
        
        return "\n".join(lines)

    def _format_language_info_as_text(self, info: dict[str, Any]) -> str:
        """Format specific language information as text."""
        lines = []
        
        lines.append(f"LANGUAGE INFORMATION: {info['language']}")
        lines.append("=" * 50)
        
        if info.get("error"):
            lines.append(f"ERROR: {info['error']}")
            return "\n".join(lines)
        
        lines.append(f"Supported: {'Yes' if info['supported'] else 'No'}")
        lines.append(f"File Extensions: {', '.join(info['extensions']) if info['extensions'] else 'None'}")
        
        if info.get("plugin_info"):
            plugin = info["plugin_info"]
            lines.append("\nPlugin Information:")
            lines.append(f"  Class: {plugin['class_name']}")
            lines.append(f"  Module: {plugin['module']}")
            lines.append(f"  Extensions: {', '.join(plugin['extensions'])}")
            lines.append(f"  Available Methods: {', '.join(plugin['methods'])}")
        
        if info.get("detector_info"):
            detector_info = info["detector_info"]
            lines.append("\nDetector Information:")
            lines.append(f"  Extensions: {', '.join(detector_info.get('extensions', []))}")
            lines.append(f"  Patterns: {len(detector_info.get('patterns', []))} detection patterns")
        
        return "\n".join(lines)