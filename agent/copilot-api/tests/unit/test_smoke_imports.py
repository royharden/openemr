"""Smoke-import test — confirms the sidecar package imports cleanly."""

from __future__ import annotations


def test_app_package_imports() -> None:
    import app  # noqa: F401
    from app import schemas as _schemas  # noqa: F401


def test_startup_module_imports() -> None:
    from app.startup import (  # noqa: F401
        StartupSelfTestError,
        startup_self_test,
        validate_corpus_db,
        validate_provider_credentials,
    )


def test_check_pr_has_tests_script_imports() -> None:
    """The PR-tests guard script must be importable so we can unit-test its
    helpers if a future agent breaks the heuristic."""
    import importlib.util
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "check_pr_has_tests.py"
    assert script.exists(), "scripts/check_pr_has_tests.py missing"
    spec = importlib.util.spec_from_file_location("_check_pr_has_tests", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
