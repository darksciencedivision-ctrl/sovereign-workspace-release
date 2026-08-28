#!/usr/bin/env python3
"""
Sovereign Distillery — Phase D2: Teacher Registry  (v2)

Enumerates the local model library (Ollama + LM Studio + loose GGUF trees),
reads GGUF metadata headers for architecture / parameter count / quantization,
and emits an ordered teacher queue, smallest to largest.

Reads only. Writes only its own outputs.

Usage:
    python d2_registry.py
    python d2_registry.py --extra-dir "D:\\models" --extra-dir "E:\\gguf"
    python d2_registry.py --no-gguf          # sizes only, skip header parsing

Writes: registry/teachers.json  and  registry/teachers.md

v2 fixes (defects found by running v1 on the real library):
  TD-1  ordering was wrong -> size_label parsing + size-derived fallback + consistency gate
  TD-2  embedding models classified as teachers -> role classification
  TD-3  non-model artifact counted as a model -> ARTIFACT role
  TD-4  dedup by path -> dedup by blob content hash; base_family / derived_from added
  TD-5  incomplete file_type map -> extended
  TD-6  MoE / bad labels -> label rejected when it disagrees with file size by >50%

LICENSE FIELDS ARE LEFT AS "UNKNOWN" BY DESIGN.
Per the accepted specification, license class must be assigned from the primary
license text of each model, not inferred from its family name. This tool does
not guess. It produces the queue; the license audit is a separate manual step.
"""
import argparse, json, os, re, struct, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- GGUF reader

GGUF_MAGIC = b"GGUF"
# value type ids -> (struct fmt, byte width); STRING=8 and ARRAY=9 handled separately
_SCALAR = {0:("<B",1), 1:("<b",1), 2:("<H",2), 3:("<h",2), 4:("<I",4), 5:("<i",4),
           6:("<f",4), 7:("<?",1), 10:("<Q",8), 11:("<q",8), 12:("<d",8)}

# Metadata keys worth keeping. Everything else (notably the 150k-entry token
# array) is walked past without being retained.
_WANTED_SUFFIXES = (
    "general.architecture", "general.name", "general.basename",
    "general.size_label", "general.file_type", "general.quantization_version",
    "general.parameter_count", "general.license", "general.license.name",
    "general.license.link", "general.finetune", "general.organization",
    "tokenizer.ggml.model", "tokenizer.ggml.pre",
)
_WANTED_PATTERNS = (".context_length", ".embedding_length", ".block_count",
                    ".attention.head_count", ".vocab_size", ".expert_count")

# file_type enum -> human label (llama.cpp ggml_ftype)
FTYPE = {0:"F32",1:"F16",2:"Q4_0",3:"Q4_1",7:"Q8_0",8:"Q5_0",9:"Q5_1",10:"Q2_K",
         11:"Q3_K_S",12:"Q3_K_M",13:"Q3_K_L",14:"Q4_K_S",15:"Q4_K_M",16:"Q5_K_S",
         17:"Q5_K_M",18:"Q6_K",19:"IQ2_XXS",20:"IQ2_XS",21:"Q2_K_S",22:"IQ3_XS",
         23:"IQ3_XXS",24:"IQ1_S",25:"IQ4_NL",26:"IQ3_S",27:"IQ3_M",28:"IQ2_S",
         29:"IQ2_M",30:"IQ4_XS",31:"IQ1_M",32:"BF16",33:"MXFP4",36:"TQ1_0",37:"TQ2_0"}

# Effective bits-per-weight, calibrated against library entries where both the
# declared parameter count and the file size are known. Agreement within ~5%.
BPW = {"F32":32.0,"F16":16.0,"BF16":16.0,"Q8_0":8.6,"Q6_K":6.6,"Q5_K_M":5.7,
       "Q5_K_S":5.5,"Q4_K_M":4.95,"Q4_K_S":4.8,"Q4_0":4.64,"Q4_1":5.0,
       "Q3_K_M":3.9,"Q2_K":3.0,"IQ2_M":3.30,"IQ2_S":2.9,"IQ4_XS":4.3,
       "MXFP4":4.30,"ftype_4":4.30}

