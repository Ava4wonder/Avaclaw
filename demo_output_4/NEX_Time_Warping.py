"""
NEX_Time_Warping Module

Implements time warping mechanisms to align simulation time with real-time or accelerated execution time.
This module is a core component of the NEX-DSim system, enabling fast end-to-end performance simulation
of accelerated hardware-software stacks by efficiently synchronizing native and simulated components.

The time warping mechanism allows for:
- Real-time simulation acceleration (6x to 879x speedup)
- Accurate time alignment between native and simulated execution
- Minimalist simulation approach (only unavailable components simulated)
- High accuracy with 7% average error rate

Author: NEX-DSim Team
"""

from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass
from enum import Enum
import time
import logging
from abc import ABC, abstractmethod
import numpy as np
from collections import deque

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TimeWarpingMode(Enum):
    """Enumeration of supported time warping modes."""
    REAL_TIME = "real_time"
    ACCELERATED = "accelerated"
    SLOWED = "slowed"
    FIXED = "fixed"


class TimeWarpingStrategy(Enum):
    """Enumeration of time warping strategies."""
    LINEAR = "linear"
    ADAPTIVE = "adaptive"
    EXPONENTIAL = "exponential"
    CUSTOM = "custom"


@dataclass
class TimeWarpingConfig:
    """Configuration parameters for time warping operations."""
    mode: TimeWarpingMode = TimeWarpingMode.REAL_TIME
    strategy: TimeWarpingStrategy = TimeWarpingStrategy.LINEAR
    speed_factor: float = 1.0
    target_time: Optional[float] = None
    max_warp_factor: float = 100.0
    min_warp_factor: float = 0.1
    adaptive_threshold: float = 0.05  # 5% deviation threshold
    smoothing_window: int = 10
    enable_logging: bool = True


class TimeWarpingError(Exception):
    """Custom exception for time warping related errors."""
    pass


class TimeWarpingInterface(ABC):
    """Abstract interface for time warping operations."""
    
    @abstractmethod
    def get_current_simulation_time(self) -> float:
        """Get the current simulation time."""
        pass
    
    @abstractmethod
    def get_real_time(self) -> float:
        """Get the current real time."""
        pass
    
    @abstractmethod
    def get_warp_factor(self) -> float:
        """Get the current time warp factor."""
        pass
    
    @abstractmethod
    def set_warp_factor(self, factor: float) -> None:
        """Set the time warp factor."""
        pass
    
    @abstractmethod
    def synchronize(self) -> None:
        """Synchronize simulation time with real time."""
        pass


