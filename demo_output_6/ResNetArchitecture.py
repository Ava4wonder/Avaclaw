"""
ResNetArchitecture Module

Implements ResNet-based neural network models with configurable depth and 
regularization techniques including weight decay and AdamW optimizer.

This module provides a flexible ResNet implementation that can be configured
for different depths and regularization strategies to improve model performance
and generalization.
"""

import jax
import jax.numpy as jnp
import haiku as hk
import optax
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
import numpy as np


@dataclass
class ResNetConfig:
    """Configuration class for ResNet architecture."""
    num_channels: int = 64
    num_blocks: int = 18
    num_classes: int = 1000
    use_bias: bool = False
    use_batch_norm: bool = True
    weight_decay: float = 1e-4
    learning_rate: float = 0.001
    adamw_b1: float = 0.9
    adamw_b2: float = 0.999
    adamw_eps: float = 1e-8


class ResNetBlock(hk.Module):
    """A single ResNet block with optional batch normalization and residual connection."""
    
    def __init__(self, 
                 num_channels: int,
                 stride: int = 1,
                 use_batch_norm: bool = True,
                 use_bias: bool = False,
                 name: str = "resnet_block"):
        """
        Initialize a ResNet block.
        
        Args:
            num_channels: Number of output channels
            stride: Stride for the first convolutional layer
            use_batch_norm: Whether to use batch normalization
            use_bias: Whether to use bias in convolutions
            name: Module name for Haiku
        """
        super().__init__(name=name)
        self.num_channels = num_channels
        self.stride = stride
        self.use_batch_norm = use_batch_norm
        self.use_bias = use_bias
        
    def __call__(self, x: jnp.ndarray, is_training: bool) -> jnp.ndarray:
        """
        Forward pass through the ResNet block.
        
        Args:
            x: Input tensor of shape (batch, height, width, channels)
            is_training: Whether in training mode for batch norm
            
        Returns:
            Output tensor of same shape as input
        """
        # Save input for residual connection
        residual = x
        
        # First convolutional layer
        x = hk.Conv2D(
            output_channels=self.num_channels,
            kernel_shape=3,
            stride=self.stride,
            padding="SAME",
            with_bias=self.use_bias
        )(x)
        
        if self.use_batch_norm:
            x = hk.BatchNorm(create_offset=True, create_scale=True, is_training=is_training)(x)
            
        x = jax.nn.relu(x)
        
        # Second convolutional layer
        x = hk.Conv2D(
            output_channels=self.num_channels,
            kernel_shape=3,
            stride=1,
            padding="SAME",
            with_bias=self.use_bias
        )(x)
        
        if self.use_batch_norm:
            x = hk.BatchNorm(create_offset=True, create_scale=True, is_training=is_training)(x)
            
        # Apply residual connection
        # TODO: Handle channel mismatch in residual connection (if needed)
        if self.stride != 1 or residual.shape[-1] != self.num_channels:
            # Adjust dimensions of residual to match x
            residual = hk.Conv2D(
                output_channels=self.num_channels,
                kernel_shape=1,
                stride=self.stride,
                padding="SAME",
                with_bias=self.use_bias
            )(residual)
            
        x = x + residual
        x = jax.nn.relu(x)
        
        return x


