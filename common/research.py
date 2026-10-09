"""Runs a Nimble Web Search Agent from a notebook and returns its rows with their sources."""
import json
import os


def run_agent(nimble, spec_file, task, input_data=None, effort=None, run_id=None):
    """Create the agent from spec_file (or reuse it), start a run, wait for it and return (agent_id, run_id, rows, confidence).
    Pass run_id to read a run that already finished instead of starting a new one."""
    spec = json.load(open(spec_file))
    agent_id = nimble.wsa_create(spec)
    print(f"Agent '{spec['display_name']}': {agent_id}")
    if not run_id:
        run_id = nimble.wsa_start(agent_id, task, input_data=input_data, effort=effort or spec.get("effort"))
        print(f"Run {run_id} started. Effort {effort or spec.get('effort')}. Status every 30 s:")
    status = nimble.wsa_wait(agent_id, run_id)
    if status != "completed":
        raise RuntimeError(f"Run {run_id} ended with status {status}. Run this cell again with RUN_ID = '{run_id}' to read it later.")
    rows, confidence = nimble.wsa_result(agent_id, run_id)
    print(f"{len(rows)} rows, run confidence {confidence}")
    return agent_id, run_id, rows, confidence


def run_agent_parallel(nimble, spec_file, tasks, effort=None, every=30, max_minutes=45):
    """Start one run per task at the same time, wait for all of them and return (agent_id, rows).
    Each row gets _run_id and _run_confidence. Smaller tasks come back more complete than one large task."""
    import time
    spec = json.load(open(spec_file))
    agent_id = nimble.wsa_create(spec)
    print(f"Agent '{spec['display_name']}': {agent_id}")
    runs = {}
    for label, task in tasks.items():
        runs[label] = nimble.wsa_start(agent_id, task, effort=effort or spec.get("effort"))
        print(f"  started {label}: {runs[label]}")
    pending, status, retried, t0 = set(runs), {}, set(), time.time()
    while pending and time.time() - t0 < max_minutes * 60:
        time.sleep(every)
        for label in list(pending):
            s = nimble.wsa_status(agent_id, runs[label])
            if s == "failed" and label not in retried:  # one retry for a failed run
                retried.add(label)
                runs[label] = nimble.wsa_start(agent_id, tasks[label], effort=effort or spec.get("effort"))
                print(f"  {int(time.time() - t0):>5}s  {label}: failed, retrying as {runs[label]}")
                continue
            if s in ("completed", "failed", "cancelled"):
                status[label] = s
                pending.discard(label)
                print(f"  {int(time.time() - t0):>5}s  {label}: {s}")
    rows = []
    for label, run_id in runs.items():
        if status.get(label) != "completed":
            print(f"  {label} did not complete ({status.get(label, 'still running')}). Run id {run_id}")
            continue
        got, confidence = nimble.wsa_result(agent_id, run_id)
        for r in got:
            r["_run_id"], r["_run_confidence"] = run_id, confidence
        rows += got
        print(f"  {label}: {len(got)} rows, confidence {confidence}")
    return agent_id, rows
