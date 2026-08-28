# Debate Table

Debate Table is a local Windows app that seats two to four locally installed Ollama models around a live, watchable discussion table. Models address one another by name, answer directed questions, challenge claims, concede strong points, reframe issues, and extend the discussion. The public stage is designed for a 1920×1080 OBS Browser Source.

It is not a truth-scoring system, claim ledger, autonomous tool agent, audience-chat service, voice app, avatar system, account platform, or cloud service.

## Requirements

- Windows
- Python 3.10 or newer
- Ollama running locally
- Two or more installed chat-capable Ollama models
- Enough RAM and VRAM for the selected models

The default Ollama endpoint is `http://127.0.0.1:11434`. Set `OLLAMA_URL` to override it.

## Install and start

From this folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

On Linux or macOS, use `python3 -m venv .venv` and `.venv/bin/python` instead.

Open [http://127.0.0.1:8700](http://127.0.0.1:8700).

Stop the app with `Ctrl+C`.

`requirements.txt` declares what the app depends on without pinning versions. To
install the exact versions this release was validated against, use
`requirements.lock.txt` in its place. For a full cold-start on a machine that has
never seen this project — including model downloads and integrity verification —
follow [SNAPSHOT-RESTORE.md](SNAPSHOT-RESTORE.md).

## Seats and models

Edit `config.json` to define two, three, or four seats. Each seat has:

- `name`: the public participant name
- `model`: an installed Ollama model
- `color`: the seat accent color
- `persona`: private behavioral guidance for that participant

Press `C` to open the hidden operator drawer. Each seat has an accessible model dropdown populated from Ollama. A model change applies to that seat's next turn and is atomically saved to `config.json`, so it survives restart. If Ollama is unreachable, model controls are disabled and the debate loop fails turns safely until Ollama returns.

Larger models can have long cold-load delays and may use system RAM when they do not fit in VRAM. Prefer models that reliably reach public speech within the configured `num_predict` budget. Qualification on one machine does not establish performance on different hardware.

## Topics and conversation controls

The app generates a topic at startup and rotates topics after `topic_rotate_turns` completed turns. In the operator drawer:

- Set topic interrupts the active generation, clears the current transcript and move state, and starts the replacement topic.
- Interject queues a one-shot operator note for the next seat turn.
- Pause interrupts the active turn and prevents new turns until Resume.

The move selector uses only in-memory conversation state and makes no extra model calls. Directed questions take precedence, repeated phrasing forces a reframe or challenge, and a quiet consensus window increases the weight of scrutiny moves. The selected trigger reason appears only in drawer diagnostics.

## Optional heuristic insight panel

`insight_panel` is `false` by default. When enabled, one bounded background worker may ask `extractor_model` for an approximate stance, addressed seat, possible claims, and possible question after a public turn.

The drawer labels this output:

> Heuristic extraction — may be incomplete or incorrect.

Insights never appear on the public stage and never affect model prompts, move selection, routing, topics, or public claims. Generation always has priority; active extraction is canceled when a seat turn begins. Missing models, timeouts, cancellations, malformed output, and other failures render as an em dash. To disable all insight work and controls, keep:

```json
"insight_panel": false
```

## Reasoning handling and failed turns

Ollama models may emit hidden reasoning in `thinking` fields or tags such as `<think>`. The backend ignores separate thinking fields and incrementally strips hidden-reasoning regions before any public WebSocket fragment is sent. Raw reasoning is not included in the stage, transcript, or OBS output.

A reasoning-only or otherwise empty public response is retried once by default. If the retry is also empty, the turn is skipped and the next seat continues. Transport failures also become bounded skipped turns. The thinking indicator begins at `turn_start`, remains active during model loading and hidden reasoning, changes to a loading label after ten seconds without public speech, and clears on the first public fragment or an explicit skip.

## OBS Browser Source

Add a Browser Source in OBS with:

- URL: `http://127.0.0.1:8700`
- Width: `1920`
- Height: `1080`

The operator drawer is hidden by default. Do not press `C` in the captured browser unless you intend to expose operator controls temporarily.

## Configuration reference

Important keys include:

- `port`: local app port
- `topic_rotate_turns`: completed turns before automatic rotation; `0` disables
- `anchor_every_turns`: completed turns between continuity refreshes; `0` disables
- `turn_delay_ms`: intentional delay between turns
- `context_turns`: recent transcript turns included in prompts
- `num_predict`, `temperature`, `top_p`: Ollama generation options
- `empty_spoken_retry_count`: retries for reasoning-only or empty public output
- `repetition_overlap_threshold`, `repetition_min_tokens`: self-repetition detector
- `consensus_window_turns`, `consensus_challenge_weight`: scrutiny weighting
- `insight_panel`, `extractor_model`, `insight_timeout_seconds`, `insight_queue_max`: optional drawer insights

Missing keys receive safe defaults. Invalid values fall back to defaults. Configuration writes use UTF-8 and atomic replacement.

## Tests

Install pytest as a development-only tool, then run:

```powershell
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest -q -W error
```

The offline suite starts a deterministic local Ollama-compatible mock and uses temporary configs under `tests/`. It does not call real Ollama and verifies that production `config.json` is unchanged.

Live verification utilities are separate from pytest:

```powershell
C:\Python314\python.exe tests\live_qualify.py
C:\Python314\python.exe tests\live_soak.py --minutes 30 --models "qwen2.5:14b-instruct" "phi4:14b"
```

Both use isolated configs and write evidence under `audit/`.

## Known limitations

- Model quality and latency depend strongly on model family, quantization, prompt behavior, RAM, VRAM, and current Ollama residency.
- Reasoning-heavy models may spend the entire output budget before producing public speech and will be skipped after the configured retry.
- Heuristic insights can be incomplete, incorrect, canceled, or unavailable.
- A seat model can occasionally attribute a prior position incorrectly, especially on an opening turn after a topic reset.
- Windows `CTRL_BREAK_EVENT` shutdown can return a nonzero process code even when stderr is empty and cleanup is complete.
