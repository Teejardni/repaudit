
import tomllib
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

from repaudit.models import Manifest, ParsedDependency


class ManifestParseError(ValueError):
    """Raised when a supported manifest cannot be parsed."""


def _manifest_path(manifest: Manifest, repository_root: Path) -> Path:
    """Resolve a repository-relative manifest path."""
    return repository_root / manifest.path


def _dependency_from_requirement(
    raw: str,
    manifest: Manifest,
    *,
    details: dict | None = None,
) -> ParsedDependency:
    """Parse a PEP 508 requirement while preserving its original expression."""
    try:
        requirement = Requirement(raw)
    except InvalidRequirement as exc:
        raise ManifestParseError(
            f"Invalid requirement {raw!r}: {exc}"
        ) from exc

    return ParsedDependency(
        name=requirement.name,
        ecosystem="python",
        file_style=manifest.filename,
        source_file=manifest.path,
        version_spec=str(requirement.specifier) or None,
        details={
            **(details or {}),
            "extras": sorted(requirement.extras),
            "marker": str(requirement.marker) if requirement.marker else None,
            "url": requirement.url,
            "raw_requirement": raw,
        },
    )


def parse_requirements_txt(
    manifest: Manifest,
    repository_root: Path,
) -> list[ParsedDependency]:
    """Parse package requirements from a requirements-style text file."""
    path: Path = _manifest_path(manifest, repository_root)
    dependencies: list[ParsedDependency] = []

    try:
        lines: list[str] = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ManifestParseError(f"Could not read file: {exc}") from exc

    for line_number, original_line in enumerate(lines, start=1):
        line = original_line.strip()

        if not line or line.startswith("#"):
            continue

        # Preserve pip directives as metadata rather than treating them
        # as package requirements. Recursive inclusion is out of scope.
        if line.startswith(
            ("-r ", "--requirement ", "-c ", "--constraint ")
        ):
            continue

        # Index options, editable installs, and other pip directives are
        # not package requirement declarations in this initial parser.
        if line.startswith("-"):
            continue

        # Only strip comments introduced by whitespace, so URL fragments
        # are not accidentally truncated.
        comment_index: int = line.find(" #")
        if comment_index >= 0:
            line: str = line[:comment_index].rstrip()

        if not line:
            continue

        dependencies.append(
            _dependency_from_requirement(
                line,
                manifest,
                details={
                    "line": line_number,
                    "raw_line": original_line,
                    "dependency_group": "requirements",
                },
            )
        )

    return dependencies


def _toml_file(
    manifest: Manifest,
    repository_root: Path,
) -> dict:
    """Read and decode a TOML manifest."""
    path: Path = _manifest_path(manifest, repository_root)

    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ManifestParseError(f"Could not parse TOML: {exc}") from exc


def _poetry_dependency(
    name: str,
    value: str | dict,
    manifest: Manifest,
    group: str,
) -> ParsedDependency:
    """Parse a Poetry declaration without interpreting it as PEP 508."""
    if name.lower() == "python":
        raise ManifestParseError(
            "The Poetry Python-version constraint is project metadata, "
            "not a package dependency."
        )

    if isinstance(value, str):
        version_spec = None if value in {"", "*"} else value
        details = {
            "dependency_group": group,
            "poetry": True,
            "raw_requirement": f"{name} {value}".strip(),
        }

    elif isinstance(value, dict):
        version = value.get("version", "*")
        if not isinstance(version, str):
            raise ManifestParseError(
                f"Invalid Poetry version constraint for {name!r}"
            )

        version_spec = None if version in {"", "*"} else version
        details = {
            "dependency_group": group,
            "poetry": True,
            "raw_requirement": f"{name} {version}".strip(),
            "extras": value.get("extras", []),
            "optional": value.get("optional", False),
            "source": value.get("source"),
            "markers": value.get("markers"),
            "python": value.get("python"),
            "git": value.get("git"),
            "url": value.get("url"),
            "path": value.get("path"),
        }

    else:
        raise ManifestParseError(
            f"Unsupported Poetry declaration for dependency {name!r}"
        )

    return ParsedDependency(
        name=name,
        ecosystem="python",
        file_style=manifest.filename,
        source_file=manifest.path,
        version_spec=version_spec,
        details=details,
    )


