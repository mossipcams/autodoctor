from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


PYTEST_TIMEOUT_SECONDS = 60


def discover_mutants(mutants_root: Path) -> list[str]:
    mutant_names: list[str] = []
    for meta_path in sorted(mutants_root.rglob("*.meta")):
        data = json.loads(meta_path.read_text())
        mutant_names.extend(sorted(data.get("exit_code_by_key", {})))
    return mutant_names


def mutant_name_to_mangled_name(mutant_name: str) -> str:
    return mutant_name.partition("__mutmut_")[0]


def tests_for_mutant(mutant_name: str, stats_path: Path) -> list[str]:
    data = json.loads(stats_path.read_text())
    tests_by_name = data["tests_by_mangled_function_name"]
    return sorted(tests_by_name.get(mutant_name_to_mangled_name(mutant_name), []))


def build_pytest_command(test_names: list[str], extra_args: list[str] | None = None) -> list[str]:
    return [
        ".venv/bin/python",
        "-m",
        "pytest",
        "--rootdir=.",
        "--tb=native",
        "-x",
        "-q",
        "-p",
        "no:randomly",
        "-p",
        "no:random-order",
        *test_names,
        *(extra_args or []),
    ]


def _load_mutmut_main():
    import mutmut.__main__ as mutmut_main

    return mutmut_main


def recreate_mutants_dir(mutants_dir: Path) -> None:
    if mutants_dir.exists():
        shutil.rmtree(mutants_dir)
    mutants_dir.mkdir(parents=True, exist_ok=True)


def copy_package_tree(source_root: Path, mutants_dir: Path) -> None:
    shutil.copytree(
        source_root / "custom_components",
        mutants_dir / "custom_components",
        dirs_exist_ok=True,
    )


def _prepare_mutation_data() -> None:
    mutmut_main = _load_mutmut_main()
    os.environ["MUTANT_UNDER_TEST"] = "mutant_generation"
    mutmut_main.ensure_config_loaded()
    mutants_dir = Path("mutants")
    recreate_mutants_dir(mutants_dir)
    copy_package_tree(Path("."), mutants_dir)
    mutmut_main.copy_src_dir()
    mutmut_main.copy_also_copy_files()
    mutmut_main.setup_source_paths()
    mutmut_main.store_lines_covered_by_tests()
    for path in mutmut_main.walk_source_files():
        result = mutmut_main.create_file_mutants(path)
        if result.error is not None:
            raise result.error

    runner = mutmut_main.PytestRunner()
    runner.prepare_main_test_run()
    mutmut_main.collect_or_load_stats(runner)
    os.environ["MUTANT_UNDER_TEST"] = ""


def _mutation_extra_pytest_args() -> list[str]:
    mutmut_main = _load_mutmut_main()
    mutmut_main.ensure_config_loaded()
    return list(mutmut_main.mutmut.config.pytest_add_cli_args)


def _source_path_for_mutant(mutant_name: str) -> Path:
    mutmut_main = _load_mutmut_main()
    return Path(mutmut_main.find_mutant(mutant_name).path)


def _apply_mutant(mutant_name: str) -> None:
    mutmut_main = _load_mutmut_main()
    mutmut_main.apply_mutant(mutant_name)


def run_mutant(mutant_name: str, stats_path: Path) -> dict[str, object]:
    source_path = _source_path_for_mutant(mutant_name)
    original_source = source_path.read_text()
    selected_tests = tests_for_mutant(mutant_name, stats_path)
    start = time.perf_counter()

    try:
        _apply_mutant(mutant_name)
        if not selected_tests:
            return {
                "mutant_name": mutant_name,
                "status": "no_tests",
                "source_path": str(source_path),
                "tests": [],
                "duration_seconds": round(time.perf_counter() - start, 3),
            }

        result = subprocess.run(
            build_pytest_command(selected_tests, extra_args=_mutation_extra_pytest_args()),
            check=False,
            timeout=PYTEST_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
        return {
            "mutant_name": mutant_name,
            "status": "survived" if result.returncode == 0 else "killed",
            "returncode": result.returncode,
            "source_path": str(source_path),
            "tests": selected_tests,
            "duration_seconds": round(time.perf_counter() - start, 3),
        }
    except subprocess.TimeoutExpired:
        return {
            "mutant_name": mutant_name,
            "status": "timeout",
            "source_path": str(source_path),
            "tests": selected_tests,
            "duration_seconds": round(time.perf_counter() - start, 3),
        }
    finally:
        source_path.write_text(original_source)


def write_results(results_file: Path, results: list[dict[str, object]]) -> None:
    results_file.parent.mkdir(parents=True, exist_ok=True)
    results_file.write_text(json.dumps(results, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run mutmut mutants in fresh pytest subprocesses")
    parser.add_argument("--results-file", required=True)
    parser.add_argument("mutant_names", nargs="*")
    args = parser.parse_args()

    _prepare_mutation_data()
    stats_path = Path("mutants/mutmut-stats.json")
    mutant_names = list(args.mutant_names) or discover_mutants(Path("mutants"))
    results: list[dict[str, object]] = []
    results_file = Path(args.results_file)

    for mutant_name in mutant_names:
        result = run_mutant(mutant_name, stats_path)
        results.append(result)
        write_results(results_file, results)
        print(f"{result['status']}: {mutant_name}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
