"""
Environment Context Module for Human-level Reward Design via Coding Large Language Models

This module models the environment as context for reward design, capturing state and action spaces
to inform reward function generation. It provides functionality to extract environment information
from source code or APIs, and prepares it for use with LLMs for reward generation.

Paper Context:
- Environment context is provided to LLMs for zero-shot reward generation
- Only environment variables (state and action) need to be exposed
- Supports both source code and API-based environment information
- Automatic extraction of relevant code snippets to fit within LLM context windows
"""

import ast
import inspect
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Union, Any
from pathlib import Path

# TODO: Consider using more sophisticated AST parsing for complex environments
# TODO: Implement proper error handling for malformed environment code

@dataclass
class EnvironmentVariables:
    """Data class to store environment state and action variables."""
    state_vars: Dict[str, Any]
    action_vars: Dict[str, Any]
    observation_space: Dict[str, Any]
    action_space: Dict[str, Any]

class EnvironmentContextError(Exception):
    """Custom exception for environment context errors."""
    pass

class EnvironmentExtractor(ABC):
    """Abstract base class for environment extractors."""
    
    @abstractmethod
    def extract_context(self, environment_source: Union[str, Path]) -> EnvironmentVariables:
        """
        Extract environment context from source code or API.
        
        Args:
            environment_source: Source code or path to environment file
            
        Returns:
            EnvironmentVariables containing state and action information
            
        Raises:
            EnvironmentContextError: If extraction fails
        """
        pass

class SourceCodeExtractor(EnvironmentExtractor):
    """Extractor for environment information from source code."""
    
    def __init__(self):
        self.state_var_pattern = re.compile(r'(\w+)\s*=\s*.*?(\w+\.state|self\.state|state)')
        self.action_var_pattern = re.compile(r'(\w+)\s*=\s*.*?(\w+\.action|self\.action|action)')
        
    def extract_context(self, environment_source: Union[str, Path]) -> EnvironmentVariables:
        """
        Extract environment context from source code.
        
        Args:
            environment_source: Source code string or path to environment file
            
        Returns:
            EnvironmentVariables containing state and action information
            
        Raises:
            EnvironmentContextError: If extraction fails
        """
        try:
            # If it's a path, read the file
            if isinstance(environment_source, Path):
                with open(environment_source, 'r') as f:
                    source_code = f.read()
            else:
                source_code = environment_source
                
            # Parse the AST to find relevant variables
            tree = ast.parse(source_code)
            
            # Extract state and action variables
            state_vars = self._extract_variables(tree, 'state')
            action_vars = self._extract_variables(tree, 'action')
            
            # Extract observation and action spaces
            observation_space = self._extract_observation_space(tree)
            action_space = self._extract_action_space(tree)
            
            return EnvironmentVariables(
                state_vars=state_vars,
                action_vars=action_vars,
                observation_space=observation_space,
                action_space=action_space
            )
            
        except Exception as e:
            raise EnvironmentContextError(f"Failed to extract environment context: {str(e)}")
    
    def _extract_variables(self, tree: ast.AST, var_type: str) -> Dict[str, Any]:
        """
        Extract variables of a specific type from AST.
        
        Args:
            tree: AST of the source code
            var_type: Type of variables to extract ('state' or 'action')
            
        Returns:
            Dictionary of variable names and their types
        """
        variables = {}
        
        # TODO: Implement more sophisticated variable extraction logic
        # This is a simplified version that looks for assignments
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        # Simple heuristic: if variable name contains 'state' or 'action'
                        if var_type in var_name.lower():
                            variables[var_name] = self._infer_type(node.value)
        
        return variables
    
    def _extract_observation_space(self, tree: ast.AST) -> Dict[str, Any]:
        """
        Extract observation space information from AST.
        
        Args:
            tree: AST of the source code
            
        Returns:
            Dictionary describing the observation space
        """
        # TODO: Implement more sophisticated observation space extraction
        # This is a placeholder implementation
        return {
            "type": "dict",
            "description": "Observation space extracted from environment",
            "variables": []
        }
    
    def _extract_action_space(self, tree: ast.AST) -> Dict[str, Any]:
        """
        Extract action space information from AST.
        
        Args:
            tree: AST of the source code
            
        Returns:
            Dictionary describing the action space
        """
        # TODO: Implement more sophisticated action space extraction
        # This is a placeholder implementation
        return {
            "type": "dict",
            "description": "Action space extracted from environment",
            "variables": []
        }
    
    def _infer_type(self, node: ast.AST) -> str:
        """
        Infer the type of an AST node.
        
        Args:
            node: AST node
            
        Returns:
            String representation of the inferred type
        """
        # TODO: Implement more sophisticated type inference
        # This is a placeholder implementation
        if isinstance(node, ast.List):
            return "list"
        elif isinstance(node, ast.Dict):
            return "dict"
        elif isinstance(node, ast.Tuple):
            return "tuple"
        elif isinstance(node, ast.Num):
            return "number"
        elif isinstance(node, ast.Str):
            return "string"
        else:
            return "unknown"

