"""
NEX_Scheduler Module
====================

Schedules execution of native and simulated components, optimizing for performance 
and ensuring correct temporal ordering.

This module implements the core scheduling functionality for the NEX-DSim 
simulation framework, managing both native and simulated component execution
while maintaining temporal coherence between them.

Author: NEX Team
"""

import time
import heapq
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComponentType(Enum):
    """Enumeration of component types for scheduling."""
    NATIVE = "native"
    SIMULATED = "simulated"
    MIXED = "mixed"

class SchedulingPolicy(Enum):
    """Enumeration of scheduling policies."""
    FIFO = "fifo"
    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"
    EDF = "earliest_deadline_first"

@dataclass
class Component:
    """Represents a component in the simulation system."""
    id: str
    name: str
    component_type: ComponentType
    execution_time: float  # in simulation time units
    priority: int = 0
    deadline: Optional[float] = None
    is_available: bool = True
    callback: Optional[Callable] = None
    
    def __repr__(self):
        return f"Component(id={self.id}, name={self.name}, type={self.component_type.value})"

@dataclass
class ScheduleItem:
    """Represents an item in the scheduler's queue."""
    timestamp: float
    component: Component
    priority: int
    
    def __lt__(self, other):
        # For heapq comparison - lower priority values are processed first
        if self.priority == other.priority:
            return self.timestamp < other.timestamp
        return self.priority < other.priority

