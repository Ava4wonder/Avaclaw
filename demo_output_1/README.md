# Demo Implementation: Human-Level Reward Design via Coding Large Language Models

This repository contains a demo implementation of the method described in the paper *"Human-level Reward Design via Coding Large Language Models"*. The system demonstrates how large language models (LLMs) can be used to design reward functions that align with human-level performance by integrating environment modeling, evolutionary optimization, and feedback-driven refinement.

---

## 🧠 Overview

The system implements a modular architecture for designing human-level rewards using LLMs through coding. It supports both **initialization** and **refinement** of reward functions via:

- **Environment modeling** to capture state and action spaces.
- **Evolutionary search** to optimize reward functions.
- **LLM-based reflection** to incorporate feedback and improve reward design iteratively.

---

## 🏗️ Architecture

### Modules

| Module Name                  | Purpose                                                                 | Complexity |
|-----------------------------|-------------------------------------------------------------------------|------------|
| Environment Context Module  | Models environment state and action space for reward design             | Medium     |
| Evolutionary Search Engine  | Performs evolutionary search over reward candidates                     | High       |
| Reward Reflection Engine    | Refines reward functions using LLMs and human feedback                  | High       |
| Human Feedback Interface    | Collects and integrates human feedback into reward design               | Medium     |
| LLM Prompt Designer         | Generates prompts for LLMs to produce reward functions                  | Medium     |
| Reward Evaluation Suite     | Evaluates reward function performance in simulated environments         | Medium     |
| Configuration Manager       | Manages system configuration and settings                               | Low        |

### Dependencies

- `Environment Context Module` → `Evolutionary Search Engine`
- `Evolutionary Search Engine` → `Reward Evaluation Suite`
- `Reward Reflection Engine` → `LLM Prompt Designer`
- `Human Feedback Interface` → `Reward Reflection Engine`
- `LLM Prompt Designer` → `Environment Context Module`
- `Reward Evaluation Suite` → `Evolutionary Search Engine`

---

## 🛠️ Setup Instructions

### Prerequisites

- Python 3.8+
- Docker (for LLM service containerization)
- Virtual environment (recommended)

### Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-username/demo-llm-reward-design.git
   cd demo-llm-reward-design
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up LLM services (optional but recommended):**

   Use Docker to run LLM services:

   ```bash
   docker-compose up -d
   ```

---

## 🚀 Usage

### Running the Demo

1. **Initialize the system:**

   ```bash
   python main.py --mode init
   ```

2. **Run evolutionary search:**

   ```bash
   python main.py --mode search
   ```

3. **Refine reward function with feedback:**

   ```bash
   python main.py --mode reflect
   ```

4. **Evaluate reward performance:**

   ```bash
   python main.py --mode evaluate
   ```

### Configuration

All configuration parameters are managed via `config.yaml`. Modify settings such as:

- Environment details
- Search parameters
- LLM prompt templates
- Feedback integration settings

---

## ⚠️ Notes on Placeholders

This demo implementation includes placeholders for:

- **LLM API keys**: Replace with valid keys in `config.yaml`.
- **Environment-specific data**: Replace with actual environment state/action space definitions.
- **Human feedback data**: Simulated feedback is used in this demo; real-world usage requires integration with a feedback collection system.
- **Reward evaluation metrics**: Default metrics are included; customize for your specific use case.

---

## 🧰 Framework Suggestions

To extend or deploy this system, consider using:

- **Deep Learning**: PyTorch or TensorFlow
- **Containerization**: Docker
- **API Framework**: FastAPI or Flask
- **Optimization**: Ray or Optuna
- **LLM Integration**: LangChain or LlamaIndex

---

## 📄 License

This project is licensed under the MIT License.

---

## 📬 Contact

For questions or contributions, please open an issue or contact the maintainers.

---