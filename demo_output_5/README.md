# Fast End-to-End Performance Simulation Framework

**Demo Implementation of "Fast End-to-End Performance Simulation Architecture for Accelerated Hardware-Software Stacks"**

---

## Overview

This repository implements a minimalist full-stack simulation framework inspired by **NEX** and **DSim**, designed to achieve orders-of-magnitude faster performance simulation while maintaining accuracy. The system separates native execution components from simulated ones, with precise synchronization mechanisms to ensure correctness.

The core idea is to simulate only unavailable components and run the rest natively, with cycle-accurate simulation of performance-critical aspects of simulated components.

---

## Architecture

### Core Modules

| Module | Purpose | Complexity |
|--------|---------|------------|
| **NEX Orchestrator** | Manages the overall simulation workflow, including synchronization, runtime execution, scheduling, and time warping | High |
| **NEX Synchronization** | Handles precise synchronization between native and simulated components | High |
| **NEX Runtime** | Provides runtime environment for native components and interfaces with simulated components | Medium |
| **NEX Scheduler** | Determines which components to simulate vs. execute natively, based on availability and performance-criticality | Medium |
| **DSim Di-Simulator** | Simulates performance-critical aspects of unavailable components with cycle accuracy | High |
| **DSim LPN Engine** | Computes performance using Labelled Petri Nets (LPNs) | High |
| **DSim Functionality Engine** | Handles functional simulation of components | Medium |
| **DSim Synchronization Manager** | Ensures synchronization between performance and functionality simulation | High |
| **Interface Layer** | Provides modular composition interfaces between native and simulated components | Medium |

### Module Dependencies

```
NEX Synchronization → NEX Runtime
NEX Scheduler → NEX Orchestrator
DSim Di-Simulator → NEX Orchestrator
DSim LPN Engine → DSim Di-Simulator
DSim Functionality Engine → DSim Di-Simulator
DSim Synchronization Manager → DSim Di-Simulator
Interface Layer → NEX Runtime
Interface Layer → DSim Di-Simulator
```

### Language & Framework Suggestions

- **Language**: Python
- **Frameworks**:
  - PyPy or CPython with Cython for performance-critical native execution
  - SimPy for event-driven simulation
  - PyPES or custom LPN implementation for Petri net modeling
  - asyncio for concurrent execution
  - pytest for testing and validation

---

## Setup Instructions

### Prerequisites

- Python 3.8+
- pip

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/fast-simulation-demo.git
   cd fast-simulation-demo
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

---

## Usage

### Running the Demo

To run a basic simulation:

```bash
python demo.py
```

### Configuration

Simulation parameters can be configured via:

- `config.yaml` – for high-level simulation settings
- `components.json` – for defining native and simulated components
- `scheduler_config.json` – for scheduling policies

### Example Simulation Flow

1. Initialize the NEX Orchestrator
2. Load components into the NEX Runtime
3. Schedule components using the NEX Scheduler
4. Simulate performance-critical components using DSim
5. Synchronize results with native execution via NEX Synchronization
6. Output final performance metrics

---

## Notes on Placeholders

This demo implementation includes several placeholder modules and configurations that are intended for demonstration purposes only:

- **DSim LPN Engine**: Placeholder for LPN-based performance modeling; requires integration with a Petri net library.
- **DSim Functionality Engine**: Placeholder for functional simulation logic; needs to be extended with actual component behavior models.
- **Interface Layer**: Modular interfaces are stubbed; actual integration logic must be implemented per use case.
- **Component Definitions**: Sample component configurations are included but not exhaustive; users should define their own based on target hardware/software stacks.

---

## Contributing

We welcome contributions! Please open an issue or submit a pull request if you'd like to improve this demo or add new features.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

--- 

*This demo is a simplified implementation of the architecture described in the paper. It is intended for educational and research purposes.*