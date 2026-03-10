from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "mutmut_subprocess_runner.py"
    spec = importlib.util.spec_from_file_location("mutmut_subprocess_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discover_mutants_reads_names_from_meta_files(tmp_path):
    runner = _load_module()
    meta_dir = tmp_path / "custom_components" / "autodoctor"
    meta_dir.mkdir(parents=True)
    (meta_dir / "validator.py.meta").write_text(
        json.dumps(
            {
                "exit_code_by_key": {
                    "custom_components.autodoctor.validator.x_a__mutmut_1": None,
                    "custom_components.autodoctor.validator.x_b__mutmut_2": 1,
                },
                "hash_by_function_name": {},
                "durations_by_key": {},
                "estimated_durations_by_key": {},
            }
        )
    )

    assert runner.discover_mutants(tmp_path) == [
        "custom_components.autodoctor.validator.x_a__mutmut_1",
        "custom_components.autodoctor.validator.x_b__mutmut_2",
    ]


def test_tests_for_mutant_reads_stats_mapping(tmp_path):
    runner = _load_module()
    stats_path = tmp_path / "mutmut-stats.json"
    stats_path.write_text(
        json.dumps(
            {
                "tests_by_mangled_function_name": {
                    "custom_components.autodoctor.validator.x_rule": [
                        "tests/test_validator.py::test_rule",
                        "tests/test_validator.py::test_other_rule",
                    ]
                },
                "duration_by_test": {},
                "stats_time": 0,
            }
        )
    )

    assert runner.tests_for_mutant(
        "custom_components.autodoctor.validator.x_rule__mutmut_4",
        stats_path,
    ) == [
        "tests/test_validator.py::test_other_rule",
        "tests/test_validator.py::test_rule",
    ]


def test_build_pytest_command_uses_selected_tests():
    runner = _load_module()

    assert runner.build_pytest_command(
        ["tests/test_validator.py::test_rule"],
        extra_args=["--maxfail=1"],
    ) == [
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
        "tests/test_validator.py::test_rule",
        "--maxfail=1",
    ]


def test_recreate_mutants_dir_removes_stale_generated_files(tmp_path):
    runner = _load_module()
    mutants_dir = tmp_path / "mutants"
    (mutants_dir / "custom_components" / "autodoctor").mkdir(parents=True)
    (mutants_dir / "custom_components" / "autodoctor" / "validator.py.meta").write_text("{}")
    (mutants_dir / "workflow").mkdir(parents=True)
    (mutants_dir / "workflow" / "mutation_results.json").write_text("[]")

    runner.recreate_mutants_dir(mutants_dir)

    assert mutants_dir.exists()
    assert not (mutants_dir / "custom_components" / "autodoctor" / "validator.py.meta").exists()


def test_copy_package_tree_preserves_support_files(tmp_path):
    runner = _load_module()
    source_root = tmp_path / "source"
    package_dir = source_root / "custom_components" / "autodoctor"
    package_dir.mkdir(parents=True)
    (package_dir / "manifest.json").write_text('{"domain": "autodoctor"}')
    mutants_dir = tmp_path / "mutants"

    runner.copy_package_tree(source_root, mutants_dir)

    assert (mutants_dir / "custom_components" / "autodoctor" / "manifest.json").read_text() == (
        '{"domain": "autodoctor"}'
    )
