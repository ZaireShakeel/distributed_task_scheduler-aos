"""
main.py - Entry Point
Two modes:
  1. PIPELINE mode (default): reads input/pipeline.json, processes real data,
     writes output/scheduling_report.txt
  2. SCENARIO mode: runs built-in simulation scenarios (ml, fault, large)

Usage:
  python main.py                          # pipeline mode (real data)
  python main.py --scenario ml            # simulation scenario
  python main.py --scenario fault
  python main.py --scenario large
"""

import sys
import time
import argparse
import os

sys.path.insert(0, os.path.dirname(__file__))

from scheduler.task import Task
from scheduler.dag import DAG, DAGValidationError
from scheduler.master import Master
from scheduler.pipeline_loader import load_pipeline
from workers.worker import Worker
from monitoring.metrics import MetricsCollector
from database.state_db import StateDB


# ======================================================================
# BUILT-IN SIMULATION SCENARIOS
# ======================================================================

def scenario_ml_pipeline() -> list:
    return [
        Task(name="fetch_data",    func="data_fetch",          priority=1),
        Task(name="clean_data",    func="data_clean",          priority=2,
             dependencies=["fetch_data"]),
        Task(name="feature_eng",   func="feature_engineering", priority=2,
             dependencies=["clean_data"]),
        Task(name="train_model_A", func="model_train",         priority=3,
             dependencies=["feature_eng"], args={"duration": 2.0}),
        Task(name="train_model_B", func="model_train",         priority=3,
             dependencies=["feature_eng"], args={"duration": 1.5}),
        Task(name="evaluate",      func="model_evaluate",      priority=4,
             dependencies=["train_model_A", "train_model_B"]),
        Task(name="report",        func="report_generate",     priority=5,
             dependencies=["evaluate"]),
        Task(name="notify",        func="notify",              priority=6,
             dependencies=["report"]),
    ]


def scenario_fault_tolerance() -> list:
    return [
        Task(name="fetch",         func="data_fetch",      priority=1),
        Task(name="flaky_process", func="flaky_task",      priority=2,
             dependencies=["fetch"], max_retries=3),
        Task(name="report",        func="report_generate", priority=3,
             dependencies=["flaky_process"]),
        Task(name="notify",        func="notify",          priority=3,
             dependencies=["flaky_process"]),
    ]


def scenario_large_pipeline() -> list:
    return [
        Task(name="ingest_A",  func="data_fetch",          priority=1, args={"rows": 5000}),
        Task(name="ingest_B",  func="data_fetch",          priority=1, args={"rows": 3000}),
        Task(name="ingest_C",  func="data_fetch",          priority=1, args={"rows": 8000}),
        Task(name="merge",     func="data_clean",          priority=2,
             dependencies=["ingest_A", "ingest_B", "ingest_C"]),
        Task(name="transform", func="feature_engineering", priority=3,
             dependencies=["merge"]),
        Task(name="validate",  func="model_evaluate",      priority=4,
             dependencies=["transform"]),
        Task(name="export",    func="report_generate",     priority=5,
             dependencies=["validate"]),
        Task(name="archive",   func="data_clean",          priority=6,
             dependencies=["export"]),
        Task(name="cleanup",   func="notify",              priority=7,
             dependencies=["archive"]),
        Task(name="done",      func="notify",              priority=8,
             dependencies=["cleanup"], args={"email": "admin@itu.edu.pk"}),
    ]


SCENARIOS = {
    "ml":    (scenario_ml_pipeline,     3),
    "fault": (scenario_fault_tolerance, 2),
    "large": (scenario_large_pipeline,  4),
}


# ======================================================================
# SHARED RUNNER
# ======================================================================

def run_pipeline(tasks: list, num_workers: int, pipeline_name: str):
    print("\n" + "=" * 65)
    print("   DISTRIBUTED TASK SCHEDULER — DAG ORCHESTRATION ENGINE")
    print(f"   Pipeline : {pipeline_name}")
    print(f"   Workers  : {num_workers}")
    print("=" * 65 + "\n")

    dag = DAG()
    for task in tasks:
        dag.add_task(task)
    try:
        dag.build_edges()
    except DAGValidationError as e:
        print(f"[ERROR] DAG validation failed: {e}")
        sys.exit(1)

    print(f"  DAG built   : {len(dag.tasks)} tasks")
    print(f"  Exec order  : {' → '.join(dag.topological_order())}\n")

    metrics = MetricsCollector()
    db = StateDB()
    db.clear()
    for task in dag.tasks.values():
        db.insert_task(task)

    master = Master(dag=dag, metrics=metrics, db=db)
    workers = []
    for i in range(1, num_workers + 1):
        w = Worker(worker_id=f"worker-{i}", master=master)
        w.start()
        master.register_worker(w)
        workers.append(w)

    print(f"  {len(workers)} worker(s) online.\n")

    master.start()
    master.wait_until_done(timeout=180)
    time.sleep(0.5)

    for w in workers:
        w.stop()

    master.print_state_table()
    db.print_state_table()
    metrics.print_report()

    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "metrics.csv")
    metrics.export_csv(csv_path)

    # Print and confirm the .txt output report if pipeline mode was used
    from workers.real_tasks import DATA_STORE
    report_path = DATA_STORE.get("report_path")
    if report_path and os.path.exists(report_path):
        print("\n" + "=" * 65)
        print("  OUTPUT FILE — scheduling_report.txt")
        print("=" * 65)
        with open(report_path, "r") as f:
            print(f.read())

    if dag.has_failed_tasks():
        print("  ⚠  Some tasks failed.\n")
        sys.exit(1)
    else:
        print("  ✓  Pipeline completed successfully!\n")
        if report_path:
            print(f"  → Report  : {report_path}")
        print(f"  → Metrics : {csv_path}\n")


# ======================================================================
# MAIN
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description="DAG Task Scheduler")
    parser.add_argument(
        "--scenario", choices=list(SCENARIOS.keys()), default=None,
        help="Run a simulation scenario (ml / fault / large)"
    )
    parser.add_argument(
        "--pipeline", default="input/pipeline.json",
        help="Path to pipeline JSON file (default: input/pipeline.json)"
    )
    parser.add_argument(
        "--workers", type=int, default=None,
        help="Override number of workers"
    )
    args = parser.parse_args()

    if args.scenario:
        task_fn, default_workers = SCENARIOS[args.scenario]
        num_workers = args.workers or default_workers
        run_pipeline(task_fn(), num_workers, f"Scenario — {args.scenario.upper()}")
    else:
        pipeline_path = os.path.join(os.path.dirname(__file__), args.pipeline)
        config = load_pipeline(pipeline_path)
        num_workers = args.workers or config["num_workers"]
        run_pipeline(config["tasks"], num_workers, config["pipeline_name"])


if __name__ == "__main__":
    main()
