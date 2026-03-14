# MAHL: Multi-Agent LLM-Guided Hierarchical Chiplet Design Demo Implementation

## Overview

This repository contains a **demo implementation** of the **MAHL (Multi-Agent LLM-Guided Hierarchical Chiplet Design)** system. The demo simulates the core concepts of hierarchical chiplet design generation using LLM agents, including:

- Design description generation
- RTL implementation
- Validation
- Design space exploration

The system demonstrates how multiple specialized agents collaborate to generate chiplet designs from high-level specifications.

---

## Architecture

### Modules

| Module Name                        | Purpose                                                                 | Complexity |
|-----------------------------------|-------------------------------------------------------------------------|------------|
| LLM Agent Manager                 | Coordinates specialized LLM agents for design tasks                     | Medium     |
| Hierarchical Design Generator     | Breaks down specifications into modular chiplet components              | High       |
| RTL Implementation Engine         | Converts hierarchical designs into RTL code using LLM-guided synthesis  | High       |
| Design Space Explorer             | Explores design alternatives and optimizes configurations               | Medium     |
| Validation and Debugging System   | Validates RTL and provides adaptive debugging assistance                | Medium     |
| Specification Parser              | Interprets high-level specs into structured inputs                      | Low        |
| Output Formatter                  | Formats and presents generated designs and results                      | Low        |

### Dependencies

- `LLM Agent Manager` → `Hierarchical Design Generator`
- `LLM Agent Manager` → `RTL Implementation Engine`
- `LLM Agent Manager` → `Design Space Explorer`
- `LLM Agent Manager` → `Validation and Debugging System`
- `Hierarchical Design Generator` → `RTL Implementation Engine`
- `RTL Implementation Engine` → `Validation and Debugging System`
- `Design Space Explorer` → `Hierarchical Design Generator`
- `Specification Parser` → `LLM Agent Manager`
- `Validation and Debugging System` → `Output Formatter`

---

## Setup Instructions

### Prerequisites

- Python 3.9+
- Docker (optional, for containerization)

### Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-org/ma-hl-demo.git
   cd ma-hl-demo
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **(Optional) Set up Docker containers for modules:**

   ```bash
   docker build -t ma-hl-modules .
   ```

---

## Usage

### Running the Demo

1. **Start the LLM Agent Manager:**

   ```bash
   python main.py
   ```

2. **Provide a high-level specification (e.g., in `spec.json`):**

   ```json
   {
     "chiplet_name": "ExampleChiplet",
     "description": "A simple chiplet for processing 32-bit data streams",
     "performance_target": "100 MHz",
     "constraints": ["low_power", "small_area"]
   }
   ```

3. **View outputs in the `output/` directory:**

   - `hierarchical_design.json`
   - `rtl_code.v`
   - `validation_report.json`

---

## Notes on Placeholders

This demo implementation uses placeholders for:

- **LLM API Keys**: Replace with real keys or mock responses in `config.py`.
- **RTL Code Generation**: Simulated with placeholder templates; actual LLM integration is not included.
- **Design Space Exploration**: Mocked with sample configurations; real optimization logic is not implemented.
- **Validation Logic**: Simulated with basic checks; full validation system is not included.

> ⚠️ **Note**: This is a **demonstration-only** implementation. Actual LLM integration, RTL synthesis, and full validation are not included in this version.

---

## Framework Suggestions

- **LLM Integration**: Use [LangChain](https://github.com/langchain-ai/langchain) or [LlamaIndex](https://github.com/run-llama/llama_index)
- **ML Components**: [PyTorch](https://pytorch.org/) or [TensorFlow](https://www.tensorflow.org/)
- **API Framework**: [FastAPI](https://fastapi.tiangolo.com/) or [Flask](https://flask.palletsprojects.com/)
- **Containerization**: [Docker](https://www.docker.com/)
- **Testing**: [pytest](https://docs.pytest.org/)
- **Version Control**: [Git](https://git-scm.com/) with CI/CD pipeline

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Contact

For questions or feedback, please open an issue or contact the maintainers.