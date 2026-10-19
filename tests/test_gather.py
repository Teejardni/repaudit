import time

import pytest

from repaudit.audit import gather


def touch(root, relative_path):
    """Create a file and any parent directories needed for it."""
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def find_node(root, relative_path):
    """Look up a node by its repository-relative directory path."""
    node = root

    if relative_path == ".":
        return node

    for part in relative_path.split("/"):
        node = node.children[part]

    return node


def test_discovers_single_python_manifest(tmp_path):
    touch(tmp_path, "pyproject.toml")

    result = gather(tmp_path)

    assert result.path == "."
    assert len(result.manifests) == 1

    manifest = result.manifests[0]
    assert manifest.path == "pyproject.toml"
    assert manifest.filename == "pyproject.toml"
    assert manifest.ecosystem == "python"
    assert manifest.manifest_type == "manifest"


def test_discovers_multiple_ecosystems_in_one_directory(tmp_path):
    touch(tmp_path, "pyproject.toml")
    touch(tmp_path, "package.json")
    touch(tmp_path, "Dockerfile")
    touch(tmp_path, "go.mod")

    result = gather(tmp_path)

    ecosystems = {manifest.ecosystem for manifest in result.manifests}

    assert ecosystems == {"python", "node", "docker", "go"}


def test_preserves_nested_repository_structure(tmp_path):
    touch(tmp_path, "backend/pyproject.toml")
    touch(tmp_path, "frontend/package.json")
    (tmp_path / "empty" / "nested").mkdir(parents=True)

    result = gather(tmp_path)

    assert set(result.children) == {"backend", "empty", "frontend"}
    assert result.children["backend"].path == "backend"
    assert result.children["frontend"].path == "frontend"
    assert result.children["empty"].children["nested"].path == "empty/nested"

    assert result.children["backend"].manifests[0].path == "backend/pyproject.toml"
    assert result.children["frontend"].manifests[0].path == "frontend/package.json"


def test_discovers_multiple_manifests_in_same_directory(tmp_path):
    touch(tmp_path, "requirements.txt")
    touch(tmp_path, "requirements-dev.txt")
    touch(tmp_path, "uv.lock")

    result = gather(tmp_path)

    assert len(result.manifests) == 3
    assert {manifest.filename for manifest in result.manifests} == {
        "requirements.txt",
        "requirements-dev.txt",
        "uv.lock",
    }


def test_classifies_lockfiles_separately(tmp_path):
    touch(tmp_path, "package.json")
    touch(tmp_path, "package-lock.json")
    touch(tmp_path, "go.mod")
    touch(tmp_path, "go.sum")

    result = gather(tmp_path)

    types = {manifest.filename: manifest.manifest_type for manifest in result.manifests}

    assert types["package.json"] == "manifest"
    assert types["package-lock.json"] == "lockfile"
    assert types["go.mod"] == "manifest"
    assert types["go.sum"] == "lockfile"


def test_skips_excluded_directories(tmp_path):
    touch(tmp_path, ".git/config")
    touch(tmp_path, ".venv/pyproject.toml")
    touch(tmp_path, "node_modules/package.json")
    touch(tmp_path, "src/pyproject.toml")

    result = gather(tmp_path)

    assert set(result.children) == {"src"}
    assert result.children["src"].manifests[0].ecosystem == "python"


def test_traverses_other_hidden_directories(tmp_path):
    touch(tmp_path, ".github/workflows/ci.yml")
    touch(tmp_path, ".config/package.json")

    result = gather(tmp_path)

    assert ".github" in result.children
    assert ".config" in result.children

    workflows = find_node(result, ".github/workflows")
    assert workflows.manifests[0].ecosystem == "github-actions"


def test_ignores_unrecognized_files(tmp_path):
    touch(tmp_path, "notes.txt")
    touch(tmp_path, "random.yaml")
    touch(tmp_path, "src/main.py")

    result = gather(tmp_path)

    assert result.manifests == []
    assert "src" in result.children


def test_empty_repository_returns_root_node(tmp_path):
    result = gather(tmp_path)

    assert result.path == "."
    assert result.manifests == []
    assert result.children == {}


def test_invalid_path_raises_file_not_found(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        gather(missing)


def test_file_path_raises_not_a_directory(tmp_path):
    file_path = touch(tmp_path, "pyproject.toml")

    with pytest.raises(NotADirectoryError):
        gather(file_path)


def test_discovery_order_is_deterministic(tmp_path):
    touch(tmp_path, "z/package.json")
    touch(tmp_path, "a/pyproject.toml")
    touch(tmp_path, "requirements.txt")

    first = gather(tmp_path)
    second = gather(tmp_path)

    assert list(first.children) == list(second.children)
    assert first.manifests == second.manifests


def test_gather_performance(tmp_path):
    """Benchmark gather() against a synthetic repository tree."""
    num_dirs = 100
    manifests_per_dir = 3

    # Build a synthetic repository.
    for i in range(num_dirs):
        for j in range(manifests_per_dir):
            if j == 0:
                filename = "pyproject.toml"
            elif j == 1:
                filename = "package.json"
            else:
                filename = "Dockerfile"

            touch(tmp_path, f"project_{i}/component_{j}/{filename}")

    # Warm-up run to reduce first-call effects.
    gather(tmp_path)

    start = time.perf_counter()
    result = gather(tmp_path)
    elapsed = time.perf_counter() - start
    assert len(result.children) == num_dirs

    print(
        f"\ngather() scanned {num_dirs} projects "
        f"with {manifests_per_dir} manifests each "
        f"in {elapsed:.4f} seconds"
    )
