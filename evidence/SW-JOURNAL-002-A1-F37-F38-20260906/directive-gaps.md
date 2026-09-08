# utc: 2026-09-06T19:23:17.197387+00:00
# producer: Codex Step6 finding notes
FACT[operator-declaration.md] The operator narrowed this build to F-37 and F-38; F-39 is deferred to its own directive and A3 is not implemented or claimed here.

INTERPRETATION: A3 confused the execution-selection vocabulary with governed adapter support; the earlier required_change_outside_A4 stop remains valid. The prepared amendment has not been edited.

RECOMMENDATION: Carry the standing host-quiescence rule into the next amendment explicitly: before every future build, the host must be quiescent; after every acceptance run the operator closes both the application and the shell. Independently verify ports 5175, 8700 and 5180 and worktree module processes before editing. A non-quiescent host requires HOST_NOT_QUIESCENT and no source edits.

INTERPRETATION: Closing the host avoids a running process reading a partially written source file; this is a substantive precondition, not a ceremonial check.
