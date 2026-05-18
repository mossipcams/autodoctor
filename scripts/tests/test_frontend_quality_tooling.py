from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_PACKAGE = ROOT / "www" / "autodoctor" / "package.json"
PRE_PR_CHECKS = ROOT / "scripts" / "pre_pr_checks.sh"
BUILD_CARD_WORKFLOW = ROOT / ".github" / "workflows" / "build-card.yml"
README = ROOT / "README.md"


def test_frontend_quality_gate_is_wired_into_local_and_ci_checks():
    package = json.loads(FRONTEND_PACKAGE.read_text())
    scripts = package["scripts"]

    assert "quality:code-health" in scripts
    assert "lint:deps" in scripts
    assert "lint:deadcode" in scripts
    assert "lint:duplicates" in scripts
    assert scripts["quality:code-health"] == "node ./quality-checks.mjs"
    assert "dependency-cruiser" in package["devDependencies"]
    assert "knip" in package["devDependencies"]
    assert "jscpd" in package["devDependencies"]

    pre_pr_checks = PRE_PR_CHECKS.read_text()
    assert "run quality:code-health" in pre_pr_checks

    build_card_workflow = BUILD_CARD_WORKFLOW.read_text()
    assert "run: npm run quality:code-health" in build_card_workflow

    quality_runner = (ROOT / "www" / "autodoctor" / "quality-checks.mjs").read_text()
    assert "lint:deps" in quality_runner
    assert "lint:deadcode" in quality_runner
    assert "lint:duplicates" in quality_runner

    depcruise_config = ROOT / "www" / "autodoctor" / ".dependency-cruiser.cjs"
    config_text = depcruise_config.read_text()

    assert depcruise_config.exists()
    assert "no-circular" in config_text
    assert "no-orphans" in config_text
    assert "not-to-dev-dependency" in config_text

    knip_config = ROOT / "www" / "autodoctor" / "knip.json"
    knip_text = knip_config.read_text()

    assert knip_config.exists()
    assert '"entry"' in knip_text
    assert '"project"' in knip_text
    assert '"ignoreDependencies"' in knip_text

    jscpd_config = ROOT / "www" / "autodoctor" / ".jscpd.json"
    jscpd_text = jscpd_config.read_text()

    assert jscpd_config.exists()
    assert '"threshold"' in jscpd_text
    assert '"minTokens"' in jscpd_text
    assert '"ignore"' in jscpd_text

    readme = README.read_text()
    assert "quality:code-health" in readme
    assert "dependency-cruiser" in readme
    assert "knip" in readme
    assert "jscpd" in readme
