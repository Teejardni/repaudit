import asyncio
import json

# import sys
from pathlib import Path

import click
import httpx

from .audit import gather
from .dagger import build_dependency_graph
from .models import Manifest, RepositoryNode
from .parsers.manifest_parser import parse_repository
from .resolvers.pypi_resolver import parse_manifest
from .resolvers.pypi_resolver import resolve as resolve_packages
from .viz import visualize_matplotlib, visualize_pydot


def render_tree(node: RepositoryNode) -> list[str]:
    """Render a repository tree for the discovery checkpoint."""
    lines = [f"{node.path}/"]

    def render_children(current: RepositoryNode, prefix: str) -> None:
        entries = []

        for name, child in current.children.items():
            entries.append((name, "directory", child))

        for manifest in current.manifests:
            entries.append((manifest.filename, "manifest", manifest))

        entries.sort(key=lambda entry: (entry[0].lower(), entry[1]))

        for index, (name, kind, item) in enumerate(entries):
            is_last = index == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{name}")

            if kind == "manifest":
                lines.append(
                    f"{prefix}{'    ' if is_last else '│   '}"
                    f"[{item.ecosystem}: {item.manifest_type}]"
                )
            else:
                child_prefix = prefix + ("    " if is_last else "│   ")
                render_children(item, child_prefix)

    render_children(node, "")
    return lines

def render_parsed_tree(node):
    """Render parsed dependencies and manifest failures by directory."""
    lines = [f"{node.path}/"]

    for dependency in node.dependencies:
        version = (
            f" (constraint: {dependency.version_spec})"
            if dependency.version_spec
            else ""
        )
        if dependency.locked_version:
            version += f" (locked: {dependency.locked_version})"

        lines.append(
            f"  {dependency.name}{version}"
            f" [{dependency.file_style}]"
        )

    for failure in node.failures:
        lines.append(
            f"  PARSE FAILURE [{failure.category}] "
            f"{failure.source_file}: {failure.message}"
        )

    for child in node.children.values():
        lines.extend(render_parsed_tree(child))

    return lines
# async def _run_audit(path: Path):
#     async with httpx.AsyncClient() as client:
#         return await run_audit(path, client)


# @click.group(invoke_without_command=True)
# @click.argument("path", default=".", type=click.Path(exists=True))
# @click.pass_context
# def cli(ctx, path):
#     """Audit a repository's dependencies."""
#     if ctx.invoked_subcommand is None:
#         findings = asyncio.run(_run_audit(Path(path)))
#         has_errors = any(f.severity == "error" for f in findings)
#         for f in findings:
#             click.echo(str(f))
#         sys.exit(1 if has_errors else 0)


@click.group(invoke_without_command=True)
@click.argument(
    "path",
    default=".",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=Path, resolve_path=True
    ),
)
@click.pass_context
def cli(ctx, path: Path):
    """Discover ecosystems and audit a repository's dependencies."""
    if ctx.invoked_subcommand is None:
        try:
            repository = gather(path)
            parsed_repository = parse_repository(repository, path)
        except (OSError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc

        for line in render_parsed_tree(parsed_repository):
            click.echo(line)


@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option(
    "--fancy", "-f", is_flag=True, help="Matplotlib visualisation instead of pydot"
)
@click.option("--json", "as_json", is_flag=True, help="Dump raw output as JSON")
def resolve(path, fancy, as_json):
    """Resolve dependencies from a pyproject.toml or requirements.txt"""

    async def _run():
        async with httpx.AsyncClient() as client:
            _, packages = parse_manifest(Path(path))
            deps = await resolve_packages(client, packages)
            graph, order = build_dependency_graph(deps)
            return deps, graph, order

    deps, graph, order = asyncio.run(_run())
    if order is None:
        click.echo(click.style("Cycle detected, cannot visualize", fg="red"))
        return
    if as_json:
        click.echo(json.dumps(deps, indent=2, default=str))
        return
    if fancy:
        visualize_matplotlib(graph)
    else:
        visualize_pydot(graph)


@cli.command()
@click.argument("package")
@click.option("--json", "as_json", is_flag=True, help="Dump raw output as JSON")
def inspect(package, as_json):
    """Inspect a single package and its full dependency tree"""

    async def _run():
        async with httpx.AsyncClient() as client:
            deps = await resolve(client, {package: ""})
            graph, order = build_dependency_graph(deps)
            return deps, graph, order

    deps, graph, _ = asyncio.run(_run())
    if as_json:
        click.echo(json.dumps(deps, indent=2, default=str))
        return
    visualize_pydot(graph)


@cli.command()
@click.option("--clear", is_flag=True, help="Delete all cached entries")
@click.option(
    "--stats", "show_stats", is_flag=True, help="Show cache size and entry count"
)
def cache(clear, show_stats):
    """Manage the repaudit cache"""
    from . import cache as cache_module

    if clear:
        deleted = cache_module.clear()
        click.echo(click.style(f"Cleared {deleted} cached entries", fg="green"))
    elif show_stats:
        s = cache_module.stats()
        click.echo(f"Path:    {s['path']}")
        click.echo(f"Entries: {s['entries']}")
        click.echo(f"Size:    {s['size_bytes'] / 1024:.1f} KB")
    else:
        click.echo("Use --clear or --stats")


if __name__ == "__main__":
    cli()
