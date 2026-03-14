"""
NEX Scheduler Module

This module determines which components to simulate versus execute natively,
based on availability and performance-criticality, and manages the scheduling
of simulation tasks in the NEX+DSim framework.

The scheduler implements a hybrid approach where:
- Native components are executed directly
- Simulated components are run with cycle-accurate performance simulation
- Scheduling decisions are made based on component availability and criticality
"""

import time
import asyncio
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComponentType(Enum):
    """Enumeration of component types that can be scheduled"""
    NATIVE = "native"
    SIMULATED = "simulated"
    MIXED = "mixed"

class SchedulingPolicy(Enum):
    """Enumeration of scheduling policies"""
    PERFORMANCE_CRITICAL = "performance_critical"
    AVAILABILITY_BASED = "availability_based"
    BALANCED = "balanced"

@dataclass
class ComponentInfo:
    """Information about a component that can be scheduled"""
    name: str
    type: ComponentType
    is_available: bool
    performance_criticality: float  # 0.0 to 1.0 scale
    estimated_execution_time: float  # in simulation cycles
    dependencies: List[str]  # names of components this depends on
    priority: int  # 1-10 scale, higher is more important

@dataclass
class ScheduleDecision:
    """Decision about how to schedule a component"""
    component_name: str
    execution_mode: str  # 'native' or 'simulated'
    simulation_accuracy: float  # 0.0 to 1.0 scale
    estimated_runtime: float
    scheduling_policy: SchedulingPolicy

class NEXScheduler:
    """
    NEX Scheduler for determining component execution modes and managing simulation tasks.
    
    This scheduler makes decisions about which components to execute natively versus
    simulate, based on availability, performance-criticality, and system constraints.
    """
    
    def __init__(self, policy: SchedulingPolicy = SchedulingPolicy.BALANCED):
        """
        Initialize the NEX Scheduler
        
        Args:
            policy: The scheduling policy to use for decision making
        """
        self.policy = policy
        self.components: Dict[str, ComponentInfo] = {}
        self.scheduled_tasks: Dict[str, ScheduleDecision] = {}
        self.simulation_queue: List[str] = []
        self.native_execution_queue: List[str] = []
        
        # Performance metrics tracking
        self.total_simulation_cycles = 0
        self.total_native_cycles = 0
        self.scheduling_decisions_made = 0
        
    def register_component(self, component: ComponentInfo) -> None:
        """
        Register a component with the scheduler
        
        Args:
            component: Component information to register
        """
        self.components[component.name] = component
        logger.info(f"Registered component: {component.name}")
        
    def get_component(self, name: str) -> Optional[ComponentInfo]:
        """
        Get component information by name
        
        Args:
            name: Name of the component
            
        Returns:
            ComponentInfo if found, None otherwise
        """
        return self.components.get(name)
        
    def update_component_availability(self, name: str, is_available: bool) -> None:
        """
        Update the availability status of a component
        
        Args:
            name: Name of the component
            is_available: New availability status
        """
        if name in self.components:
            self.components[name].is_available = is_available
            logger.info(f"Updated availability for {name}: {is_available}")
        else:
            logger.warning(f"Component {name} not found when updating availability")
            
    def _calculate_scheduling_score(self, component: ComponentInfo) -> float:
        """
        Calculate a score for scheduling decision based on current policy
        
        Args:
            component: Component to score
            
        Returns:
            Score indicating scheduling priority (higher is more important)
        """
        if self.policy == SchedulingPolicy.PERFORMANCE_CRITICAL:
            # Prioritize performance-critical components
            return component.performance_criticality
        elif self.policy == SchedulingPolicy.AVAILABILITY_BASED:
            # Prioritize unavailable components
            if not component.is_available:
                return 1.0
            else:
                return 0.0
        else:  # BALANCED
            # Balanced approach: consider both availability and criticality
            availability_score = 1.0 if not component.is_available else 0.0
            criticality_score = component.performance_criticality
            return (availability_score + criticality_score) / 2.0
            
    def _decide_execution_mode(self, component: ComponentInfo) -> ScheduleDecision:
        """
        Decide whether to execute a component natively or simulate it
        
        Args:
            component: Component to decide on
            
        Returns:
            ScheduleDecision with execution mode and parameters
        """
        # TODO: Implement more sophisticated decision logic
        # This is a simplified version that can be enhanced with:
        # - System resource constraints
        # - Memory usage considerations
        # - Communication overhead between native and simulated components
        # - Historical performance data
        
        if not component.is_available:
            # Unavailable components must be simulated
            execution_mode = "simulated"
            simulation_accuracy = 1.0  # Full accuracy for unavailable components
        elif component.performance_criticality > 0.7:
            # Highly performance-critical components may be simulated
            # even if available, to maintain accuracy
            execution_mode = "simulated"
            simulation_accuracy = 0.9  # High accuracy for critical components
        else:
            # Standard components can run natively
            execution_mode = "native"
            simulation_accuracy = 0.0  # No simulation needed
            
        # TODO: Add more sophisticated logic for determining simulation accuracy
        # based on component complexity, communication patterns, etc.
        
        estimated_runtime = component.estimated_execution_time
        
        return ScheduleDecision(
            component_name=component.name,
            execution_mode=execution_mode,
            simulation_accuracy=simulation_accuracy,
            estimated_runtime=estimated_runtime,
            scheduling_policy=self.policy
        )
        
    def schedule_all_components(self) -> Dict[str, ScheduleDecision]:
        """
        Schedule all registered components based on current policy
        
        Returns:
            Dictionary mapping component names to scheduling decisions
        """
        logger.info("Starting scheduling process...")
        
        # Reset scheduling state
        self.scheduled_tasks.clear()
        self.simulation_queue.clear()
        self.native_execution_queue.clear()
        
        # Sort components by scheduling score
        sorted_components = sorted(
            self.components.values(),
            key=self._calculate_scheduling_score,
            reverse=True
        )
        
        # Make scheduling decisions for each component
        for component in sorted_components:
            decision = self._decide_execution_mode(component)
            self.scheduled_tasks[component.name] = decision
            
            # Update queues based on execution mode
            if decision.execution_mode == "simulated":
                self.simulation_queue.append(component.name)
            else:
                self.native_execution_queue.append(component.name)
                
            self.scheduling_decisions_made += 1
            
        logger.info(f"Scheduling completed. {len(self.scheduled_tasks)} components scheduled.")
        return self.scheduled_tasks
        
    def get_simulation_queue(self) -> List[str]:
        """
        Get the list of components scheduled for simulation
        
        Returns:
            List of component names to be simulated
        """
        return self.simulation_queue.copy()
        
    def get_native_execution_queue(self) -> List[str]:
        """
        Get the list of components scheduled for native execution
        
        Returns:
            List of component names to be executed natively
        """
        return self.native_execution_queue.copy()
        
    def get_scheduling_summary(self) -> Dict:
        """
        Get a summary of scheduling decisions
        
        Returns:
            Dictionary with scheduling statistics
        """
        total_components = len(self.components)
        simulated_count = len(self.simulation_queue)
        native_count = len(self.native_execution_queue)
        
        return {
            "total_components": total_components,
            "simulated_components": simulated_count,
            "native_components": native_count,
            "simulation_percentage": (simulated_count / total_components) * 100 if total_components > 0 else 0,
            "scheduling_decisions_made": self.scheduling_decisions_made,
            "total_simulation_cycles": self.total_simulation_cycles,
            "total_native_cycles": self.total_native_cycles
        }
        
    def update_performance_metrics(self, simulation_cycles: int, native_cycles: int) -> None:
        """
        Update performance metrics after execution
        
        Args:
            simulation_cycles: Number of simulation cycles executed
            native_cycles: Number of native cycles executed
        """
        self.total_simulation_cycles += simulation_cycles
        self.total_native_cycles += native_cycles

