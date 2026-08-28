"""Phase 14E assembled product-level validation harness (directive §9 table 14E).

The assembled run stands up one conductor + one frontier worker + one OpenCode/local coder
worker + one local reasoning worker over live shared MCP, then exercises succession, a bounded
debate, a gated coding task, and full restart+recovery. This package holds the harness; it
degrades HONESTLY (directive §10.4) to whatever subset proved live and records exactly which
legs were LIVE vs MOCK vs DETERMINISTIC-SUBSTITUTE — it never presents a substituted result as
a real-provider result.
"""
