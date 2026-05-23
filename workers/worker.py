"""
worker.py - Worker Node
Simulates a remote computing node.
- Executes tasks assigned by the Master
- Sends periodic heartbeats to prove it is alive
- Reports CPU/RAM usage for monitoring
"""

import time
import random
import threading
import logging
import psutil
import os

logger = logging.getLogger("worker")


# ------------------------------------------------------------------
# Simulated task functions
# These represent real workloads (data processing, ML, I/O, etc.)
# ------------------------------------------------------------------

def simulate_data_fetch(args: dict) -> str:
    duration = args.get("duration", random.uniform(0.5, 1.5))
    time.sleep(duration)
    return f"Fetched {args.get('rows', 1000)} rows in {duration:.2f}s"

def simulate_data_clean(args: dict) -> str:
    duration = args.get("duration", random.uniform(0.3, 1.0))
    time.sleep(duration)
    return f"Cleaned dataset: removed {random.randint(5, 50)} nulls"

def simulate_feature_engineering(args: dict) -> str:
    duration = args.get("duration", random.uniform(0.5, 2.0))
    time.sleep(duration)
    return f"Engineered {random.randint(5, 20)} features"

def simulate_model_train(args: dict) -> str:
    duration = args.get("duration", random.uniform(1.0, 3.0))
    time.sleep(duration)
    acc = random.uniform(0.80, 0.99)
    return f"Model trained. Accuracy: {acc:.4f}"

def simulate_model_evaluate(args: dict) -> str:
    duration = args.get("duration", random.uniform(0.2, 0.8))
    time.sleep(duration)
    return f"Evaluation complete. F1: {random.uniform(0.78, 0.97):.4f}"

def simulate_report_generate(args: dict) -> str:
    duration = args.get("duration", random.uniform(0.2, 0.6))
    time.sleep(duration)
    return "Report generated and saved to /outputs/report.pdf"

def simulate_notify(args: dict) -> str:
    time.sleep(0.1)
    return f"Notification sent to {args.get('email', 'team@example.com')}"

def simulate_failing_task(args: dict) -> str:
    """Always fails — used to test retry/fault logic."""
    raise RuntimeError("Simulated task failure for fault-tolerance testing.")

def simulate_flaky_task(args: dict) -> str:
    """Fails 60% of the time — tests retry logic."""
    if random.random() < 0.6:
        raise RuntimeError("Flaky task failed (transient error).")
    time.sleep(0.3)
    return "Flaky task eventually succeeded."


TASK_REGISTRY = {
    "data_fetch":           simulate_data_fetch,
    "data_clean":           simulate_data_clean,
    "feature_engineering":  simulate_feature_engineering,
    "model_train":          simulate_model_train,
    "model_evaluate":       simulate_model_evaluate,
    "report_generate":      simulate_report_generate,
    "notify":               simulate_notify,
    "failing_task":         simulate_failing_task,
    "flaky_task":           simulate_flaky_task,
}


# ------------------------------------------------------------------
# Worker class
# ------------------------------------------------------------------

class Worker:
    HEARTBEAT_INTERVAL = 3  # seconds

    def __init__(self, worker_id: str, master=None):
        self.worker_id = worker_id
        self.master = master
        self._heartbeat_thread: threading.Thread = None
        self._alive = False
        self.tasks_completed = 0
        self.tasks_failed = 0

    def start(self):
        """Start heartbeat thread."""
        self._alive = True
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"Heartbeat-{self.worker_id}"
        )
        self._heartbeat_thread.start()
        logger.info(f"Worker '{self.worker_id}' started (PID={os.getpid()})")

    def stop(self):
        self._alive = False
        logger.info(f"Worker '{self.worker_id}' stopped. "
                    f"Completed={self.tasks_completed}, Failed={self.tasks_failed}")

    def _heartbeat_loop(self):
        while self._alive:
            if self.master:
                self.master.receive_heartbeat(self.worker_id)
            time.sleep(self.HEARTBEAT_INTERVAL)

    def execute(self, task) -> str:
        """
        Execute a task.
        Checks REAL_TASK_REGISTRY first (pipeline mode), then TASK_REGISTRY (simulation mode).
        """
        from workers.real_tasks import REAL_TASK_REGISTRY
        func_name = task.func

        combined = {**TASK_REGISTRY, **REAL_TASK_REGISTRY}
        if func_name not in combined:
            raise ValueError(f"Unknown function: '{func_name}'")

        logger.info(f"[{self.worker_id}] Executing '{task.name}' ({func_name})")
        result = combined[func_name](task.args)
        self.tasks_completed += 1
        return result

    def get_resource_usage(self) -> dict:
        """Returns current CPU and RAM usage of this process."""
        proc = psutil.Process(os.getpid())
        return {
            "worker_id": self.worker_id,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_mb": proc.memory_info().rss / (1024 * 1024),
            "timestamp": time.time(),
        }
