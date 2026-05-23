# Distributed Task Scheduler with DAG-Based Dependency Resolution

> **CS-511 Advanced Operating Systems** | Information Technology University, Lahore
> **Author:** Zaire Shakeel | **Instructor:** Dr. Khawaja M. Umar Suleman

---

## What This Project Does

This project is a **Master-Worker orchestration system** that takes a list of OS tasks with dependencies, figures out which tasks can run in parallel and which must wait, distributes them across multiple worker nodes, recovers automatically from failures, and produces a measurable performance report.

In simple terms:
- You give it an **input file** (`processes.txt`) with 25 OS process records
- It runs a **6-task pipeline** that analyses those records in parallel
- It produces an **output report** (`scheduling_report.txt`) with scheduling analysis and a recommendation

---

## System Architecture

```
processes.txt  +  pipeline.json
        │               │
        └───────┬───────┘
                ▼
        pipeline_loader.py
        (reads JSON → builds Task objects)
                │
                ▼
         DAG Engine (dag.py)
         ┌─────────────────────┐
         │ Kahn's Algorithm    │  ← topological sort, cycle detection
         │ Dependency Resolver │  ← BLOCKED → READY when parents done
         └─────────────────────┘
                │
                ▼
         Master Scheduler (master.py)
         ┌─────────────────────────────────┐
         │ Assigns tasks to idle workers   │
         │ Monitors heartbeats every 3s    │
         │ Re-assigns from dead workers    │
         │ Reads/writes SQLite State Table │
         └─────────────────────────────────┘
                │
        ┌───────┼───────┐
        ▼       ▼       ▼
    worker-1 worker-2 worker-3   ← run in PARALLEL
        │       │       │
        └───────┴───────┘
                │
                ▼
         real_tasks.py
         (reads data, computes, writes report)
                │
        ┌───────┴───────┐
        ▼               ▼
scheduling_report.txt  metrics.csv
(human-readable output) (performance data)
```

---

## The Pipeline — 6 Tasks

| Task | Depends On | Worker | What It Does |
|---|---|---|---|
| `load_processes` | nothing | worker-1 | Reads all 25 records from `processes.txt` |
| `filter_high_priority` | load_processes | worker-1 | Filters processes with priority >= 5 |
| `compute_burst_stats` | load_processes | worker-2 | Calculates mean, median, stdev of burst times |
| `compute_wait_stats` | load_processes | worker-3 | Simulates FCFS and computes wait times |
| `detect_starvation` | compute_wait_stats | worker-1 | Flags processes waiting > 20ms |
| `generate_report` | filter + burst + starvation | worker-1 | Writes `scheduling_report.txt` |

> `filter_high_priority`, `compute_burst_stats`, and `compute_wait_stats` run **in parallel** across 3 workers simultaneously — this is the core demonstration of DAG-based parallelism.

---

## Project Structure

```
dag_scheduler/
│
├── main.py                    ← Entry point — run this
│
├── input/
│   ├── processes.txt          ← Input: 25 OS process records
│   └── pipeline.json          ← Pipeline task definitions + dependencies
│
├── output/
│   ├── scheduling_report.txt  ← Output: 5-section analysis report
│   └── metrics.csv            ← Output: per-task performance data
│
├── scheduler/
│   ├── task.py                ← Task model + 6 status states
│   ├── dag.py                 ← DAG engine + Kahn's algorithm
│   ├── master.py              ← Master orchestrator + fault tolerance
│   └── pipeline_loader.py     ← Reads pipeline.json → Task objects
│
├── workers/
│   ├── worker.py              ← Worker node + heartbeat
│   └── real_tasks.py          ← Real task functions that process data
│
├── monitoring/
│   └── metrics.py             ← Performance monitoring framework
│
├── database/
│   └── state_db.py            ← SQLite Metadata State Table
│
├── tests/
│   └── test_dag.py            ← 24 unit tests (pytest)
│
└── requirements.txt
```

---

## Key Concepts

### DAG — Directed Acyclic Graph
A dependency map where arrows go one way and no loops are allowed. Each task is a node. Each dependency is an edge. Kahn's algorithm resolves the execution order and detects cycles before any task runs.

### Task States
```
PENDING → BLOCKED → READY → RUNNING → COMPLETED
                                   → FAILED
```
- **BLOCKED** — has unfinished parents, cannot run yet
- **READY** — all parents done, waiting for an idle worker
- **RUNNING** — assigned to a worker and executing

### Fault Tolerance
Every worker sends a **heartbeat** to the Master every 3 seconds.
If no heartbeat is received for 10 seconds, the worker is declared dead.
The Master reads the **SQLite State Table**, finds tasks that were RUNNING on the dead worker, and promotes them back to READY for re-assignment.

### Metadata State Table
A SQLite database that persists every task's status, assigned worker, start time, result, and retry count. Updated on every state change. If the Master crashes, it reads this table to resume from the exact point of failure.