EMBEDDING_HINTS = ("embed", "bge-", "gte-", "e5-", "nomic-embed", "mxbai")

def parse_size_label(lbl):
    """'8B' -> 8e9 ; '567M' -> 567e6 ; '256x2.2B' -> (total, active, True)."""
    if not lbl or not isinstance(lbl, str):
        return None, None, False
    lbl = lbl.strip()
    m = re.fullmatch(r"(\d+)x([\d.]+)\s*[Bb]", lbl)
    if m:
        n, per = int(m.group(1)), float(m.group(2))
        return int(n*per*1e9), int(per*1e9), True
    m = re.fullmatch(r"([\d.]+)\s*([BbMm])", lbl)
    if m:
        v = float(m.group(1)) * (1e9 if m.group(2).lower()=="b" else 1e6)
        return int(v), int(v), False
    return None, None, False

def size_derived_params(disk_bytes, quant):
    bpw = BPW.get(quant, 4.95)
    return int(disk_bytes * 8 / bpw) if disk_bytes and bpw else None

def sha256_file(path, chunk=1<<22, limit=None):
    """Hash for dedup. `limit` hashes only the first N bytes (fast mode)."""
    import hashlib
    h = hashlib.sha256(); read = 0
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b: break
                h.update(b); read += len(b)
                if limit and read >= limit: break
        return "sha256:" + h.hexdigest()
    except Exception:
        return None


class _R:
    """Minimal buffered reader over a GGUF file."""
    def __init__(self, fh): self.fh = fh
    def raw(self, n):
        b = self.fh.read(n)
        if len(b) != n:
            raise EOFError("truncated GGUF")
        return b
    def u32(self): return struct.unpack("<I", self.raw(4))[0]
    def u64(self): return struct.unpack("<Q", self.raw(8))[0]
    def string(self):
        n = self.u64()
        if n > 1 << 24:
            raise ValueError("implausible string length")
        return self.raw(n).decode("utf-8", errors="replace")
    def skip(self, n): self.fh.seek(n, os.SEEK_CUR)

    def value(self, vtype, keep=True):
        if vtype in _SCALAR:
            fmt, w = _SCALAR[vtype]
            b = self.raw(w)
            return struct.unpack(fmt, b)[0] if keep else None
        if vtype == 8:
            if keep:
                return self.string()
            n = self.u64(); self.skip(n); return None
        if vtype == 9:
            et = self.u32(); cnt = self.u64()
            if et in _SCALAR:
                w = _SCALAR[et][1]
                if not keep or cnt > 4096:
                    self.skip(w * cnt)
                    return f"<array {cnt} items>" if keep else None
                return [self.value(et) for _ in range(cnt)]
            if et == 8:
                out = []
                for _ in range(cnt):
                    n = self.u64()
                    if keep and len(out) < 32:
                        out.append(self.raw(n).decode("utf-8", errors="replace"))
                    else:
                        self.skip(n)
                if not keep:
                    return None
                return out if cnt <= 32 else f"<array {cnt} strings>"
            # nested arrays: not used by any real model file; bail loudly
            raise ValueError(f"unsupported nested array element type {et}")
        raise ValueError(f"unknown GGUF value type {vtype}")


def read_gguf_metadata(path, max_kv=2048):
    """Return a dict of selected GGUF metadata, or {'gguf_error': ...}."""
    try:
        with open(path, "rb") as fh:
            r = _R(fh)
            if r.raw(4) != GGUF_MAGIC:
                return {"gguf_error": "not a GGUF file"}
            ver = r.u32()
            if ver not in (1, 2, 3):
                return {"gguf_error": f"unsupported GGUF version {ver}"}
            tensor_count = r.u64()
            kv_count = r.u64()
            if kv_count > max_kv:
                return {"gguf_error": f"implausible kv_count {kv_count}"}
            md = {"gguf_version": ver, "tensor_count": tensor_count}
            for _ in range(kv_count):
                key = r.string()
                vtype = r.u32()
                keep = key.endswith(_WANTED_SUFFIXES) or any(p in key for p in _WANTED_PATTERNS)
                val = r.value(vtype, keep=keep)
                if keep:
                    md[key] = val
            ft = md.get("general.file_type")
            if isinstance(ft, int):
                md["quantization"] = FTYPE.get(ft, f"ftype_{ft}")
            return md
    except Exception as e:
        return {"gguf_error": f"{type(e).__name__}: {e}"}


