"""
dag.py - Directed Acyclic Graph Engine
This is the brain of the dependency resolver.
It knows which tasks depend on which, and decides what is READY to run.
"""

from typing import Dict, List, Set, Optional
from collections import defaultdict, deque
from scheduler.task import Task, TaskStatus


class DAGValidationError(Exception):
    pass


class DAG:
    """
    Represents the full dependency graph.
    Nodes = Tasks, Edges = "must finish before" relationships.
    """

    def __init__(self):
        self.tasks: Dict[str, Task] = {}          # name -> Task
        self._children: Dict[str, Set[str]] = defaultdict(set)   # parent -> children that depend on it
        self._parents: Dict[str, Set[str]] = defaultdict(set)    # child -> its parents

    def add_task(self, task: Task):
        if task.name in self.tasks:
            raise DAGValidationError(f"Task '{task.name}' already exists in DAG.")
        self.tasks[task.name] = task

    def build_edges(self):
        """
        Call after all tasks are added.
        Builds the parent/child relationship maps and detects cycles.
        """
        for name, task in self.tasks.items():
            for dep in task.dependencies:
                if dep not in self.tasks:
                    raise DAGValidationError(
                        f"Task '{name}' depends on '{dep}' which does not exist."
                    )
                self._parents[name].add(dep)
                self._children[dep].add(name)

        self._detect_cycles()
        self._set_initial_statuses()

    def _detect_cycles(self):
        """
        Kahn's Algorithm - topological sort to detect cycles.
        If we can't process all nodes, there is a cycle.
        """
        in_degree = {name: len(self._parents[name]) for name in self.tasks}
        queue = deque([n for n, d in in_degree.items() if d == 0])
        visited = 0

        while queue:
            node = queue.popleft()
            visited += 1
            for child in self._children[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if visited != len(self.tasks):
            raise DAGValidationError(
                "Cycle detected in task dependencies! A task cannot depend on itself or form a loop."
            )

    def _set_initial_statuses(self):
        """
        Tasks with no parents are READY immediately.
        Tasks with parents start as BLOCKED.
        """
        for name, task in self.tasks.items():
            if not self._parents[name]:
                task.status = TaskStatus.READY
            else:
                task.status = TaskStatus.BLOCKED

    def on_task_completed(self, task_name: str) -> List[str]:
        """
        Called when a task finishes.
        Checks all children: if all their parents are done, promote them to READY.
        Returns list of newly unblocked task names.
        """
        newly_ready = []
        for child_name in self._children[task_name]:
            child = self.tasks[child_name]
            if child.status != TaskStatus.BLOCKED:
                continue
            all_parents_done = all(
                self.tasks[p].status == TaskStatus.COMPLETED
                for p in self._parents[child_name]
            )
            if all_parents_done:
                child.status = TaskStatus.READY
                newly_ready.append(child_name)
        return newly_ready

    def get_ready_tasks(self) -> List[Task]:
        """Returns all tasks currently in READY state, sorted by priority."""
        ready = [t for t in self.tasks.values() if t.status == TaskStatus.READY]
        return sorted(ready, key=lambda t: t.priority)

    def is_complete(self) -> bool:
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            for t in self.tasks.values()
        )

    def has_failed_tasks(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self.tasks.values())

    def summary(self) -> Dict[str, int]:
        counts = {s.value: 0 for s in TaskStatus}
        for t in self.tasks.values():
            counts[t.status.value] += 1
        return counts

    def topological_order(self) -> List[str]:
        """Returns execution order respecting dependencies."""
        in_degree = {name: len(self._parents[name]) for name in self.tasks}
        queue = deque([n for n, d in in_degree.items() if d == 0])
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for child in sorted(self._children[node]):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        return order
