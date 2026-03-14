"""
OptimizerConfig module for managing optimization configurations including AdamW 
with weight decay regularization.

This module provides configuration management for the AdamW optimizer as used 
in the AlphaEvolve system, specifically tailored for ResNet architectures with 
weight decay regularization to prevent overfitting.
"""

from dataclasses import dataclass
from typing import Optional
import optax


@dataclass
class OptimizerConfig:
    """
    Configuration class for optimizer settings including AdamW with weight decay.
    
    This configuration is used in the AlphaEvolve system to manage optimization 
    parameters for neural network training, particularly with ResNet architectures.
    
    Attributes:
        learning_rate (float): The learning rate for the optimizer. Default: 0.001
        weight_decay (float): Weight decay coefficient for regularization. 
                             Default: 0.0001
        beta1 (float): Exponential decay rate for the first moment estimates. 
                      Default: 0.9
        beta2 (float): Exponential decay rate for the second moment estimates. 
                      Default: 0.999
        eps (float): Small constant for numerical stability. Default: 1e-8
        clip_global_norm (Optional[float]): Global norm clipping value. If None, 
                                           no clipping is applied. Default: None
    """
    
    learning_rate: float = 0.001
    weight_decay: float = 0.0001
    beta1: float = 0.9
    beta2: float = 0.999
    eps: float = 1e-8
    clip_global_norm: Optional[float] = None
    
    def get_optimizer(self) -> optax.GradientTransformation:
        """
        Creates and returns the AdamW optimizer with specified configuration.
        
        Returns:
            optax.GradientTransformation: Configured AdamW optimizer with weight decay
            
        Note:
            This implementation follows the paper's recommendation to use AdamW 
            instead of Adam, especially with weight decay regularization for better
            training stability and generalization.
        """
        # Create AdamW optimizer with specified parameters
        optimizer = optax.adamw(
            learning_rate=self.learning_rate,
            b1=self.beta1,
            b2=self.beta2,
            eps=self.eps,
            weight_decay=self.weight_decay
        )
        
        # Apply global norm clipping if specified
        if self.clip_global_norm is not None:
            optimizer = optax.chain(
                optax.clip_by_global_norm(self.clip_global_norm),
                optimizer
            )
        
        return optimizer


def create_default_optimizer_config() -> OptimizerConfig:
    """
    Creates a default optimizer configuration suitable for most ResNet training tasks.
    
    Returns:
        OptimizerConfig: Default configuration with standard AdamW parameters
        
    Note:
        The default configuration follows common practices for ResNet training
        and the paper's emphasis on weight decay regularization to prevent overfitting.
    """
    return OptimizerConfig(
        learning_rate=0.001,
        weight_decay=0.0001,
        beta1=0.9,
        beta2=0.999,
        eps=1e-8
    )


def create_hyperparameter_optimizer_config() -> OptimizerConfig:
    """
    Creates an optimizer configuration suitable for hyperparameter optimization.
    
    Returns:
        OptimizerConfig: Configuration with broader parameter ranges for 
                        exploration during evolutionary processes
        
    Note:
        This configuration is designed for use in the hyperparameter sweep process
        where more exploratory settings are beneficial, as mentioned in the paper's
        evaluation and creative generation sections.
    """
    return OptimizerConfig(
        learning_rate=0.01,  # Broader range for exploration
        weight_decay=0.0001,  # Standard weight decay
        beta1=0.9,
        beta2=0.999,
        eps=1e-8,
        clip_global_norm=1.0  # Add clipping for stability during exploration
    )


# Example usage:
if __name__ == "__main__":
    # Create default optimizer configuration
    config = create_default_optimizer_config()
    print(f"Default optimizer config: {config}")
    
    # Get the actual optimizer
    optimizer = config.get_optimizer()
    print(f"Optimizer created: {optimizer}")
    
    # Create hyperparameter optimized configuration
    hp_config = create_hyperparameter_optimizer_config()
    print(f"Hyperparameter optimizer config: {hp_config}")
    
    # Get the hyperparameter optimizer
    hp_optimizer = hp_config.get_optimizer()
    print(f"Hyperparameter optimizer created: {hp_optimizer}")