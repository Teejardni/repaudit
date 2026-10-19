from pathlib import Path
from typing import Dict, List, Tuple
from packaging.requirements import Requirement, InvalidRequirement


SKIP_PREFIXES = (
    "--",  # installer flags
    "-i",  # --index-url
    "-e",  # editable installs (local paths, not auditable via PyPI)
    "#",  # comments
)


def _parse_line(line: str) -> Tuple[str, str] | None:
    """
    Parse a single requirement line into (name, specifier).
    Returns None if the line should be skipped.
    """
    line = line.strip()

    if not line:
        return None

    if any(line.startswith(p) for p in SKIP_PREFIXES):
        return None

    try:
        req = Requirement(line)

        if req.marker and "extra" in str(req.marker):  # Skip extra marked deps
            return None
        return req.name.lower(), str(req.specifier)
    except InvalidRequirement:
        print(f"Warning: could not parse requirement '{line}', skipping")
        return None


def _resolve_includes(file_path: Path, visited: set) -> Dict[str, str]:
    """
    Recursively follow -r and -c include directives.
    """
    packages = {}
    abs_path = file_path.resolve()  # circular includes guard
    if abs_path in visited:
        return packages
    visited.add(abs_path)

    if not file_path.exists():
        print(f"Warning: included file '{file_path}' not found, skipping")
        return packages

    for line in file_path.read_text().splitlines():
        line = line.strip()
        if line.startswith(("-r ", "-c ")):
            included = file_path.parent / line[3:].strip()
            packages.update(_resolve_includes(included, visited))
            continue

        result = _parse_line(line)
        if result:
            name, specifier = result
            packages[name] = specifier

    return packages


ENV_CANDIDATES = {
    "prod": [
        "requirements/prod.txt",
        "requirements/production.txt",
        "requirements-prod.txt",
    ],
    "dev": [
        "requirements/dev.txt",
        "requirements/development.txt",
        "requirements-dev.txt",
    ],
    "base": [
        "requirements/base.txt",
        "requirements/common.txt",
        "requirements-base.txt",
    ],
    "plain": ["requirements.txt"],
}


def detect_environment(project_path: Path) -> Dict[str, Path]:
    """
    Scan project for known requirements file patterns.
    Returns dict of {env_name: path} for all found environments.
    """
    found = {}
    for env, candidates in ENV_CANDIDATES.items():
        for candidate in candidates:
            path = project_path / candidate
            if path.exists():
                found[env] = path
                break
    return found


def parse(file_path: Path) -> Dict[str, str]:
    """
    Public entry point. Parse a requirements file and all its includes.
    Returns {package_name: specifier} — same shape as pypi_resolver
    parse_manifest() so audit.py can treat both identically.
    """
    return _resolve_includes(file_path, visited=set())


def parse_environment(
    project_path: Path, env: str | None = None
) -> Tuple[Dict[str, str], str]:
    """
    Parse the appropriate requirements file for the given environment.
    If env is None, prefer prod > base > plain — most conservative first,
    since audit findings on prod deps are highest priority.

    Returns (packages, env_name) so the caller knows which env was used.
    """
    found = detect_environment(project_path)

    if not found:
        return {}, "none"

    if env:
        if env not in found:
            print(
                f"Warning: environment '{env}' not found, falling back to auto-detect"
            )
        else:
            return parse(found[env]), env

    for preferred in ("prod", "base", "plain", "dev"):
        if preferred in found:
            return parse(found[preferred]), preferred

    return {}, "none"
