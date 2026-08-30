# utc: 2026-08-30T03:42:00Z
# producer: grok-opencode LIVE-CENSUS-20260830
# host: DESKTOP-03PTABH

# sovereign.md

Launch argv (T-RW sovereign.json): `${root}/.venv/Scripts/python.exe -m sovereign_product.server --root ${root} --host 127.0.0.1 --port 5175 --workers 1`. Health url /v1/health required_keys status, product_version.

SPA: T-RW ui/ui_shell/src exists and dist exists. T-PW dist only.

db: both have runtime/sovereign.db; size/timestamp only; not queried.

Provenance: T-RW MATCH 150e518e… = SOVEREIGN_ENTERPRISE_PRODUCTION_20260813_142520.zip. T-PW CROSS_PRODUCT_HASH 620e8459… = Distillery enterprise zip. T-RW INSTALL-PROVENANCE documents the superseded defective record. Not silently rewritten.
