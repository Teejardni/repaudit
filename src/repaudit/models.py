from dataclasses import dataclass, field
from typing import Any


@dataclass
class Manifest:
    """A dependency declaration in a repository."""

    path: str
    filename: str
    ecosystem: str
    manifest_type: str


@dataclass
class RepositoryNode:
    """A directory and its discovered files and subdirectories."""

    path: str
    manifests: list[Manifest] = field(default_factory=list)
    children: dict[str, "RepositoryNode"] = field(default_factory=dict)


@dataclass
class ParsedDependency:
    """A dependency declaration extracted from a manifest."""

    name: str
    ecosystem: str
    file_style: str
    source_file: str
    version_spec: str | None = None
    locked_version: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseFailure:
    """A failure to parse a particular manifest."""

    source_file: str
    category: str
    message: str


@dataclass
class ParsedRepositoryNode:
    """A discovered directory enriched with parsed dependency data."""

    path: str
    dependencies: list[ParsedDependency] = field(default_factory=list)
    failures: list[ParseFailure] = field(default_factory=list)
    children: dict[str, "ParsedRepositoryNode"] = field(default_factory=dict)
