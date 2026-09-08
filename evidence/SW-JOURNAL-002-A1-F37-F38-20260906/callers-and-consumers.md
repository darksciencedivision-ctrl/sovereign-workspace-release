# utc: 2026-09-06T19:22:08.471153+00:00
# producer: Codex Step6 evidence
FACT[patches/apps__desktop__main.js.patch] Typed operator chat and classified voice chat share deliverConductorConversation, which retrieves the bounded roster/view before the existing deliverConductorChat writer.

FACT[patches/apps__desktop__main.js.patch] delegateToWorkerPane preserves delegation arguments and returned result; createAnswerTally records only returned observed answer counts scoped to the journal session.

FACT[patches/apps__desktop__control__conductor-view.js.patch] The roster is reserved inside characterBudget; full excerpts use remaining capacity, greetings and /no-workspace retain the roster, and unknown or insufficient budget withholds delivery.

FACT[patches/apps__desktop__renderer__renderer.js.patch] workspace_view metadata is consumed by the outgoing transcript row, collapsed summary, and always-visible context notice using textContent.

FACT[deployment-manifest.json] Preload, picker, policy, memory service, graph, delegation implementation and journal write/store/runtime files remain byte-identical to the captured preimages.
