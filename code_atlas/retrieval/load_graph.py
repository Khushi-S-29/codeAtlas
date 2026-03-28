import networkx as nx
import pickle
import os

GRAPH_PATH = "/root/.code_atlas/graphs/graph.pkl"

def load_graph(path=GRAPH_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    
    graph = nx.DiGraph() 
    return graph

# PURPOSE: Manages the persistence of the code relationship graph.
