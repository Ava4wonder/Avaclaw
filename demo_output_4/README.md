# NEX-DSim Fast End-to-End Performance Simulation Demo

This repository contains a demo implementation of the **NEX-DSim** architecture for fast end-to-end performance simulation of accelerated hardware-software stacks. The system simulates only the unavailable components while running the rest natively, with precise synchronization between native and simulated execution.

---

## 🧠 Overview

The NEX-DSim architecture is designed to provide high-speed, accurate simulation of complex systems by combining:
- **NEX** (Native Execution and Simulation Orchestrator)
- **DSim** (Discrete Simulator)

It supports modular composition and enables precise synchronization between native and simulated components, making it ideal for performance evaluation of accelerated systems.

---

## 🏗️ Architecture

### Modules

| Module Name                     | Purpose                                                                 | Complexity |
|-------------------------------|-------------------------------------------------------------------------|------------|
| `NEX_Orchestrator`            | Manages overall simulation workflow including scheduling and time warping | High       |
| `NEX_Synchronization`         | Ensures correct synchronization between native and simulated components | High       |
| `NEX_Runtime`                 | Provides runtime environment for native components                      | Medium     |
| `NEX_Scheduler`               | Schedules execution of native and simulated components                  | Medium     |
| `NEX_Time_Warping`            | Aligns simulation time with real-time or accelerated execution          | High       |
| `DSim_DiSimulator`            | Simulates performance-critical unavailable components using LPNs        | High       |
| `DSim_Performance_Computation`| Computes performance metrics for simulated components                   | Medium     |
| `DSim_Functionality_Computation`| Ensures functional correctness of simulated components               | Medium     |
| `DSim_Synchronization_Manager`| Coordinates performance and functionality computations in DSim          | High       |
| `Interface_Composer`          | Enables interoperability between NEX and DSim modules                   | Medium     |

### Dependencies

- `NEX_Synchronization` → `NEX_Runtime`
- `NEX_Scheduler` → `NEX_Orchestrator`
- `NEX_Time_Warping` → `NEX_Orchestrator`
- `DSim_Performance_Computation` → `DSim_DiSimulator`
- `DSim_Functionality_Computation` → `DSim_DiSimulator`
- `DSim_Synchronization_Manager` → `DSim_DiSimulator`
- `Interface_Composer` → `NEX_Orchestrator`
- `Interface_Composer` → `DSim_DiSimulator`

### Language & Frameworks

- **Language**: Python
- **Suggested Frameworks**:
  - [SimPy](https://simpy.readthedocs.io/) – Discrete event simulation
  - [NumPy](https://numpy.org/) – Numerical computations
  - [Pybind11](https://github.com/pybind/pybind11) – C++ integration (optional)
  - [PyQt](https://www.riverbankcomputing.com/static/Docs/PyQt5/) or [Tkinter](https://docs.python.org/3/library/tkinter.html) – Visualization
  - [pytest](https://docs.pytest.org/) – Unit testing

---

## 🛠️ Setup Instructions

### Prerequisites

- Python 3.8+
- pip

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/nex-dsim-demo.git
   cd nex-dsim-demo
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the demo:
   ```bash
   python demo.py
   ```

> Note: If you're using optional visualization or C++ integration, install those packages separately.

---

## 🚀 Usage

The demo simulates a basic system where:
- Some components run natively.
- Others are simulated using DSim.
- All components are synchronized via NEX modules.

### Example Output

```text
[INFO] Starting simulation...
[INFO] NEX_Orchestrator initialized.
[INFO] DSim_DiSimulator started.
[INFO] Native component executed.
[INFO] Simulation completed in 10.2s.
```

You can customize the simulation by modifying:
- `config.json`: Define components and their behavior.
- `modules/`: Extend or replace individual modules.

---

## ⚠️ Notes on Placeholders

This demo uses placeholder implementations for demonstration purposes. Actual use cases may require:

- Real hardware/software models in `DSim_DiSimulator`
- Integration with real native components
- Custom scheduling logic in `NEX_Scheduler`
- Advanced time warping in `NEX_Time_Warping`

> 🔧 Placeholder modules are marked with `# TODO` comments and should be replaced with actual logic for production use.

---

## 📦 Repository Structure

```
.
├── demo.py                 # Entry point for the demo
├── config.json             # Simulation configuration
├── modules/
│   ├── __init__.py
│   ├── NEX_Orchestrator.py
│   ├── NEX_Synchronization.py
│   ├── NEX_Runtime.py
│   ├── NEX_Scheduler.py
│   ├── NEX_Time_Warping.py
│   ├── DSim_DiSimulator.py
│   ├── DSim_Performance_Computation.py
│   ├── DSim_Functionality_Computation.py
│   ├── DSim_Synchronization_Manager.py
│   └── Interface_Composer.py
├── tests/
│   └── test_modules.py
├── requirements.txt
└── README.md
```

---

## 🧪 Testing

Run unit tests using pytest:

```bash
pytest tests/
```

---

## 📄 License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---

## 📬 Contact

For questions or contributions, please open an issue or contact the maintainers.

--- 

*Demo Implementation of the NEX-DSim Fast End-to-End Performance Simulation Architecture*  
**Paper**: [Demo Paper Implementation]  
**Version**: v0.1.0  
**Author**: [Your Name or Organization]