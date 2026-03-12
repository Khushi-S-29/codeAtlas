from __future__ import annotations

import pickle
from pathlib import Path
import networkx as nx

from code_atlas.core.config import GRAPHS_DIR


def graph_path(repo_id: str) -> Path:
    """
    Return path where graph for repo will be stored.
    """
    return GRAPHS_DIR / f"{repo_id}.pkl"


def save_graph(repo_id: str, graph: nx.DiGraph) -> Path:
    """
    Persist graph to disk using pickle.
    """
    path = graph_path(repo_id)

    with open(path, "wb") as f:
        pickle.dump(graph, f)

    return path


def load_graph(repo_id: str) -> nx.DiGraph | None:
    """
    Load graph from disk if it exists.
    """
    path = graph_path(repo_id)

    if not path.exists():
        return None

    with open(path, "rb") as f:
        graph = pickle.load(f)

    return graph