from typing import Dict, Generator
import networkx as nx

from .resolvers.pypi_resolver import resolve_dependency_versions


def build_dependency_graph(deps: Dict) -> tuple[nx.DiGraph, Generator | None]:
    graph = nx.DiGraph()

    for package, metadata in deps.items():
        graph.add_node(package)
        sub_deps = resolve_dependency_versions(metadata["requires_dist"])
        for dep in sub_deps:
            if dep in deps:
                graph.add_edge(dep, package)  # dep must exist before package
    try:
        cycle = nx.find_cycle(graph)
        print(f"Cycle detected, cannot resolve install order: {list(cycle)}")
        return graph, None
    except nx.NetworkXNoCycle:
        order = nx.topological_sort(graph)
    return graph, order
