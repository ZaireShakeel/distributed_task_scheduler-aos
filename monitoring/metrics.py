"""
metrics.py - Performance Monitoring Framework
Collects real-time metrics on:
  - Task lifecycle (dispatch, complete, fail, retry)
  - Worker health (registered, failed)
  - System performance (throughput, latency, wait time)

All data is stored in-memory and can be printed as a report.
"""

import time
import threading
from typing import Dict, List
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TaskMetricRecord:
    name: str
    dispatched_at: float = 0.0
    completed_at: float = 0.0
    failed_at: float = 0.0
    worker_id: str = ""
    retries: int = 0
    execution_time: float = 0.0
    waiting_time: float = 0.0
    turnaround_time: float = 0.0
    success: bool = False


class MetricsCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._task_records: Dict[str, TaskMetricRecord] = {}
        self._worker_failures: List[dict] = []
        self._worker_registrations: List[str] = []
        self._timeline: List[dict] = []   # ordered log of events
        self._start_time = time.time()

    # ------------------------------------------------------------------
    # Recording events
    # ------------------------------------------------------------------

    def record_worker_registered(self, worker_id: str):
        with self._lock:
            self._worker_registrations.append(worker_id)
            self._log_event("WORKER_REGISTERED", worker_id=worker_id)

    def record_worker_failure(self, worker_id: str):
        with self._lock:
            self._worker_failures.append({"worker_id": worker_id, "at": time.time()})
            self._log_event("WORKER_FAILED", worker_id=worker_id)

    def record_task_dispatched(self, task_name: str, worker_id: str):
        with self._lock:
            rec = self._task_records.setdefault(task_name, TaskMetricRecord(name=task_name))
            rec.dispatched_at = time.time()
            rec.worker_id = worker_id
            self._log_event("TASK_DISPATCHED", task=task_name, worker=worker_id)

    def record_task_completed(self, task):
        with self._lock:
            rec = self._task_records.setdefault(task.name, TaskMetricRecord(name=task.name))
            rec.completed_at = time.time()
            rec.success = True
            rec.execution_time = task.execution_time or 0.0
            rec.waiting_time = task.waiting_time or 0.0
            rec.turnaround_time = task.turnaround_time or 0.0
            self._log_event("TASK_COMPLETED", task=task.name,
                            exec_time=f"{rec.execution_time:.2f}s")

    def record_task_failed(self, task):
        with self._lock:
            rec = self._task_records.setdefault(task.name, TaskMetricRecord(name=task.name))
            rec.failed_at = time.time()
            rec.success = False
            self._log_event("TASK_FAILED", task=task.name, retries=task.retry_count)

    def record_task_retry(self, task_name: str):
        with self._lock:
            rec = self._task_records.setdefault(task_name, TaskMetricRecord(name=task_name))
            rec.retries += 1
            self._log_event("TASK_RETRY", task=task_name)

    def _log_event(self, event: str, **kwargs):
        self._timeline.append({
            "t": round(time.time() - self._start_time, 2),
            "event": event,
            **kwargs
        })

    # ------------------------------------------------------------------
    # Computed metrics
    # ------------------------------------------------------------------

    def throughput(self) -> float:
        """Tasks completed per second since system start."""
        elapsed = time.time() - self._start_time
        completed = sum(1 for r in self._task_records.values() if r.success)
        return completed / elapsed if elapsed > 0 else 0.0

    def avg_waiting_time(self) -> float:
        times = [r.waiting_time for r in self._task_records.values() if r.success and r.waiting_time]
        return sum(times) / len(times) if times else 0.0

    def avg_turnaround_time(self) -> float:
        times = [r.turnaround_time for r in self._task_records.values() if r.success and r.turnaround_time]
        return sum(times) / len(times) if times else 0.0

    def avg_execution_time(self) -> float:
        times = [r.execution_time for r in self._task_records.values() if r.success and r.execution_time]
        return sum(times) / len(times) if times else 0.0

    def worker_load(self) -> Dict[str, int]:
        """Tasks completed per worker."""
        load = defaultdict(int)
        for r in self._task_records.values():
            if r.success and r.worker_id:
                load[r.worker_id] += 1
        return dict(load)

    def load_balance_fairness(self) -> float:
        """
        Variance in tasks per worker. Lower = more balanced.
        0.0 = perfectly balanced.
        """
        load = list(self.worker_load().values())
        if len(load) < 2:
            return 0.0
        mean = sum(load) / len(load)
        variance = sum((x - mean) ** 2 for x in load) / len(load)
        return round(variance, 4)

    # ------------------------------------------------------------------
    # Report output
    # ------------------------------------------------------------------

    def print_report(self):
        print("\n" + "=" * 65)
        print("       PERFORMANCE MONITORING REPORT")
        print("=" * 65)

        elapsed = time.time() - self._start_time
        total = len(self._task_records)
        completed = sum(1 for r in self._task_records.values() if r.success)
        failed = total - completed
        retries = sum(r.retries for r in self._task_records.values())

        print(f"\n  Total Wall-clock Time  : {elapsed:.2f}s")
        print(f"  Tasks Total            : {total}")
        print(f"  Tasks Completed        : {completed}")
        print(f"  Tasks Failed           : {failed}")
        print(f"  Total Retries          : {retries}")
        print(f"  Worker Failures        : {len(self._worker_failures)}")
        print()
        print(f"  Throughput             : {self.throughput():.3f} tasks/sec")
        print(f"  Avg Waiting Time       : {self.avg_waiting_time():.3f}s")
        print(f"  Avg Execution Time     : {self.avg_execution_time():.3f}s")
        print(f"  Avg Turnaround Time    : {self.avg_turnaround_time():.3f}s")
        print(f"  Load Balance Variance  : {self.load_balance_fairness():.4f}")
        print()

        print("  Worker Load Distribution:")
        for wid, count in self.worker_load().items():
            bar = "█" * count
            print(f"    {wid:<15} {bar}  ({count} tasks)")

        print()
        print("  Per-Task Summary:")
        print(f"  {'TASK':<22} {'STATUS':<10} {'WAIT':<8} {'EXEC':<8} {'RETRIES':<8}")
        print("  " + "-" * 60)
        for r in self._task_records.values():
            status = "OK" if r.success else "FAIL"
            wait = f"{r.waiting_time:.2f}s" if r.waiting_time else "-"
            exec_t = f"{r.execution_time:.2f}s" if r.execution_time else "-"
            print(f"  {r.name:<22} {status:<10} {wait:<8} {exec_t:<8} {r.retries:<8}")

        print()
        print("  Event Timeline (last 20 events):")
        for ev in self._timeline[-20:]:
            details = "  ".join(f"{k}={v}" for k, v in ev.items() if k not in ("t", "event"))
            print(f"    +{ev['t']:>6.2f}s  {ev['event']:<22} {details}")

        print("=" * 65 + "\n")

    def export_csv(self, path: str):
        import csv
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "task", "success", "worker", "wait_s", "exec_s",
                "turnaround_s", "retries"
            ])
            for r in self._task_records.values():
                writer.writerow([
                    r.name, r.success, r.worker_id,
                    round(r.waiting_time, 3),
                    round(r.execution_time, 3),
                    round(r.turnaround_time, 3),
                    r.retries
                ])
        print(f"  Metrics exported → {path}")
