"""
PromptSampling module for AlphaEvolve: A coding agent for scientific and algorithmic discovery.

This module generates diverse prompts for creative code generation using various sampling 
strategies and heuristics as described in the paper.
"""

import json
import random
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import jax
import jax.numpy as jnp
import flax
from flax import linen as nn
import numpy as np

@dataclass
class PromptTemplate:
    """Template for prompt generation with placeholders and alternatives."""
    template: str
    placeholders: Dict[str, List[str]]
    probability_distribution: Dict[str, List[float]]

@dataclass
class SamplingConfig:
    """Configuration for prompt sampling strategies."""
    stochastic_formatting: bool = True
    meta_prompt_evolution: bool = True
    explicit_context: bool = True
    rendered_evaluation_results: bool = True
    template_config_file: str = "templates/config.json"
    meta_prompt_database: str = "meta_prompts.db"

class PromptSampling:
    """
    Generates diverse prompts for creative code generation using various sampling 
    strategies and heuristics.
    
    Implements:
    - Stochastic formatting with template placeholders and human-provided alternatives
    - Meta prompt evolution co-evolved in a separate database
    - Explicit context from problem specifications
    - Rendered evaluation results as part of prompt composition
    """
    
    def __init__(self, config: SamplingConfig):
        self.config = config
        self.templates = {}
        self.meta_prompts_db = {}
        self._load_templates()
        self._load_meta_prompts()
        
    def _load_templates(self):
        """Load template configurations from JSON file."""
        try:
            with open(self.config.template_config_file, 'r') as f:
                template_data = json.load(f)
            
            for template_name, template_info in template_data.items():
                self.templates[template_name] = PromptTemplate(
                    template=template_info['template'],
                    placeholders=template_info['placeholders'],
                    probability_distribution=template_info.get('probabilities', {})
                )
        except FileNotFoundError:
            # Create default templates if config file doesn't exist
            self._create_default_templates()
    
    def _create_default_templates(self):
        """Create default prompt templates for demonstration."""
        self.templates['algorithmic_problem'] = PromptTemplate(
            template="Implement a {algorithm_type} algorithm to solve {problem_description}. "
                     "Use {programming_language} and follow {approach_style} approach.",
            placeholders={
                'algorithm_type': ['sorting', 'searching', 'graph traversal', 'dynamic programming'],
                'problem_description': ['the shortest path problem', 'maximum subarray sum', 
                                      'binary tree traversal', 'knapsack problem'],
                'programming_language': ['Python', 'C++', 'Java', 'JavaScript'],
                'approach_style': ['divide and conquer', 'greedy', 'recursive', 'iterative']
            },
            probability_distribution={
                'algorithm_type': [0.25, 0.25, 0.25, 0.25],
                'problem_description': [0.25, 0.25, 0.25, 0.25],
                'programming_language': [0.25, 0.25, 0.25, 0.25],
                'approach_style': [0.25, 0.25, 0.25, 0.25]
            }
        )
        
        self.templates['scientific_problem'] = PromptTemplate(
            template="Develop a {mathematical_model} to model {phenomenon}. "
                     "Include {equation_type} and validate with {test_method}.",
            placeholders={
                'mathematical_model': ['differential equation', 'statistical model', 
                                     'machine learning model', 'optimization problem'],
                'phenomenon': ['population growth', 'heat conduction', 'financial market', 'neural network'],
                'equation_type': ['ordinary differential equations', 'partial differential equations',
                                'linear regression', 'gradient descent'],
                'test_method': ['cross-validation', 'simulation', 'experimental data', 'theoretical analysis']
            },
            probability_distribution={
                'mathematical_model': [0.25, 0.25, 0.25, 0.25],
                'phenomenon': [0.25, 0.25, 0.25, 0.25],
                'equation_type': [0.25, 0.25, 0.25, 0.25],
                'test_method': [0.25, 0.25, 0.25, 0.25]
            }
        )
    
    def _load_meta_prompts(self):
        """Load meta-prompts from database for co-evolution."""
        # TODO: Implement actual database loading logic
        # This would typically load from a separate database file or connection
        self.meta_prompts_db = {
            'meta_prompt_1': "You are an expert in {domain} problem solving. "
                           "Generate code that is efficient, readable, and follows best practices.",
            'meta_prompt_2': "Solve the following problem using {approach}. "
                           "Ensure your solution handles edge cases appropriately."
        }
    
    def _stochastic_formatting(self, template_name: str) -> str:
        """
        Apply stochastic formatting to template placeholders with human-provided 
        alternatives using probability distributions.
        
        Args:
            template_name: Name of the template to instantiate
            
        Returns:
            Formatted prompt string
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
            
        template = self.templates[template_name]
        prompt = template.template
        
        # Sample placeholders according to probability distributions
        for placeholder, alternatives in template.placeholders.items():
            if placeholder in template.probability_distribution:
                probs = template.probability_distribution[placeholder]
                # Sample with replacement using probabilities
                selected_alt = np.random.choice(alternatives, p=probs)
            else:
                # Default to uniform sampling
                selected_alt = random.choice(alternatives)
                
            prompt = prompt.replace(f"{{{placeholder}}}", selected_alt)
            
        return prompt
    
    def _meta_prompt_evolution(self) -> str:
        """
        Generate meta-prompt using co-evolved prompts from database.
        
        Returns:
            Generated meta-prompt string
        """
        # TODO: Implement actual meta-prompt evolution logic
        # This would involve selecting and combining prompts from the meta-prompts database
        # based on evolutionary selection criteria
        
        if not self.meta_prompts_db:
            return "You are a helpful AI assistant that generates code solutions."
            
        # For now, return a random meta-prompt for demonstration
        prompt_key = random.choice(list(self.meta_prompts_db.keys()))
        return self.meta_prompts_db[prompt_key]
    
    def _explicit_context(self, problem_spec: Dict[str, Any]) -> str:
        """
        Add explicit context from problem specifications.
        
        Args:
            problem_spec: Dictionary containing problem details
            
        Returns:
            Context string with problem details
        """
        # TODO: Implement more sophisticated context generation
        # This should include human-written instructions, equations, code snippets,
        # or relevant literature
        
        context_parts = []
        
        if 'instructions' in problem_spec:
            context_parts.append(f"Instructions: {problem_spec['instructions']}")
            
        if 'equations' in problem_spec:
            eq_str = "; ".join(problem_spec['equations'])
            context_parts.append(f"Relevant equations: {eq_str}")
            
        if 'code_snippets' in problem_spec:
            snippet_str = "; ".join(problem_spec['code_snippets'])
            context_parts.append(f"Reference code snippets: {snippet_str}")
            
        if 'literature' in problem_spec:
            lit_str = "; ".join(problem_spec['literature'])
            context_parts.append(f"Relevant literature: {lit_str}")
            
        return "\n".join(context_parts) if context_parts else ""
    
    def _rendered_evaluation_results(self, evaluation_data: List[Dict[str, Any]]) -> str:
        """
        Include rendered evaluation results in prompt.
        
        Args:
            evaluation_data: List of evaluation results
            
        Returns:
            Formatted evaluation results string
        """
        # TODO: Implement proper rendering of evaluation results
        # This should include programs, execution results, and scores
        
        if not evaluation_data:
            return ""
            
        results_str = "Previous evaluation results:\n"
        for i, result in enumerate(evaluation_data[:3]):  # Limit to first 3 results
            results_str += f"Result {i+1}:\n"
            results_str += f"  Program: {result.get('program', 'N/A')}\n"
            results_str += f"  Execution Result: {result.get('execution_result', 'N/A')}\n"
            results_str += f"  Score: {result.get('score', 'N/A')}\n\n"
            
        return results_str
    
    def generate_prompt(self, 
                       problem_spec: Dict[str, Any],
                       evaluation_data: Optional[List[Dict[str, Any]]] = None,
                       template_name: str = "algorithmic_problem") -> str:
        """
        Generate a diverse prompt for creative code generation.
        
        Args:
            problem_spec: Dictionary containing problem details
            evaluation_data: Previous evaluation results to include in prompt
            template_name: Name of the template to use
            
        Returns:
            Generated prompt string
        """
        # Initialize components
        components = []
        
        # Add meta-prompt if enabled
        if self.config.meta_prompt_evolution:
            meta_prompt = self._meta_prompt_evolution()
            components.append(meta_prompt)
        
        # Add stochastic formatting
        if self.config.stochastic_formatting:
            formatted_prompt = self._stochastic_formatting(template_name)
            components.append(formatted_prompt)
        
        # Add explicit context
        if self.config.explicit_context:
            explicit_context = self._explicit_context(problem_spec)
            if explicit_context:
                components.append(explicit_context)
        
        # Add rendered evaluation results
        if self.config.rendered_evaluation_results and evaluation_data:
            eval_results = self._rendered_evaluation_results(evaluation_data)
            if eval_results:
                components.append(eval_results)
        
        # Combine all components
        prompt = "\n\n".join(components)
        return prompt
    
    def generate_multiple_prompts(self, 
                                 problem_spec: Dict[str, Any],
                                 num_prompts: int = 5,
                                 evaluation_data: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """
        Generate multiple diverse prompts for the same problem.
        
        Args:
            problem_spec: Dictionary containing problem details
            num_prompts: Number of prompts to generate
            evaluation_data: Previous evaluation results to include in prompts
            
        Returns:
            List of generated prompt strings
        """
        prompts = []
        for _ in range(num_prompts):
            prompt = self.generate_prompt(
                problem_spec=problem_spec,
                evaluation_data=evaluation_data,
                template_name=random.choice(list(self.templates.keys()))
            )
            prompts.append(prompt)
            
        return prompts

# JAX/Flax integration for efficient sampling
class PromptSamplingJAX:
    """
    JAX/Flax optimized version of PromptSampling for efficient computation.
    
    Uses JAX's functional programming model and automatic differentiation 
    for sampling strategies that benefit from vectorized operations.
    """
    
    def __init__(self, config: SamplingConfig):
        self.config = config
        self.prompt_sampler = PromptSampling(config)
        
    @staticmethod
    @jax.jit
    def _sample_with_jax(probabilities: jnp.ndarray) -> int:
        """
        Sample from probability distribution using JAX.
        
        Args:
            probabilities: Probability distribution as JAX array
            
        Returns:
            Sampled index
        """
        # Normalize probabilities
        probs = probabilities / jnp.sum(probabilities)
        # Sample using Gumbel-max trick for differentiable sampling
        gumbel = -jnp.log(-jnp.log(jax.random.uniform(jax.random.PRNGKey(0), probs.shape)))
        return jnp.argmax(probs + gumbel)
    
    def generate_prompts_jax(self, 
                           problem_spec: Dict[str, Any],
                           num_prompts: int = 5,
                           evaluation_data: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """
        Generate prompts using JAX optimizations.
        
        Args:
            problem_spec: Dictionary containing problem details
            num_prompts: Number of prompts to generate
            evaluation_data: Previous evaluation results
            
        Returns:
            List of generated prompt strings
        """
        # For demonstration, we'll use the regular implementation but show how
        # JAX could be integrated for sampling-heavy operations
        
        return self.prompt_sampler.generate_multiple_prompts(
            problem_spec=problem_spec,
            num_prompts=num_prompts,
            evaluation_data=evaluation_data
        )

# Example usage and demo
def demo_prompt_sampling():
    """Demonstrate the PromptSampling module functionality."""
    
    # Configuration
    config = SamplingConfig(
        stochastic_formatting=True,
        meta_prompt_evolution=True,
        explicit_context=True,
        rendered_evaluation_results=True
    )
    
    # Initialize sampler
    sampler = PromptSampling(config)
    
    # Example problem specification
    problem_spec = {
        'instructions': 'Implement an efficient algorithm to find the maximum sum of a contiguous subarray',
        'equations': ['Kadane\'s algorithm', 'Dynamic programming recurrence'],
        'code_snippets': ['def kadane(arr): ...'],
        'literature': ['Kadane, J. (1984). Maximum subarray problem']
    }
    
    # Example evaluation data
    evaluation_data = [
        {
            'program': 'def max_subarray_sum(arr):\n    max_ending_here = max_so_far = arr[0]\n    for x in arr[1:]:\n        max_ending_here = max(x, max_ending_here + x)\n        max_so_far = max(max_so_far, max_ending_here)\n    return max_so_far',
            'execution_result': 'Success',
            'score': 0.95
        }
    ]
    
    # Generate single prompt
    print("Single Prompt:")
    single_prompt = sampler.generate_prompt(
        problem_spec=problem_spec,
        evaluation_data=evaluation_data
    )
    print(single_prompt)
    print("\n" + "="*80 + "\n")
    
    # Generate multiple prompts
    print("Multiple Prompts:")
    multiple_prompts = sampler.generate_multiple_prompts(
        problem_spec=problem_spec,
        num_prompts=3,
        evaluation_data=evaluation_data
    )
    
    for i, prompt in enumerate(multiple_prompts, 1):
        print(f"Prompt {i}:")
        print(prompt)
        print("-" * 40)

if __name__ == "__main__":
    demo_prompt_sampling()