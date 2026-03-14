"""
NEX_Runtime Module

Provides the runtime environment for executing native components and managing 
their interaction with simulated components in the NEX-DSim system.

This module implements the core runtime functionality that bridges native and 
simulated execution environments, handling component lifecycle management,
synchronization, and interaction protocols.

Author: NEX-DSim Team
"""

import time
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComponentType(Enum):
    """Enumeration of component types supported by the runtime."""
    NATIVE = "native"
    SIMULATED = "simulated"
    MIXED = "mixed"

class RuntimeState(Enum):
    """Enumeration of runtime states."""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"

@dataclass
class ComponentInfo:
    """Data class to hold component information."""
    id: str
    type: ComponentType
    name: str
    execution_time: float = 0.0
    status: str = "idle"
    dependencies: List[str] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

class ComponentRegistry:
    """Registry to manage all components in the runtime environment."""
    
    def __init__(self):
        self.components: Dict[str, ComponentInfo] = {}
        self._lock = threading.RLock()
    
    def register_component(self, component_info: ComponentInfo) -> None:
        """Register a component in the runtime."""
        with self._lock:
            self.components[component_info.id] = component_info
            logger.debug(f"Registered component: {component_info.name}")
    
    def get_component(self, component_id: str) -> Optional[ComponentInfo]:
        """Retrieve a component by ID."""
        with self._lock:
            return self.components.get(component_id)
    
    def update_component_status(self, component_id: str, status: str) -> None:
        """Update the status of a component."""
        with self._lock:
            if component_id in self.components:
                self.components[component_id].status = status
                logger.debug(f"Updated component {component_id} status to: {status}")
    
    def get_all_components(self) -> List[ComponentInfo]:
        """Get all registered components."""
        with self._lock:
            return list(self.components.values())

class SynchronizationManager:
    """Manages synchronization between native and simulated components."""
    
    def __init__(self):
        self._sync_lock = threading.Lock()
        self._sync_points: Dict[str, threading.Event] = {}
        self._time_reference = 0.0
    
    def set_time_reference(self, time_ref: float) -> None:
        """Set the global time reference for synchronization."""
        self._time_reference = time_ref
    
    def create_sync_point(self, point_id: str) -> None:
        """Create a synchronization point."""
        with self._sync_lock:
            self._sync_points[point_id] = threading.Event()
            logger.debug(f"Created sync point: {point_id}")
    
    def wait_for_sync_point(self, point_id: str, timeout: float = 1.0) -> bool:
        """Wait for a synchronization point to be reached."""
        with self._sync_lock:
            if point_id not in self._sync_points:
                logger.warning(f"Sync point {point_id} not found")
                return False
            
            return self._sync_points[point_id].wait(timeout)
    
    def signal_sync_point(self, point_id: str) -> None:
        """Signal that a synchronization point has been reached."""
        with self._sync_lock:
            if point_id in self._sync_points:
                self._sync_points[point_id].set()
                logger.debug(f"Signaled sync point: {point_id}")
            else:
                logger.warning(f"Sync point {point_id} not found")

class NativeComponentExecutor:
    """Executes native components in the runtime environment."""
    
    def __init__(self):
        self._executors: Dict[str, Callable] = {}
        self._execution_lock = threading.Lock()
    
    def register_executor(self, component_id: str, executor_func: Callable) -> None:
        """Register an executor function for a native component."""
        with self._execution_lock:
            self._executors[component_id] = executor_func
            logger.debug(f"Registered executor for component: {component_id}")
    
    def execute_component(self, component_id: str, *args, **kwargs) -> Any:
        """Execute a native component."""
        with self._execution_lock:
            if component_id not in self._executors:
                raise ValueError(f"No executor registered for component: {component_id}")
            
            logger.debug(f"Executing native component: {component_id}")
            start_time = time.time()
            
            try:
                result = self._executors[component_id](*args, **kwargs)
                execution_time = time.time() - start_time
                logger.debug(f"Native component {component_id} executed in {execution_time:.4f}s")
                return result
            except Exception as e:
                logger.error(f"Error executing native component {component_id}: {e}")
                raise

