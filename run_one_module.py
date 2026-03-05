"""Run mutation testing for a single module. No multiprocessing.

Usage: python run_one_module.py <module_name> [max_mutants]
Output: /tmp/mutation_<module_name>.json
"""

import json
import subprocess
import sys
from pathlib import Path

MODULE_MAP = {
    "analyzer": {
        "source": "custom_components/autodoctor/analyzer.py",
        "tests": [
            "tests/test_analyzer.py",
            "tests/test_property_based.py",
        ],
    },
    "jinja_validator": {
        "source": "custom_components/autodoctor/jinja_validator.py",
        "tests": [
            "tests/test_jinja_validator.py",
            "tests/test_property_based_jinja.py",
        ],
    },
    "knowledge_base": {
        "source": "custom_components/autodoctor/knowledge_base.py",
        "tests": ["tests/test_knowledge_base.py"],
    },
    "service_validator": {
        "source": "custom_components/autodoctor/service_validator.py",
        "tests": ["tests/test_service_validator.py"],
    },
    "validator": {
        "source": "custom_components/autodoctor/validator.py",
        "tests": [
            "tests/test_validator.py",
            "tests/test_property_based_validator.py",
        ],
    },
}


def get_module_mutants(module):
    """Get mutant names for a specific module."""
    result = subprocess.run(
        [".venv/bin/mutmut", "results"], capture_output=True, text=True
    )
    names = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        name = line.split(":")[0].strip()
        if f".{module}." in name:
            names.append(name)
    return names


def main():
    module = sys.argv[1]
    max_mutants = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    if module not in MODULE_MAP:
        print(f"Unknown module: {module}")
        sys.exit(1)

    source = MODULE_MAP[module]["source"]
    tests = MODULE_MAP[module]["tests"]
    output_file = Path(f"/tmp/mutation_{module}.json")
    source_path = Path(source)
    original_source_text = source_path.read_text()

    print(f"[{module}] Loading mutants...", flush=True)
    mutant_names = get_module_mutants(module)
    available_total = len(mutant_names)
    if max_mutants > 0:
        mutant_names = mutant_names[:max_mutants]
    total = len(mutant_names)
    print(f"[{module}] {total} mutants to test (available={available_total})", flush=True)

    killed = 0
    survived = 0
    survived_names = []

    for i, name in enumerate(mutant_names, 1):
        # Apply the mutation to the working tree copy of the source file.
        subprocess.run(
            [".venv/bin/mutmut", "apply", name], capture_output=True, timeout=30
        )

        # Test
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
                    *tests,
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
            killed += 1

        # Restore exact original source contents without touching git state.
        source_path.write_text(original_source_text)

        # Progress every 25
        if i % 25 == 0 or i == total:
            pct = survived / i * 100
            print(
                f"[{module}] [{i}/{total}] k={killed} s={survived} ({pct:.1f}%)",
                flush=True,
            )

        # Save incremental every 50
        if i % 50 == 0 or i == total:
            output_file.write_text(
                json.dumps(
                    {
                        "module": module,
                        "total": total,
                        "processed": i,
                        "killed": killed,
                        "survived": survived,
                        "survival_pct": round(survived / i * 100, 1),
                        "survived_mutants": survived_names,
                        "complete": i == total,
                    },
                    indent=2,
                )
            )

    pct = survived / total * 100 if total else 0
    output_file.write_text(
        json.dumps(
            {
                "module": module,
                "total": total,
                "available_total": available_total,
                "processed": total,
                "killed": killed,
                "survived": survived,
                "survival_pct": round(pct, 1),
                "survived_mutants": survived_names,
                "complete": True,
            },
            indent=2,
        )
    )
    print(f"[{module}] DONE: {killed}k/{survived}s ({pct:.1f}% survival)", flush=True)


if __name__ == "__main__":
    main()
