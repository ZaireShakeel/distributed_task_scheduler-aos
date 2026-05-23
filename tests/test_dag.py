"""
tests/test_dag.py
Unit tests for the DAG engine and task model.
Run with: pytest tests/ -v
"""

import sys
import os
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scheduler.task import Task, TaskStatus
from scheduler.dag import DAG, DAGValidationError


# -----------------------------------------------------------------------
# Task model tests
# -----------------------------------------------------------------------

class TestTask:
    def test_task_defaults(self):
        t = Task(name="t1", func="data_fetch")
        assert t.status == TaskStatus.PENDING
        assert t.retry_count == 0
        assert t.dependencies == []
        assert t.task_id is not None

    def test_unique_ids(self):
        t1 = Task(name="a", func="f")
        t2 = Task(name="b", func="f")
        assert t1.task_id != t2.task_id

    def test_waiting_time(self):
        t = Task(name="t", func="f")
        time.sleep(0.05)
        assert t.waiting_time >= 0.04

    def test_execution_time_none_before_completion(self):
        t = Task(name="t", func="f")
        assert t.execution_time is None

    def test_execution_time_after_completion(self):
        t = Task(name="t", func="f")
        t.started_at = time.time() - 2.0
        t.completed_at = time.time()
        assert t.execution_time >= 1.9

    def test_turnaround_time(self):
        t = Task(name="t", func="f")
        t.completed_at = time.time()
        assert t.turnaround_time is not None
        assert t.turnaround_time >= 0


# -----------------------------------------------------------------------
# DAG construction tests
# -----------------------------------------------------------------------

class TestDAGConstruction:
    def _simple_dag(self):
        dag = DAG()
        dag.add_task(Task(name="A", func="f"))
        dag.add_task(Task(name="B", func="f", dependencies=["A"]))
        dag.add_task(Task(name="C", func="f", dependencies=["B"]))
        dag.build_edges()
        return dag

    def test_ready_tasks_at_start(self):
        dag = self._simple_dag()
        ready = dag.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].name == "A"

    def test_blocked_tasks_at_start(self):
        dag = self._simple_dag()
        assert dag.tasks["B"].status == TaskStatus.BLOCKED
        assert dag.tasks["C"].status == TaskStatus.BLOCKED

    def test_duplicate_task_raises(self):
        dag = DAG()
        dag.add_task(Task(name="A", func="f"))
        with pytest.raises(DAGValidationError):
            dag.add_task(Task(name="A", func="f"))

    def test_missing_dependency_raises(self):
        dag = DAG()
        dag.add_task(Task(name="B", func="f", dependencies=["A"]))
        with pytest.raises(DAGValidationError, match="does not exist"):
            dag.build_edges()

    def test_cycle_detection(self):
        dag = DAG()
        dag.add_task(Task(name="A", func="f", dependencies=["C"]))
        dag.add_task(Task(name="B", func="f", dependencies=["A"]))
        dag.add_task(Task(name="C", func="f", dependencies=["B"]))
        with pytest.raises(DAGValidationError, match="Cycle"):
            dag.build_edges()

    def test_self_cycle_detection(self):
        dag = DAG()
        dag.add_task(Task(name="A", func="f", dependencies=["A"]))
        with pytest.raises(DAGValidationError):
            dag.build_edges()


# -----------------------------------------------------------------------
# DAG state transition tests
# -----------------------------------------------------------------------

