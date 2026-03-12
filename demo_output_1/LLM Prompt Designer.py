"""
LLM Prompt Designer Module

This module generates and manages prompts for LLMs to produce reward functions,
supporting both initialization and reflection phases as described in the paper
"Human-level Reward Design via Coding Large Language Models".

The module implements:
- Prompt generation for reward function initialization
- Prompt generation for reward reflection
- Prompt management and caching
- Integration with environment context
"""

import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class EnvironmentContext:
    """Represents the environment context for reward function design."""
    state_space: Dict[str, Any]
    action_space: Dict[str, Any]
    task_description: str
    constraints: List[str]
    reward_examples: List[Dict[str, Any]]

@dataclass
class PromptTemplate:
    """Template for LLM prompts with placeholders."""
    name: str
    template: str
    placeholders: List[str]
    description: str

class PromptDesigner(ABC):
    """Abstract base class for prompt designers."""
    
    def __init__(self):
        self.prompt_templates: Dict[str, PromptTemplate] = {}
        self.cache: Dict[str, str] = {}
    
    @abstractmethod
    def generate_prompt(self, context: EnvironmentContext, **kwargs) -> str:
        """Generate a prompt for the given context."""
        pass
    
    def _generate_cache_key(self, prompt: str, **kwargs) -> str:
        """Generate a cache key for the prompt."""
        key_string = f"{prompt}_{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get_cached_prompt(self, prompt: str, **kwargs) -> Optional[str]:
        """Retrieve a cached prompt if available."""
        cache_key = self._generate_cache_key(prompt, **kwargs)
        return self.cache.get(cache_key)
    
    def cache_prompt(self, prompt: str, generated_prompt: str, **kwargs) -> None:
        """Cache a generated prompt."""
        cache_key = self._generate_cache_key(prompt, **kwargs)
        self.cache[cache_key] = generated_prompt

class RewardInitializationPromptDesigner(PromptDesigner):
    """Designs prompts for initializing reward functions."""
    
    def __init__(self):
        super().__init__()
        self._initialize_templates()
    
    def _initialize_templates(self):
        """Initialize prompt templates for reward initialization."""
        self.prompt_templates = {
            "basic_reward_design": PromptTemplate(
                name="basic_reward_design",
                template="""
You are an expert in reinforcement learning and reward function design. 
Your task is to design a reward function for the following environment:

Environment Description:
{task_description}

State Space:
{state_space}

Action Space:
{action_space}

Constraints:
{constraints}

Examples of good reward functions:
{reward_examples}

Please design a reward function that:
1. Encourages the agent to achieve the desired behavior
2. Is well-defined and computationally efficient
3. Avoids unintended consequences
4. Is aligned with human values

Return only the reward function code in Python format.
                """,
                placeholders=["task_description", "state_space", "action_space", "constraints", "reward_examples"],
                description="Basic reward function design prompt"
            ),
            "human_aligned_reward": PromptTemplate(
                name="human_aligned_reward",
                template="""
You are an expert in human-aligned reinforcement learning. 
Design a reward function that aligns with human values and intentions.

Environment Context:
{task_description}

State Space:
{state_space}

Action Space:
{action_space}

Constraints:
{constraints}

Human Feedback Examples:
{reward_examples}

Design a reward function that:
1. Incorporates human values and intentions
2. Is robust to different interpretations
3. Provides clear guidance to the agent
4. Is interpretable and explainable

Return only the reward function code in Python format.
                """,
                placeholders=["task_description", "state_space", "action_space", "constraints", "reward_examples"],
                description="Human-aligned reward function design prompt"
            )
        }
    
    def generate_prompt(self, context: EnvironmentContext, template_name: str = "basic_reward_design") -> str:
        """Generate a reward initialization prompt."""
        # Check cache first
        cached = self.get_cached_prompt(template_name, context=context)
        if cached:
            logger.info("Using cached prompt for reward initialization")
            return cached
        
        # Get template
        template = self.prompt_templates.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}")
        
        # Fill placeholders
        filled_prompt = template.template.format(
            task_description=context.task_description,
            state_space=json.dumps(context.state_space, indent=2),
            action_space=json.dumps(context.action_space, indent=2),
            constraints="\n".join(context.constraints),
            reward_examples=json.dumps(context.reward_examples, indent=2)
        )
        
        # Cache the result
        self.cache_prompt(template_name, filled_prompt, context=context)
        
        return filled_prompt

