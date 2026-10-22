import pytest
from packaging.markers import Marker

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
        dependency for dependency in parsed.dependencies if dependency.name == "httpx"
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


def test_keeps_good_requirements_around_a_bad_line(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        """
httpx>=0.27
this is !!! not a valid requirement
click>=8.3
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert [dependency.name for dependency in parsed.dependencies] == [
        "httpx",
        "click",
    ]
    assert len(parsed.failures) == 1
    assert parsed.failures[0].source_file == "requirements.txt"


def test_keeps_good_pyproject_entries_around_a_bad_entry(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = [
    "httpx>=0.27",
    "!!!bad!!!",
    "click>=8.3",
]
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert {dependency.name for dependency in parsed.dependencies} == {
        "httpx",
        "click",
    }
    assert len(parsed.failures) == 1
    assert parsed.failures[0].source_file == "pyproject.toml"


def test_expands_pep735_include_group(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
dependencies = []

[dependency-groups]
test = ["pytest>=8"]
dev = [{include-group = "test"}, "ruff>=0.5"]
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    dev_names = {
        dependency.name
        for dependency in parsed.dependencies
        if dependency.details["dependency_group"] == "dev"
    }

    assert not parsed.failures
    assert {"pytest", "ruff"} <= dev_names


def test_parses_poetry_multi_constraint_dependency(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.poetry.dependencies]
python = "^3.9"
httpx = "^0.28"
numpy = [
    { version = "^1.26", python = "<3.12" },
    { version = "^2.0", python = ">=3.12" },
]
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    # pyrefly: ignore[bad-specialization]
    numpy_specs = sorted(
        dependency.version_spec
        for dependency in parsed.dependencies
        if dependency.name == "numpy"
    )

    assert not parsed.failures
    assert numpy_specs == ["^1.26", "^2.0"]
    assert any(dependency.name == "httpx" for dependency in parsed.dependencies)


def test_poetry_python_constraint_is_not_a_dependency(tmp_path):
    # Every Poetry table shape skips ``python`` before it reaches
    # ``_poetry_dependency``, which makes the guard inside that helper
    # unreachable. Remove either the guard or the callers' checks.
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.poetry.dependencies]
python = "^3.12"
httpx = "^0.28"

[tool.poetry.dev-dependencies]
python = "^3.12"
pytest = "^8"

[tool.poetry.group.docs.dependencies]
python = "^3.12"
sphinx = "^7"
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert not parsed.failures
    assert {dependency.name for dependency in parsed.dependencies} == {
        "httpx",
        "pytest",
        "sphinx",
    }


def test_parses_requirements_with_backslash_continuations(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        """
httpx==0.28.1 \\
    --hash=sha256:aaaa \\
    --hash=sha256:bbbb
click==8.3.1
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    httpx_dependency = next(
        dependency for dependency in parsed.dependencies if dependency.name == "httpx"
    )

    assert not parsed.failures
    assert [dependency.name for dependency in parsed.dependencies] == [
        "httpx",
        "click",
    ]
    assert httpx_dependency.version_spec == "==0.28.1"


def test_parses_requirement_with_inline_hash_option(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "httpx==0.28.1 --hash=sha256:aaaa\n",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert not parsed.failures
    assert [dependency.name for dependency in parsed.dependencies] == ["httpx"]
    assert parsed.dependencies[0].version_spec == "==0.28.1"


@pytest.mark.parametrize(
    "bare_line",
    [
        "./vendor/mypkg",
        "../sibling/project",
        "/abs/path/to/pkg",
        "https://example.com/pkg-1.0-py3-none-any.whl",
    ],
)
def test_bare_paths_and_urls_do_not_hide_other_requirements(
    tmp_path,
    bare_line,
):
    (tmp_path / "requirements.txt").write_text(
        f"httpx>=0.27\n{bare_line}\nclick>=8.3\n",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    # Whether the bare entry is skipped or reported is a design choice; its
    # neighbours must survive either way.
    assert {"httpx", "click"} <= {dependency.name for dependency in parsed.dependencies}


def test_url_fragment_survives_inline_comment_stripping(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "pkg @ https://example.com/pkg.zip#sha256=abc123  # pinned\n",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert not parsed.failures
    assert parsed.dependencies[0].name == "pkg"
    assert (
        parsed.dependencies[0].details["url"]
        == "https://example.com/pkg.zip#sha256=abc123"
    )


def test_parses_uv_lock_packages(tmp_path):
    (tmp_path / "uv.lock").write_text(
        """
version = 1

[[package]]
name = "click"
version = "8.3.1"
source = { registry = "https://pypi.org/simple" }
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert not parsed.failures
    assert parsed.dependencies[0].name == "click"
    assert parsed.dependencies[0].locked_version == "8.3.1"
    assert parsed.dependencies[0].version_spec is None


@pytest.mark.parametrize(
    "source",
    [
        '{ editable = "." }',
        '{ virtual = "." }',
    ],
)
def test_uv_lock_excludes_the_project_itself(tmp_path, source):
    (tmp_path / "uv.lock").write_text(
        f"""
version = 1

[[package]]
name = "click"
version = "8.3.1"
source = {{ registry = "https://pypi.org/simple" }}

[[package]]
name = "repaudit"
version = "0.0.1"
source = {source}
dependencies = [
    {{ name = "click" }},
]
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    assert not parsed.failures
    assert [dependency.name for dependency in parsed.dependencies] == ["click"]


def test_marker_key_is_consistent_across_manifest_styles(tmp_path):
    pep621 = tmp_path / "pep621"
    pep621.mkdir()
    (pep621 / "pyproject.toml").write_text(
        """
[project]
dependencies = ["colorama; sys_platform == 'win32'"]
""",
        encoding="utf-8",
    )

    poetry = tmp_path / "poetry"
    poetry.mkdir()
    (poetry / "pyproject.toml").write_text(
        """
[tool.poetry.dependencies]
colorama = { version = "*", markers = "sys_platform == 'win32'" }
""",
        encoding="utf-8",
    )

    parsed = parse_repository(gather(tmp_path), tmp_path)

    pep621_details = parsed.children["pep621"].dependencies[0].details
    poetry_details = parsed.children["poetry"].dependencies[0].details

    assert "marker" in pep621_details
    assert "marker" in poetry_details
    # Quote style differs textually, so compare semantically.
    assert Marker(pep621_details["marker"]) == Marker(poetry_details["marker"])