---

## Input File Format

**`input/processes.txt`**
```
# PID | process_name | arrival_time | burst_time | priority | state
P01 | sys_init        |  0 |  4 |  9 | TERMINATED
P02 | kernel_thread   |  1 |  7 |  8 | TERMINATED
P06 | disk_scheduler  |  5 |  3 | 10 | TERMINATED
...
P25 | bg_service      | 24 | 20 |  4 | TERMINATED
```

- **arrival_time** — when the process entered the system
- **burst_time** — CPU time the process needs (milliseconds)
- **priority** — 1 = lowest, 10 = highest

---

## Output — What the Report Shows

**`output/scheduling_report.txt`** has 5 sections:

| Section | What It Contains |
|---|---|
| 1. High Priority Processes | 16 of 25 processes with priority >= 5 |
| 2. CPU Burst Time Statistics | Mean=13ms, Median=9ms, StdDev=9.89ms |
| 3. FCFS Wait Time Analysis | Per-process wait time under First-Come-First-Served |
| 4. Starvation Analysis | 21 of 25 processes waited > 20ms threshold |
| 5. Scheduling Recommendation | Priority Scheduling with Aging (data-driven) |

> The recommendation is **not hardcoded**. If starvation is detected the system recommends Priority Scheduling with Aging. If no starvation is found it recommends monitoring. Change the input data and the recommendation changes automatically.

---

## Performance Results (Actual Run)

| Metric | Value |
|---|---|
| Total wall-clock time | 2.84s |
| Throughput | 2.116 tasks/sec |
| Avg execution time | 0.306s per task |
| Avg turnaround time | 1.156s |
| Load balance variance | 2.0 |
| Tasks completed | 6 / 6 |
| Failed | 0 |

---

## Setup and Installation

**Prerequisites:** Python 3.8+

```bash
# 1. Clone the repository
git clone https://github.com/ZaireShakeel/distributed_task_scheduler-aos.git
cd distributed_task_scheduler-aos

# 2. Create virtual environment
python -m venv .venv

# 3. Activate it
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Mac / Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

---

## How to Run

```bash
# Main pipeline — reads processes.txt, writes scheduling_report.txt
python main.py

# Fault tolerance demo — shows automatic retry and recovery
python main.py --scenario fault

# Large 10-task pipeline with 4 workers
python main.py --scenario large --workers 4

# Run all 24 unit tests
python -m pytest tests/ -v
```

---

## Example Terminal Output

```
DAG built: 6 tasks
Exec order: load_processes → compute_burst_stats → compute_wait_stats
            → filter_high_priority → detect_starvation → generate_report

Dispatching 'load_processes'       → worker-1
Task 'load_processes' COMPLETED in 0.44s

Task 'filter_high_priority'  unblocked → READY
Task 'compute_burst_stats'   unblocked → READY
Task 'compute_wait_stats'    unblocked → READY

Dispatching 'filter_high_priority' → worker-1  ┐
Dispatching 'compute_burst_stats'  → worker-2  ├─ PARALLEL
Dispatching 'compute_wait_stats'   → worker-3  ┘

Task 'detect_starvation' unblocked → READY
Task 'generate_report'   unblocked → READY

✓  Pipeline completed successfully!
→  Report  : output/scheduling_report.txt
→  Metrics : output/metrics.csv
```

---

## Running the Tests

```bash
python -m pytest tests/ -v
```

Expected output:
```
tests/test_dag.py::TestTask::test_task_defaults                          PASSED
tests/test_dag.py::TestDAGConstruction::test_cycle_detection             PASSED
tests/test_dag.py::TestDAGStateTransitions::test_both_parents_done...    PASSED
tests/test_dag.py::TestIntegration::test_full_linear_pipeline            PASSED
...
24 passed in 2.18s
```

---

## Technologies Used

| Technology | Purpose |
|---|---|
| Python 3 | Core language |
| threading | Parallel worker execution |
| sqlite3 | Metadata State Table persistence |
| psutil | Resource monitoring |
| pytest | Unit testing |
| dataclasses | Task model |
| statistics | Burst time and wait time analysis |
| json | Pipeline configuration |

---

## Academic Context

This project was developed for **CS-511 Advanced Operating Systems** at ITU Lahore. It demonstrates:

- **DAG-based task dependency resolution** using Kahn's topological sort algorithm
- **True parallel execution** of independent tasks across multiple worker threads
- **Fault tolerance** through heartbeat monitoring and State Table-based task re-assignment
- **Observable performance monitoring** with throughput, turnaround time, and load balance metrics
- **Real-world scheduling analysis** demonstrating why FCFS causes starvation and recommending Priority Scheduling with Aging

---

## License

This project is developed for academic purposes as part of the MSCS program at ITU Lahore.
