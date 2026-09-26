"""The two ways a big workload is sharded (sharded inference P4 + P5).

Both modes drive ``shard_runner.ShardRunner``: every task is a fresh session that sees only its
instruction, the ledger and its own input. They differ in where tasks come from.

* ``InputShardMode`` (P4, map / reduce): a large INPUT (a long document, a codebase dump, a log) is
  split at natural boundaries into chunks sized from real token counts so each fits the window with
  the ledger and the reply. Each chunk is MAPPED in a fresh session; the results are then REDUCED in
  rounds of fresh sessions (as many results per reduce as fit) until one final answer remains. A
  chunk that failed is named in the reduce input, so the final answer states its coverage gap
  instead of silently omitting it.
* ``PlanStepMode`` (P5, agentic steps): a PLAN session turns the objective into a list of steps;
  each STEP runs in a fresh session against the running ledger; a bounded number of REVIEW sessions
  may add steps; a final SYNTHESIZE session writes the answer from the ledger and the step results.

Task ids are deterministic functions of the run's own results, so a mode replayed on resume
recreates exactly the same tasks (the runner ignores duplicates).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from .shard_runner import RunLimits, RunState, ShardRunner, ShardTask

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


# --- splitting ------------------------------------------------------------------------------------

def split_text(text: str, *, count_tokens: Callable[[str], int], max_tokens: int) -> list[str]:
    """Split ``text`` into chunks of at most ``max_tokens`` (by the model's own counter).

    Boundaries are tried from coarse to fine - blank lines, then lines, then sentences - and a
    piece still too big is cut by characters as a last resort. Every chunk returned is verified
    with ``count_tokens``; nothing is dropped and the chunks rejoin to the original text.
    """
    if max_tokens < 16:
        raise ValueError("max_tokens is too small to shard with")
    if not text:
        return []

    def pieces(block: str, level: int) -> list[str]:
        if count_tokens(block) <= max_tokens:
            return [block]
        if level == 0:
            parts = re.split(r"(?<=\n\n)", block)
        elif level == 1:
            parts = re.split(r"(?<=\n)", block)
        elif level == 2:
            parts = _SENTENCE_END.split(block)
            # keep the whitespace the split consumed so the chunks rejoin exactly
            rebuilt, cursor = [], 0
            for part in parts:
                index = block.index(part, cursor)
                if rebuilt:
                    rebuilt[-1] += block[cursor:index]
                rebuilt.append(part)
                cursor = index + len(part)
            if rebuilt:
                rebuilt[-1] += block[cursor:]
            parts = rebuilt
        else:
            size = max(1, len(block) * max_tokens // max(1, count_tokens(block)) - 1)
            return [block[i:i + size] for i in range(0, len(block), size)]
        parts = [p for p in parts if p]
        if len(parts) <= 1:
            return pieces(block, level + 1)
        out: list[str] = []
        for part in parts:
            out.extend(pieces(part, level + 1) if count_tokens(part) > max_tokens else [part])
        return out

    chunks: list[str] = []
    current = ""
    for piece in pieces(text, 0):
        candidate = current + piece
        if current and count_tokens(candidate) > max_tokens:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _content_budget(runner: ShardRunner, instruction: str, max_output: int) -> int:
    probe = ShardTask(task_id="probe", kind="probe", instruction=instruction,
                      max_output_tokens=max_output)
    # Reserve the ledger's whole budget: it can grow up to that before being condensed.
    fixed = (runner.model.count_tokens(runner.fixed_prompt(probe, runner.state.ledger
                                                           if runner.state else _empty()))
             + runner.limits.ledger_budget_tokens + 64)
    budget = runner.limits.content_budget(fixed, max_output)
    if budget < 256:
        raise ValueError("the window leaves no room for shard content; lower the ledger budget "
                         "or reply size, or use a larger context")
    return budget


def _empty():
    from .shard_runner import Ledger
    return Ledger()


# --- P4: input shards (map / reduce) --------------------------------------------------------------

# The parts are DISJOINT slices of one input. Live, maps answered as if each part were the whole
# input ("16, 26", "1516: 92, 25") and the reduce copied one part's count instead of adding them.
# So maps report labeled per-part values, and the reduce is told how values combine. (Asking maps
# to also list the items made a reasoning model enumerate hundreds of records into its reply cap.)
MAP_PART_RULES = (
    "The other parts of the input are handled separately; report for THIS PART ONLY, as short "
    "labeled values that can be combined later: give every count or total for this part with "
    "its label (e.g. 'items matching X in this part: 12') and this part's best/largest/smallest "
    "candidate with its value. Report the values, not the items behind them. Do not guess "
    "about other parts.")
MIN_SPLIT_TOKENS = 1024  # a cut-off map smaller than this is retried, not split further
REDUCE_RULES = (
    "Each partial result covers a DIFFERENT, non-overlapping part of the input. Combine them: "
    "ADD counts and totals across all parts; compare maxima, minima and rankings across parts "
    "and pick the overall one (report ties); merge lists without duplicates. Never give one "
    "part's value as the answer for the whole input.")

@dataclass(frozen=True)
class InputShardMode:
    objective: str
    map_instruction: str
    reduce_instruction: str
    max_output_tokens: int = 2048

    #: Map/reduce passes results through reduce inputs, not the ledger (see ShardRunner).
    summary_kinds: frozenset = frozenset()
    isolated_kinds = frozenset({"map"})

    def plan(self, runner: ShardRunner, text: str) -> list[ShardTask]:
        budget = _content_budget(runner, self._map_text(), self.max_output_tokens)
        chunks = split_text(text, count_tokens=runner.model.count_tokens, max_tokens=budget)
        width = max(4, len(str(len(chunks))))
        return [ShardTask(task_id=f"map-{i + 1:0{width}d}", kind="map",
                          instruction=self._map_text(i + 1, len(chunks)), content=chunk,
                          max_output_tokens=self.max_output_tokens)
                for i, chunk in enumerate(chunks)]

    def split_task(self, runner: ShardRunner, task: ShardTask) -> list[ShardTask] | None:
        """A map whose reply was cut off becomes two (or more) smaller maps over the same input.

        Live, a reasoning model counting ~20k tokens of dense records ran out of its reply budget
        on 5 of 9 calls and lost a part after three identical retries. Half the input needs about
        half the reasoning. Only maps split, and not below MIN_SPLIT_TOKENS (then: retry).
        """
        if task.kind != "map" or not task.content:
            return None
        size = runner.model.count_tokens(task.content)
        if size < MIN_SPLIT_TOKENS:
            return None
        halves = split_text(task.content, count_tokens=runner.model.count_tokens,
                            max_tokens=max(16, -(-size // 2)))
        if len(halves) < 2:
            return None
        letters = "abcdefghijklmnopqrstuvwxyz"
        if len(halves) > len(letters):
            return None
        return [ShardTask(task_id=f"{task.task_id}{letters[i]}", kind="map",
                          instruction=(f"{task.instruction}\n(Slice {i + 1} of {len(halves)} of "
                                       f"{task.task_id}: that part was split because a reply ran "
                                       "out of room. Report for this slice only.)"),
                          content=piece, max_output_tokens=task.max_output_tokens)
                for i, piece in enumerate(halves)]

    def _map_text(self, index: int = 0, total: int = 0) -> str:
        where = f" This is part {index} of {total} of the input." if total else ""
        return f"Objective: {self.objective}\n{self.map_instruction}{where}\n{MAP_PART_RULES}"

    def _reduce_text(self, round_no: int, index: int, total: int, final: bool) -> str:
        role = ("Produce the FINAL answer to the objective for the WHOLE input: first list the "
                "per-part values you combined, then the answer."
                if final else f"Merge these partial results (reduce round {round_no}, group "
                              f"{index} of {total}) into ONE partial result for the parts they "
                              "cover, keeping the same labeled values (combined, not final "
                              "prose).")
        return (f"Objective: {self.objective}\n{self.reduce_instruction}\n{REDUCE_RULES}\n"
                f"{role} Name any part marked FAILED as a gap in coverage.")

    def on_task_done(self, runner: ShardRunner, state: RunState, task: ShardTask) -> None:
        """When every task of the latest round is done, add the next reduce round (or stop)."""
        rounds: dict[int, list[ShardTask]] = {}
        for t in state.tasks:
            rounds.setdefault(0 if t.kind == "map" else int(t.task_id.split("-")[1][1:]),
                              []).append(t)
        latest = max(rounds)
        members = rounds[latest]
        if any(t.task_id not in state.completed and t.task_id not in state.failed
               for t in members):
            return
        if len(members) == 1 and latest > 0:
            return  # the final reduce is done
        if len(members) == 1 and latest == 0 and members[0].task_id in state.completed:
            return  # a single chunk: its map result is the answer
        entries = []
        for t in members:
            if t.task_id in state.completed:
                entries.append(f"RESULT of {t.task_id}:\n{runner.output_of(state, t.task_id)}")
            else:
                entries.append(f"RESULT of {t.task_id}: FAILED ({state.failed[t.task_id][:200]})")
        budget = _content_budget(runner, self._reduce_text(latest + 1, 1, 1, False),
                                 self.max_output_tokens)
        groups: list[list[str]] = [[]]
        for entry in entries:
            trial = "\n\n".join(groups[-1] + [entry])
            if groups[-1] and runner.model.count_tokens(trial) > budget:
                groups.append([entry])
            else:
                groups[-1].append(entry)
        final = len(groups) == 1
        round_no = latest + 1
        width = max(4, len(str(len(groups))))
        runner.add_tasks(
            ShardTask(task_id=f"reduce-r{round_no}-{i + 1:0{width}d}", kind="reduce",
                      instruction=self._reduce_text(round_no, i + 1, len(groups), final),
                      content="\n\n".join(group), max_output_tokens=self.max_output_tokens)
            for i, group in enumerate(groups))

    def final_output(self, runner: ShardRunner, state: RunState) -> str | None:
        reduces = [t for t in state.tasks if t.kind == "reduce"]
        if reduces:
            last_round = max(int(t.task_id.split("-")[1][1:]) for t in reduces)
            members = [t for t in reduces if int(t.task_id.split("-")[1][1:]) == last_round]
        else:
            members = [t for t in state.tasks if t.kind == "map"]
        if len(members) == 1 and members[0].task_id in state.completed:
            return runner.output_of(state, members[0].task_id)
        return None


# --- P5: plan steps (agentic) ---------------------------------------------------------------------

def _parse_steps(result: str) -> list[str]:
    start, end = result.find("["), result.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("the plan must be a JSON list of step strings")
    steps = json.loads(result[start:end + 1])
    if (not isinstance(steps, list) or not all(isinstance(s, str) and s.strip() for s in steps)):
        raise ValueError("the plan must be a JSON list of non-empty step strings")
    return [s.strip() for s in steps]


def _validate_plan(result: str) -> None:
    if not _parse_steps(result):
        raise ValueError("the plan has no steps")


def _validate_review(result: str) -> None:
    _parse_steps(result)  # an empty list (no more steps) is valid for a review


@dataclass(frozen=True)
class PlanStepMode:
    objective: str
    context: str = ""               # shared brief every step sees as its input
    max_steps: int = 24
    review_rounds: int = 1
    max_output_tokens: int = 2048

    validators = {"plan": _validate_plan, "review": _validate_review}
    #: Steps must know what earlier steps did, so their results are summarized in the ledger.
    summary_kinds = frozenset({"plan", "step", "review"})

    def plan(self, runner: ShardRunner) -> list[ShardTask]:
        return [ShardTask(
            task_id="plan", kind="plan",
            instruction=(f"Objective: {self.objective}\nBreak the objective into at most "
                         f"{self.max_steps} concrete steps, each doable in one focused session "
                         'with only the ledger for memory. "result" must be a JSON list of step '
                         'strings, e.g. ["...", "..."].'),
            content=self.context, max_output_tokens=self.max_output_tokens)]

    def _step_tasks(self, steps: list[str], prefix: str, first_number: int) -> list[ShardTask]:
        """Step ids are derived from WHO added them (the plan, or review N), never from a running
        count, so a mode replayed on resume recreates identical ids."""
        return [ShardTask(task_id=f"step-{prefix}{i + 1:03d}", kind="step",
                          instruction=(f"Objective: {self.objective}\nDo step "
                                       f"{first_number + i}: {step}\nRecord what later steps "
                                       "need in the ledger."),
                          content=self.context, max_output_tokens=self.max_output_tokens)
                for i, step in enumerate(steps)]

    def _synthesize(self) -> ShardTask:
        return ShardTask(
            task_id="synthesize", kind="synthesize",
            instruction=(f"Objective: {self.objective}\nWrite the final answer from the ledger. "
                         "State plainly anything a failed step left undone."),
            content=self.context, max_output_tokens=self.max_output_tokens)

    def on_task_done(self, runner: ShardRunner, state: RunState, task: ShardTask) -> None:
        steps = [t for t in state.tasks if t.kind == "step"]
        if task.kind == "plan":
            if task.task_id in state.completed:
                planned = _parse_steps(runner.output_of(state, "plan"))[: self.max_steps]
                runner.add_tasks(self._step_tasks(planned, "", 1))
            return  # a failed plan leaves nothing to do; the run ends failed
        pending = [t for t in state.tasks if t.task_id not in state.completed
                   and t.task_id not in state.failed]
        if pending or any(t.kind == "synthesize" for t in state.tasks):
            return
        if task.kind == "review" and task.task_id in state.completed:
            extra = _parse_steps(runner.output_of(state, task.task_id))
            room = self.max_steps - len(steps)
            if extra and room > 0:
                number = task.task_id.split("-")[1]
                runner.add_tasks(self._step_tasks(extra[:room], f"r{number}-", len(steps) + 1))
                return
            runner.add_tasks([self._synthesize()])  # the review says the objective is met
            return
        reviews = [t for t in state.tasks if t.kind == "review"]
        if len(reviews) < self.review_rounds and len(steps) < self.max_steps:
            runner.add_tasks([ShardTask(
                task_id=f"review-{len(reviews) + 1:02d}", kind="review",
                instruction=(f"Objective: {self.objective}\nReview the ledger. If the objective "
                             'is not yet met, "result" is a JSON list of the additional steps '
                             'still needed; if it is met, "result" is [].'),
                content=self.context, max_output_tokens=self.max_output_tokens)])
            return
        runner.add_tasks([self._synthesize()])

    def final_output(self, runner: ShardRunner, state: RunState) -> str | None:
        if "synthesize" in state.completed:
            return runner.output_of(state, "synthesize")
        return None