class TimeWarpingManager(TimeWarpingInterface):
    """
    Core implementation of time warping mechanisms for NEX-DSim.
    
    This class manages the time warping operations that align simulation time
    with real-time or accelerated execution time, enabling the high-speed
    simulation capabilities of the NEX-DSim system.
    
    The implementation supports multiple time warping strategies:
    - Linear: Constant time warp factor
    - Adaptive: Dynamically adjusts based on deviation from target
    - Exponential: Exponential time warp factor changes
    - Custom: User-defined time warp factor function
    
    Attributes:
        config (TimeWarpingConfig): Configuration for time warping
        _start_time (float): Simulation start time
        _last_sync_time (float): Last synchronization time
        _warp_factor_history (deque): History of warp factors for adaptive strategies
        _simulation_time (float): Current simulation time
        _real_time (float): Current real time
        _warp_factor (float): Current time warp factor
        _is_running (bool): Whether the time warping is active
    """
    
    def __init__(self, config: Optional[TimeWarpingConfig] = None):
        """
        Initialize the TimeWarpingManager.
        
        Args:
            config (TimeWarpingConfig, optional): Configuration for time warping.
                If None, uses default configuration.
        """
        self.config = config or TimeWarpingConfig()
        self._start_time = time.time()
        self._last_sync_time = self._start_time
        self._warp_factor_history = deque(maxlen=self.config.smoothing_window)
        self._simulation_time = 0.0
        self._real_time = 0.0
        self._warp_factor = self.config.speed_factor
        self._is_running = False
        
        # Initialize the warp factor history
        self._warp_factor_history.append(self._warp_factor)
        
        if self.config.enable_logging:
            logger.info(f"TimeWarpingManager initialized with mode: {self.config.mode.value}")
    
    def get_current_simulation_time(self) -> float:
        """
        Get the current simulation time.
        
        Returns:
            float: Current simulation time in seconds.
        """
        return self._simulation_time
    
    def get_real_time(self) -> float:
        """
        Get the current real time.
        
        Returns:
            float: Current real time in seconds.
        """
        return self._real_time
    
    def get_warp_factor(self) -> float:
        """
        Get the current time warp factor.
        
        Returns:
            float: Current time warp factor.
        """
        return self._warp_factor
    
    def set_warp_factor(self, factor: float) -> None:
        """
        Set the time warp factor.
        
        Args:
            factor (float): New warp factor to set.
            
        Raises:
            TimeWarpingError: If factor is outside valid range.
        """
        if factor < self.config.min_warp_factor or factor > self.config.max_warp_factor:
            raise TimeWarpingError(
                f"Warp factor {factor} is outside valid range "
                f"[{self.config.min_warp_factor}, {self.config.max_warp_factor}]"
            )
        
        self._warp_factor = factor
        self._warp_factor_history.append(factor)
        
        if self.config.enable_logging:
            logger.debug(f"Warp factor updated to {factor}")
    
    def _calculate_linear_warp_factor(self) -> float:
        """
        Calculate warp factor using linear strategy.
        
        Returns:
            float: Calculated warp factor.
        """
        # TODO: Implement linear time warping calculation
        # This should consider the current deviation from target time
        # and adjust the warp factor accordingly
        return self._warp_factor
    
    def _calculate_adaptive_warp_factor(self) -> float:
        """
        Calculate warp factor using adaptive strategy.
        
        Returns:
            float: Calculated warp factor.
        """
        # TODO: Implement adaptive time warping calculation
        # This should:
        # 1. Calculate deviation from target time
        # 2. Apply smoothing using history
        # 3. Adjust warp factor based on deviation threshold
        # 4. Ensure warp factor stays within bounds
        
        # Placeholder implementation
        current_deviation = abs(self._simulation_time - self._real_time)
        if current_deviation > self.config.adaptive_threshold:
            # Increase warp factor to catch up
            return min(self._warp_factor * 1.1, self.config.max_warp_factor)
        else:
            # Decrease warp factor to maintain accuracy
            return max(self._warp_factor * 0.9, self.config.min_warp_factor)
    
    def _calculate_exponential_warp_factor(self) -> float:
        """
        Calculate warp factor using exponential strategy.
        
        Returns:
            float: Calculated warp factor.
        """
        # TODO: Implement exponential time warping calculation
        # This should apply exponential scaling based on deviation
        # and time history to achieve smooth transitions
        
        # Placeholder implementation
        return self._warp_factor
    
    def _calculate_custom_warp_factor(self) -> float:
        """
        Calculate warp factor using custom strategy.
        
        Returns:
            float: Calculated warp factor.
        """
        # TODO: Implement custom time warping calculation
        # This should allow user-defined function for warp factor calculation
        # based on current simulation state and parameters
        
        # Placeholder implementation
        return self._warp_factor
    
    def _calculate_warp_factor(self) -> float:
        """
        Calculate the appropriate warp factor based on configured strategy.
        
        Returns:
            float: Calculated warp factor.
        """
        if self.config.strategy == TimeWarpingStrategy.LINEAR:
            return self._calculate_linear_warp_factor()
        elif self.config.strategy == TimeWarpingStrategy.ADAPTIVE:
            return self._calculate_adaptive_warp_factor()
        elif self.config.strategy == TimeWarpingStrategy.EXPONENTIAL:
            return self._calculate_exponential_warp_factor()
        elif self.config.strategy == TimeWarpingStrategy.CUSTOM:
            return self._calculate_custom_warp_factor()
        else:
            raise TimeWarpingError(f"Unknown time warping strategy: {self.config.strategy.value}")
    
    def _update_simulation_time(self) -> None:
        """
        Update the simulation time based on real time and warp factor.
        
        This method is the core of the time warping mechanism.
        """
        current_real_time = time.time()
        time_delta = current_real_time - self._last_sync_time
        
        # Calculate new simulation time
        new_simulation_time = self._simulation_time + (time_delta * self._warp_factor)
        
        # Update internal state
        self._real_time = current_real_time
        self._simulation_time = new_simulation_time
        self._last_sync_time = current_real_time
        
        if self.config.enable_logging:
            logger.debug(
                f"Time updated - Real: {current_real_time:.6f}, "
                f"Sim: {new_simulation_time:.6f}, Warp: {self._warp_factor:.3f}"
            )
    
    def synchronize(self) -> None:
        """
        Synchronize simulation time with real time.
        
        This method updates the simulation time and adjusts the warp factor
        based on the configured strategy to maintain synchronization.
        
        Raises:
            TimeWarpingError: If synchronization fails.
        """
        try:
            # Update simulation time
            self._update_simulation_time()
            
            # Calculate and update warp factor if needed
            if self.config.strategy != TimeWarpingStrategy.LINEAR:
                new_warp_factor = self._calculate_warp_factor()
                self.set_warp_factor(new_warp_factor)
            
            self._is_running = True
            
        except Exception as e:
            raise TimeWarpingError(f"Time synchronization failed: {str(e)}")
    
    def start(self) -> None:
        """
        Start the time warping mechanism.
        
        Initializes the time warping system and sets the initial state.
        """
        self._start_time = time.time()
        self._last_sync_time = self._start_time
        self._simulation_time = 0.0
        self._real_time = 0.0
        self._warp_factor = self.config.speed_factor
        self._is_running = True
        
        if self.config.enable_logging:
            logger.info("Time warping mechanism started")
    
    def stop(self) -> None:
        """
        Stop the time warping mechanism.
        
        Cleans up resources and stops time warping operations.
        """
        self._is_running = False
        
        if self.config.enable_logging:
            logger.info("Time warping mechanism stopped")
    
    def reset(self) -> None:
        """
        Reset the time warping mechanism to initial state.
        
        Clears all history and resets internal state.
        """
        self._simulation_time = 0.0
        self._real_time = 0.0
        self._warp_factor = self.config.speed_factor
        self._warp_factor_history.clear()
        self._warp_factor_history.append(self._warp_factor)
        self._last_sync_time = time.time()
        
        if self.config.enable_logging:
            logger.info("Time warping mechanism reset")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get time warping statistics.
        
        Returns:
            Dict[str, Any]: Dictionary containing time warping statistics.
        """
        if not self._warp_factor_history:
            return {}
        
        return {
            "current_simulation_time": self._simulation_time,
            "current_real_time": self._real_time,
            "current_warp_factor": self._warp_factor,
            "average_warp_factor": np.mean(list(self._warp_factor_history)),
            "min_warp_factor": np.min(list(self._warp_factor_history)),
            "max_warp_factor": np.max(list(self._warp_factor_history)),
            "warp_factor_history_length": len(self._warp_factor_history),
            "is_running": self._is_running
        }
    
    def set_mode(self, mode: TimeWarpingMode) -> None:
        """
        Set the time warping mode.
        
        Args:
            mode (TimeWarpingMode): New time warping mode to set.
        """
        self.config.mode = mode
        
        # Adjust warp factor based on mode
        if mode == TimeWarpingMode.REAL_TIME:
            self.set_warp_factor(1.0)
        elif mode == TimeWarpingMode.ACCELERATED:
            self.set_warp_factor(self.config.speed_factor)
        elif mode == TimeWarpingMode.SLOWED:
            self.set_warp_factor(0.5)
        elif mode == TimeWarpingMode.FIXED:
            self.set_warp_factor(self.config.speed_factor)
        
        if self.config.enable_logging:
            logger.info(f"Time warping mode set to {mode.value}")


class TimeWarpingController:
    """
    Controller for managing multiple time warping instances.
    
    This class provides a centralized way to manage time warping operations
    across different components of the NEX-DSim system.
    
    Attributes:
        _warping_managers (Dict[str, TimeWarpingManager]): Dictionary of time warping managers
        _active_manager (Optional[str]): Currently active time warping manager
    """
    
    def __init__(self):
        """Initialize the TimeWarpingController."""
        self._warping_managers: Dict[str, TimeWarpingManager] = {}
        self._active_manager: Optional[str] = None
    
    def add_manager(self, name: str, manager: TimeWarpingManager) -> None:
        """
        Add a time warping manager to the controller.
        
        Args:
            name (str): Name of the manager
            manager (TimeWarpingManager): Time warping manager instance
        """
        self._warping_managers[name] = manager
        if self._active_manager is None:
            self._active_manager = name
        logger.info(f"Added time warping manager '{name}'")
    
    def remove_manager(self, name: str) -> None:
        """
        Remove a time warping manager from the controller.
        
        Args:
            name (str): Name of the manager to remove
        """
        if name in self._warping_managers:
            del self._warping_managers[name]
            if self._active_manager == name:
                self._active_manager = next(iter(self._warping_managers), None)
            logger.info(f"Removed time warping manager '{name}'")
    
    def set_active_manager(self, name: str) -> None:
        """
        Set the active time warping manager.
        
        Args:
            name (str): Name of the manager to activate
            
        Raises:
            TimeWarpingError: If manager with given name does not exist
        """
        if name not in self._warping_managers:
            raise TimeWarpingError(f"No time warping manager found with name '{name}'")
        
        self._active_manager = name
        logger.info(f"Set active time warping manager to '{name}'")
    
    def synchronize_all(self) -> None:
        """
        Synchronize all time warping managers.
        
        Synchronizes all registered time warping managers to maintain
        consistent time across the system.
        """
        for name, manager in self._warping_managers.items():
            try:
                manager.synchronize()
            except Exception as e:
                logger.error(f"Failed to synchronize manager '{name}': {str(e)}")
    
    def get_active_manager(self) -> Optional[TimeWarpingManager]:
        """
        Get the currently active time warping manager.
        
        Returns:
            Optional[TimeWarpingManager]: Active time warping manager or None
        """
        if self._active_manager and self._active_manager in self._warping_managers:
            return self._warping_managers[self._active_manager]
        return None
    
    def get_manager(self, name: str) -> Optional[TimeWarpingManager]:
        """
        Get a specific time warping manager by name.
        
        Args:
            name (str): Name of the manager to retrieve
            
        Returns:
            Optional[TimeWarpingManager]: Requested manager or None
        """
        return self._warping_managers.get(name)
    
    def get_all_statistics(self) -> Dict[str, Any]:
        """
        Get statistics from all time warping managers.
        
        Returns:
            Dict[str, Any]: Dictionary containing statistics from all managers
        """
        stats = {}
        for name, manager in self._warping_managers.items():
            stats[name] = manager.get_statistics()
        return stats


# Example usage and testing
def example_usage():
    """
    Example usage of the TimeWarping module.
    
    This demonstrates how to use the time warping mechanisms in practice.
    """
    # Create configuration
    config = TimeWarpingConfig(
        mode=TimeWarpingMode.ACCELERATED,
        strategy=TimeWarpingStrategy.ADAPTIVE,
        speed_factor=10.0,  # 10x acceleration
        max_warp_factor=100.0,
        min_warp_factor=0.1,
        adaptive_threshold=0.02,
        smoothing_window=5
    )
    
    # Create time warping manager
    tw_manager = TimeWarpingManager(config)
    
    # Start the time warping
    tw_manager.start()
    
    # Simulate some time synchronization
    try:
        for i in range(5):
            tw_manager.synchronize()
            stats = tw_manager.get_statistics()
            print(f"Step {i+1}: Sim Time={stats['current_simulation_time']:.3f}, "
                  f"Real Time={stats['current_real_time']:.3f}, "
                  f"Warp Factor={stats['current_warp_factor']:.3f}")
            time.sleep(0.1)  # Simulate some processing time
            
    except Exception as e:
        logger.error(f"Error during time warping: {str(e)}")
    
    # Stop the time warping
    tw_manager.stop()
    
    # Print final statistics
    final_stats = tw_manager.get_statistics()
    print("Final Statistics:")
    for key, value in final_stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    # Run example usage
    example_usage()