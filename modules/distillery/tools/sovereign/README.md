# Distillery tools

Two instruments for the two named blockers. Both are read-only inspection.
Neither downloads, trains, or modifies anything.

## D1 — Machine characterization

Converts the modelled hardware envelope into a measured profile. **Run this in the
Python environment you intend to train in** — the answer differs per environment.

```
cd "D:\Sovereign Distillery"
python tools\d1_characterize.py
python tools\d1_characterize.py --vram-probe     # close other GPU apps first
```

Writes `runs\hardware_profile.json`. Prints a verdict separating **blockers**
(the plan does not work as written) from **warnings** (proceed with care).

The check that matters most: whether `sm_120` appears in the installed PyTorch
build's arch list, and whether a `bitsandbytes` 4-bit forward pass actually
executes on the device. If either fails, the local QLoRA path is unavailable
regardless of VRAM, and that is a blocker rather than a tuning problem.

`--vram-probe` allocates fp16 blocks until failure to measure headroom after the
Windows compositor reserve. It is safe — allocations are freed on exit — but it
will briefly consume all free VRAM, so close other GPU applications first.

## D2 — Teacher registry

Enumerates the local model library and emits the ordered teacher queue.

```
python tools\d2_registry.py
python tools\d2_registry.py --extra-dir "D:\models" --extra-dir "E:\gguf"
python tools\d2_registry.py --no-gguf            # sizes only, skip header parsing
```

Scans Ollama manifests + blobs (honours `OLLAMA_MODELS`), the LM Studio model
tree, and any `--extra-dir`. Reads GGUF metadata headers directly for
architecture, parameter count, quantization, context length, and tokenizer.
Writes `registry\teachers.json` and `registry\teachers.md`, ordered ascending by
parameter count where known and by disk size otherwise.

If nothing is found, the tool falls back to printing `ollama list` output so the
queue can be reconstructed by hand.

### On the license fields

Every entry is emitted with `license_class: "UNKNOWN"`.

Where a GGUF header declares a license, it is recorded as `license_identifier`
and marked as **declared, still requiring verification**. The tool does not infer
a class from a family name, because family-level inference is exactly the
secondary-source reasoning the specification rejects — terms differ between
versions within one family.

Assigning `license_class` from primary license texts is a separate manual step,
and no teacher should reach `ELIGIBLE` before it is done.

## Verification status

The GGUF metadata parser was tested against a synthetic file exercising scalar,
string, and large-array value types, plus truncated and non-GGUF inputs. It
recovers architecture, parameter count, quantization, context length, tokenizer,
and license, skips large token arrays without retaining them, and degrades to a
size-only entry on any unreadable header rather than failing the scan.

**It has not been run against a real model file.** First real run is itself a test.
