# MAHL: Multi-Agent LLM-Guided Hierarchical Chiplet Design - Demo Implementation

## Overview

This repository contains a demo implementation of the **MAHL (Multi-Agent LLM-Guided Hierarchical Chiplet Design with Adaptive Debugging)** framework. The system demonstrates how large language models (LLMs) can be leveraged to guide chiplet design processes through hierarchical description generation, RTL implementation, and adaptive debugging.

The demo showcases a modular architecture that enables multi-agent LLM coordination for chiplet design, supporting design space exploration and validation with real-time debugging capabilities.

---

## Architecture

### Modules

| Module Name                  | Purpose                                                                 | Complexity |
|-----------------------------|-------------------------------------------------------------------------|------------|
| `MultiAgentLLMCoordinator`  | Coordinates multiple LLM agents to guide chiplet design process         | High       |
| `HierarchicalDescriptionGenerator` | Generates hierarchical chiplet descriptions using LLMs              | High       |
| `RTLImplementationEngine`   | Handles RTL code generation and implementation                          | Medium     |
| `DesignSpaceExplorer`       | Performs design space exploration using LLM guidance                    | High       |
| `AdaptiveDebugger`          | Implements adaptive debugging mechanisms for real-time issue resolution | Medium     |
| `ValidationFramework`       | Provides RTL validation and verification for generated designs          | Medium     |
| `LLMInterfaceManager`       | Manages communication with LLM services and agent coordination          | Medium     |
| `ChipletRepository`         | Stores and manages chiplet IP libraries and reusable components         | Low        |

### Dependencies

- `MultiAgentLLMCoordinator` → `HierarchicalDescriptionGenerator`
- `MultiAgentLLMCoordinator` → `DesignSpaceExplorer`
- `MultiAgentLLMCoordinator` → `RTLImplementationEngine`
- `MultiAgentLLMCoordinator` → `AdaptiveDebugger`
- `HierarchicalDescriptionGenerator` → `LLMInterfaceManager`
- `DesignSpaceExplorer` → `LLMInterfaceManager`
- `RTLImplementationEngine` → `HierarchicalDescriptionGenerator`
- `RTLImplementationEngine` → `ValidationFramework`
- `AdaptiveDebugger` → `ValidationFramework`
- `LLMInterfaceManager` → `ChipletRepository`

---

## Setup Instructions

### Prerequisites

- Python 3.9+
- Docker (for containerized LLM services)
- pipenv or virtual environment

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd mahl-demo
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. (Optional) Set up Docker containers for LLM services:
   ```bash
   docker-compose up -d
   ```

---

## Usage

### Running the Demo

To run the demo, execute the main entrypoint script:

```bash
python main.py
```

This will initialize the system and demonstrate a full chiplet design workflow:
1. Hierarchical description generation
2. RTL implementation
3. Design space exploration
4. Adaptive debugging

### Configuration

Configuration is managed via `config.yaml` and Pydantic models. Modify settings such as:
- LLM API endpoints
- Chiplet repository paths
- Validation parameters

---

## Notes on Placeholders

This demo implementation includes several placeholders for:
- **LLM API keys and endpoints**: These must be configured in `config.yaml` or environment variables.
- **Chiplet templates and libraries**: Sample data is included but should be replaced with actual chiplet designs.
- **Validation test cases**: Placeholder test cases are included for demonstration purposes.

> ⚠️ **Important**: Before running the demo in a production environment, ensure all placeholders are replaced with valid configurations and data.

---

## Framework Suggestions

The following frameworks are suggested for extending or deploying this system:

- **Pydantic**: For data validation and configuration management
- **LangChain**: For LLM integration and agent management
- **FastAPI**: For REST API endpoints for system interaction
- **Docker**: For containerization of LLM services and components
- **Celery**: For distributed task execution across agents
- **SQLAlchemy**: For database management of chiplet designs and repositories

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Contact

For questions or feedback, please open an issue or contact the maintainers.