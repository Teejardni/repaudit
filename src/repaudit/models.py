
from dataclasses import dataclass, field


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
