"""
pipeline_loader.py
Reads input/pipeline.json and builds Task objects for the DAG.
This is the bridge between your input file and the scheduling engine.
"""

import json
import os
import logging
from scheduler.task import Task

logger = logging.getLogger("pipeline_loader")


def load_pipeline(json_path: str) -> dict:
    """
    Reads the pipeline JSON file.
    Returns a dict with pipeline metadata and a list of Task objects.
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(
            f"Pipeline file not found: {json_path}\n"
            f"Make sure 'pipeline.json' exists in the input/ folder."
        )

    with open(json_path, "r") as f:
        config = json.load(f)

    pipeline_name = config.get("pipeline_name", "Unnamed Pipeline")
    description   = config.get("description", "")
    num_workers   = config.get("workers", 3)
    task_configs  = config.get("tasks", [])

    if not task_configs:
        raise ValueError("pipeline.json has no tasks defined.")

    tasks = []
    for tc in task_configs:
        t = Task(
            name         = tc["name"],
            func         = tc["func"],
            args         = tc.get("args", {}),
            priority     = tc.get("priority", 5),
            dependencies = tc.get("dependencies", []),
        )
        tasks.append(t)

    logger.info(f"Loaded pipeline '{pipeline_name}' with {len(tasks)} tasks.")

    return {
        "pipeline_name": pipeline_name,
        "description":   description,
        "num_workers":   num_workers,
        "tasks":         tasks,
    }