class TestDAGStateTransitions:
    def _two_parallel_dag(self):
        """
        A ──┐
            ├──► C
        B ──┘
        """
        dag = DAG()
        dag.add_task(Task(name="A", func="f"))
        dag.add_task(Task(name="B", func="f"))
        dag.add_task(Task(name="C", func="f", dependencies=["A", "B"]))
        dag.build_edges()
        return dag

    def test_parallel_roots_are_both_ready(self):
        dag = self._two_parallel_dag()
        ready_names = {t.name for t in dag.get_ready_tasks()}
        assert ready_names == {"A", "B"}

    def test_one_parent_done_does_not_unblock_child(self):
        dag = self._two_parallel_dag()
        dag.tasks["A"].status = TaskStatus.COMPLETED
        newly_ready = dag.on_task_completed("A")
        assert "C" not in newly_ready   # B still not done
        assert dag.tasks["C"].status == TaskStatus.BLOCKED

    def test_both_parents_done_unblocks_child(self):
        dag = self._two_parallel_dag()
        dag.tasks["A"].status = TaskStatus.COMPLETED
        dag.on_task_completed("A")
        dag.tasks["B"].status = TaskStatus.COMPLETED
        newly_ready = dag.on_task_completed("B")
        assert "C" in newly_ready
        assert dag.tasks["C"].status == TaskStatus.READY

    def test_is_complete_false_when_running(self):
        dag = self._two_parallel_dag()
        assert not dag.is_complete()

    def test_is_complete_true_when_all_done(self):
        dag = self._two_parallel_dag()
        for t in dag.tasks.values():
            t.status = TaskStatus.COMPLETED
        assert dag.is_complete()

    def test_topological_order_respects_deps(self):
        dag = DAG()
        dag.add_task(Task(name="A", func="f"))
        dag.add_task(Task(name="B", func="f", dependencies=["A"]))
        dag.add_task(Task(name="C", func="f", dependencies=["B"]))
        dag.build_edges()
        order = dag.topological_order()
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_summary_counts(self):
        dag = self._two_parallel_dag()
        summary = dag.summary()
        assert summary["READY"] == 2
        assert summary["BLOCKED"] == 1

    def test_priority_ordering(self):
        dag = DAG()
        dag.add_task(Task(name="low",  func="f", priority=9))
        dag.add_task(Task(name="high", func="f", priority=1))
        dag.add_task(Task(name="mid",  func="f", priority=5))
        dag.build_edges()
        ready = dag.get_ready_tasks()
        names = [t.name for t in ready]
        assert names == ["high", "mid", "low"]


# -----------------------------------------------------------------------
# Metrics tests
# -----------------------------------------------------------------------

class TestMetrics:
    def test_throughput_zero_at_start(self):
        from monitoring.metrics import MetricsCollector
        m = MetricsCollector()
        assert m.throughput() == 0.0

    def test_load_balance_single_worker(self):
        from monitoring.metrics import MetricsCollector
        m = MetricsCollector()
        m.record_task_dispatched("t1", "w1")
        t = Task(name="t1", func="f")
        t.started_at = time.time() - 1
        t.completed_at = time.time()
        m.record_task_completed(t)
        assert m.load_balance_fairness() == 0.0   # only 1 worker

    def test_retry_counting(self):
        from monitoring.metrics import MetricsCollector
        m = MetricsCollector()
        m.record_task_retry("t1")
        m.record_task_retry("t1")
        assert m._task_records["t1"].retries == 2


# -----------------------------------------------------------------------
# Integration smoke test
# -----------------------------------------------------------------------

class TestIntegration:
    def test_full_linear_pipeline(self):
        """
        Full pipeline: A → B → C
        Runs actual worker execution via Worker.execute()
        """
        from workers.worker import Worker
        from monitoring.metrics import MetricsCollector
        from database.state_db import StateDB
        from scheduler.master import Master
        import tempfile

        # Use a temp DB
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        dag = DAG()
        dag.add_task(Task(name="step1", func="data_fetch",  priority=1, args={"duration": 0.1}))
        dag.add_task(Task(name="step2", func="data_clean",  priority=2,
                          dependencies=["step1"], args={"duration": 0.1}))
        dag.add_task(Task(name="step3", func="notify",      priority=3,
                          dependencies=["step2"]))
        dag.build_edges()

        metrics = MetricsCollector()
        db = StateDB(db_path=db_path)
        db.clear()
        for t in dag.tasks.values():
            db.insert_task(t)

        master = Master(dag=dag, metrics=metrics, db=db)
        worker = Worker(worker_id="test-worker", master=master)
        worker.start()
        master.register_worker(worker)
        master.start()
        master.wait_until_done(timeout=30)
        worker.stop()

        assert dag.tasks["step1"].status == TaskStatus.COMPLETED
        assert dag.tasks["step2"].status == TaskStatus.COMPLETED
        assert dag.tasks["step3"].status == TaskStatus.COMPLETED
        assert not dag.has_failed_tasks()

        os.unlink(db_path)
