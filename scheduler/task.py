"""
task.py - Task and DAG data models
Every task in the system is represented here.
"""

import uuid
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class TaskStatus(Enum):
    PENDING   = "PENDING"    # Created, not yet evaluated
    BLOCKED   = "BLOCKED"    # Waiting for parent tasks to finish
    READY     = "READY"      # All dependencies done, can be executed
    RUNNING   = "RUNNING"    # Currently assigned to a worker
    COMPLETED = "COMPLETED"  # Finished successfully
    FAILED    = "FAILED"     # Execution failed


@dataclass
class Task:
    name: str
    func: str                        # Name of function to run (string for simulation)
    args: dict = field(default_factory=dict)
    priority: int = 5                # 1=highest, 10=lowest
    dependencies: List[str] = field(default_factory=list)  # list of task names this depends on

    # Auto-assigned
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: TaskStatus = TaskStatus.PENDING
    assigned_worker: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2

    @property
    def waiting_time(self) -> float:
        if self.started_at:
            return self.started_at - self.created_at
        return time.time() - self.created_at

    @property
    def execution_time(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    @property
    def turnaround_time(self) -> Optional[float]:
        if self.completed_at:
            return self.completed_at - self.created_at
        return None

    def __repr__(self):
        return f"Task({self.name!r}, status={self.status.value}, priority={self.priority})"
