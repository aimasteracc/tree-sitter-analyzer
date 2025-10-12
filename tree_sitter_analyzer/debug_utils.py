#!/usr/bin/env python3
"""
Debug Script Manager for Tree-Sitter Analyzer

This module provides functionality to create and execute debug scripts safely,
avoiding Windows command line issues with special characters and complex code.
"""

import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Dict, Any
import shutil
import atexit

from .utils import setup_logger

# Set up logging
logger = setup_logger(__name__)


class DebugScriptManager:
    """
    Manages debug script creation, execution, and cleanup for safe code execution
    on Windows systems, avoiding command line character encoding issues.
    """

    def __init__(self, temp_dir: Optional[str] = None):
        """
        Initialize the debug script manager.

        Args:
            temp_dir: Optional custom temporary directory. If None, uses system temp.
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.debug_dir = Path(self.temp_dir) / "tree_sitter_debug"
        self.created_scripts: Dict[str, Path] = {}
        self._ensure_debug_directory()
        
        # Register cleanup on exit
        atexit.register(self.cleanup_all_scripts)

    def _ensure_debug_directory(self) -> None:
        """Ensure the debug directory exists."""
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Debug directory ensured: {self.debug_dir}")
        except OSError as e:
            logger.error(f"Failed to create debug directory {self.debug_dir}: {e}")
            # Fallback to system temp directory
            self.debug_dir = Path(tempfile.gettempdir())

    def create_script(self,
                     code: str,
                     script_name: Optional[str] = None,
                     cleanup_after_execution: bool = True) -> str:
        """
        Create a debug script file from Python code.

        Args:
            code: Python code to write to the script
            script_name: Optional custom script name. If None, generates unique name.
            cleanup_after_execution: Whether to automatically cleanup after execution

        Returns:
            Path to the created script file

        Raises:
            OSError: If script file cannot be created
            ValueError: If code is empty
        """
        if not code or not code.strip():
            raise ValueError("Code cannot be empty")

        # Generate unique script name if not provided
        if script_name is None:
            script_name = f"debug_script_{uuid.uuid4().hex[:8]}.py"
        elif not script_name.endswith('.py'):
            script_name += '.py'

        script_path = self.debug_dir / script_name

        try:
            # Write script with UTF-8 encoding for Windows compatibility
            with open(script_path, 'w', encoding='utf-8', newline='\n') as f:
                # Add encoding declaration for Python
                f.write('#!/usr/bin/env python3\n')
                f.write('# -*- coding: utf-8 -*-\n')
                f.write('\n')
                
                # Add current directory to Python path for module imports
                f.write('import sys\n')
                f.write('import os\n')
                f.write('# Add current working directory to Python path\n')
                f.write('current_dir = os.getcwd()\n')
                f.write('if current_dir not in sys.path:\n')
                f.write('    sys.path.insert(0, current_dir)\n')
                f.write('\n')
                
                f.write(code)

            # Make script executable on Unix-like systems
            if os.name != 'nt':
                script_path.chmod(0o755)

            # Track created script
            self.created_scripts[str(script_path)] = script_path
            
            logger.info(f"Debug script created: {script_path}")
            return str(script_path)

        except OSError as e:
            logger.error(f"Failed to create debug script {script_path}: {e}")
            raise

    def execute_script(self, 
                      script_path: str, 
                      capture_output: bool = True,
                      timeout: Optional[int] = 30,
                      cwd: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a debug script and return results.

        Args:
            script_path: Path to the script to execute
            capture_output: Whether to capture stdout/stderr
            timeout: Execution timeout in seconds
            cwd: Working directory for script execution

        Returns:
            Dictionary containing execution results:
            - 'returncode': Process return code
            - 'stdout': Standard output (if captured)
            - 'stderr': Standard error (if captured)
            - 'success': Boolean indicating success
            - 'error': Error message if execution failed

        Raises:
            FileNotFoundError: If script file doesn't exist
        """
        script_path_obj = Path(script_path)
        if not script_path_obj.exists():
            raise FileNotFoundError(f"Script file not found: {script_path}")

        try:
            # Prepare command for execution
            cmd = ['python', str(script_path)]
            
            # Use current working directory if not specified
            if cwd is None:
                cwd = os.getcwd()
            
            # Execute script with proper encoding handling
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                encoding='utf-8',
                timeout=timeout,
                cwd=cwd,
                errors='replace'  # Handle encoding errors gracefully
            )

            execution_result = {
                'returncode': result.returncode,
                'success': result.returncode == 0,
                'error': None
            }

            if capture_output:
                execution_result['stdout'] = result.stdout
                execution_result['stderr'] = result.stderr
            
            if result.returncode == 0:
                logger.info(f"Debug script executed successfully: {script_path}")
            else:
                logger.warning(f"Debug script failed with code {result.returncode}: {script_path}")
                if capture_output and result.stderr:
                    logger.warning(f"Script stderr: {result.stderr}")

            return execution_result

        except subprocess.TimeoutExpired as e:
            error_msg = f"Script execution timed out after {timeout} seconds"
            logger.error(f"{error_msg}: {script_path}")
            return {
                'returncode': -1,
                'success': False,
                'error': error_msg,
                'stdout': '',
                'stderr': error_msg
            }

        except Exception as e:
            error_msg = f"Script execution failed: {str(e)}"
            logger.error(f"{error_msg}: {script_path}")
            return {
                'returncode': -1,
                'success': False,
                'error': error_msg,
                'stdout': '',
                'stderr': error_msg
            }

    def create_and_execute(self, 
                          code: str,
                          script_name: Optional[str] = None,
                          capture_output: bool = True,
                          timeout: Optional[int] = 30,
                          cwd: Optional[str] = None,
                          cleanup_after: bool = True) -> Dict[str, Any]:
        """
        Create and execute a debug script in one operation.

        Args:
            code: Python code to execute
            script_name: Optional custom script name
            capture_output: Whether to capture stdout/stderr
            timeout: Execution timeout in seconds
            cwd: Working directory for script execution
            cleanup_after: Whether to cleanup script after execution

        Returns:
            Dictionary containing execution results (same as execute_script)
        """
        try:
            script_path = self.create_script(code, script_name, cleanup_after)
            result = self.execute_script(script_path, capture_output, timeout, cwd)
            
            if cleanup_after:
                self.cleanup_script(script_path)
            
            return result

        except Exception as e:
            error_msg = f"Failed to create and execute debug script: {str(e)}"
            logger.error(error_msg)
            return {
                'returncode': -1,
                'success': False,
                'error': error_msg,
                'stdout': '',
                'stderr': error_msg
            }

    def cleanup_script(self, script_path: str) -> bool:
        """
        Clean up a specific debug script.

        Args:
            script_path: Path to the script to cleanup

        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            script_path_obj = Path(script_path)
            if script_path_obj.exists():
                script_path_obj.unlink()
                logger.debug(f"Cleaned up debug script: {script_path}")
            
            # Remove from tracking
            self.created_scripts.pop(script_path, None)
            return True

        except Exception as e:
            logger.warning(f"Failed to cleanup debug script {script_path}: {e}")
            return False

    def cleanup_all_scripts(self) -> int:
        """
        Clean up all created debug scripts.

        Returns:
            Number of scripts successfully cleaned up
        """
        cleaned_count = 0
        scripts_to_cleanup = list(self.created_scripts.keys())
        
        for script_path in scripts_to_cleanup:
            if self.cleanup_script(script_path):
                cleaned_count += 1

        logger.info(f"Cleaned up {cleaned_count} debug scripts")
        return cleaned_count

    def list_scripts(self) -> list[str]:
        """
        List all currently tracked debug scripts.

        Returns:
            List of script paths
        """
        return list(self.created_scripts.keys())

    def get_debug_directory(self) -> str:
        """
        Get the debug directory path.

        Returns:
            Path to the debug directory
        """
        return str(self.debug_dir)


# Global instance for convenience
_global_debug_manager: Optional[DebugScriptManager] = None


def get_debug_manager() -> DebugScriptManager:
    """
    Get the global debug script manager instance.

    Returns:
        Global DebugScriptManager instance
    """
    global _global_debug_manager
    if _global_debug_manager is None:
        _global_debug_manager = DebugScriptManager()
    return _global_debug_manager


def create_debug_script(code: str, script_name: Optional[str] = None) -> str:
    """
    Convenience function to create a debug script using the global manager.

    Args:
        code: Python code to write to the script
        script_name: Optional custom script name

    Returns:
        Path to the created script file
    """
    return get_debug_manager().create_script(code, script_name)


def execute_debug_code(code: str, 
                      capture_output: bool = True,
                      timeout: Optional[int] = 30,
                      cwd: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to create and execute debug code using the global manager.

    Args:
        code: Python code to execute
        capture_output: Whether to capture stdout/stderr
        timeout: Execution timeout in seconds
        cwd: Working directory for script execution

    Returns:
        Dictionary containing execution results
    """
    return get_debug_manager().create_and_execute(
        code, capture_output=capture_output, timeout=timeout, cwd=cwd
    )


def cleanup_debug_scripts() -> int:
    """
    Convenience function to cleanup all debug scripts using the global manager.

    Returns:
        Number of scripts successfully cleaned up
    """
    return get_debug_manager().cleanup_all_scripts()