class APIExtractor(EnvironmentExtractor):
    """Extractor for environment information from API."""
    
    def __init__(self, api_endpoint: str):
        self.api_endpoint = api_endpoint
        
    def extract_context(self, environment_source: Union[str, Path]) -> EnvironmentVariables:
        """
        Extract environment context from API endpoint.
        
        Args:
            environment_source: Not used for API extraction, but kept for interface consistency
            
        Returns:
            EnvironmentVariables containing state and action information
            
        Raises:
            EnvironmentContextError: If extraction fails
        """
        # TODO: Implement actual API call logic
        # This is a placeholder implementation
        try:
            # Simulate API call
            # In practice, this would make an HTTP request to the API endpoint
            # and parse the response to extract environment information
            
            # Placeholder data
            return EnvironmentVariables(
                state_vars={"state_var1": "float", "state_var2": "int"},
                action_vars={"action_var1": "float", "action_var2": "int"},
                observation_space={"type": "dict", "variables": ["state_var1", "state_var2"]},
                action_space={"type": "dict", "variables": ["action_var1", "action_var2"]}
            )
        except Exception as e:
            raise EnvironmentContextError(f"Failed to extract environment context from API: {str(e)}")

class EnvironmentContextModule:
    """Main module for modeling environment as context for reward design."""
    
    def __init__(self, extractor: EnvironmentExtractor = None):
        """
        Initialize the Environment Context Module.
        
        Args:
            extractor: Environment extractor to use (defaults to SourceCodeExtractor)
        """
        self.extractor = extractor or SourceCodeExtractor()
        self.environment_context = None
        self.context_snippets = []
        
    def load_environment(self, environment_source: Union[str, Path]) -> Dict[str, Any]:
        """
        Load and extract environment context from source.
        
        Args:
            environment_source: Source code or path to environment file
            
        Returns:
            Dictionary containing environment context information
            
        Raises:
            EnvironmentContextError: If environment loading fails
        """
        try:
            # Extract environment variables
            env_vars = self.extractor.extract_context(environment_source)
            
            # Store the context
            self.environment_context = env_vars
            
            # Create context snippets for LLM consumption
            self.context_snippets = self._create_context_snippets(env_vars)
            
            return {
                "state_variables": env_vars.state_vars,
                "action_variables": env_vars.action_vars,
                "observation_space": env_vars.observation_space,
                "action_space": env_vars.action_space,
                "context_snippets": self.context_snippets
            }
            
        except Exception as e:
            raise EnvironmentContextError(f"Failed to load environment: {str(e)}")
    
    def _create_context_snippets(self, env_vars: EnvironmentVariables) -> List[str]:
        """
        Create context snippets suitable for LLM input.
        
        Args:
            env_vars: Environment variables to create snippets from
            
        Returns:
            List of context snippets
        """
        snippets = []
        
        # Create state variables snippet
        if env_vars.state_vars:
            state_snippet = "State variables:\n"
            for var_name, var_type in env_vars.state_vars.items():
                state_snippet += f"  {var_name}: {var_type}\n"
            snippets.append(state_snippet)
        
        # Create action variables snippet
        if env_vars.action_vars:
            action_snippet = "Action variables:\n"
            for var_name, var_type in env_vars.action_vars.items():
                action_snippet += f"  {var_name}: {var_type}\n"
            snippets.append(action_snippet)
        
        # Create observation space snippet
        if env_vars.observation_space:
            obs_snippet = "Observation space:\n"
            obs_snippet += f"  Type: {env_vars.observation_space.get('type', 'unknown')}\n"
            obs_snippet += f"  Description: {env_vars.observation_space.get('description', 'No description')}\n"
            if 'variables' in env_vars.observation_space:
                obs_snippet += "  Variables:\n"
                for var in env_vars.observation_space['variables']:
                    obs_snippet += f"    - {var}\n"
            snippets.append(obs_snippet)
        
        # Create action space snippet
        if env_vars.action_space:
            action_space_snippet = "Action space:\n"
            action_space_snippet += f"  Type: {env_vars.action_space.get('type', 'unknown')}\n"
            action_space_snippet += f"  Description: {env_vars.action_space.get('description', 'No description')}\n"
            if 'variables' in env_vars.action_space:
                action_space_snippet += "  Variables:\n"
                for var in env_vars.action_space['variables']:
                    action_space_snippet += f"    - {var}\n"
            snippets.append(action_space_snippet)
        
        return snippets
    
    def get_context_for_llm(self) -> str:
        """
        Get environment context formatted for LLM input.
        
        Returns:
            Formatted string containing environment context for LLM
        """
        if not self.context_snippets:
            raise EnvironmentContextError("No environment context loaded. Call load_environment() first.")
        
        return "\n".join(self.context_snippets)
    
    def get_state_variables(self) -> Dict[str, Any]:
        """
        Get state variables from environment context.
        
        Returns:
            Dictionary of state variables
            
        Raises:
            EnvironmentContextError: If no environment context is loaded
        """
        if self.environment_context is None:
            raise EnvironmentContextError("No environment context loaded. Call load_environment() first.")
        
        return self.environment_context.state_vars
    
    def get_action_variables(self) -> Dict[str, Any]:
        """
        Get action variables from environment context.
        
        Returns:
            Dictionary of action variables
            
        Raises:
            EnvironmentContextError: If no environment context is loaded
        """
        if self.environment_context is None:
            raise EnvironmentContextError("No environment context loaded. Call load_environment() first.")
        
        return self.environment_context.action_vars
    
    def get_observation_space(self) -> Dict[str, Any]:
        """
        Get observation space from environment context.
        
        Returns:
            Dictionary describing observation space
            
        Raises:
            EnvironmentContextError: If no environment context is loaded
        """
        if self.environment_context is None:
            raise EnvironmentContextError("No environment context loaded. Call load_environment() first.")
        
        return self.environment_context.observation_space
    
    def get_action_space(self) -> Dict[str, Any]:
        """
        Get action space from environment context.
        
        Returns:
            Dictionary describing action space
            
        Raises:
            EnvironmentContextError: If no environment context is loaded
        """
        if self.environment_context is None:
            raise EnvironmentContextError("No environment context loaded. Call load_environment() first.")
        
        return self.environment_context.action_space

# Example usage
if __name__ == "__main__":
    # Example environment source code
    example_env_code = """
import numpy as np

class SimpleEnvironment:
    def __init__(self):
        self.state = np.array([0.0, 0.0])
        self.action = np.array([0.0, 0.0])
        self.observation_space = {"type": "box", "shape": (2,)}
        self.action_space = {"type": "box", "shape": (2,)}
    
    def step(self, action):
        self.state += action
        reward = -np.sum(np.square(self.state))
        return self.state, reward, False, {}
    
    def reset(self):
        self.state = np.array([0.0, 0.0])
        return self.state
"""
    
    # Initialize the environment context module
    env_module = EnvironmentContextModule()
    
    # Load environment
    try:
        context = env_module.load_environment(example_env_code)
        print("Environment context loaded successfully!")
        print("State variables:", context["state_variables"])
        print("Action variables:", context["action_variables"])
        print("Observation space:", context["observation_space"])
        print("Action space:", context["action_space"])
        
        # Get context for LLM
        llm_context = env_module.get_context_for_llm()
        print("\nContext for LLM:")
        print(llm_context)
        
    except EnvironmentContextError as e:
        print(f"Error loading environment: {e}")