# Example usage and testing
def demo_scheduler():
    """Demonstrate the NEX Scheduler functionality"""
    
    # Create scheduler with balanced policy
    scheduler = NEXScheduler(policy=SchedulingPolicy.BALANCED)
    
    # Register some example components
    components = [
        ComponentInfo(
            name="CPU_Core",
            type=ComponentType.NATIVE,
            is_available=True,
            performance_criticality=0.9,
            estimated_execution_time=1000,
            dependencies=[],
            priority=10
        ),
        ComponentInfo(
            name="GPU_Renderer",
            type=ComponentType.SIMULATED,
            is_available=False,
            performance_criticality=0.8,
            estimated_execution_time=5000,
            dependencies=["CPU_Core"],
            priority=8
        ),
        ComponentInfo(
            name="Memory_Controller",
            type=ComponentType.NATIVE,
            is_available=True,
            performance_criticality=0.6,
            estimated_execution_time=200,
            dependencies=["CPU_Core"],
            priority=7
        ),
        ComponentInfo(
            name="Network_Interface",
            type=ComponentType.SIMULATED,
            is_available=False,
            performance_criticality=0.4,
            estimated_execution_time=1500,
            dependencies=["CPU_Core"],
            priority=5
        )
    ]
    
    # Register components
    for component in components:
        scheduler.register_component(component)
    
    # Schedule all components
    decisions = scheduler.schedule_all_components()
    
    # Print scheduling results
    print("Scheduling Decisions:")
    for component_name, decision in decisions.items():
        print(f"  {component_name}: {decision.execution_mode} "
              f"(accuracy: {decision.simulation_accuracy:.2f})")
    
    # Print queues
    print("\nSimulation Queue:", scheduler.get_simulation_queue())
    print("Native Execution Queue:", scheduler.get_native_execution_queue())
    
    # Print summary
    summary = scheduler.get_scheduling_summary()
    print("\nScheduling Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    demo_scheduler()