class RewardReflectionPromptDesigner(PromptDesigner):
    """Designs prompts for reward reflection and refinement."""
    
    def __init__(self):
        super().__init__()
        self._initialize_templates()
    
    def _initialize_templates(self):
        """Initialize prompt templates for reward reflection."""
        self.prompt_templates = {
            "reflection_initial": PromptTemplate(
                name="reflection_initial",
                template="""
You are an expert in reward function refinement and human feedback integration. 
You will analyze and improve a reward function based on human feedback.

Current Reward Function:
{current_reward_function}

Human Feedback:
{human_feedback}

Previous Reward Function:
{previous_reward_function}

Environment Context:
{task_description}

State Space:
{state_space}

Action Space:
{action_space}

Constraints:
{constraints}

Please analyze the feedback and suggest improvements to the reward function. 
Consider:
1. Alignment with human intentions
2. Avoiding unintended consequences
3. Improving performance metrics
4. Maintaining interpretability

Return only the improved reward function code in Python format.
                """,
                placeholders=["current_reward_function", "human_feedback", "previous_reward_function", 
                            "task_description", "state_space", "action_space", "constraints"],
                description="Initial reward reflection prompt"
            ),
            "reflection_iteration": PromptTemplate(
                name="reflection_iteration",
                template="""
You are an expert in reward function refinement. 
You will iteratively improve a reward function based on multiple feedback rounds.

Current Reward Function:
{current_reward_function}

Human Feedback Round {round_number}:
{human_feedback}

Previous Reward Function:
{previous_reward_function}

Environment Context:
{task_description}

State Space:
{state_space}

Action Space:
{action_space}

Constraints:
{constraints}

Please analyze the feedback and suggest improvements. 
Consider:
1. Iterative refinement approach
2. Consistency with previous improvements
3. Addressing specific feedback points
4. Maintaining reward function quality

Return only the improved reward function code in Python format.
                """,
                placeholders=["current_reward_function", "human_feedback", "previous_reward_function", 
                            "task_description", "state_space", "action_space", "constraints", "round_number"],
                description="Iterative reward reflection prompt"
            ),
            "comprehensive_reflection": PromptTemplate(
                name="comprehensive_reflection",
                template="""
You are an expert in comprehensive reward function analysis. 
Analyze and improve a reward function considering multiple aspects.

Current Reward Function:
{current_reward_function}

Human Feedback:
{human_feedback}

Previous Reward Function:
{previous_reward_function}

Environment Context:
{task_description}

State Space:
{state_space}

Action Space:
{action_space}

Constraints:
{constraints}

Analysis Requirements:
1. Performance evaluation
2. Human alignment assessment
3. Robustness analysis
4. Interpretability review

Please provide a comprehensive improvement to the reward function that addresses all aspects.
Return only the improved reward function code in Python format.
                """,
                placeholders=["current_reward_function", "human_feedback", "previous_reward_function", 
                            "task_description", "state_space", "action_space", "constraints"],
                description="Comprehensive reward reflection prompt"
            )
        }
    
    def generate_prompt(self, 
                      context: EnvironmentContext,
                      current_reward_function: str,
                      human_feedback: str,
                      previous_reward_function: str = "",
                      round_number: int = 1,
                      template_name: str = "reflection_initial") -> str:
        """Generate a reward reflection prompt."""
        # Check cache first
        cached = self.get_cached_prompt(template_name, 
                                       context=context,
                                       current_reward_function=current_reward_function,
                                       human_feedback=human_feedback,
                                       previous_reward_function=previous_reward_function,
                                       round_number=round_number)
        if cached:
            logger.info("Using cached prompt for reward reflection")
            return cached
        
        # Get template
        template = self.prompt_templates.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}")
        
        # Fill placeholders
        if "round_number" in template.placeholders:
            filled_prompt = template.template.format(
                current_reward_function=current_reward_function,
                human_feedback=human_feedback,
                previous_reward_function=previous_reward_function,
                task_description=context.task_description,
                state_space=json.dumps(context.state_space, indent=2),
                action_space=json.dumps(context.action_space, indent=2),
                constraints="\n".join(context.constraints),
                round_number=round_number
            )
        else:
            filled_prompt = template.template.format(
                current_reward_function=current_reward_function,
                human_feedback=human_feedback,
                previous_reward_function=previous_reward_function,
                task_description=context.task_description,
                state_space=json.dumps(context.state_space, indent=2),
                action_space=json.dumps(context.action_space, indent=2),
                constraints="\n".join(context.constraints)
            )
        
        # Cache the result
        self.cache_prompt(template_name, filled_prompt,
                         context=context,
                         current_reward_function=current_reward_function,
                         human_feedback=human_feedback,
                         previous_reward_function=previous_reward_function,
                         round_number=round_number)
        
        return filled_prompt