def parse_pyproject_toml(
    manifest: Manifest,
    repository_root: Path,
) -> list[ParsedDependency]:
    """Parse PEP 621 and Poetry dependency declarations."""
    data = _toml_file(manifest, repository_root)
    dependencies = []

    project = data.get("project", {})

    for raw in project.get("dependencies", []):
        if not isinstance(raw, str):
            raise ManifestParseError(
                "Each project.dependencies entry must be a string"
            )

        dependencies.append(
            _dependency_from_requirement(
                raw,
                manifest,
                details={"dependency_group": "runtime"},
            )
        )

    optional_dependencies = project.get("optional-dependencies", {})
    if not isinstance(optional_dependencies, dict):
        raise ManifestParseError(
            "project.optional-dependencies must be a TOML table"
        )

    for group, requirements in optional_dependencies.items():
        for raw in requirements:
            if not isinstance(raw, str):
                raise ManifestParseError(
                    f"Invalid dependency in optional group {group!r}"
                )

            dependencies.append(
                _dependency_from_requirement(
                    raw,
                    manifest,
                    details={"dependency_group": group},
                )
            )

    dependency_groups = data.get("dependency-groups", {})
    if not isinstance(dependency_groups, dict):
        raise ManifestParseError("dependency-groups must be a TOML table")

    for group, requirements in dependency_groups.items():
        for raw in requirements:
            if not isinstance(raw, str):
                raise ManifestParseError(
                    f"Unsupported dependency-group entry in {group!r}: "
                    f"{raw!r}"
                )

            dependencies.append(
                _dependency_from_requirement(
                    raw,
                    manifest,
                    details={"dependency_group": group},
                )
            )

    poetry = data.get("tool", {}).get("poetry", {})

    # Legacy Poetry dependency tables.
    for table_name, group in (
        ("dependencies", "runtime"),
        ("dev-dependencies", "dev"),
    ):
        table = poetry.get(table_name, {})
        for name, value in table.items():
            if name.lower() == "python":
                continue

            dependencies.append(
                _poetry_dependency(name, value, manifest, group)
            )

    # Poetry's newer dependency-group format.
    poetry_groups = poetry.get("group", {})
    for group, group_data in poetry_groups.items():
        table = group_data.get("dependencies", {})
        for name, value in table.items():
            if name.lower() == "python":
                continue

            dependencies.append(
                _poetry_dependency(name, value, manifest, group)
            )

    return dependencies


def _parse_lockfile(
    manifest: Manifest,
    repository_root: Path,
) -> list[ParsedDependency]:
    """Parse TOML lockfiles with an array of package tables."""
    data = _toml_file(manifest, repository_root)
    packages = data.get("package")

    if not isinstance(packages, list):
        raise ManifestParseError(
            "Expected an array of package entries in the TOML lockfile"
        )

    dependencies = []

    for package in packages:
        if not isinstance(package, dict):
            raise ManifestParseError(
                "Lockfile package entry must be a TOML table"
            )

        name = package.get("name")
        version = package.get("version")

        if not isinstance(name, str) or not isinstance(version, str):
            raise ManifestParseError(
                "Lockfile package entries must contain string name and version"
            )

        dependencies.append(
            ParsedDependency(
                name=name,
                ecosystem="python",
                file_style=manifest.filename,
                source_file=manifest.path,
                locked_version=version,
                details={
                    "source": package.get("source"),
                    "dependencies": package.get("dependencies", {}),
                    "optional": package.get("optional"),
                    "python_versions": package.get("python-versions"),
                },
            )
        )

    return dependencies


def parse_poetry_lock(
    manifest: Manifest,
    repository_root: Path,
) -> list[ParsedDependency]:
    """Parse the package entries in poetry.lock."""
    return _parse_lockfile(manifest, repository_root)


def parse_uv_lock(
    manifest: Manifest,
    repository_root: Path,
) -> list[ParsedDependency]:
    """Parse the package entries in uv.lock."""
    return _parse_lockfile(manifest, repository_root)


def python_deps_parser(
    file_style: str,
    manifest: Manifest,
    repository_root: Path,
) -> list[ParsedDependency]:
    """Dispatch a Python manifest to its format-specific parser."""
    parsers = {
        "pyproject.toml": parse_pyproject_toml,
        "requirements.txt": parse_requirements_txt,
        "poetry.lock": parse_poetry_lock,
        "uv.lock": parse_uv_lock,
    }

    # Support the currently recognised requirements*.txt filenames.
    if file_style.startswith("requirements") and file_style.endswith(".txt"):
        parser   = parse_requirements_txt
    else:
        parser = parsers.get(file_style)

    if parser is None:
        raise ManifestParseError(
            f"Unsupported Python manifest format: {file_style}"
        )

    return parser(manifest, repository_root)
