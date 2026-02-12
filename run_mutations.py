"""Parallel mutation testing runner using subprocess (macOS/Python 3.14).

mutmut 3.x's fork-based execution segfaults with HA test framework.
This runs mutmut apply + pytest + git checkout per mutant, with 4
module workers in parallel using multiprocessing with spawn method.
Results saved incrementally to /tmp/mutation_results.json.
"""

import json
import multiprocessing
import subprocess
from pathlib import Path

# Force spawn start method to avoid fork issues on Python 3.14/macOS
multiprocessing.set_start_method("spawn", force=True)

RESULTS_FILE = Path("/tmp/mutation_results.json")
REPORT_EVERY = 25

MODULE_MAP = {
    "jinja_validator": {
        "source": "custom_components/autodoctor/jinja_validator.py",
        "tests": "tests/test_jinja_validator.py",
    },
    "knowledge_base": {
        "source": "custom_components/autodoctor/knowledge_base.py",
        "tests": "tests/test_knowledge_base.py",
    },
    "service_validator": {
        "source": "custom_components/autodoctor/service_validator.py",
        "tests": "tests/test_service_validator.py",
    },
    "validator": {
        "source": "custom_components/autodoctor/validator.py",
        "tests": "tests/test_validator.py",
    },
}


def get_all_mutants():
    """Parse mutant names from mutmut results, grouped by module."""
    result = subprocess.run(
        [".venv/bin/mutmut", "results"], capture_output=True, text=True
    )
    mutants = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        name = line.split(":")[0].strip()
        for module in MODULE_MAP:
            if f".{module}." in name:
                mutants.setdefault(module, []).append(name)
                break
    return mutants


def worker(module, mutant_names, q):
    """Run mutations for a single module."""
    source = MODULE_MAP[module]["source"]
    tests = MODULE_MAP[module]["tests"]
    killed = 0
    survived = 0
    survived_names = []

    for i, name in enumerate(mutant_names, 1):
        # Apply mutation
        subprocess.run(
            [".venv/bin/mutmut", "apply", name], capture_output=True, timeout=30
        )

        # Run tests
        try:
            r = subprocess.run(
                [
                    ".venv/bin/python",
                    "-m",
                    "pytest",
                    "-x",
                    "--assert=plain",
                    "-q",
                    "--tb=no",
                    "--no-header",
                    tests,
                ],
                capture_output=True,
                timeout=60,
            )
            if r.returncode == 0:
                survived += 1
                survived_names.append(name)
            else:
                killed += 1
        except subprocess.TimeoutExpired:
            killed += 1  # timeout = test detected the mutation

        # Revert
        subprocess.run(["git", "checkout", "--", source], capture_output=True)

        # Report progress
        if i % REPORT_EVERY == 0 or i == len(mutant_names):
            total = killed + survived
            pct = (survived / total * 100) if total else 0
            q.put(("progress", module, i, len(mutant_names), killed, survived, pct))

    # Final report
    q.put(("done", module, killed, survived, survived_names))


def save_results(results):
    """Save current results to JSON file."""
    RESULTS_FILE.write_text(json.dumps(results, indent=2))


def main():
    print("=" * 60)
    print("Parallel Mutation Testing (4 workers, spawn mode)")
    print("=" * 60)
    print(flush=True)

    mutants = get_all_mutants()
    total = sum(len(v) for v in mutants.values())
    print(f"{total} mutants found")
    for module, names in sorted(mutants.items()):
        print(f"  {module}: {len(names)}")
    print(flush=True)

    if not mutants:
        print("No mutants found!")
        return

    # Launch workers
    q = multiprocessing.Queue()
    workers = {}
    results = {}

    print(f"Starting {len(mutants)} workers...", flush=True)
    print(flush=True)

    for module, names in mutants.items():
        p = multiprocessing.Process(target=worker, args=(module, names, q))
        p.start()
        workers[module] = p

    done_count = 0
    target_count = len(workers)

    while done_count < target_count:
        try:
            msg = q.get(timeout=600)
        except Exception:
            print("  Queue timeout — checking workers...", flush=True)
            alive = sum(1 for p in workers.values() if p.is_alive())
            if alive == 0:
                break
            continue

        if msg[0] == "progress":
            _, module, i, n, k, s, pct = msg
            print(f"  [{module}] [{i}/{n}] k={k} s={s} ({pct:.1f}%)", flush=True)

        elif msg[0] == "done":
            _, module, k, s, survived_names = msg
            n = k + s
            pct = (s / n * 100) if n else 0
            done_count += 1
            results[module] = {
                "total": n,
                "killed": k,
                "survived": s,
                "survival_pct": round(pct, 1),
                "survived_mutants": survived_names,
            }
            print(flush=True)
            print(f"  ** {module} DONE: {k}k/{s}s ({pct:.1f}% survival) **", flush=True)
            print(flush=True)
            # Save incrementally
            save_results(results)

    # Wait for all workers
    for p in workers.values():
        p.join(timeout=10)

    # Final summary
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    total_k = sum(r["killed"] for r in results.values())
    total_s = sum(r["survived"] for r in results.values())
    total_n = total_k + total_s
    total_pct = (total_s / total_n * 100) if total_n else 0

    for module, r in sorted(results.items()):
        print(
            f"  {module}: {r['killed']}k/{r['survived']}s ({r['survival_pct']}% survival)"
        )
    print()
    print(f"  TOTAL: {total_k}k/{total_s}s ({total_pct:.1f}% survival)")
    print(flush=True)

    save_results(results)
    print(f"\nResults saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
