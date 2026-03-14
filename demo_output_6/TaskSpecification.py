"""
TaskSpecification Module

Defines the problem space and constraints for scientific discovery tasks including 
mathematical problems, algorithmic challenges, and optimization problems.

This module provides the foundational structure for specifying tasks that AlphaEvolve
will tackle, including mathematical formulations, constraints, and evaluation criteria.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union
from enum import Enum
import json
import logging

# Configure logging
logger = logging.getLogger(__name__)

class ProblemType(Enum):
    """Enumeration of problem types that can be specified."""
    MATHEMATICAL = "mathematical"
    ALGORITHMIC = "algorithmic"
    OPTIMIZATION = "optimization"
    CRYPTOGRAPHIC = "cryptographic"
    PHYSICAL_SIMULATION = "physical_simulation"

class ConstraintType(Enum):
    """Enumeration of constraint types that can be applied to tasks."""
    TIME_COMPLEXITY = "time_complexity"
    SPACE_COMPLEXITY = "space_complexity"
    RESOURCE_LIMIT = "resource_limit"
    CORRECTNESS = "correctness"
    PROVABILITY = "provability"
    STABILITY = "stability"

@dataclass
class MathematicalProblem:
    """Represents a mathematical problem specification."""
    equation: str
    variables: List[str]
    constraints: List[str]
    solution_space: str
    target_precision: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'equation': self.equation,
            'variables': self.variables,
            'constraints': self.constraints,
            'solution_space': self.solution_space,
            'target_precision': self.target_precision
        }

@dataclass
class AlgorithmicProblem:
    """Represents an algorithmic challenge specification."""
    problem_description: str
    input_format: str
    output_format: str
    expected_complexity: str
    constraints: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'problem_description': self.problem_description,
            'input_format': self.input_format,
            'output_format': self.output_format,
            'expected_complexity': self.expected_complexity,
            'constraints': self.constraints
        }

@dataclass
class OptimizationProblem:
    """Represents an optimization problem specification."""
    objective_function: str
    decision_variables: List[str]
    constraints: List[str]
    bounds: Dict[str, tuple]
    optimization_type: str  # 'minimize' or 'maximize'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'objective_function': self.objective_function,
            'decision_variables': self.decision_variables,
            'constraints': self.constraints,
            'bounds': self.bounds,
            'optimization_type': self.optimization_type
        }

class TaskSpecification(ABC):
    """Abstract base class for task specifications in scientific discovery."""
    
    def __init__(self, 
                 problem_type: ProblemType,
                 description: str,
                 constraints: List[ConstraintType],
                 metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize a task specification.
        
        Args:
            problem_type: Type of the problem (mathematical, algorithmic, etc.)
            description: Human-readable description of the problem
            constraints: List of constraints that must be satisfied
            metadata: Additional metadata about the task
        """
        self.problem_type = problem_type
        self.description = description
        self.constraints = constraints
        self.metadata = metadata or {}
        self.created_at = None  # TODO: Implement timestamp creation
        
    @abstractmethod
    def validate(self) -> bool:
        """Validate that the task specification is well-formed."""
        pass
    
    @abstractmethod
    def get_problem_formulation(self) -> Dict[str, Any]:
        """Get the formal mathematical or algorithmic formulation of the problem."""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task specification to dictionary format."""
        return {
            'problem_type': self.problem_type.value,
            'description': self.description,
            'constraints': [c.value for c in self.constraints],
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskSpecification':
        """Create task specification from dictionary."""
        # TODO: Implement deserialization logic
        raise NotImplementedError("Subclasses must implement this method")

class MathematicalTask(TaskSpecification):
    """Task specification for mathematical problems."""
    
    def __init__(self, 
                 description: str,
                 mathematical_problem: MathematicalProblem,
                 constraints: List[ConstraintType],
                 metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize a mathematical task specification.
        
        Args:
            description: Human-readable description of the mathematical problem
            mathematical_problem: Formal mathematical problem definition
            constraints: List of constraints that must be satisfied
            metadata: Additional metadata about the task
        """
        super().__init__(ProblemType.MATHEMATICAL, description, constraints, metadata)
        self.mathematical_problem = mathematical_problem
        
    def validate(self) -> bool:
        """Validate that the mathematical task is well-formed."""
        # TODO: Implement validation logic for mathematical problems
        # Check equation format, variable definitions, etc.
        logger.info("Validating mathematical task...")
        return True  # Placeholder
    
    def get_problem_formulation(self) -> Dict[str, Any]:
        """Get the formal mathematical formulation of the problem."""
        return {
            'type': 'mathematical',
            'problem': self.mathematical_problem.to_dict(),
            'constraints': [c.value for c in self.constraints]
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert mathematical task specification to dictionary format."""
        base_dict = super().to_dict()
        base_dict['mathematical_problem'] = self.mathematical_problem.to_dict()
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MathematicalTask':
        """Create mathematical task specification from dictionary."""
        # TODO: Implement deserialization logic for MathematicalTask
        raise NotImplementedError("Deserialization not yet implemented")

class AlgorithmicTask(TaskSpecification):
    """Task specification for algorithmic challenges."""
    
    def __init__(self, 
                 description: str,
                 algorithmic_problem: AlgorithmicProblem,
                 constraints: List[ConstraintType],
                 metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize an algorithmic task specification.
        
        Args:
            description: Human-readable description of the algorithmic problem
            algorithmic_problem: Formal algorithmic problem definition
            constraints: List of constraints that must be satisfied
            metadata: Additional metadata about the task
        """
        super().__init__(ProblemType.ALGORITHMIC, description, constraints, metadata)
        self.algorithmic_problem = algorithmic_problem
        
    def validate(self) -> bool:
        """Validate that the algorithmic task is well-formed."""
        # TODO: Implement validation logic for algorithmic problems
        # Check input/output formats, complexity expectations, etc.
        logger.info("Validating algorithmic task...")
        return True  # Placeholder
    
    def get_problem_formulation(self) -> Dict[str, Any]:
        """Get the formal algorithmic formulation of the problem."""
        return {
            'type': 'algorithmic',
            'problem': self.algorithmic_problem.to_dict(),
            'constraints': [c.value for c in self.constraints]
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert algorithmic task specification to dictionary format."""
        base_dict = super().to_dict()
        base_dict['algorithmic_problem'] = self.algorithmic_problem.to_dict()
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlgorithmicTask':
        """Create algorithmic task specification from dictionary."""
        # TODO: Implement deserialization logic for AlgorithmicTask
        raise NotImplementedError("Deserialization not yet implemented")

class OptimizationTask(TaskSpecification):
    """Task specification for optimization problems."""
    
    def __init__(self, 
                 description: str,
                 optimization_problem: OptimizationProblem,
                 constraints: List[ConstraintType],
                 metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize an optimization task specification.
        
        Args:
            description: Human-readable description of the optimization problem
            optimization_problem: Formal optimization problem definition
            constraints: List of constraints that must be satisfied
            metadata: Additional metadata about the task
        """
        super().__init__(ProblemType.OPTIMIZATION, description, constraints, metadata)
        self.optimization_problem = optimization_problem
        
    def validate(self) -> bool:
        """Validate that the optimization task is well-formed."""
        # TODO: Implement validation logic for optimization problems
        # Check objective function, variable bounds, etc.
        logger.info("Validating optimization task...")
        return True  # Placeholder
    
    def get_problem_formulation(self) -> Dict[str, Any]:
        """Get the formal optimization formulation of the problem."""
        return {
            'type': 'optimization',
            'problem': self.optimization_problem.to_dict(),
            'constraints': [c.value for c in self.constraints]
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert optimization task specification to dictionary format."""
        base_dict = super().to_dict()
        base_dict['optimization_problem'] = self.optimization_problem.to_dict()
        return base_dict
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptimizationTask':
        """Create optimization task specification from dictionary."""
        # TODO: Implement deserialization logic for OptimizationTask
        raise NotImplementedError("Deserialization not yet implemented")

class TaskSpecificationFactory:
    """Factory class for creating different types of task specifications."""
    
    @staticmethod
    def create_mathematical_task(
        description: str,
        equation: str,
        variables: List[str],
        constraints: List[str],
        solution_space: str,
        target_precision: float,
        additional_constraints: List[ConstraintType] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MathematicalTask:
        """
        Create a mathematical task specification.
        
        Args:
            description: Human-readable description of the problem
            equation: Mathematical equation to solve
            variables: List of variables involved in the equation
            constraints: List of constraint equations or conditions
            solution_space: The space where solutions are expected to exist
            target_precision: Required precision for the solution
            additional_constraints: Additional constraint types
            metadata: Additional metadata
            
        Returns:
            MathematicalTask instance
        """
        math_problem = MathematicalProblem(
            equation=equation,
            variables=variables,
            constraints=constraints,
            solution_space=solution_space,
            target_precision=target_precision
        )
        
        constraints_list = additional_constraints or []
        return MathematicalTask(
            description=description,
            mathematical_problem=math_problem,
            constraints=constraints_list,
            metadata=metadata
        )
    
    @staticmethod
    def create_algorithmic_task(
        description: str,
        problem_description: str,
        input_format: str,
        output_format: str,
        expected_complexity: str,
        constraints: List[str],
        additional_constraints: List[ConstraintType] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AlgorithmicTask:
        """
        Create an algorithmic task specification.
        
        Args:
            description: Human-readable description of the problem
            problem_description: Description of what needs to be computed
            input_format: Format of the input data
            output_format: Format of the expected output
            expected_complexity: Expected time/space complexity
            constraints: List of algorithmic constraints
            additional_constraints: Additional constraint types
            metadata: Additional metadata
            
        Returns:
            AlgorithmicTask instance
        """
        algo_problem = AlgorithmicProblem(
            problem_description=problem_description,
            input_format=input_format,
            output_format=output_format,
            expected_complexity=expected_complexity,
            constraints=constraints
        )
        
        constraints_list = additional_constraints or []
        return AlgorithmicTask(
            description=description,
            algorithmic_problem=algo_problem,
            constraints=constraints_list,
            metadata=metadata
        )
    
    @staticmethod
    def create_optimization_task(
        description: str,
        objective_function: str,
        decision_variables: List[str],
        constraints: List[str],
        bounds: Dict[str, tuple],
        optimization_type: str,
        additional_constraints: List[ConstraintType] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> OptimizationTask:
        """
        Create an optimization task specification.
        
        Args:
            description: Human-readable description of the problem
            objective_function: Mathematical expression to optimize
            decision_variables: Variables to optimize over
            constraints: List of constraint equations or conditions
            bounds: Bounds for each variable (min, max)
            optimization_type: 'minimize' or 'maximize'
            additional_constraints: Additional constraint types
            metadata: Additional metadata
            
        Returns:
            OptimizationTask instance
        """
        opt_problem = OptimizationProblem(
            objective_function=objective_function,
            decision_variables=decision_variables,
            constraints=constraints,
            bounds=bounds,
            optimization_type=optimization_type
        )
        
        constraints_list = additional_constraints or []
        return OptimizationTask(
            description=description,
            optimization_problem=opt_problem,
            constraints=constraints_list,
            metadata=metadata
        )

# Example usage and testing
def demo_task_specifications():
    """Demonstrate the usage of task specifications."""
    
    # Create a mathematical task (e.g., finding roots of a polynomial)
    math_task = TaskSpecificationFactory.create_mathematical_task(
        description="Find all real roots of the quadratic equation x^2 - 5x + 6 = 0",
        equation="x^2 - 5x + 6 = 0",
        variables=["x"],
        constraints=["x ∈ ℝ"],
        solution_space="Real numbers",
        target_precision=1e-10,
        additional_constraints=[ConstraintType.CORRECTNESS],
        metadata={"domain": "algebra", "difficulty": "intermediate"}
    )
    
    print("Mathematical Task:")
    print(json.dumps(math_task.to_dict(), indent=2))
    print(f"Valid: {math_task.validate()}")
    print()
    
    # Create an algorithmic task (e.g., sorting algorithm)
    algo_task = TaskSpecificationFactory.create_algorithmic_task(
        description="Implement a merge sort algorithm that sorts an array of integers",
        problem_description="Sort an array of integers in ascending order using merge sort",
        input_format="Array of integers [1, 5, 3, 9, 2]",
        output_format="Sorted array [1, 2, 3, 5, 9]",
        expected_complexity="O(n log n)",
        constraints=["Must be stable", "Handle empty arrays"],
        additional_constraints=[ConstraintType.TIME_COMPLEXITY],
        metadata={"domain": "computer_science", "algorithm_type": "sorting"}
    )
    
    print("Algorithmic Task:")
    print(json.dumps(algo_task.to_dict(), indent=2))
    print(f"Valid: {algo_task.validate()}")
    print()
    
    # Create an optimization task (e.g., linear programming)
    opt_task = TaskSpecificationFactory.create_optimization_task(
        description="Minimize cost function subject to resource constraints",
        objective_function="3x + 2y",
        decision_variables=["x", "y"],
        constraints=["2x + y ≤ 10", "x + 3y ≤ 15", "x ≥ 0, y ≥ 0"],
        bounds={"x": (0, float('inf')), "y": (0, float('inf'))},
        optimization_type="minimize",
        additional_constraints=[ConstraintType.RESOURCE_LIMIT],
        metadata={"domain": "operations_research", "method": "linear_programming"}
    )
    
    print("Optimization Task:")
    print(json.dumps(opt_task.to_dict(), indent=2))
    print(f"Valid: {opt_task.validate()}")

if __name__ == "__main__":
    # Run demo
    demo_task_specifications()