class LLMPromptDesigner:
    """Main class for managing LLM prompts in reward function design."""
    
    def __init__(self):
        self.initialization_designer = RewardInitializationPromptDesigner()
        self.reflection_designer = RewardReflectionPromptDesigner()
        self.logger = logging.getLogger(__name__)
    
    def generate_initialization_prompt(self, 
                                     context: EnvironmentContext,
                                     template_name: str = "basic_reward_design") -> str:
        """Generate a prompt for initializing reward functions."""
        self.logger.info("Generating initialization prompt")
        return self.initialization_designer.generate_prompt(context, template_name=template_name)
    
    def generate_reflection_prompt(self,
                                 context: EnvironmentContext,
                                 current_reward_function: str,
                                 human_feedback: str,
                                 previous_reward_function: str = "",
                                 round_number: int = 1,
                                 template_name: str = "reflection_initial") -> str:
        """Generate a prompt for reward function reflection."""
        self.logger.info("Generating reflection prompt")
        return self.reflection_designer.generate_prompt(
            context=context,
            current_reward_function=current_reward_function,
            human_feedback=human_feedback,
            previous_reward_function=previous_reward_function,
            round_number=round_number,
            template_name=template_name
        )
    
    def get_available_templates(self) -> Dict[str, Dict[str, str]]:
        """Get all available prompt templates."""
        return {
            "initialization": {
                name: template.description 
                for name, template in self.initialization_designer.prompt_templates.items()
            },
            "reflection": {
                name: template.description 
                for name, template in self.reflection_designer.prompt_templates.items()
            }
        }

# Example usage and demonstration
def demo_prompt_designer():
    """Demonstrate the LLM Prompt Designer functionality."""
    
    # Create environment context
    context = EnvironmentContext(
        state_space={
            "position": {"type": "continuous", "range": [-10, 10]},
            "velocity": {"type": "continuous", "range": [-5, 5]},
            "time": {"type": "discrete", "range": [0, 100]}
        },
        action_space={
            "accelerate": {"type": "continuous", "range": [-1, 1]},
            "brake": {"type": "continuous", "range": [0, 1]}
        },
        task_description="Navigate a car to reach a target position while avoiding obstacles",
        constraints=[
            "Agent must not exceed speed limit of 10 units",
            "Agent must not collide with obstacles",
            "Agent must reach target within 100 time steps"
        ],
        reward_examples=[
            {
                "example": "Simple distance-based reward",
                "code": "def reward(state, action, next_state):\n    return -abs(next_state['position'] - target_position)"
            }
        ]
    )
    
    # Initialize prompt designer
    prompt_designer = LLMPromptDesigner()
    
    # Generate initialization prompt
    print("=== Initialization Prompt ===")
    init_prompt = prompt_designer.generate_initialization_prompt(context)
    print(init_prompt[:500] + "..." if len(init_prompt) > 500 else init_prompt)
    
    # Generate reflection prompt
    print("\n=== Reflection Prompt ===")
    reflection_prompt = prompt_designer.generate_reflection_prompt(
        context=context,
        current_reward_function="def reward(state, action, next_state):\n    return -abs(next_state['position'] - target_position)",
        human_feedback="The reward function doesn't encourage reaching the target quickly enough",
        previous_reward_function="def reward(state, action, next_state):\n    return -abs(next_state['position'] - target_position)"
    )
    print(reflection_prompt[:500] + "..." if len(reflection_prompt) > 500 else reflection_prompt)
    
    # Show available templates
    print("\n=== Available Templates ===")
    templates = prompt_designer.get_available_templates()
    for category, template_list in templates.items():
        print(f"{category.upper()} Templates:")
        for name, description in template_list.items():
            print(f"  - {name}: {description}")

if __name__ == "__main__":
    demo_prompt_designer()