def human_params(n):
    if not isinstance(n, int) or n <= 0:
        return None
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if n >= div:
            return f"{n/div:.1f}{suf}".replace(".0", "")
    return str(n)


# ------------------------------------------------------------------ discovery

def ollama_root():
    env = os.environ.get("OLLAMA_MODELS")
    if env and Path(env).exists():
        return Path(env)
    for c in (Path.home()/".ollama"/"models",
              Path("C:/Users")/os.environ.get("USERNAME","")/".ollama"/"models",
              Path("/usr/share/ollama/.ollama/models")):
        if c.exists():
            return c
    return None


def scan_ollama(errors):
    root = ollama_root()
    if not root:
        errors.append("ollama: models directory not found")
        return []
    manifests = root / "manifests"
    blobs = root / "blobs"
    if not manifests.exists():
        errors.append(f"ollama: no manifests dir under {root}")
        return []
    found = []
    for mf in manifests.rglob("*"):
        if not mf.is_file():
            continue
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        layers = data.get("layers") or []
        if not layers:
            continue
        rel = mf.relative_to(manifests).as_posix().split("/")
        tag = rel[-1]
        name = rel[-2] if len(rel) >= 2 else mf.stem
        model_layer = max(
            (l for l in layers if "model" in (l.get("mediaType") or "")),
            key=lambda l: l.get("size", 0), default=None)
        if model_layer is None:
            model_layer = max(layers, key=lambda l: l.get("size", 0))
        digest = (model_layer.get("digest") or "").replace(":", "-")
        blob = blobs / digest
        lic = None
        for l in layers:
            if "license" in (l.get("mediaType") or ""):
                lp = blobs / (l.get("digest","").replace(":", "-"))
                if lp.exists():
                    try:
                        lic = lp.read_text(encoding="utf-8", errors="replace")[:400].strip()
                    except Exception:
                        pass
        found.append({
            "source_runtime": "ollama",
            "display_name": f"{name}:{tag}",
            "manifest_path": str(mf),
            "blob_path": str(blob) if blob.exists() else None,
            "disk_size_bytes": model_layer.get("size", 0),
            "license_blob_excerpt": lic,
        })
    return found


def scan_lmstudio(errors):
    roots = [Path.home()/".lmstudio"/"models",
             Path.home()/".cache"/"lm-studio"/"models"]
    root = next((r for r in roots if r.exists()), None)
    if not root:
        errors.append("lmstudio: models directory not found")
        return []
    return scan_gguf_tree(root, "lmstudio")


def scan_gguf_tree(root, runtime):
    out = []
    root = Path(root)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".gguf", ".safetensors", ".bin"):
            try:
                sz = p.stat().st_size
            except Exception:
                continue
            if sz < 10 * 1024 * 1024:      # skip tokenizers, configs, shards of noise
                continue
            out.append({
                "source_runtime": runtime,
                "display_name": p.relative_to(root).as_posix(),
                "blob_path": str(p),
                "disk_size_bytes": sz,
            })
    return out


def ollama_list_fallback(errors):
    try:
        p = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=25)
        if p.returncode == 0:
            return p.stdout.strip()
    except Exception as e:
        errors.append(f"ollama list: {type(e).__name__}: {e}")
    return None


# -------------------------------------------------------------------- assembly

def classify_role(name, params, quant, gib, all_names):
    n = name.lower()
    if any(h in n for h in EMBEDDING_HINTS):
        return "INFRASTRUCTURE", ("Embedding model. Cannot generate instruction data; "
                                  "use for dedup / diversity scoring / retrieval validation.")
    if quant in ("F32","F16","BF16") and params and params < 1.5e9:
        stem = name.split(":")[0].split("/")[-1].lower()
        if sum(1 for o in all_names if stem in o.lower()) > 1:
            return "ARTIFACT", ("Small full-precision file sharing a name with a larger "
                                "model — probable projector / adapter / shard.")
    return "TEACHER", ""


