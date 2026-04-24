# Distributed Task Scheduler with Performance Monitoring Framework

A modular distributed system designed to simulate, execute, and analyze task scheduling across multiple computing nodes. This project focuses on the implementation of classical scheduling algorithms and a robust framework for real-time performance analytics.

## 🎓 Project Context
* **Institution:** Information Technology University (ITU), Lahore
* **Course:** Advanced Operating Systems (CS-511)
* **Instructor:** Dr. Khawaja M. Umar Suleman
* **Author:** Zaire Shakeel

## 🚀 Overview
In high-performance distributed environments, efficient task distribution is critical. This project implements a central **Scheduler** that assigns tasks to independent **Worker Nodes**. The system includes a **Performance Monitoring Framework** to evaluate and compare scheduling strategies based on measurable system metrics.

## 🏗️ System Architecture
The project is divided into four functional modules:
1.  **Central Scheduler:** Receives tasks, manages the ready queue, and implements scheduling logic.
2.  **Worker Nodes:** Simulates remote execution environments that process tasks and report health (heartbeats).
3.  **Monitoring Module:** Collects data on throughput, CPU utilization, and task-specific timings.
4.  **Database/Log Module:** Stores execution history for post-simulation analysis.

## 📋 Features & Algorithms
The system supports the following scheduling strategies:
* **FCFS (First-Come, First-Served):** Baseline non-preemptive scheduling.
* **Round Robin (RR):** Time-sliced fair distribution.
* **Shortest Job First (SJF):** Optimization for average waiting time.
* **Priority Scheduling:** Support for urgent workload handling.

## 📊 Performance Metrics
The framework provides comparative analysis using:
* **Turnaround Time:** Total time from task arrival to completion.
* **Waiting Time:** Time spent by tasks in the ready queue.
* **Throughput:** Number of tasks completed per unit of time.
* **Load Balancing Fairness:** Variance in CPU utilization across worker nodes.

## 📂 Project Structure
```text
distributed-task-scheduler-aos/
│── scheduler/       # Logic for queueing and algorithm selection
│── workers/         # Worker node simulation scripts
│── monitoring/      # Metrics collection and log generation
│── database/        # Storage for task history and node logs
│── docs/            # Technical reports and survey data
│── tests/           # Unit tests for scheduling logic
│── main.py          # Entry point to launch the system
└── requirements.txt # Project dependencies

🛠️ Setup & Installation

1. Clone the repository:

git clone [https://github.com/ZaireShakeel/distributed_task_scheduler-aos.git](https://github.com/ZaireShakeel/distributed_task_scheduler-aos.git)
cd distributed_task_scheduler-aos

2. Setup Virtual Environment:

python -m venv .venv
.venv\Scripts\Activate.ps1

3. Install Dependencies:

pip install -r requirements.txt

📝 License

This project is developed for academic purposes as part of the MSCS program at ITU.
