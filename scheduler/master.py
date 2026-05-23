"""
master.py - The Master / Central Orchestrator
This is the conductor. It:
  - Holds the DAG
  - Assigns READY tasks to idle Workers
  - Listens for heartbeats
  - Re-assigns tasks from dead workers (fault tolerance)
  - Updates the Metadata State Table
"""

import time
import threading
import logging
from typing import Dict, List, Optional
from scheduler.dag import DAG
from scheduler.task import Task, TaskStatus
from monitoring.metrics import MetricsCollector
from database.state_db import StateDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MASTER] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("master")


class Master:
    """
    The central brain of the system.
    Runs a continuous scheduling loop in a background thread.
    """

    HEARTBEAT_TIMEOUT = 10  # seconds before a worker is considered dead

    def __init__(self, dag: DAG, metrics: MetricsCollector, db: StateDB):
        self.dag = dag
        self.metrics = metrics
        self.db = db

        # Worker registry: worker_id -> {"worker": Worker, "last_heartbeat": float, "busy": bool}
        self._workers: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Worker registration
    # ------------------------------------------------------------------

    def register_worker(self, worker):
        with self._lock:
            self._workers[worker.worker_id] = {
                "worker": worker,
                "last_heartbeat": time.time(),
                "busy": False,
            }
        logger.info(f"Worker '{worker.worker_id}' registered.")
        self.metrics.record_worker_registered(worker.worker_id)

    def receive_heartbeat(self, worker_id: str):
        with self._lock:
            if worker_id in self._workers:
                self._workers[worker_id]["last_heartbeat"] = time.time()

    # ------------------------------------------------------------------
    # Main scheduling loop
    # ------------------------------------------------------------------

    def start(self):
        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduling_loop, daemon=True, name="SchedulerLoop"
        )
        self._scheduler_thread.start()
        logger.info("Master scheduler started.")

    def stop(self):
        self._running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info("Master scheduler stopped.")

    def _scheduling_loop(self):
        while self._running:
            self._check_heartbeats()
            self._assign_tasks()
            if self.dag.is_complete():
                logger.info("All tasks completed. Scheduler loop ending.")
                self._running = False
                break
            time.sleep(0.5)  # polling interval

    # ------------------------------------------------------------------
    # Heartbeat checker - fault tolerance core
    # ------------------------------------------------------------------

    def _check_heartbeats(self):
        now = time.time()
        dead_workers = []

        with self._lock:
            for wid, info in self._workers.items():
                if now - info["last_heartbeat"] > self.HEARTBEAT_TIMEOUT:
                    dead_workers.append(wid)

        for wid in dead_workers:
            self._handle_dead_worker(wid)

    def _handle_dead_worker(self, worker_id: str):
        logger.warning(f"Worker '{worker_id}' missed heartbeat — considered DEAD.")
        self.metrics.record_worker_failure(worker_id)

        # Find tasks that were RUNNING on this worker and re-queue them
        with self._lock:
            for task in self.dag.tasks.values():
                if (
                    task.assigned_worker == worker_id
                    and task.status == TaskStatus.RUNNING
                ):
                    if task.retry_count < task.max_retries:
                        task.retry_count += 1
                        task.status = TaskStatus.READY
                        task.assigned_worker = None
                        task.started_at = None
                        logger.warning(
                            f"Task '{task.name}' re-queued (retry {task.retry_count}/{task.max_retries})."
                        )
                        self.metrics.record_task_retry(task.name)
                        self.db.update_task(task)
                    else:
                        task.status = TaskStatus.FAILED
                        task.error = f"Worker '{worker_id}' died. Max retries exceeded."
                        logger.error(f"Task '{task.name}' permanently FAILED.")
                        self.db.update_task(task)

            # Remove dead worker from registry
            self._workers.pop(worker_id, None)

    # ------------------------------------------------------------------
    # Task assignment
    # ------------------------------------------------------------------

    def _assign_tasks(self):
        ready_tasks = self.dag.get_ready_tasks()
        if not ready_tasks:
            return

        with self._lock:
            idle_workers = [
                info["worker"]
                for info in self._workers.values()
                if not info["busy"]
            ]

        if not idle_workers:
            return

        for task, worker in zip(ready_tasks, idle_workers):
            self._dispatch(task, worker)

    def _dispatch(self, task: Task, worker):
        with self._lock:
            if task.status != TaskStatus.READY:
                return  # already grabbed by another thread

            task.status = TaskStatus.RUNNING
            task.assigned_worker = worker.worker_id
            task.started_at = time.time()
            self._workers[worker.worker_id]["busy"] = True

        logger.info(f"Dispatching task '{task.name}' → Worker '{worker.worker_id}'")
        self.metrics.record_task_dispatched(task.name, worker.worker_id)
        self.db.update_task(task)

        # Run the task in a separate thread so the scheduling loop isn't blocked
        t = threading.Thread(
            target=self._run_task_on_worker,
            args=(task, worker),
            daemon=True,
            name=f"Task-{task.name}"
        )
        t.start()

    def _run_task_on_worker(self, task: Task, worker):
        try:
            result = worker.execute(task)
            self._on_task_success(task, worker, result)
        except Exception as e:
            self._on_task_failure(task, worker, str(e))

    def _on_task_success(self, task: Task, worker, result: str):
        with self._lock:
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()
            self._workers[worker.worker_id]["busy"] = False

        logger.info(
            f"Task '{task.name}' COMPLETED on '{worker.worker_id}' "
            f"in {task.execution_time:.2f}s"
        )
        self.metrics.record_task_completed(task)
        self.db.update_task(task)

        # Unlock dependent tasks
        newly_ready = self.dag.on_task_completed(task.name)
        for name in newly_ready:
            logger.info(f"Task '{name}' unblocked → READY")
            self.db.update_task(self.dag.tasks[name])

    def _on_task_failure(self, task: Task, worker, error: str):
        with self._lock:
            self._workers[worker.worker_id]["busy"] = False

        if task.retry_count < task.max_retries:
            with self._lock:
                task.retry_count += 1
                task.status = TaskStatus.READY
                task.assigned_worker = None
                task.started_at = None
            logger.warning(
                f"Task '{task.name}' failed — retrying ({task.retry_count}/{task.max_retries}). Error: {error}"
            )
            self.metrics.record_task_retry(task.name)
        else:
            with self._lock:
                task.status = TaskStatus.FAILED
                task.error = error
                task.completed_at = time.time()
            logger.error(f"Task '{task.name}' permanently FAILED. Error: {error}")
            self.metrics.record_task_failed(task)

        self.db.update_task(task)

    # ------------------------------------------------------------------
    # Status display
    # ------------------------------------------------------------------

    def print_state_table(self):
        print("\n" + "=" * 70)
        print(f"{'TASK NAME':<20} {'STATUS':<12} {'WORKER':<15} {'WAIT(s)':<10} {'EXEC(s)':<10}")
        print("=" * 70)
        for task in self.dag.tasks.values():
            wait = f"{task.waiting_time:.2f}" if task.waiting_time else "-"
            exec_t = f"{task.execution_time:.2f}" if task.execution_time else "-"
            worker = task.assigned_worker or "-"
            print(f"{task.name:<20} {task.status.value:<12} {worker:<15} {wait:<10} {exec_t:<10}")
        print("=" * 70)
        summary = self.dag.summary()
        print("  ".join(f"{k}: {v}" for k, v in summary.items()))
        print()

    def wait_until_done(self, timeout: float = 120):
        """Block until all tasks finish or timeout."""
        start = time.time()
        while not self.dag.is_complete():
            if time.time() - start > timeout:
                logger.error("Timeout waiting for tasks to complete!")
                break
            time.sleep(1)
        self.stop()
