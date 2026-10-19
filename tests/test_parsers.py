import pytest

from repaudit.audit import gather
from repaudit.parsers.manifest_parser import parse_repository


def test_parses_pyproject_dependencies(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = [
    "httpx>=0.27,<1",
    "packaging==24.0",
]

[project.optional-dependencies]
dev = ["pytest>=8"]
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert not parsed.failures
    assert {dependency.name for dependency in parsed.dependencies} == {
        "httpx",
        "packaging",
        "pytest",
    }

    httpx_dependency = next(
        dependency
        for dependency in parsed.dependencies
        if dependency.name == "httpx"
    )
    assert httpx_dependency.version_spec == ">=0.27,<1"
    assert httpx_dependency.source_file == "pyproject.toml"


def test_reports_malformed_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project\ninvalid",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert len(parsed.failures) == 1
    assert parsed.failures[0].source_file == "pyproject.toml"
    assert parsed.failures[0].category == "malformed_manifest"


def test_parses_requirements_file(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        """
httpx>=0.27,<1
requests[socks]>=2.31 ; python_version >= "3.12"
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert not parsed.failures
    assert len(parsed.dependencies) == 2

    request_dependency = next(
        dependency
        for dependency in parsed.dependencies
        if dependency.name == "requests"
    )
    assert request_dependency.version_spec == ">=2.31"
    assert request_dependency.details["extras"] == ["socks"]


def test_preserves_nested_repository_structure(tmp_path):
    nested = tmp_path / "backend"
    nested.mkdir()
    (nested / "requirements.txt").write_text(
        "httpx>=0.27\n",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert parsed.dependencies == []
    assert parsed.children["backend"].path == "backend"
    assert parsed.children["backend"].dependencies[0].name == "httpx"
    assert (
        parsed.children["backend"].dependencies[0].source_file
        == "backend/requirements.txt"
    )


def test_continues_after_a_malformed_manifest(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project\ninvalid",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "httpx>=0.27\n",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert len(parsed.failures) == 1
    assert [dependency.name for dependency in parsed.dependencies] == ["httpx"]