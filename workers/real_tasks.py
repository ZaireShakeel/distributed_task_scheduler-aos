"""
real_tasks.py
Real task functions that read, process, and write actual data.
Each function receives 'args' dict and a shared 'data_store' dict.
Results are stored in data_store so downstream tasks can use them.

DAG flow:
    load_processes
         │
         ├──► filter_high_priority  ──┐
         ├──► compute_burst_stats   ──┼──► generate_report
         └──► compute_wait_stats       │
                    │                  │
                    └──► detect_starvation ──┘
"""

import os
import time
import statistics

# ------------------------------------------------------------------
# Shared in-memory data store
# Tasks write results here; downstream tasks read from here.
# ------------------------------------------------------------------
DATA_STORE = {}


def _parse_processes(file_path: str) -> list:
    """Parse processes.txt into a list of dicts."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(base, file_path)

    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Input file not found: {full_path}")

    processes = []
    with open(full_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 6:
                continue
            processes.append({
                "process_id":   parts[0],
                "process_name": parts[1],
                "arrival_time": int(parts[2]),
                "burst_time":   int(parts[3]),
                "priority":     int(parts[4]),
                "state":        parts[5],
            })
    return processes


# ------------------------------------------------------------------
# Task 1: read_process_log
# Loads processes.txt into DATA_STORE
# ------------------------------------------------------------------
def read_process_log(args: dict) -> str:
    file_path = args.get("file", "input/processes.txt")
    time.sleep(0.3)  # simulate I/O
    processes = _parse_processes(file_path)
    DATA_STORE["processes"] = processes
    return f"Loaded {len(processes)} processes from '{file_path}'"


# ------------------------------------------------------------------
# Task 2: filter_by_priority  (INDEPENDENT of compute_* tasks)
# Filters processes with priority >= min_priority
# ------------------------------------------------------------------
def filter_by_priority(args: dict) -> str:
    time.sleep(0.2)
    processes = DATA_STORE.get("processes", [])
    if not processes:
        raise RuntimeError("No process data loaded. load_processes must run first.")

    min_p = args.get("min_priority", 5)
    high  = [p for p in processes if p["priority"] >= min_p]
    DATA_STORE["high_priority_processes"] = high

    names = ", ".join(p["process_name"] for p in high)
    return (
        f"Found {len(high)}/{len(processes)} high-priority processes "
        f"(priority >= {min_p}): {names}"
    )


# ------------------------------------------------------------------
# Task 3: compute_burst_statistics  (INDEPENDENT of filter_* task)
# Computes stats on burst times
# ------------------------------------------------------------------
def compute_burst_statistics(args: dict) -> str:
    time.sleep(0.3)
    processes = DATA_STORE.get("processes", [])
    if not processes:
        raise RuntimeError("No process data available.")

    bursts = [p["burst_time"] for p in processes]
    stats = {
        "count":  len(bursts),
        "mean":   round(statistics.mean(bursts), 2),
        "median": round(statistics.median(bursts), 2),
        "stdev":  round(statistics.stdev(bursts), 2),
        "min":    min(bursts),
        "max":    max(bursts),
        "total":  sum(bursts),
    }
    DATA_STORE["burst_stats"] = stats
    return (
        f"Burst time stats — Mean: {stats['mean']}ms  "
        f"Median: {stats['median']}ms  StdDev: {stats['stdev']}ms  "
        f"Min: {stats['min']}ms  Max: {stats['max']}ms  "
        f"Total CPU: {stats['total']}ms"
    )


# ------------------------------------------------------------------
# Task 4: compute_wait_statistics  (INDEPENDENT of filter_* task)
# Simulates FCFS waiting time for each process
# ------------------------------------------------------------------
def compute_wait_statistics(args: dict) -> str:
    time.sleep(0.3)
    processes = DATA_STORE.get("processes", [])
    if not processes:
        raise RuntimeError("No process data available.")

    # FCFS: sort by arrival_time, accumulate wait
    sorted_procs = sorted(processes, key=lambda p: p["arrival_time"])
    current_time = 0
    wait_times = []

    for p in sorted_procs:
        start = max(current_time, p["arrival_time"])
        wait  = start - p["arrival_time"]
        wait_times.append({"process_id": p["process_id"],
                            "process_name": p["process_name"],
                            "wait_time": wait,
                            "priority": p["priority"]})
        current_time = start + p["burst_time"]

    DATA_STORE["wait_times"] = wait_times

    avg_wait = round(statistics.mean(w["wait_time"] for w in wait_times), 2)
    max_wait = max(w["wait_time"] for w in wait_times)
    return (
        f"FCFS wait time analysis — "
        f"Avg wait: {avg_wait}ms  Max wait: {max_wait}ms  "
        f"Processes analysed: {len(wait_times)}"
    )


# ------------------------------------------------------------------
# Task 5: detect_starvation  (DEPENDS on compute_wait_stats)
# Flags processes waiting longer than threshold
# ------------------------------------------------------------------
def detect_starvation(args: dict) -> str:
    time.sleep(0.2)
    wait_times = DATA_STORE.get("wait_times", [])
    if not wait_times:
        raise RuntimeError("Wait time data not available.")

    threshold = args.get("wait_threshold", 20)
    starved   = [w for w in wait_times if w["wait_time"] > threshold]
    DATA_STORE["starved_processes"] = starved

    if starved:
        names = ", ".join(
            f"{w['process_name']}({w['wait_time']}ms)" for w in starved
        )
        return (
            f"STARVATION DETECTED — {len(starved)} process(es) waited > {threshold}ms: "
            f"{names}"
        )
    return f"No starvation detected. All processes waited <= {threshold}ms."


# ------------------------------------------------------------------
# Task 6: write_report  (DEPENDS on filter, burst_stats, starvation)
# Writes the final .txt output report
# ------------------------------------------------------------------
def write_report(args: dict) -> str:
    time.sleep(0.2)
    output_path = args.get("output", "output/scheduling_report.txt")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(base, output_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    processes        = DATA_STORE.get("processes", [])
    high_priority    = DATA_STORE.get("high_priority_processes", [])
    burst_stats      = DATA_STORE.get("burst_stats", {})
    wait_times       = DATA_STORE.get("wait_times", [])
    starved          = DATA_STORE.get("starved_processes", [])

    sep  = "=" * 62
    sep2 = "-" * 62

    lines = [
        sep,
        "   OS PROCESS SCHEDULING ANALYSIS — OUTPUT REPORT",
        "   CS-511 Advanced Operating Systems | ITU Lahore",
        sep,
        "",
        f"  Pipeline     : OS Process Scheduling Analysis",
        f"  Input File   : input/processes.txt",
        f"  Total Procs  : {len(processes)}",
        f"  Run by       : DAG Distributed Task Scheduler",
        "",
        sep2,
        "  SECTION 1 — HIGH PRIORITY PROCESSES (priority >= 5)",
        sep2,
        f"  Count : {len(high_priority)} out of {len(processes)}",
        "",
    ]

    for p in sorted(high_priority, key=lambda x: -x["priority"]):
        lines.append(
            f"  [{p['process_id']}]  {p['process_name']:<18} "
            f"Priority={p['priority']}  Burst={p['burst_time']}ms"
        )

    lines += [
        "",
        sep2,
        "  SECTION 2 — CPU BURST TIME STATISTICS",
        sep2,
        f"  Total Processes   : {burst_stats.get('count', 'N/A')}",
        f"  Mean Burst Time   : {burst_stats.get('mean', 'N/A')} ms",
        f"  Median Burst Time : {burst_stats.get('median', 'N/A')} ms",
        f"  Std Deviation     : {burst_stats.get('stdev', 'N/A')} ms",
        f"  Min Burst Time    : {burst_stats.get('min', 'N/A')} ms",
        f"  Max Burst Time    : {burst_stats.get('max', 'N/A')} ms",
        f"  Total CPU Time    : {burst_stats.get('total', 'N/A')} ms",
        "",
        sep2,
        "  SECTION 3 — FCFS WAIT TIME ANALYSIS (per process)",
        sep2,
    ]

    lines.append(f"  {'PID':<5} {'Name':<18} {'Wait(ms)':<12} {'Priority'}")
    lines.append("  " + "-" * 44)
    for w in wait_times:
        flag = "  *** STARVED" if w["wait_time"] > 20 else ""
        lines.append(
            f"  {w['process_id']:<5} {w['process_name']:<18} "
            f"{w['wait_time']:<12} {w['priority']}{flag}"
        )

    starvation_status = (
        f"DETECTED — {len(starved)} process(es) starved"
        if starved else "NONE DETECTED"
    )
    lines += [
        "",
        sep2,
        "  SECTION 4 — STARVATION ANALYSIS",
        sep2,
        f"  Threshold     : 20 ms wait time",
        f"  Status        : {starvation_status}",
        "",
    ]

    if starved:
        lines.append("  Starved processes:")
        for s in starved:
            lines.append(
                f"    - {s['process_name']} (PID {s['process_id']}) "
                f"waited {s['wait_time']}ms at priority {s['priority']}"
            )
    lines += [
        "",
        sep2,
        "  SECTION 5 — SCHEDULING RECOMMENDATION",
        sep2,
    ]

    if starved:
        lines.append(
            "  Low-priority processes are experiencing starvation under FCFS."
        )
        lines.append(
            "  RECOMMENDATION: Switch to Priority Scheduling with Aging."
        )
        lines.append(
            "  Aging gradually increases priority of waiting processes,"
        )
        lines.append(
            "  preventing indefinite starvation of low-priority processes."
        )
    else:
        lines.append(
            "  No starvation detected under FCFS scheduling."
        )
        lines.append(
            "  Current workload is manageable with FCFS."
        )
        lines.append(
            "  RECOMMENDATION: Monitor as workload grows."
        )

    lines += [
        "",
        sep,
        "  END OF REPORT",
        sep,
    ]

    with open(full_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    DATA_STORE["report_path"] = full_path
    return f"Report written to '{output_path}' ({len(lines)} lines)"


# ------------------------------------------------------------------
# Registry — maps function name strings to actual functions
# ------------------------------------------------------------------
REAL_TASK_REGISTRY = {
    "read_process_log":        read_process_log,
    "filter_by_priority":      filter_by_priority,
    "compute_burst_statistics": compute_burst_statistics,
    "compute_wait_statistics":  compute_wait_statistics,
    "detect_starvation":        detect_starvation,
    "write_report":             write_report,
}
