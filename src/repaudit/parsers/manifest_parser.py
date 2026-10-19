from pathlib import Path

from repaudit.models import (
    Manifest,
    ParsedDependency,
    ParsedRepositoryNode,
    ParseFailure,
    RepositoryNode,
)

from .python_parser import ManifestParseError, python_deps_parser


class UnsupportedManifestError(ValueError):
    """Raised when no parser supports a manifest's ecosystem or format."""


def manifest_parser(
    ecosystem_name: str,
    file_style: str,
    manifest: Manifest,
    repository_root: Path,
) -> list[ParsedDependency]:
    """Dispatch a manifest to its ecosystem-specific parser."""
    if ecosystem_name == "python":
        return python_deps_parser(file_style, manifest, repository_root)

    raise UnsupportedManifestError(
        f"No parser implemented for ecosystem {ecosystem_name!r}"
    )


def parse_repository(
    repository: RepositoryNode,
    repository_root: Path,
) -> ParsedRepositoryNode:
    """Parse discovered manifests while preserving the directory tree."""
    parsed = ParsedRepositoryNode(path=repository.path)

    for manifest in repository.manifests:
        try:
            dependencies = manifest_parser(
                manifest.ecosystem,
                manifest.filename,
                manifest,
                repository_root,
            )
            parsed.dependencies.extend(dependencies)

        except ManifestParseError as exc:
            parsed.failures.append(
                ParseFailure(
                    source_file=manifest.path,
                    category="malformed_manifest",
                    message=str(exc),
                )
            )

        except UnsupportedManifestError as exc:
            parsed.failures.append(
                ParseFailure(
                    source_file=manifest.path,
                    category="unsupported_manifest",
                    message=str(exc),
                )
            )

    for name, child in repository.children.items():
        parsed.children[name] = parse_repository(child, repository_root)

    return parsed