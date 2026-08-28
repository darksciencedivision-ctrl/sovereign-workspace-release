# Release Gate Policy

Release verdicts bind to a clean archive of the exact release commit.
Run `git archive HEAD`, extract it to an empty temporary directory, and run the package boundary gate there.
Archive results are authoritative because ignored host state is absent by construction.
Live-tree scans are operational-hygiene checks and may report ignored caches or dependencies.
Keep `node_modules` for the offline desktop suite; it is ignored and never enters `git archive`.
Before packaging, remove test caches, bytecode, and test-created databases outside quarantined evidence lanes.
Record both archive and live-tree measurements; never substitute one for the other.
