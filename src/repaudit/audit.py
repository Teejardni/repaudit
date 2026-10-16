from pathlib import Path

import httpx

from repaudit.models import RepositoryNode

from .models import Manifest
from .report import Report
from .resolvers.pypi_resolver import parse_manifest, resolve

_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".cache",
    "*.egg-info",
}


def _classify_file(path: Path, relative_path: Path) -> Manifest | None:
    """Classify a discovered file without parsing its contents."""
    filename = path.name
    ecosystem = None
    manifest_type = None

    # Python
    if filename == "pyproject.toml" or filename == "Pipfile":
        ecosystem, manifest_type = "python", "manifest"
    elif filename == "Pipfile.lock":
        ecosystem, manifest_type = "python", "lockfile"
    elif filename.startswith("requirements") and filename.endswith(".txt"):
        ecosystem, manifest_type = "python", "manifest"
    elif filename in {"poetry.lock", "uv.lock", "pdm.lock"}:
        ecosystem, manifest_type = "python", "lockfile"

    # Node.js / npm
    elif filename == "package.json":
        ecosystem, manifest_type = "node", "manifest"
    elif filename in {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    }:
        ecosystem, manifest_type = "node", "lockfile"

    # Go
    elif filename == "go.mod":
        ecosystem, manifest_type = "go", "manifest"
    elif filename == "go.sum":
        ecosystem, manifest_type = "go", "lockfile"

    # Docker and container definitions
    elif (
        filename in {"Dockerfile", "Containerfile"}
        or filename.startswith(("Dockerfile.", "Containerfile."))
        or filename
        in {
            "compose.yml",
            "compose.yaml",
            "docker-compose.yml",
            "docker-compose.yaml",
        }
    ):
        ecosystem, manifest_type = "docker", "container"

    # Conda / Pixi
    elif filename in {"environment.yml", "environment.yaml", "pixi.toml"}:
        ecosystem, manifest_type = "conda", "manifest"
    elif filename == "pixi.lock":
        ecosystem, manifest_type = "conda", "lockfile"

    # GitHub Actions workflows
    elif (
        path.suffix.lower() in {".yml", ".yaml"}
        and len(relative_path.parts) >= 3
        and relative_path.parts[-3:-1] == (".github", "workflows")
    ):
        ecosystem, manifest_type = "github-actions", "workflow"

    if ecosystem is None or manifest_type is None:
        return None

    return Manifest(
        path=relative_path.as_posix(),
        filename=filename,
        ecosystem=ecosystem,
        manifest_type=manifest_type,
    )


def gather(path: str | Path) -> RepositoryNode:
    """Recursively discover dependency-related files under a repository root."""
    root = Path(path).expanduser()

    if not root.exists():
        raise FileNotFoundError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {root}")

    root = root.resolve()

    def visit(directory: Path) -> RepositoryNode:
        relative_directory = directory.relative_to(root)
        node = RepositoryNode(
            path="."
            if relative_directory == Path(".")
            else relative_directory.as_posix()
        )

        for entry in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
            # Do not follow symbolic links during discovery.
            if entry.is_symlink():
                continue

            if entry.is_dir():
                if entry.name in _EXCLUDED_DIRS:
                    continue

                child = visit(entry)
                node.children[entry.name] = child

            elif entry.is_file():
                relative_file = entry.relative_to(root)
                manifest = _classify_file(entry, relative_file)
                if manifest is not None:
                    node.manifests.append(manifest)

        return node

    return visit(root)


def check_unpinned(pkgs: dict[str, str]):
    for name, specifier in pkgs:
        if not specifier:
            return


def check_drift(pkgs: dict[str, str]):
    for name, specifier in pkgs:
        if not specifier:
            break
        if not name:
            break


async def run_audit(path: Path, client: httpx.AsyncClient) -> list[Report]:
    findings: list[Report] = []
    requires_python, packages = parse_manifest(path)
    if not packages:
        return findings
    await resolve(client, packages)
    # TODO: checks go here (CVE, unpinned, version mismatch, cycles, deprecations)
    return findings
