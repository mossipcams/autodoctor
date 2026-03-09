from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


CORE_MUTATION_PATHS = [
    "custom_components/autodoctor/action_walker.py",
    "custom_components/autodoctor/analyzer.py",
    "custom_components/autodoctor/jinja_validator.py",
    "custom_components/autodoctor/knowledge_base.py",
    "custom_components/autodoctor/service_validator.py",
    "custom_components/autodoctor/template_utils.py",
    "custom_components/autodoctor/validator.py",
]
MUTATION_RESULTS_FILENAME = "mutation_results.json"
RESULTS_TIMEOUT_SECONDS = 180
SHOW_TIMEOUT_SECONDS = 120
RUN_TIMEOUT_SECONDS = 7200


def get_core_mutation_paths() -> list[str]:
    return CORE_MUTATION_PATHS.copy()


def get_typecheck_commands() -> list[list[str]]:
    return [
        [".venv/bin/pyright", "custom_components/"],
        [
            ".venv/bin/mypy",
            "--strict",
            "--follow-imports=skip",
            *get_core_mutation_paths(),
        ],
    ]


def run_typechecks() -> int:
    for cmd in get_typecheck_commands():
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


def parse_survivors(results_output: str) -> list[str]:
    survivors: list[str] = []
    for raw_line in results_output.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        name, status = line.split(":", 1)
        if "survived" in status.lower():
            survivors.append(name.strip())
    return survivors


def get_mutation_results_path(artifacts_dir: Path) -> Path:
    return artifacts_dir / MUTATION_RESULTS_FILENAME


def load_mutation_results(artifacts_dir: Path) -> list[dict[str, object]]:
    results_path = get_mutation_results_path(artifacts_dir)
    if not results_path.exists():
        return []
    return json.loads(results_path.read_text())


def get_survivor_mutants(artifacts_dir: Path) -> list[str]:
    return [
        str(result["mutant_name"])
        for result in load_mutation_results(artifacts_dir)
        if result.get("status") == "survived"
    ]


def get_mutant_diff(mutant_name: str) -> str:
    result = subprocess.run(
        [".venv/bin/mutmut", "show", mutant_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=SHOW_TIMEOUT_SECONDS,
    )
    return result.stdout


def collect_survivor_diffs(mutant_names: list[str]) -> dict[str, str]:
    return {name: get_mutant_diff(name) for name in mutant_names}


def build_survivor_prompt(survivor_diffs: dict[str, str]) -> str:
    lines = [
        "Write tests to kill these mutants.",
        "Focus on behavioral assertions; do not weaken existing tests.",
        "",
    ]
    for mutant_name in sorted(survivor_diffs):
        lines.append(f"Mutant: {mutant_name}")
        lines.append("```diff")
        lines.append(survivor_diffs[mutant_name].rstrip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_survivor_prompt(artifacts_dir: Path) -> int:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    survivors = get_survivor_mutants(artifacts_dir)
    diffs = collect_survivor_diffs(survivors)
    prompt = build_survivor_prompt(diffs)
    (artifacts_dir / "survivor_prompt.md").write_text(prompt)
    (artifacts_dir / "survivors.json").write_text(json.dumps(sorted(survivors), indent=2))
    return 0


def rerun_survivors(artifacts_dir: Path) -> int:
    survivors_file = artifacts_dir / "survivors.json"
    if survivors_file.exists():
        survivors = json.loads(survivors_file.read_text())
    else:
        survivors = get_survivor_mutants(artifacts_dir)

    if not survivors:
        return 0

    cmd = get_mutation_runner_command(artifacts_dir, survivors)
    result = subprocess.run(cmd, check=False, timeout=RUN_TIMEOUT_SECONDS)
    return result.returncode


def should_stop(history: list[float], critical_path_score: float) -> tuple[bool, str]:
    if critical_path_score >= 70.0:
        return True, "threshold"
    if len(history) >= 3:
        recent = history[-3:]
        if max(recent) - min(recent) <= 0.25:
            return True, "plateau"
    return False, ""


def run_baseline(artifacts_dir: Path) -> int:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        ".venv/bin/python",
        "-m",
        "pytest",
        "--cov=custom_components/autodoctor",
        "--cov-branch",
        "--cov-report=term-missing:skip-covered",
        "tests/",
    ]
    result = subprocess.run(cmd, check=False)
    (artifacts_dir / "baseline_coverage.txt").write_text("baseline complete\n")
    return result.returncode


def get_mutation_runner_command(artifacts_dir: Path, mutant_names: list[str] | None = None) -> list[str]:
    mutant_names = mutant_names or []
    return [
        ".venv/bin/python",
        "scripts/mutmut_subprocess_runner.py",
        "--results-file",
        str(get_mutation_results_path(artifacts_dir)),
        *mutant_names,
    ]


def run_mutation_suite(artifacts_dir: Path, mutant_names: list[str] | None = None) -> int:
    rc = run_typechecks()
    if rc != 0:
        return rc
    return subprocess.run(
        get_mutation_runner_command(artifacts_dir, mutant_names),
        check=False,
        timeout=RUN_TIMEOUT_SECONDS,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Mutation testing workflow runner")
    parser.add_argument(
        "command",
        choices=["baseline", "run", "show-survivors", "rerun-survivors"],
    )
    parser.add_argument(
        "--artifacts-dir",
        default="mutants/workflow",
        help="Directory to store workflow artifacts",
    )
    parser.add_argument("mutant_names", nargs="*")
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)

    if args.command == "baseline":
        return run_baseline(artifacts_dir)
    if args.command == "run":
        return run_mutation_suite(artifacts_dir, args.mutant_names)
    if args.command == "show-survivors":
        return export_survivor_prompt(artifacts_dir)
    if args.command == "rerun-survivors":
        return rerun_survivors(artifacts_dir)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
