"""
Evolution Module for AlphaEvolve: A Coding Agent for Scientific and Algorithmic Discovery

This module implements evolutionary algorithms to iteratively improve code quality
through selection, crossover, and mutation operations. It forms the core of the
evolutionary process that enhances algorithmic solutions over time.

The Evolution module is designed to work in conjunction with other components
of AlphaEvolve such as CreativeGeneration, Evaluation, and PromptSampling.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional, Callable, Tuple
import random
import copy
import logging
from dataclasses import dataclass
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Individual:
    """
    Represents an individual in the evolutionary population.
    
    An individual contains a program/code representation and its associated fitness score.
    """
    code: str
    fitness: float
    generation: int
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class FitnessEvaluator(ABC):
    """
    Abstract base class for fitness evaluation of individuals.
    
    This class defines the interface for evaluating the quality of generated code.
    Subclasses should implement the evaluate method to provide specific evaluation logic.
    """
    
    @abstractmethod
    def evaluate(self, individual: Individual) -> float:
        """
        Evaluate the fitness of an individual.
        
        Args:
            individual: The individual to evaluate
            
        Returns:
            Fitness score (higher is better)
        """
        pass


class EvolutionaryOperator(ABC):
    """
    Abstract base class for evolutionary operators.
    
    Defines the interface for selection, crossover, and mutation operations.
    """
    
    @abstractmethod
    def select(self, population: List[Individual]) -> Individual:
        """
        Select an individual from the population.
        
        Args:
            population: List of individuals to select from
            
        Returns:
            Selected individual
        """
        pass
    
    @abstractmethod
    def crossover(self, parent1: Individual, parent2: Individual) -> Tuple[Individual, Individual]:
        """
        Perform crossover between two parents to produce offspring.
        
        Args:
            parent1: First parent individual
            parent2: Second parent individual
            
        Returns:
            Tuple of two offspring individuals
        """
        pass
    
    @abstractmethod
    def mutate(self, individual: Individual) -> Individual:
        """
        Mutate an individual.
        
        Args:
            individual: Individual to mutate
            
        Returns:
            Mutated individual
        """
        pass


class TournamentSelection(EvolutionaryOperator):
    """
    Tournament selection operator for evolutionary algorithms.
    
    Selects individuals based on tournament competition where multiple individuals
    compete and the best one is selected.
    """
    
    def __init__(self, tournament_size: int = 3):
        self.tournament_size = tournament_size
    
    def select(self, population: List[Individual]) -> Individual:
        """
        Select an individual using tournament selection.
        
        Args:
            population: List of individuals to select from
            
        Returns:
            Selected individual
        """
        if len(population) < self.tournament_size:
            # If population is smaller than tournament size, return best
            return max(population, key=lambda x: x.fitness)
        
        # Select random individuals for tournament
        tournament = random.sample(population, self.tournament_size)
        return max(tournament, key=lambda x: x.fitness)
    
    def crossover(self, parent1: Individual, parent2: Individual) -> Tuple[Individual, Individual]:
        """
        Perform uniform crossover between two parents.
        
        TODO: Implement more sophisticated code-level crossover operations
              that understand the structure of Python code and can perform
              meaningful code recombination.
              
        Args:
            parent1: First parent individual
            parent2: Second parent individual
            
        Returns:
            Tuple of two offspring individuals
        """
        # Simple string-based crossover - this needs to be enhanced for real code
        # For now, we'll just return copies of parents
        return copy.deepcopy(parent1), copy.deepcopy(parent2)
    
    def mutate(self, individual: Individual) -> Individual:
        """
        Apply mutation to an individual.
        
        TODO: Implement code-level mutation operations that can modify Python code
              in meaningful ways such as changing variable names, modifying logic,
              or restructuring code blocks.
              
        Args:
            individual: Individual to mutate
            
        Returns:
            Mutated individual
        """
        # Simple random mutation - this needs enhancement for real code mutation
        mutated_individual = copy.deepcopy(individual)
        
        # For demonstration purposes, we'll just slightly modify the fitness
        # In practice, this should modify the actual code content
        mutated_individual.fitness += random.uniform(-0.1, 0.1)
        
        return mutated_individual


class EvolutionEngine:
    """
    Main evolutionary engine that orchestrates the evolution process.
    
    This class manages the population, evolutionary operators, and evaluation
    to iteratively improve code solutions.
    """
    
    def __init__(
        self,
        fitness_evaluator: FitnessEvaluator,
        evolutionary_operator: EvolutionaryOperator,
        population_size: int = 50,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.8,
        max_generations: int = 100
    ):
        """
        Initialize the evolution engine.
        
        Args:
            fitness_evaluator: Object that evaluates individual fitness
            evolutionary_operator: Object that performs evolutionary operations
            population_size: Number of individuals in each generation
            mutation_rate: Probability of mutation for each individual
            crossover_rate: Probability of crossover between parents
            max_generations: Maximum number of generations to evolve
        """
        self.fitness_evaluator = fitness_evaluator
        self.evolutionary_operator = evolutionary_operator
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.max_generations = max_generations
        
        # Initialize population
        self.population: List[Individual] = []
        self.generation = 0
        self.best_individual: Optional[Individual] = None
        
        logger.info("Evolution engine initialized")
    
    def initialize_population(self, initial_code_samples: List[str]) -> None:
        """
        Initialize the population with given code samples.
        
        Args:
            initial_code_samples: List of initial code strings to seed the population
        """
        self.population = []
        
        # Create individuals from initial code samples
        for i, code in enumerate(initial_code_samples):
            fitness = self.fitness_evaluator.evaluate(
                Individual(code=code, fitness=0.0, generation=0)
            )
            
            individual = Individual(
                code=code,
                fitness=fitness,
                generation=0,
                metadata={"source": "initial"}
            )
            
            self.population.append(individual)
        
        # Fill up population if needed
        while len(self.population) < self.population_size:
            # Generate random code or use some other method to fill population
            # TODO: Implement proper random code generation or sampling from a code corpus
            random_code = "# Random code sample\nprint('Hello, World!')"
            fitness = self.fitness_evaluator.evaluate(
                Individual(code=random_code, fitness=0.0, generation=0)
            )
            
            individual = Individual(
                code=random_code,
                fitness=fitness,
                generation=0,
                metadata={"source": "random"}
            )
            
            self.population.append(individual)
        
        # Update best individual
        self.best_individual = max(self.population, key=lambda x: x.fitness)
        logger.info(f"Population initialized with {len(self.population)} individuals")
    
    def evaluate_population(self) -> None:
        """
        Evaluate fitness of all individuals in the current population.
        
        TODO: Implement parallel evaluation for better performance when dealing
              with large populations or expensive evaluation functions.
        """
        for individual in self.population:
            individual.fitness = self.fitness_evaluator.evaluate(individual)
    
    def evolve(self) -> Individual:
        """
        Run one generation of evolution.
        
        Returns:
            Best individual from the evolved population
        """
        logger.info(f"Starting evolution generation {self.generation}")
        
        # Evaluate current population
        self.evaluate_population()
        
        # Update best individual
        current_best = max(self.population, key=lambda x: x.fitness)
        if self.best_individual is None or current_best.fitness > self.best_individual.fitness:
            self.best_individual = current_best
        
        # Create new population
        new_population = []
        
        # Elitism - keep best individuals
        elite_count = max(1, int(self.population_size * 0.1))
        sorted_population = sorted(self.population, key=lambda x: x.fitness, reverse=True)
        new_population.extend(sorted_population[:elite_count])
        
        # Generate offspring through selection, crossover, and mutation
        while len(new_population) < self.population_size:
            # Selection
            parent1 = self.evolutionary_operator.select(self.population)
            parent2 = self.evolutionary_operator.select(self.population)
            
            # Crossover
            if random.random() < self.crossover_rate:
                offspring1, offspring2 = self.evolutionary_operator.crossover(parent1, parent2)
            else:
                offspring1, offspring2 = copy.deepcopy(parent1), copy.deepcopy(parent2)
            
            # Mutation
            if random.random() < self.mutation_rate:
                offspring1 = self.evolutionary_operator.mutate(offspring1)
            
            if random.random() < self.mutation_rate:
                offspring2 = self.evolutionary_operator.mutate(offspring2)
            
            # Update generation number
            offspring1.generation = self.generation + 1
            offspring2.generation = self.generation + 1
            
            new_population.extend([offspring1, offspring2])
        
        # Trim population to exact size
        self.population = new_population[:self.population_size]
        self.generation += 1
        
        logger.info(f"Evolution generation {self.generation} completed")
        return self.best_individual
    
    def run_evolution(self) -> Individual:
        """
        Run the complete evolution process for maximum generations.
        
        Returns:
            Best individual found during evolution
        """
        logger.info("Starting full evolution process")
        
        for gen in range(self.max_generations):
            best = self.evolve()
            logger.info(f"Generation {gen}: Best fitness = {best.fitness:.4f}")
            
            # Early stopping condition (if needed)
            if gen > 10 and abs(best.fitness - self.best_individual.fitness) < 0.001:
                logger.info("Early stopping: fitness improvement below threshold")
                break
        
        logger.info("Evolution process completed")
        return self.best_individual


# Example implementation of a fitness evaluator for demonstration
class SimpleCodeFitnessEvaluator(FitnessEvaluator):
    """
    Simple fitness evaluator that evaluates code based on basic metrics.
    
    This is a placeholder implementation that should be replaced with more
    sophisticated evaluation logic that can actually assess code quality,
    correctness, and performance.
    """
    
    def evaluate(self, individual: Individual) -> float:
        """
        Evaluate the fitness of an individual.
        
        TODO: Implement actual code evaluation logic including:
              - Code correctness (does it run without errors?)
              - Performance metrics
              - Code quality indicators
              - Algorithmic efficiency
              - Novelty scores
        
        Args:
            individual: The individual to evaluate
            
        Returns:
            Fitness score (higher is better)
        """
        # Placeholder evaluation logic
        fitness = 0.0
        
        # Reward for code length (not necessarily good, but demonstrates concept)
        code_length = len(individual.code)
        fitness += max(0, 100 - code_length / 10)  # Penalize very long code
        
        # Reward for containing certain keywords
        keywords = ['def', 'for', 'if', 'return']
        keyword_count = sum(1 for kw in keywords if kw in individual.code)
        fitness += keyword_count * 5
        
        # Add some randomness to make it interesting
        fitness += random.uniform(0, 10)
        
        return max(0, fitness)


# Example usage function
def demo_evolution():
    """
    Demonstrate the evolution engine with a simple example.
    
    This function shows how to use the EvolutionEngine with sample code.
    """
    # Create a simple fitness evaluator
    fitness_evaluator = SimpleCodeFitnessEvaluator()
    
    # Create evolutionary operator
    evolutionary_operator = TournamentSelection(tournament_size=3)
    
    # Initialize evolution engine
    engine = EvolutionEngine(
        fitness_evaluator=fitness_evaluator,
        evolutionary_operator=evolutionary_operator,
        population_size=20,
        mutation_rate=0.15,
        crossover_rate=0.7,
        max_generations=10
    )
    
    # Sample initial code
    initial_samples = [
        "def hello():\n    return 'Hello, World!'\n",
        "print('Hello, World!')\n",
        "x = 1\ny = 2\nz = x + y\nprint(z)\n"
    ]
    
    # Initialize population
    engine.initialize_population(initial_samples)
    
    # Run evolution
    best_individual = engine.run_evolution()
    
    print(f"Best individual found:")
    print(f"Fitness: {best_individual.fitness:.4f}")
    print(f"Code:\n{best_individual.code}")
    
    return best_individual


if __name__ == "__main__":
    # Run the demo
    demo_evolution()