def tier_for(gib, usable_vram_gib, corpus_tokens):
    """Estimated generation feasibility. ESTIMATE — replace with measured tok/s."""
    frac = min(1.0, (usable_vram_gib*0.90)/gib) if gib else 1.0
    tps  = 55.0 if gib <= usable_vram_gib*0.90 else max(0.55, 55.0*(frac**2.1) + 1.2*frac)
    days = corpus_tokens/tps/86400
    if   days <= 4:  t = "T1-VIABLE"
    elif days <= 21: t = "T2-COSTLY"
    elif days <= 90: t = "T3-DEFERRED"
    else:            t = "T4-INFEASIBLE"
    return t, round(tps,1), round(days,1)


def build(entries, parse_gguf=True, usable_vram_gib=5.26, corpus_tokens=8_000_000,
          hash_limit=64*1024*1024):
    recs = []
    all_names = [e["display_name"] for e in entries]
    for e in entries:
        disk = e.get("disk_size_bytes", 0)
        rec = {
            "model_id": None, "display_name": e["display_name"],
            "source_runtime": e["source_runtime"],
            "path": e.get("blob_path") or e.get("manifest_path"),
            "content_hash": None,
            "disk_size_bytes": disk, "disk_size_gib": round(disk/1024**3, 3),
            "role": "TEACHER", "role_rationale": "",
            "architecture": None,
            "parameter_count": None, "parameter_basis": None,
            "label_consistent": None, "is_moe": False, "active_parameter_count": None,
            "quantization": None, "context_length": None, "tokenizer": None,
            "base_family": None, "derived_from": None, "generation_depth": None,
            "license_identifier": "UNKNOWN", "license_source": "UNKNOWN",
            "license_class": "UNKNOWN",
            "license_note": "Assign from primary license text. Never inferred.",
            "tier": None, "estimated_tok_per_sec": None, "estimated_gen_days": None,
            "measured_tok_per_sec": None,
            "disposition": "PENDING", "disposition_history": [],
            "queue_position": None,
        }
        if e.get("license_blob_excerpt"):
            rec["license_blob_excerpt"] = e["license_blob_excerpt"]

        bp = e.get("blob_path")
        declared = label_total = label_active = None
        if parse_gguf and bp and Path(bp).exists():
            md = read_gguf_metadata(bp)
            if "gguf_error" in md:
                rec["gguf_error"] = md["gguf_error"]
            else:
                rec["architecture"] = md.get("general.architecture")
                rec["quantization"] = md.get("quantization")
                rec["tokenizer"] = md.get("tokenizer.ggml.model")
                for k, v in md.items():
                    if k.endswith(".context_length"):
                        rec["context_length"] = v; break
                pc = md.get("general.parameter_count")
                declared = pc if isinstance(pc, int) and pc > 0 else None
                label_total, label_active, moe = parse_size_label(md.get("general.size_label"))
                rec["is_moe"] = moe
                rec["active_parameter_count"] = label_active if moe else None
                for k in ("general.license", "general.license.name"):
                    if md.get(k):
                        rec["license_identifier"] = md[k]
                        rec["license_source"] = "gguf_declared"
                        rec["license_note"] = ("Declared in GGUF metadata. STILL REQUIRES "
                                               "verification against primary license text.")
                        break
                rec["gguf_metadata"] = {k: v for k, v in md.items()
                                        if k.startswith("general.") or k.startswith("tokenizer.")}
            rec["content_hash"] = sha256_file(bp, limit=hash_limit)

        q = rec["quantization"] or "Q4_K_M"
        derived = size_derived_params(disk, q)
        stated = declared or label_total
        if stated and derived:
            ratio = abs(stated - derived) / derived
            rec["label_consistent"] = ratio < 0.5           # TD-6
            if rec["label_consistent"]:
                rec["parameter_count"] = stated
                rec["parameter_basis"] = "declared" if declared else "label_parsed"
            else:
                rec["parameter_count"] = derived
                rec["parameter_basis"] = "size_derived (stated value rejected)"
        elif stated:
            rec["parameter_count"] = stated
            rec["parameter_basis"] = "declared" if declared else "label_parsed"
        else:
            rec["parameter_count"] = derived
            rec["parameter_basis"] = "size_derived"

        role, why = classify_role(rec["display_name"], rec["parameter_count"],
                                  q, rec["disk_size_gib"], all_names)
        rec["role"], rec["role_rationale"] = role, why
        if role == "TEACHER" and rec["disk_size_gib"]:
            t, tps, days = tier_for(rec["disk_size_gib"], usable_vram_gib, corpus_tokens)
            rec["tier"], rec["estimated_tok_per_sec"], rec["estimated_gen_days"] = t, tps, days
        recs.append(rec)

    # TD-4: dedup by content hash, not path
    by_hash, alias = {}, {}
    for r in recs:
        h = r["content_hash"]
        if not h:
            continue
        if h in by_hash:
            alias.setdefault(by_hash[h]["display_name"], []).append(r["display_name"])
            r["disposition"] = "SUPERSEDED"
            r["derived_from"] = by_hash[h]["display_name"]
            r["role_rationale"] = "Identical blob to " + by_hash[h]["display_name"]
        else:
            by_hash[h] = r
    for canon, names in alias.items():
        for r in recs:
            if r["display_name"] == canon:
                r["aliases"] = names

    teachers = [r for r in recs
                if r["role"] == "TEACHER" and r["disposition"] != "SUPERSEDED"]
    teachers.sort(key=lambda r: (r["parameter_count"] or 0, r["disk_size_bytes"]))
    for i, r in enumerate(teachers, 1):
        r["queue_position"] = i
        r["model_id"] = "T%03d" % i
    other = [r for r in recs if r not in teachers]
    for j, r in enumerate(other, 1):
        r["model_id"] = r["model_id"] or ("X%03d" % j)
    return teachers + other

