"""
PromptSampling module for AlphaEvolve: A coding agent for scientific and algorithmic discovery.

This module generates diverse prompts from natural language descriptions to guide 
the coding agent's creative generation process. It implements stochastic formatting 
using template placeholders with human-provided alternatives instantiated using 
probability distributions.
"""

import json
import random
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PromptTemplate:
    """Data class representing a prompt template with placeholders and alternatives."""
    name: str
    template: str
    placeholders: Dict[str, List[str]]
    probabilities: Dict[str, List[float]]

class PromptSampling:
    """
    Generates diverse prompts from natural language descriptions to guide 
    the coding agent's creative generation process.
    
    Implements stochastic formatting using template placeholders with human-provided 
    alternatives instantiated using probability distributions.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the PromptSampling module.
        
        Args:
            config_path (str, optional): Path to configuration file containing
                                       prompt templates and probability distributions
        """
        self.templates: Dict[str, PromptTemplate] = {}
        self.config_path = config_path
        
        if config_path:
            self._load_config(config_path)
        else:
            # Default templates for demonstration
            self._initialize_default_templates()
    
    def _load_config(self, config_path: str) -> None:
        """
        Load prompt templates and probability distributions from configuration file.
        
        Args:
            config_path (str): Path to the configuration JSON file
        """
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            for template_data in config.get('templates', []):
                template = PromptTemplate(
                    name=template_data['name'],
                    template=template_data['template'],
                    placeholders=template_data['placeholders'],
                    probabilities=template_data.get('probabilities', {})
                )
                self.templates[template.name] = template
                
            logger.info(f"Loaded {len(self.templates)} prompt templates from {config_path}")
            
        except FileNotFoundError:
            logger.warning(f"Config file not found at {config_path}. Using default templates.")
            self._initialize_default_templates()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._initialize_default_templates()
    
    def _initialize_default_templates(self) -> None:
        """Initialize default prompt templates for demonstration purposes."""
        # TODO: This should be replaced with actual templates from the paper
        # that are relevant to scientific and algorithmic discovery tasks
        
        default_templates = [
            PromptTemplate(
                name="algorithmic_problem",
                template="Implement an algorithm to solve {problem_type} problem. "
                         "The solution should be efficient and handle edge cases. "
                         "Use {programming_language} and follow {coding_style} style.",
                placeholders={
                    "problem_type": ["sorting", "searching", "graph traversal", "dynamic programming"],
                    "programming_language": ["Python", "C++", "Java", "JavaScript"],
                    "coding_style": ["clean", "concise", "well-documented", "optimized"]
                },
                probabilities={
                    "problem_type": [0.25, 0.25, 0.25, 0.25],
                    "programming_language": [0.3, 0.3, 0.2, 0.2],
                    "coding_style": [0.25, 0.25, 0.25, 0.25]
                }
            ),
            PromptTemplate(
                name="mathematical_proof",
                template="Provide a mathematical proof for {theorem_name}. "
                         "The proof should be rigorous and include all necessary steps. "
                         "Use {notation_style} notation and {proof_method} method.",
                placeholders={
                    "theorem_name": ["Pythagorean theorem", "Fundamental theorem of calculus", 
                                   "Prime number theorem", "Central limit theorem"],
                    "notation_style": ["standard", "LaTeX", "mathematical", "formal"],
                    "proof_method": ["inductive", "constructive", "contradiction", "direct"]
                },
                probabilities={
                    "theorem_name": [0.25, 0.25, 0.25, 0.25],
                    "notation_style": [0.3, 0.3, 0.2, 0.2],
                    "proof_method": [0.25, 0.25, 0.25, 0.25]
                }
            )
        ]
        
        for template in default_templates:
            self.templates[template.name] = template
    
    def _sample_from_distribution(self, alternatives: List[str], 
                                probabilities: Optional[List[float]] = None) -> str:
        """
        Sample an alternative from a list using probability distribution.
        
        Args:
            alternatives (List[str]): List of possible alternatives
            probabilities (List[float], optional): Probability distribution for alternatives
            
        Returns:
            str: Selected alternative
        """
        if not alternatives:
            return ""
            
        if probabilities and len(probabilities) == len(alternatives):
            # Normalize probabilities to ensure they sum to 1
            total = sum(probabilities)
            if total > 0:
                normalized_probs = [p/total for p in probabilities]
                return random.choices(alternatives, weights=normalized_probs)[0]
        
        # If no valid probability distribution, sample uniformly
        return random.choice(alternatives)
    
    def _fill_template(self, template: PromptTemplate, 
                      context: Optional[Dict[str, str]] = None) -> str:
        """
        Fill a prompt template with sampled alternatives.
        
        Args:
            template (PromptTemplate): Template to fill
            context (Dict[str, str], optional): Additional context for filling
            
        Returns:
            str: Filled prompt
        """
        prompt = template.template
        
        # Process placeholders in the template
        for placeholder_name, alternatives in template.placeholders.items():
            # Check if there's a specific value in context
            if context and placeholder_name in context:
                replacement = context[placeholder_name]
            else:
                # Sample from probability distribution
                probabilities = template.probabilities.get(placeholder_name)
                replacement = self._sample_from_distribution(alternatives, probabilities)
            
            # Replace placeholder with sampled value
            prompt = prompt.replace(f"{{{placeholder_name}}}", replacement)
        
        return prompt
    
    def generate_prompt(self, template_name: str, 
                       context: Optional[Dict[str, str]] = None,
                       num_samples: int = 1) -> List[str]:
        """
        Generate diverse prompts using specified template.
        
        Args:
            template_name (str): Name of the template to use
            context (Dict[str, str], optional): Additional context for prompt generation
            num_samples (int): Number of prompts to generate
            
        Returns:
            List[str]: List of generated prompts
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found. Available templates: {list(self.templates.keys())}")
        
        template = self.templates[template_name]
        prompts = []
        
        for _ in range(num_samples):
            prompt = self._fill_template(template, context)
            prompts.append(prompt)
        
        return prompts
    
    def generate_prompts_from_description(self, description: str,
                                        num_prompts: int = 5) -> List[str]:
        """
        Generate diverse prompts from a natural language description.
        
        This method attempts to automatically select appropriate templates based on
        the content of the description.
        
        Args:
            description (str): Natural language description of the problem
            num_prompts (int): Number of prompts to generate
            
        Returns:
            List[str]: List of generated prompts
        """
        # TODO: Implement automatic template selection based on description analysis
        # This could use NLP techniques or keyword matching
        
        # For now, we'll use a default approach - sample from all available templates
        selected_template = random.choice(list(self.templates.values()))
        
        # Create context based on description (simplified)
        context = self._create_context_from_description(description)
        
        return self.generate_prompt(selected_template.name, context, num_prompts)
    
    def _create_context_from_description(self, description: str) -> Dict[str, str]:
        """
        Create context dictionary from natural language description.
        
        Args:
            description (str): Natural language description
            
        Returns:
            Dict[str, str]: Context dictionary for prompt generation
        """
        # TODO: Implement more sophisticated NLP-based context creation
        # This could involve keyword extraction, intent classification, etc.
        
        context = {}
        
        # Simple keyword-based approach for demonstration
        keywords = description.lower().split()
        
        if any(word in keywords for word in ['algorithm', 'sort', 'search']):
            context['problem_type'] = 'sorting'
        elif any(word in keywords for word in ['math', 'proof', 'theorem']):
            context['problem_type'] = 'mathematical proof'
        else:
            context['problem_type'] = random.choice(['sorting', 'searching', 'graph traversal'])
        
        if any(word in keywords for word in ['python', 'code']):
            context['programming_language'] = 'Python'
        elif any(word in keywords for word in ['c++', 'cpp']):
            context['programming_language'] = 'C++'
        else:
            context['programming_language'] = random.choice(['Python', 'C++', 'Java'])
            
        return context
    
    def add_template(self, template: PromptTemplate) -> None:
        """
        Add a new prompt template to the collection.
        
        Args:
            template (PromptTemplate): Template to add
        """
        self.templates[template.name] = template
        logger.info(f"Added template '{template.name}'")
    
    def get_available_templates(self) -> List[str]:
        """
        Get list of available prompt templates.
        
        Returns:
            List[str]: Names of available templates
        """
        return list(self.templates.keys())
    
    def save_config(self, output_path: str) -> None:
        """
        Save current configuration to a JSON file.
        
        Args:
            output_path (str): Path to save the configuration
        """
        config_data = {
            "templates": [
                {
                    "name": template.name,
                    "template": template.template,
                    "placeholders": template.placeholders,
                    "probabilities": template.probabilities
                }
                for template in self.templates.values()
            ]
        }
        
        with open(output_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        logger.info(f"Configuration saved to {output_path}")


# Example usage and demonstration
def demo_prompt_sampling():
    """Demonstrate the PromptSampling module functionality."""
    
    print("=== AlphaEvolve Prompt Sampling Demo ===\n")
    
    # Initialize the prompt sampling module
    prompt_sampler = PromptSampling()
    
    print("Available templates:", prompt_sampler.get_available_templates())
    print()
    
    # Generate prompts using specific template
    print("1. Generating prompts using 'algorithmic_problem' template:")
    prompts = prompt_sampler.generate_prompt(
        "algorithmic_problem", 
        num_samples=3
    )
    
    for i, prompt in enumerate(prompts, 1):
        print(f"   Prompt {i}: {prompt}")
    
    print()
    
    # Generate prompts using 'mathematical_proof' template
    print("2. Generating prompts using 'mathematical_proof' template:")
    math_prompts = prompt_sampler.generate_prompt(
        "mathematical_proof", 
        num_samples=2
    )
    
    for i, prompt in enumerate(math_prompts, 1):
        print(f"   Prompt {i}: {prompt}")
    
    print()
    
    # Generate prompts from natural language description
    print("3. Generating prompts from natural language description:")
    description = "Implement a sorting algorithm that handles edge cases efficiently"
    desc_prompts = prompt_sampler.generate_prompts_from_description(
        description, 
        num_prompts=2
    )
    
    for i, prompt in enumerate(desc_prompts, 1):
        print(f"   Prompt {i}: {prompt}")
    
    print()
    
    # Add a custom template
    print("4. Adding a custom template:")
    custom_template = PromptTemplate(
        name="scientific_simulation",
        template="Create a simulation for {phenomenon} using {methodology}. "
                 "The model should include {components} and validate results against "
                 "{validation_criteria}. Use {programming_language} for implementation.",
        placeholders={
            "phenomenon": ["quantum tunneling", "population dynamics", "fluid flow"],
            "methodology": ["Monte Carlo", "finite element", "agent-based"],
            "components": ["boundary conditions", "initial states", "parameter sets"],
            "validation_criteria": ["experimental data", "theoretical predictions", "statistical tests"],
            "programming_language": ["Python", "MATLAB", "Julia"]
        },
        probabilities={
            "phenomenon": [0.3, 0.3, 0.4],
            "methodology": [0.3, 0.3, 0.4],
            "components": [0.2, 0.3, 0.5],
            "validation_criteria": [0.3, 0.3, 0.4],
            "programming_language": [0.4, 0.3, 0.3]
        }
    )
    
    prompt_sampler.add_template(custom_template)
    print("   Added 'scientific_simulation' template")
    
    # Generate from custom template
    custom_prompts = prompt_sampler.generate_prompt(
        "scientific_simulation",
        num_samples=2
    )
    
    for i, prompt in enumerate(custom_prompts, 1):
        print(f"   Prompt {i}: {prompt}")


if __name__ == "__main__":
    # Run the demo
    demo_prompt_sampling()