class SimulatedComponentManager:
    """Manages simulated components and their execution."""
    
    def __init__(self):
        self._simulators: Dict[str, Any] = {}
        self._simulation_lock = threading.Lock()
    
    def register_simulator(self, component_id: str, simulator: Any) -> None:
        """Register a simulator for a component."""
        with self._simulation_lock:
            self._simulators[component_id] = simulator
            logger.debug(f"Registered simulator for component: {component_id}")
    
    def simulate_component(self, component_id: str, *args, **kwargs) -> Any:
        """Execute simulation for a component."""
        with self._simulation_lock:
            if component_id not in self._simulators:
                raise ValueError(f"No simulator registered for component: {component_id}")
            
            logger.debug(f"Simulating component: {component_id}")
            start_time = time.time()
            
            try:
                result = self._simulators[component_id].simulate(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.debug(f"Simulated component {component_id} in {execution_time:.4f}s")
                return result
            except Exception as e:
                logger.error(f"Error simulating component {component_id}: {e}")
                raise

class NEX_Runtime:
    """
    Main runtime environment for executing native components and managing 
    their interaction with simulated components.
    
    This class provides the core runtime functionality that bridges native and 
    simulated execution environments, handling component lifecycle management,
    synchronization, and interaction protocols.
    """
    
    def __init__(self):
        self._state = RuntimeState.INITIALIZED
        self._registry = ComponentRegistry()
        self._sync_manager = SynchronizationManager()
        self._native_executor = NativeComponentExecutor()
        self._simulated_manager = SimulatedComponentManager()
        self._runtime_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._execution_threads: List[threading.Thread] = []
        
        logger.info("NEX_Runtime initialized")
    
    def start(self) -> None:
        """Start the runtime environment."""
        with self._runtime_lock:
            if self._state != RuntimeState.INITIALIZED:
                raise RuntimeError("Runtime can only be started from INITIALIZED state")
            
            self._state = RuntimeState.RUNNING
            self._stop_event.clear()
            logger.info("NEX_Runtime started")
    
    def stop(self) -> None:
        """Stop the runtime environment."""
        with self._runtime_lock:
            if self._state != RuntimeState.RUNNING:
                logger.warning("Runtime not running, cannot stop")
                return
            
            self._state = RuntimeState.STOPPED
            self._stop_event.set()
            
            # Wait for all execution threads to finish
            for thread in self._execution_threads:
                if thread.is_alive():
                    thread.join(timeout=5.0)
            
            logger.info("NEX_Runtime stopped")
    
    def pause(self) -> None:
        """Pause the runtime environment."""
        with self._runtime_lock:
            if self._state != RuntimeState.RUNNING:
                logger.warning("Runtime not running, cannot pause")
                return
            
            self._state = RuntimeState.PAUSED
            logger.info("NEX_Runtime paused")
    
    def resume(self) -> None:
        """Resume the runtime environment."""
        with self._runtime_lock:
            if self._state != RuntimeState.PAUSED:
                logger.warning("Runtime not paused, cannot resume")
                return
            
            self._state = RuntimeState.RUNNING
            logger.info("NEX_Runtime resumed")
    
    def register_component(self, component_info: ComponentInfo) -> None:
        """Register a component with the runtime."""
        with self._runtime_lock:
            self._registry.register_component(component_info)
    
    def execute_native_component(self, component_id: str, *args, **kwargs) -> Any:
        """
        Execute a native component.
        
        Args:
            component_id: ID of the component to execute
            *args: Arguments to pass to the component
            **kwargs: Keyword arguments to pass to the component
            
        Returns:
            Result of component execution
            
        Raises:
            ValueError: If component is not registered or not native
        """
        with self._runtime_lock:
            component = self._registry.get_component(component_id)
            if not component:
                raise ValueError(f"Component {component_id} not registered")
            
            if component.type != ComponentType.NATIVE:
                raise ValueError(f"Component {component_id} is not a native component")
            
            # Update component status
            self._registry.update_component_status(component_id, "executing")
            
            try:
                result = self._native_executor.execute_component(component_id, *args, **kwargs)
                self._registry.update_component_status(component_id, "completed")
                return result
            except Exception as e:
                self._registry.update_component_status(component_id, f"error: {str(e)}")
                raise
    
    def execute_simulated_component(self, component_id: str, *args, **kwargs) -> Any:
        """
        Execute a simulated component.
        
        Args:
            component_id: ID of the component to simulate
            *args: Arguments to pass to the simulation
            **kwargs: Keyword arguments to pass to the simulation
            
        Returns:
            Result of simulation
            
        Raises:
            ValueError: If component is not registered or not simulated
        """
        with self._runtime_lock:
            component = self._registry.get_component(component_id)
            if not component:
                raise ValueError(f"Component {component_id} not registered")
            
            if component.type != ComponentType.SIMULATED:
                raise ValueError(f"Component {component_id} is not a simulated component")
            
            # Update component status
            self._registry.update_component_status(component_id, "simulating")
            
            try:
                result = self._simulated_manager.simulate_component(component_id, *args, **kwargs)
                self._registry.update_component_status(component_id, "completed")
                return result
            except Exception as e:
                self._registry.update_component_status(component_id, f"error: {str(e)}")
                raise
    
    def synchronize_components(self, sync_point_id: str, timeout: float = 1.0) -> bool:
        """
        Synchronize execution between native and simulated components.
        
        Args:
            sync_point_id: Identifier for the synchronization point
            timeout: Timeout in seconds for synchronization
            
        Returns:
            True if synchronization successful, False otherwise
        """
        with self._runtime_lock:
            try:
                # Create sync point if it doesn't exist
                self._sync_manager.create_sync_point(sync_point_id)
                
                # Wait for synchronization
                success = self._sync_manager.wait_for_sync_point(sync_point_id, timeout)
                return success
            except Exception as e:
                logger.error(f"Synchronization failed: {e}")
                return False
    
    def signal_synchronization(self, sync_point_id: str) -> None:
        """
        Signal that a synchronization point has been reached.
        
        Args:
            sync_point_id: Identifier for the synchronization point
        """
        with self._runtime_lock:
            self._sync_manager.signal_sync_point(sync_point_id)
    
    def get_component_status(self, component_id: str) -> str:
        """
        Get the current status of a component.
        
        Args:
            component_id: ID of the component
            
        Returns:
            Status of the component
        """
        with self._runtime_lock:
            component = self._registry.get_component(component_id)
            return component.status if component else "unknown"
    
    def get_runtime_state(self) -> RuntimeState:
        """Get the current state of the runtime."""
        with self._runtime_lock:
            return self._state
    
    def get_all_components(self) -> List[ComponentInfo]:
        """Get information about all registered components."""
        with self._runtime_lock:
            return self._registry.get_all_components()
    
    def set_time_reference(self, time_ref: float) -> None:
        """
        Set the global time reference for synchronization.
        
        Args:
            time_ref: Time reference value
        """
        with self._runtime_lock:
            self._sync_manager.set_time_reference(time_ref)
    
    def is_running(self) -> bool:
        """Check if the runtime is currently running."""
        with self._runtime_lock:
            return self._state == RuntimeState.RUNNING

# Example usage and test functions
def example_native_component_function(data: str) -> str:
    """Example native component function."""
    time.sleep(0.1)  # Simulate processing time
    return f"Processed: {data}"

def example_simulator_component():
    """Example simulator component."""
    class MockSimulator:
        def simulate(self, data: str) -> str:
            time.sleep(0.05)  # Simulate simulation time
            return f"Simulated: {data}"
    
    return MockSimulator()

def run_example():
    """Run an example demonstrating the NEX_Runtime functionality."""
    print("Starting NEX_Runtime example...")
    
    # Initialize runtime
    runtime = NEX_Runtime()
    runtime.start()
    
    # Register components
    native_component = ComponentInfo(
        id="native_001",
        type=ComponentType.NATIVE,
        name="Example Native Component"
    )
    
    simulated_component = ComponentInfo(
        id="sim_001",
        type=ComponentType.SIMULATED,
        name="Example Simulated Component"
    )
    
    runtime.register_component(native_component)
    runtime.register_component(simulated_component)
    
    # Register executors
    runtime._native_executor.register_executor("native_001", example_native_component_function)
    runtime._simulated_manager.register_simulator("sim_001", example_simulator_component())
    
    # Execute components
    try:
        result1 = runtime.execute_native_component("native_001", "test data")
        print(f"Native component result: {result1}")
        
        result2 = runtime.execute_simulated_component("sim_001", "test data")
        print(f"Simulated component result: {result2}")
        
        # Synchronize
        runtime.synchronize_components("sync_point_001", timeout=2.0)
        runtime.signal_synchronization("sync_point_001")
        
        print("Example completed successfully")
        
    except Exception as e:
        print(f"Example failed with error: {e}")
    
    # Cleanup
    runtime.stop()
    print("Example finished")

if __name__ == "__main__":
    run_example()