def to_markdown(recs, profile_note):
    L = ["# Teacher Registry — generated", "",
         f"Generated {datetime.now(timezone.utc).isoformat()}", "",
         profile_note, "",
         "Ordering is ascending by parameter count where known, disk size otherwise.",
         "**All license classes are UNKNOWN pending primary-text audit.**", "",
         "| # | ID | Model | Params | Basis | Quant | Arch | GiB | ~tok/s | ~days | Tier |",
         "|---|---|---|---:|---|---|---|---:|---:|---:|---|"]
    for r in recs:
        if r["role"] != "TEACHER" or r["disposition"] == "SUPERSEDED":
            continue
        pc = r.get("parameter_count") or 0
        L.append("| {o} | {id} | `{n}` | {p:.0f}B | {b} | {q} | {a} | {s} | {t} | {d} | {ti} |".format(
            o=r["queue_position"], id=r["model_id"], n=r["display_name"],
            p=pc/1e9, b=(r.get("parameter_basis") or "?").split()[0],
            q=r.get("quantization") or "?", a=r.get("architecture") or "?",
            s=r["disk_size_gib"], t=r.get("estimated_tok_per_sec") or "?",
            d=r.get("estimated_gen_days") or "?", ti=r.get("tier") or "?"))
    L += ["", "## Non-teachers and superseded entries", "",
          "| ID | Model | Role | Disposition | Why |", "|---|---|---|---|---|"]
    for r in recs:
        if r["role"] != "TEACHER" or r["disposition"] == "SUPERSEDED":
            L.append("| {i} | `{n}` | {ro} | {d} | {w} |".format(
                i=r["model_id"], n=r["display_name"], ro=r["role"],
                d=r["disposition"], w=r.get("role_rationale","")))
    L += ["", "## Next step", "",
          "Assign `license_class` per model from its **primary license text**:",
          "`PERMISSIVE` · `ATTRIBUTION_REQUIRED` · `RESTRICTED_NAMING` · "
          "`RESTRICTED_USE` · `INTERNAL_ONLY` · `UNKNOWN` · `REJECTED`", "",
          "Until then every entry stays `UNKNOWN` and no teacher is `ELIGIBLE`."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra-dir", action="append", default=[],
                    help="Additional directory to scan for model files. Repeatable.")
    ap.add_argument("--no-gguf", action="store_true", help="Skip GGUF header parsing.")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--usable-vram", type=float, default=5.26,
                    help="Measured free VRAM in GiB. Default is the D1 measurement.")
    ap.add_argument("--corpus-tokens", type=int, default=8_000_000,
                    help="Corpus token budget per teacher, used for tier estimates.")
    a = ap.parse_args()

    errors, entries = [], []
    entries += scan_ollama(errors)
    entries += scan_lmstudio(errors)
    for d in a.extra_dir:
        if Path(d).exists():
            entries += scan_gguf_tree(d, "extra")
        else:
            errors.append(f"extra-dir not found: {d}")

    # De-duplicate by resolved path
    seen, uniq = set(), []
    for e in entries:
        k = e.get("blob_path") or e.get("manifest_path")
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        uniq.append(e)

    recs = build(uniq, parse_gguf=not a.no_gguf,
                 usable_vram_gib=a.usable_vram, corpus_tokens=a.corpus_tokens)

    out_dir = Path(a.out_dir) if a.out_dir else \
        Path(__file__).resolve().parent.parent / "registry"
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "sovereign-distillery/teacher_registry/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "teacher_count": len(recs),
        "scan_errors": errors,
        "license_audit_status": "NOT STARTED — all classes UNKNOWN",
        "teachers": recs,
    }
    (out_dir / "teachers.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    note = (f"{len(recs)} models discovered. "
            + ("Scan errors: " + "; ".join(errors) if errors else "No scan errors."))
    (out_dir / "teachers.md").write_text(to_markdown(recs, note), encoding="utf-8")

    print("=" * 74)
    print("SOVEREIGN DISTILLERY — D2 TEACHER REGISTRY")
    print("=" * 74)
    if not recs:
        print("  No models found.")
        for e in errors:
            print(f"  [scan-error] {e}")
        raw = ollama_list_fallback(errors)
        if raw:
            print("\n  `ollama list` output:\n")
            print("   " + raw.replace("\n", "\n   "))
    else:
        print(f"  {'#':>3}  {'ID':<5} {'MODEL':<38} {'PARAMS':>8} {'QUANT':>8} {'GiB':>7} {'~d':>5}  TIER")
        print("  " + "-" * 88)
        for r in recs:
            if r["role"] != "TEACHER" or r["disposition"] == "SUPERSEDED":
                continue
            print("  {o:>3}  {i:<5} {n:<38} {p:>7.0f}B {q:>8} {s:>7} {d:>5}  {t}".format(
                o=r["queue_position"], i=r["model_id"], n=r["display_name"][:38],
                p=(r.get("parameter_count") or 0)/1e9, q=(r.get("quantization") or "?")[:8],
                s=r["disk_size_gib"], d=r.get("estimated_gen_days") or "?",
                t=r.get("tier") or "?"))
        skipped = [r for r in recs if r["role"] != "TEACHER" or r["disposition"] == "SUPERSEDED"]
        if skipped:
            print("  " + "-" * 88)
            for r in skipped:
                print(f"  ---  {r['model_id']:<5} {r['display_name'][:38]:<38} "
                      f"{r['role']:<15} {r['disposition']}")
        for e in errors:
            print(f"  [scan-error] {e}")
        bad = [r for r in recs if r.get("gguf_error")]
        if bad:
            print(f"  [note] {len(bad)} file(s) had unreadable GGUF headers; size-only entries.")
    print("-" * 74)
    print(f"  Written: {out_dir/'teachers.json'}")
    print(f"           {out_dir/'teachers.md'}")
    print("  License classes are UNKNOWN by design — audit primary texts before use.")
    print("=" * 74)


if __name__ == "__main__":
    main()
