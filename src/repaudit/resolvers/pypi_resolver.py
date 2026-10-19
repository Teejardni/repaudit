import httpx
import asyncio
import tomllib
from pathlib import Path
from packaging.requirements import Requirement, InvalidRequirement
from .. import cache
from ..parsers.requirements_parser import parse_environment


def resolve_dependency_versions(deps: list[str]) -> dict[str, str]:
    resolved = {}
    for dep in deps:
        try:
            req = Requirement(dep)
            if req.marker and "extra" in str(req.marker):
                continue
            resolved[req.name.lower()] = str(req.specifier)
        except InvalidRequirement as e:
            print(f"Warning: could not process requirement '{dep}': {e}")
    return resolved


async def get_package_metadata(
    client: httpx.AsyncClient, package: str, version: str | None = None
) -> dict:
    url = (
        f"https://pypi.org/pypi/{package}/json"
        if not version
        else f"https://pypi.org/pypi/{package}/{version}/json"
    )
    cache_key = f"pypi:{package}:{version or 'latest'}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise ValueError(f"Package '{package}' not found on PyPI") from e
        raise
    except httpx.RequestError as e:
        raise ConnectionError(f"Network error fetching '{package}': {e}") from e

    info = response.json()["info"]
    result = {
        "name": info["name"],
        "version": info["version"],
        "requires_python": info["requires_python"],
        "requires_dist": info["requires_dist"] or [],
        "classifiers": info.get("classifiers") or [],
    }
    cache.set(cache_key, result)
    return result


async def resolve(client: httpx.AsyncClient, packages: dict[str, str]) -> dict:
    visited = {}
    queue = list(packages.keys())
    while queue:
        results = await asyncio.gather(
            *[get_package_metadata(client, package) for package in queue],
            return_exceptions=True,
        )
        next_queue = []
        for package, result in zip(queue, results):
            if isinstance(result, Exception):
                print(f"Warning: failed to fetch '{package}', skipping: {result}")
                continue
            assert isinstance(result, dict)
            visited[package] = result
            sub_deps = resolve_dependency_versions(result.get("requires_dist", []))
            for sd in sub_deps:
                if sd not in visited and sd not in next_queue:
                    next_queue.append(sd)
        queue = next_queue
    return visited


def parse_manifest(
    filepath: Path, env: str | None = None
) -> tuple[str | None, dict[str, str]]:
    filepath = Path(filepath)
    pptml = filepath / "pyproject.toml"
    if pptml.exists():
        try:
            with pptml.open("rb") as f:
                data = tomllib.load(f)
            project = data.get("project") or {}
            rp = project.get("requires-python")
            packages = resolve_dependency_versions(project.get("dependencies", []))
            return rp, packages
        except Exception as e:
            print(f"Warning: failed to parse pyproject.toml: {e}")

    packages, detected_env = parse_environment(filepath, env)
    if packages:
        return None, packages

    return None, {}