class NEX_Scheduler:
    """
    Scheduler for managing execution of native and simulated components.
    
    This scheduler optimizes performance by efficiently scheduling components
    while ensuring correct temporal ordering between native and simulated
    execution paths.
    
    Attributes:
        policy (SchedulingPolicy): The scheduling policy to use
        queue (list): Priority queue of scheduled items
        current_time (float): Current simulation time
        component_registry (dict): Registry of all components
        active_components (set): Set of currently active components
    """
    
    def __init__(self, policy: SchedulingPolicy = SchedulingPolicy.FIFO):
        """
        Initialize the NEX Scheduler.
        
        Args:
            policy (SchedulingPolicy): The scheduling policy to use
        """
        self.policy = policy
        self.queue = []
        self.current_time = 0.0
        self.component_registry = {}
        self.active_components = set()
        self._next_id = 0
        
        logger.info(f"Initialized NEX_Scheduler with policy: {policy.value}")
    
    def register_component(self, component: Component) -> str:
        """
        Register a component with the scheduler.
        
        Args:
            component (Component): The component to register
            
        Returns:
            str: Unique identifier for the registered component
        """
        component_id = f"comp_{self._next_id}"
        self._next_id += 1
        
        # Set the component ID and register it
        component.id = component_id
        self.component_registry[component_id] = component
        
        logger.debug(f"Registered component: {component.name} (ID: {component_id})")
        return component_id
    
    def schedule_component(self, component_id: str, delay: float = 0.0) -> None:
        """
        Schedule a component for execution.
        
        Args:
            component_id (str): ID of the component to schedule
            delay (float): Delay before execution (in simulation time units)
        """
        if component_id not in self.component_registry:
            raise ValueError(f"Component {component_id} not found in registry")
        
        component = self.component_registry[component_id]
        scheduled_time = self.current_time + delay
        
        # Create schedule item based on policy
        if self.policy == SchedulingPolicy.PRIORITY:
            priority = component.priority
        elif self.policy == SchedulingPolicy.EDF:
            # For EDF, use deadline as priority (lower deadline = higher priority)
            priority = component.deadline if component.deadline is not None else float('inf')
        else:
            # Default to FIFO - use timestamp as priority
            priority = scheduled_time
            
        schedule_item = ScheduleItem(
            timestamp=scheduled_time,
            component=component,
            priority=priority
        )
        
        heapq.heappush(self.queue, schedule_item)
        self.active_components.add(component_id)
        
        logger.debug(f"Scheduled component {component.name} for time {scheduled_time}")
    
    def execute_next(self) -> Optional[Component]:
        """
        Execute the next scheduled component.
        
        Returns:
            Component: The executed component, or None if queue is empty
        """
        if not self.queue:
            return None
            
        schedule_item = heapq.heappop(self.queue)
        component = schedule_item.component
        
        # Update current time
        self.current_time = schedule_item.timestamp
        
        # Execute component
        try:
            self._execute_component(component)
            self.active_components.discard(component.id)
            logger.debug(f"Executed component: {component.name} at time {self.current_time}")
            return component
        except Exception as e:
            logger.error(f"Error executing component {component.name}: {e}")
            self.active_components.discard(component.id)
            raise
    
    def _execute_component(self, component: Component) -> None:
        """
        Execute a component's logic.
        
        This is a placeholder for actual component execution logic.
        In a real implementation, this would:
        - Handle native component execution
        - Coordinate with simulated components
        - Manage synchronization points
        - Handle callbacks and notifications
        
        Args:
            component (Component): The component to execute
        """
        # TODO: Implement actual component execution logic
        # This could involve:
        # 1. Native execution for native components
        # 2. Simulation step for simulated components
        # 3. Synchronization with other components
        # 4. Time advancement for simulation
        # 5. Callback execution if provided
        
        logger.info(f"Executing {component.component_type.value} component: {component.name}")
        
        # Simulate execution time
        if component.execution_time > 0:
            # In a real implementation, this would be more sophisticated
            # and involve actual time advancement
            time.sleep(component.execution_time * 0.001)  # Simulate execution delay
        
        # Execute callback if provided
        if component.callback:
            component.callback(component)
    
    def get_pending_components(self) -> List[Component]:
        """
        Get list of all pending components.
        
        Returns:
            List[Component]: List of pending components
        """
        return [item.component for item in self.queue]
    
    def get_active_components(self) -> List[Component]:
        """
        Get list of currently active components.
        
        Returns:
            List[Component]: List of active components
        """
        return [self.component_registry[comp_id] for comp_id in self.active_components]
    
    def advance_time(self, amount: float) -> None:
        """
        Advance simulation time.
        
        Args:
            amount (float): Amount of time to advance
        """
        self.current_time += amount
        logger.debug(f"Advanced time to {self.current_time}")
    
    def get_current_time(self) -> float:
        """
        Get current simulation time.
        
        Returns:
            float: Current simulation time
        """
        return self.current_time
    
    def reset(self) -> None:
        """
        Reset the scheduler to initial state.
        """
        self.queue.clear()
        self.current_time = 0.0
        self.active_components.clear()
        logger.info("Scheduler reset to initial state")
    
    def set_policy(self, policy: SchedulingPolicy) -> None:
        """
        Change the scheduling policy.
        
        Args:
            policy (SchedulingPolicy): New scheduling policy
        """
        self.policy = policy
        logger.info(f"Changed scheduling policy to: {policy.value}")

# Example usage and testing
def example_usage():
    """Demonstrate usage of the NEX_Scheduler."""
    
    # Create scheduler with priority policy
    scheduler = NEX_Scheduler(policy=SchedulingPolicy.PRIORITY)
    
    # Create some components
    native_comp1 = Component(
        name="Native CPU Core",
        component_type=ComponentType.NATIVE,
        execution_time=10.0,
        priority=1
    )
    
    simulated_comp1 = Component(
        name="Simulated GPU",
        component_type=ComponentType.SIMULATED,
        execution_time=5.0,
        priority=2,
        deadline=100.0
    )
    
    # Register components
    comp1_id = scheduler.register_component(native_comp1)
    comp2_id = scheduler.register_component(simulated_comp1)
    
    # Schedule components
    scheduler.schedule_component(comp1_id, delay=0.0)
    scheduler.schedule_component(comp2_id, delay=2.0)
    
    # Execute scheduled components
    print("Executing scheduled components:")
    while scheduler.queue:
        component = scheduler.execute_next()
        if component:
            print(f"Executed: {component.name}")
    
    print(f"Final time: {scheduler.get_current_time()}")

if __name__ == "__main__":
    # Run example
    example_usage()