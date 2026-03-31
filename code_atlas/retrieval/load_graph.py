import networkx as nx
import pickle
import os

def load_graph(repo_id: str):
    path = f"/root/.code_atlas/graphs/{repo_id}.pkl"
    
    import pickle
    with open(path, "rb") as f:
        graph = pickle.load(f)
    
    return graph

# PURPOSE: Manages the persistence of the code relationship graph.