class ResNetArchitecture(hk.Module):
    """Main ResNet architecture implementation with configurable depth."""
    
    def __init__(self, 
                 config: ResNetConfig,
                 name: str = "resnet"):
        """
        Initialize the ResNet architecture.
        
        Args:
            config: Configuration object for ResNet
            name: Module name for Haiku
        """
        super().__init__(name=name)
        self.config = config
        
        # Determine block configuration based on num_blocks
        self.block_config = self._get_block_config()
        
    def _get_block_config(self) -> List[Tuple[int, int]]:
        """
        Generate block configuration based on number of blocks.
        
        Returns:
            List of (num_channels, stride) tuples for each block group
        """
        # TODO: Implement more sophisticated block configuration logic
        # This is a simplified version that works for standard ResNet variants
        
        if self.config.num_blocks == 18:
            # ResNet-18 style: [2, 2, 2, 2] blocks per stage
            return [(64, 1), (128, 2), (256, 2), (512, 2)]
        elif self.config.num_blocks == 34:
            # ResNet-34 style: [3, 4, 6, 3] blocks per stage
            return [(64, 1), (128, 2), (256, 2), (512, 2)]
        elif self.config.num_blocks == 50:
            # ResNet-50 style: [3, 4, 6, 3] blocks per stage
            return [(64, 1), (128, 2), (256, 2), (512, 2)]
        else:
            # Default configuration for other sizes
            return [(self.config.num_channels, 1), 
                    (self.config.num_channels * 2, 2),
                    (self.config.num_channels * 4, 2),
                    (self.config.num_channels * 8, 2)]
    
    def __call__(self, x: jnp.ndarray, is_training: bool = True) -> jnp.ndarray:
        """
        Forward pass through the ResNet architecture.
        
        Args:
            x: Input tensor of shape (batch, height, width, channels)
            is_training: Whether in training mode for batch norm
            
        Returns:
            Output logits of shape (batch, num_classes)
        """
        # Initial convolutional layer
        x = hk.Conv2D(
            output_channels=self.config.num_channels,
            kernel_shape=7,
            stride=2,
            padding="SAME",
            with_bias=self.config.use_bias
        )(x)
        
        if self.config.use_batch_norm:
            x = hk.BatchNorm(create_offset=True, create_scale=True, is_training=is_training)(x)
            
        x = jax.nn.relu(x)
        x = hk.MaxPool(window_shape=3, strides=2, padding="SAME")(x)
        
        # ResNet blocks
        for i, (num_channels, stride) in enumerate(self.block_config):
            # TODO: Implement configurable number of blocks per stage
            num_blocks_in_stage = 2  # Simplified - should be configurable
            
            for j in range(num_blocks_in_stage):
                # First block in stage uses stride
                current_stride = stride if j == 0 else 1
                x = ResNetBlock(
                    num_channels=num_channels,
                    stride=current_stride,
                    use_batch_norm=self.config.use_batch_norm,
                    use_bias=self.config.use_bias
                )(x, is_training)
        
        # Global average pooling
        x = jnp.mean(x, axis=(1, 2))  # Average over spatial dimensions
        
        # Fully connected layer for classification
        x = hk.Linear(self.config.num_classes, with_bias=self.config.use_bias)(x)
        
        return x


def create_resnet_model(config: ResNetConfig) -> hk.Transformed:
    """
    Create a ResNet model using Haiku's Transformed wrapper.
    
    Args:
        config: ResNet configuration
        
    Returns:
        Haiku Transformed object for the model
    """
    def model_fn(x, is_training=True):
        return ResNetArchitecture(config)(x, is_training)
    
    return hk.transform(model_fn)


def create_optimizer(config: ResNetConfig) -> optax.GradientTransformation:
    """
    Create AdamW optimizer with weight decay.
    
    Args:
        config: ResNet configuration
        
    Returns:
        Optimizer object
    """
    # TODO: Add support for more sophisticated learning rate scheduling
    return optax.adamw(
        learning_rate=config.learning_rate,
        b1=config.adamw_b1,
        b2=config.adamw_b2,
        eps=config.adamw_eps,
        weight_decay=config.weight_decay
    )


def create_resnet_with_optimizer(config: ResNetConfig) -> Tuple[hk.Transformed, optax.GradientTransformation]:
    """
    Create both the ResNet model and its optimizer.
    
    Args:
        config: ResNet configuration
        
    Returns:
        Tuple of (model_transformed, optimizer)
    """
    model = create_resnet_model(config)
    optimizer = create_optimizer(config)
    
    return model, optimizer


# Example usage
if __name__ == "__main__":
    # Create a ResNet-18 configuration
    config = ResNetConfig(
        num_channels=64,
        num_blocks=18,
        num_classes=1000,
        use_bias=False,
        use_batch_norm=True,
        weight_decay=1e-4,
        learning_rate=0.001
    )
    
    # Create model and optimizer
    model, optimizer = create_resnet_with_optimizer(config)
    
    # Initialize with dummy input
    rng = jax.random.PRNGKey(42)
    dummy_input = jnp.ones((1, 224, 224, 3))
    
    # Initialize parameters
    params = model.init(rng, dummy_input, is_training=True)
    
    print("ResNet model created successfully!")
    print(f"Model parameters shape: {jax.tree_util.tree_map(lambda x: x.shape, params)}")
    
    # Example forward pass
    logits = model.apply(params, rng, dummy_input, is_training=False)
    print(f"Output shape: {logits.shape}")
    
    # Create optimizer state
    opt_state = optimizer.init(params)
    print("Optimizer created successfully!")