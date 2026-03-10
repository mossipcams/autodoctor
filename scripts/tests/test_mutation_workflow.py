from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "mutation_workflow.py"
    spec = importlib.util.spec_from_file_location("mutation_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_command_writes_coverage_artifacts(tmp_path, monkeypatch):
    mw = _load_module()
    calls: list[list[str]] = []

    class FakeResult:
        returncode = 0

    def fake_run(cmd, check=False):
        calls.append(cmd)
        cov = tmp_path / ".coverage"
        cov.write_text("ok")
        return FakeResult()

    monkeypatch.setattr(mw.subprocess, "run", fake_run)

    rc = mw.run_baseline(tmp_path)

    assert rc == 0
    assert calls == [
        [
            ".venv/bin/python",
            "-m",
            "pytest",
            "--cov=custom_components/autodoctor",
            "--cov-branch",
            "--cov-report=term-missing:skip-covered",
            "tests/",
        ]
    ]
    assert (tmp_path / "baseline_coverage.txt").exists()


def test_typecheck_commands_include_mypy_and_keep_pyright():
    mw = _load_module()
    commands = mw.get_typecheck_commands()

    assert [
        ".venv/bin/mypy",
        "--strict",
        "--follow-imports=skip",
        "custom_components/autodoctor/action_walker.py",
        "custom_components/autodoctor/analyzer.py",
        "custom_components/autodoctor/jinja_validator.py",
        "custom_components/autodoctor/knowledge_base.py",
        "custom_components/autodoctor/service_validator.py",
        "custom_components/autodoctor/template_utils.py",
        "custom_components/autodoctor/validator.py",
    ] in commands
    assert [".venv/bin/pyright", "custom_components/"] in commands


def test_pyproject_has_strict_mypy_config():
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text()

    assert "[tool.mypy]" in content
    assert "strict = true" in content


def test_setup_cfg_enables_only_covered_line_mutation():
    setup_cfg = Path(__file__).resolve().parents[2] / "setup.cfg"
    content = setup_cfg.read_text()

    assert "[mutmut]" in content
    assert "mutate_only_covered_lines = true" in content


def test_core_mutation_scope_excludes_ha_glue():
    mw = _load_module()
    paths = mw.get_core_mutation_paths()

    assert "custom_components/autodoctor/analyzer.py" in paths
    assert "custom_components/autodoctor/validator.py" in paths
    assert "custom_components/autodoctor/service_validator.py" in paths

    excluded = {
        "custom_components/autodoctor/config_flow.py",
        "custom_components/autodoctor/__init__.py",
        "custom_components/autodoctor/websocket_api.py",
        "custom_components/autodoctor/sensor.py",
        "custom_components/autodoctor/binary_sensor.py",
    }
    assert excluded.isdisjoint(set(paths))


def test_build_survivor_prompt_is_paste_ready():
    mw = _load_module()
    prompt = mw.build_survivor_prompt(
        {
            "custom_components.autodoctor.validator.x_mutation_1": "- old\n+ new\n",
            "custom_components.autodoctor.analyzer.x_mutation_2": "- if x\n+ if not x\n",
        }
    )

    assert "write tests to kill these mutants" in prompt.lower()
    assert "custom_components.autodoctor.validator.x_mutation_1" in prompt
    assert "custom_components.autodoctor.analyzer.x_mutation_2" in prompt
    assert "```diff" in prompt


def test_should_stop_requires_tight_plateau_window():
    mw = _load_module()
    stop, reason = mw.should_stop([60.0, 60.4, 60.45], critical_path_score=65.0)

    assert stop is False
    assert reason == ""


def test_rerun_survivors_skips_when_no_survivors(tmp_path, monkeypatch):
    mw = _load_module()
    calls: list[list[str]] = []

    class FakeResult:
        returncode = 0

    def fake_run(cmd, check=False, **kwargs):
        calls.append(cmd)
        return FakeResult()

    monkeypatch.setattr(mw.subprocess, "run", fake_run)
    (tmp_path / "survivors.json").write_text("[]")

    rc = mw.rerun_survivors(tmp_path)

    assert rc == 0
    assert calls == []


def test_pyproject_mypy_targets_python_313():
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text()

    assert 'python_version = "3.13"' in content


def test_run_typechecks_fails_when_mypy_fails(monkeypatch):
    mw = _load_module()

    class FakeResult:
        def __init__(self, returncode):
            self.returncode = returncode

    outcomes = {
        tuple([".venv/bin/pyright", "custom_components/"]): FakeResult(0),
        tuple(
            [
                ".venv/bin/mypy",
                "--strict",
                "--follow-imports=skip",
                "custom_components/autodoctor/action_walker.py",
                "custom_components/autodoctor/analyzer.py",
                "custom_components/autodoctor/jinja_validator.py",
                "custom_components/autodoctor/knowledge_base.py",
                "custom_components/autodoctor/service_validator.py",
                "custom_components/autodoctor/template_utils.py",
                "custom_components/autodoctor/validator.py",
            ]
        ): FakeResult(1),
    }

    def fake_run(cmd, check=False):
        return outcomes[tuple(cmd)]

    monkeypatch.setattr(mw.subprocess, "run", fake_run)

    assert mw.run_typechecks() == 1


def test_mutation_runner_command_uses_fresh_python_process(tmp_path):
    mw = _load_module()

    assert mw.get_mutation_runner_command(tmp_path) == [
        ".venv/bin/python",
        "scripts/mutmut_subprocess_runner.py",
        "--results-file",
        str(tmp_path / "mutation_results.json"),
    ]


def test_run_command_keeps_typechecks_and_uses_fresh_process_runner(tmp_path, monkeypatch):
    mw = _load_module()
    calls: list[tuple[list[str], int | None]] = []

    class FakeResult:
        def __init__(self, returncode: int):
            self.returncode = returncode

    outcomes = {
        tuple([".venv/bin/pyright", "custom_components/"]): FakeResult(0),
        tuple(
            [
                ".venv/bin/mypy",
                "--strict",
                "--follow-imports=skip",
                "custom_components/autodoctor/action_walker.py",
                "custom_components/autodoctor/analyzer.py",
                "custom_components/autodoctor/jinja_validator.py",
                "custom_components/autodoctor/knowledge_base.py",
                "custom_components/autodoctor/service_validator.py",
                "custom_components/autodoctor/template_utils.py",
                "custom_components/autodoctor/validator.py",
            ]
        ): FakeResult(0),
        tuple(
            [
                ".venv/bin/python",
                "scripts/mutmut_subprocess_runner.py",
                "--results-file",
                str(tmp_path / "mutation_results.json"),
                "custom_components.autodoctor.action_walker.x_walk_automation_actions__mutmut_1",
            ]
        ): FakeResult(0),
    }

    def fake_run(cmd, check=False, timeout=None, **kwargs):
        calls.append((cmd, timeout))
        return outcomes[tuple(cmd)]

    monkeypatch.setattr(mw.subprocess, "run", fake_run)

    assert (
        mw.run_mutation_suite(
            tmp_path,
            [
                "custom_components.autodoctor.action_walker."
                "x_walk_automation_actions__mutmut_1"
            ],
        )
        == 0
    )
    assert calls == [
        ([".venv/bin/pyright", "custom_components/"], None),
        (
            [
                ".venv/bin/mypy",
                "--strict",
                "--follow-imports=skip",
                "custom_components/autodoctor/action_walker.py",
                "custom_components/autodoctor/analyzer.py",
                "custom_components/autodoctor/jinja_validator.py",
                "custom_components/autodoctor/knowledge_base.py",
                "custom_components/autodoctor/service_validator.py",
                "custom_components/autodoctor/template_utils.py",
                "custom_components/autodoctor/validator.py",
            ],
            None,
        ),
        (
            [
                ".venv/bin/python",
                "scripts/mutmut_subprocess_runner.py",
                "--results-file",
                str(tmp_path / "mutation_results.json"),
                "custom_components.autodoctor.action_walker.x_walk_automation_actions__mutmut_1",
            ],
            mw.RUN_TIMEOUT_SECONDS,
        ),
    ]


def test_get_survivor_mutants_reads_workflow_results_file(tmp_path):
    mw = _load_module()
    (tmp_path / "mutation_results.json").write_text(
        __import__("json").dumps(
            [
                {"mutant_name": "a", "status": "killed"},
                {"mutant_name": "b", "status": "survived"},
                {"mutant_name": "c", "status": "timeout"},
            ]
        )
    )

    assert mw.get_survivor_mutants(tmp_path) == ["b"]


def test_rerun_survivors_uses_fresh_process_runner(tmp_path, monkeypatch):
    mw = _load_module()
    calls: list[tuple[list[str], int | None]] = []

    class FakeResult:
        returncode = 0

    def fake_run(cmd, check=False, timeout=None, **kwargs):
        calls.append((cmd, timeout))
        return FakeResult()

    monkeypatch.setattr(mw.subprocess, "run", fake_run)
    (tmp_path / "mutation_results.json").write_text(
        __import__("json").dumps(
            [
                {"mutant_name": "custom_components.autodoctor.validator.x_a__mutmut_1", "status": "survived"},
                {"mutant_name": "custom_components.autodoctor.validator.x_b__mutmut_2", "status": "killed"},
            ]
        )
    )

    assert mw.rerun_survivors(tmp_path) == 0
    assert calls == [
        (
            [
                ".venv/bin/python",
                "scripts/mutmut_subprocess_runner.py",
                "--results-file",
                str(tmp_path / "mutation_results.json"),
                "custom_components.autodoctor.validator.x_a__mutmut_1",
            ],
            mw.RUN_TIMEOUT_SECONDS,
        )
    ]


def test_pyproject_mutmut_paths_are_list():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    paths = data["tool"]["mutmut"]["paths_to_mutate"]

    assert paths == ["custom_components/autodoctor/action_walker.py"]


def test_pyproject_mutmut_tests_dir_is_list():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    tests_dir = data["tool"]["mutmut"]["tests_dir"]

    assert tests_dir == ["tests/"]


def test_pyproject_mutmut_ignores_fuzz_target_tests():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    selection_args = data["tool"]["mutmut"]["pytest_add_cli_args_test_selection"]

    assert "--ignore=tests/test_fuzz_targets.py" in selection_args


def test_pyproject_mutmut_ignores_fuzz_runner_tests():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    selection_args = data["tool"]["mutmut"]["pytest_add_cli_args_test_selection"]

    assert "--ignore=tests/test_fuzz_runner_script.py" in selection_args


def test_pyproject_mutmut_copies_scripts_into_mutants():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    also_copy = data["tool"]["mutmut"]["also_copy"]

    assert "scripts" in also_copy


def test_pyproject_mutmut_ignores_property_mutation_gate_script_tests():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    selection_args = data["tool"]["mutmut"]["pytest_add_cli_args_test_selection"]

    assert "--ignore=tests/test_property_mutation_gate_script.py" in selection_args


def test_strict_mypy_passes_for_core_mutation_paths():
    mw = _load_module()
    mypy_cmd = [cmd for cmd in mw.get_typecheck_commands() if cmd[0].endswith("mypy")][0]

    result = __import__("subprocess").run(mypy_cmd, check=False, capture_output=True, text=True)

    assert result.returncode == 0, result.stdout + result.stderr


def test_pyproject_mypy_files_are_scoped_to_core_mutation_paths():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    files = data["tool"]["mypy"]["files"]

    assert files == [
        "custom_components/autodoctor/action_walker.py",
        "custom_components/autodoctor/analyzer.py",
        "custom_components/autodoctor/jinja_validator.py",
        "custom_components/autodoctor/knowledge_base.py",
        "custom_components/autodoctor/service_validator.py",
        "custom_components/autodoctor/template_utils.py",
        "custom_components/autodoctor/validator.py",
    ]
