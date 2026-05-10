"""Phase 7B: 5-layer edge-freshness system.

Modules:
    decay              — Layer 1: confidence decay over time (pure function)
    hash_diff          — Layer 2: business-summary hash change detector
    filing_trigger     — Layer 3: SEC EDGAR new-filing trigger
    correlation_drift  — Layer 4: peer correlation drift detector
    news_drift         — Layer 5: news-tag distribution drift detector
    orchestrator       — runs all 5 detectors and updates the edge_freshness queue
"""
