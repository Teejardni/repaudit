import click
import matplotlib.pyplot as plt
import networkx as nx
from networkx.drawing.nx_pydot import to_pydot


def visualize_pydot(graph: nx.DiGraph, output_path: str = "graph.png"):
    """Default viz — clean hierarchical layout via graphviz/pydot"""
    dot = to_pydot(graph)
    
    # styling
    dot.set_graph_defaults(
        rankdir="BT",       
        bgcolor="#1a1a1a",
        pad="0.5"
    )
    dot.set_node_defaults(
        shape="box",
        style="filled",
        fillcolor="#2d2d2d",
        fontcolor="#ffffff",
        fontname="Courier",
        fontsize="10",
        color="#444444"
    )
    dot.set_edge_defaults(
        color="#555555",
        arrowsize="0.7"
    )

    dot.write_png(output_path)
    click.echo(f"Graph written to {output_path}")

    import subprocess
    import sys
    if sys.platform == "linux":
        subprocess.run(["xdg-open", output_path])
    elif sys.platform == "darwin":
        subprocess.run(["open", output_path])
    elif sys.platform == "win32":
        subprocess.run(["start", output_path], shell=True)


def visualize_matplotlib(graph: nx.DiGraph):
    """Fancy viz — matplotlib, more control, interactive"""
    fig, ax = plt.subplots(figsize=(20, 12))
    fig.patch.set_facecolor("#1a1a1a")
    ax.set_facecolor("#1a1a1a")

    try:
        pos = nx.nx_agraph.graphviz_layout(graph, prog="dot")
    except Exception:
        # fallback if pygraphviz not installed
        pos = nx.spring_layout(graph, seed=42)

    roots = [n for n in graph.nodes if graph.in_degree(n) == 0]
    rest = [n for n in graph.nodes if graph.in_degree(n) != 0]

    nx.draw_networkx_nodes(graph, pos, nodelist=roots, node_color="#e05c5c",
                           node_size=300, ax=ax)
    nx.draw_networkx_nodes(graph, pos, nodelist=rest, node_color="#5c8de0",
                           node_size=200, ax=ax)
    nx.draw_networkx_edges(graph, pos, edge_color="#555555",
                           arrows=True, arrowsize=10,
                           connectionstyle="arc3,rad=0.1", ax=ax)
    nx.draw_networkx_labels(graph, pos, font_color="#ffffff",
                            font_size=6, font_family="monospace", ax=ax)

    ax.set_title("Dependency Graph", color="#ffffff", fontsize=14, pad=20)
    plt.tight_layout()
    plt.savefig("graph.png")
