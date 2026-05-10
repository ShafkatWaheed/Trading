"""Graph traversal + ranking for the knowledge-graph prototype.

Submodules:
    traverse — BFS expansion across stock_relations + stock_peers edges
    rank     — composite scoring (tier × industry × opp × hop_decay × confidence)
"""
