#!/usr/bin/env python3
"""
Sovereign Distillery — Phase D1: Machine Characterization

Pure inspection. Downloads nothing, trains nothing, changes nothing.
Converts the modelled hardware envelope into a measured hardware profile.

Usage:
    python d1_characterize.py                      # inspect, print, write JSON
    python d1_characterize.py --vram-probe         # additionally measure usable VRAM
    python d1_characterize.py --out <path.json>

Writes: runs/hardware_profile.json (relative to the Distillery root)
"""
import argparse, json, os, platform, shutil, subprocess, sys, traceback
from datetime import datetime, timezone

ERRORS = []

def soft(fn, label, default=None):
    try:
        return fn()
    except Exception as e:
        ERRORS.append(f"{label}: {type(e).__name__}: {e}")
        return default

def run_cmd(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip() if p.returncode == 0 else None
    except Exception:
        return None

def pkg_versions():
    names = ["torch","torchvision","transformers","accelerate","peft","trl",
             "datasets","bitsandbytes","triton","flash_attn","xformers",
             "safetensors","sentencepiece","numpy","unsloth","llama_cpp"]
    out = {}
    import importlib
    try:
        from importlib.metadata import version as md_version, PackageNotFoundError
    except Exception:
        md_version = None
    for n in names:
        v = None
        if md_version:
            for cand in (n, n.replace("_","-")):
                try:
                    v = md_version(cand); break
                except Exception:
                    continue
        if v is None:
            try:
                v = getattr(importlib.import_module(n), "__version__", "present")
            except Exception:
                v = None
        out[n] = v
    return out

def nvidia_smi():
    if not shutil.which("nvidia-smi"):
        return None
    q = ("name,driver_version,memory.total,memory.used,memory.free,"
         "compute_cap,pcie.link.gen.current,pcie.link.width.current,temperature.gpu")
    raw = run_cmd(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader"])
    if not raw:
        return {"raw": run_cmd(["nvidia-smi"])}
    gpus = []
    for line in raw.splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) < 9:
            continue
        gpus.append({
            "name": f[0], "driver_version": f[1], "memory_total": f[2],
            "memory_used": f[3], "memory_free": f[4], "compute_capability": f[5],
            "pcie_gen_current": f[6], "pcie_width_current": f[7], "temperature_c": f[8],
        })
    return gpus

def torch_info():
    import torch
    info = {
        "version": torch.__version__,
        "cuda_compiled_version": torch.version.cuda,
        "cudnn_version": soft(lambda: torch.backends.cudnn.version(), "cudnn"),
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "devices": [],
    }
    if not torch.cuda.is_available():
        return info
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        cap = (p.major, p.minor)
        arch_list = soft(lambda: torch.cuda.get_arch_list(), "arch_list", [])
        sm_tag = f"sm_{p.major}{p.minor}"
        info["devices"].append({
            "index": i, "name": p.name,
            "compute_capability": f"{p.major}.{p.minor}", "sm_tag": sm_tag,
            "total_memory_bytes": p.total_memory,
            "total_memory_gib": round(p.total_memory / 1024**3, 3),
            "multi_processor_count": p.multi_processor_count,
            "torch_arch_list": arch_list,
            "arch_supported_by_this_torch_build": (sm_tag in arch_list) if arch_list else None,
            "bf16_supported": soft(lambda: torch.cuda.is_bf16_supported(), "bf16"),
        })
    info["matmul_tf32"] = soft(lambda: torch.backends.cuda.matmul.allow_tf32, "tf32")
    return info

def bnb_check():
    """Does bitsandbytes actually work on this device? The 4-bit path is what QLoRA needs."""
    import torch, bitsandbytes as bnb
    res = {"version": getattr(bnb, "__version__", "unknown")}
    if not torch.cuda.is_available():
        res["cuda"] = False
        return res
    res["cuda"] = True
    try:
        from bitsandbytes.nn import Linear4bit
        lin = Linear4bit(256, 256, compute_dtype=torch.float16).cuda()
        x = torch.randn(4, 256, dtype=torch.float16, device="cuda")
        y = lin(x); torch.cuda.synchronize()
        res["linear4bit_forward"] = True
        res["output_shape"] = list(y.shape)
        res["output_finite"] = bool(torch.isfinite(y).all().item())
    except Exception as e:
        res["linear4bit_forward"] = False
        res["error"] = f"{type(e).__name__}: {e}"
    return res

def vram_probe():
    """Allocate until failure to measure usable VRAM (compositor reserve included)."""
    import torch
    if not torch.cuda.is_available():
        return None
    torch.cuda.empty_cache()
    block_mib, blocks, total = 64, [], 0
    try:
        while True:
            blocks.append(torch.empty(block_mib * 1024 * 1024 // 2,
                                      dtype=torch.float16, device="cuda"))
            total += block_mib
            if total > 64 * 1024:
                break
    except RuntimeError:
        pass
    finally:
        del blocks
        torch.cuda.empty_cache()
    props = torch.cuda.get_device_properties(0)
    nominal = props.total_memory / 1024**2
    return {
        "usable_vram_mib": total,
        "usable_vram_gib": round(total / 1024, 3),
        "nominal_vram_mib": round(nominal, 1),
        "reserved_by_system_mib": round(nominal - total, 1),
        "note": "Allocation ceiling in fp16 blocks. Approximates headroom after "
                "display compositor and driver reserve.",
    }

def disk_and_ram():
    out = {}
    out["system_ram"] = soft(lambda: __import__("psutil").virtual_memory()._asdict(), "psutil_ram")
    if out["system_ram"] is None and platform.system() == "Windows":
        raw = run_cmd(["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"])
        if raw:
            for tok in raw.split():
                if tok.isdigit():
                    out["system_ram"] = {"total": int(tok),
                                         "total_gib": round(int(tok)/1024**3, 2)}
                    break
    out["disks"] = {}
    for path in ["D:\\", "C:\\", "/"]:
        try:
            u = shutil.disk_usage(path)
            out["disks"][path] = {"total_gib": round(u.total/1024**3, 2),
                                  "used_gib": round(u.used/1024**3, 2),
                                  "free_gib": round(u.free/1024**3, 2)}
        except Exception:
            pass
    return out

def verdict(profile):
    """Conservative reading. Estimates only — this is not a training measurement."""
    v = {"blocking_issues": [], "warnings": [], "notes": []}
    t = profile.get("torch") or {}
    if not t:
        v["blocking_issues"].append("PyTorch not importable — no local training possible.")
        return v
    if not t.get("cuda_available"):
        v["blocking_issues"].append("torch.cuda.is_available() is False — GPU training unavailable.")
        return v
    devs = t.get("devices") or []
    if devs:
        d = devs[0]
        if d.get("arch_supported_by_this_torch_build") is False:
            v["blocking_issues"].append(
                f"{d['sm_tag']} not in this PyTorch build's arch list {d.get('torch_arch_list')}. "
                "Kernels will fall back or fail. Install a build supporting this architecture.")
        gib = d.get("total_memory_gib") or 0
        v["notes"].append(f"GPU {d.get('name')} — {gib} GiB nominal, {d.get('sm_tag')}.")
        if gib < 9:
            v["warnings"].append(
                "Under ~9 GiB nominal: QLoRA on 7B is at or past the modelled margin. "
                "Plan the conservative end of the envelope until a smoke test says otherwise.")
    b = profile.get("bitsandbytes") or {}
    if b.get("linear4bit_forward") is False:
        v["blocking_issues"].append(
            f"bitsandbytes Linear4bit failed on this device: {b.get('error')}. "
            "The QLoRA path is unavailable until this is resolved.")
    elif b.get("linear4bit_forward") is True:
        v["notes"].append("bitsandbytes 4-bit forward pass succeeded — QLoRA path viable.")
    elif not b:
        v["warnings"].append("bitsandbytes not importable — QLoRA path unverified.")
    probe = profile.get("vram_probe")
    if probe:
        v["notes"].append(
            f"Usable VRAM measured at {probe['usable_vram_gib']} GiB "
            f"({probe['reserved_by_system_mib']} MiB reserved by system).")
    for p in profile.get("packages", {}):
        pass
    missing = [n for n in ("transformers","peft","accelerate","datasets")
               if not (profile.get("packages") or {}).get(n)]
    if missing:
        v["warnings"].append(f"Training stack incomplete — missing: {', '.join(missing)}")
    return v

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--vram-probe", action="store_true",
                    help="Allocate until failure to measure usable VRAM. Close other GPU apps first.")
    a = ap.parse_args()

    profile = {
        "schema": "sovereign-distillery/hardware_profile/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor(), "python": sys.version.split()[0],
            "executable": sys.executable,
            "conda_env": os.environ.get("CONDA_DEFAULT_ENV"),
            "virtual_env": os.environ.get("VIRTUAL_ENV"),
        },
        "nvidia_smi": soft(nvidia_smi, "nvidia-smi"),
        "packages": soft(pkg_versions, "packages", {}),
        "torch": soft(torch_info, "torch", {}),
        "bitsandbytes": soft(bnb_check, "bitsandbytes", {}),
        "storage_and_ram": soft(disk_and_ram, "storage_ram", {}),
    }
    if a.vram_probe:
        profile["vram_probe"] = soft(vram_probe, "vram_probe")
    profile["errors"] = ERRORS
    profile["verdict"] = verdict(profile)

    out = a.out
    if out is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.makedirs(os.path.join(root, "runs"), exist_ok=True)
        out = os.path.join(root, "runs", "hardware_profile.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    print("=" * 66)
    print("SOVEREIGN DISTILLERY — D1 MACHINE CHARACTERIZATION")
    print("=" * 66)
    for g in (profile["nvidia_smi"] or []):
        if isinstance(g, dict) and "name" in g:
            print(f"  GPU      {g['name']}  |  {g['memory_total']} total, {g['memory_free']} free")
            print(f"  Driver   {g['driver_version']}  |  compute cap {g['compute_capability']}")
    t = profile.get("torch") or {}
    print(f"  torch    {t.get('version')}  |  CUDA {t.get('cuda_compiled_version')}  "
          f"|  available={t.get('cuda_available')}")
    for d in t.get("devices", []):
        print(f"           {d['sm_tag']} in build arch list: {d.get('arch_supported_by_this_torch_build')}")
    b = profile.get("bitsandbytes") or {}
    print(f"  bnb      {b.get('version')}  |  4-bit forward: {b.get('linear4bit_forward')}")
    print("-" * 66)
    v = profile["verdict"]
    for k, sym in (("blocking_issues","BLOCKER"), ("warnings","WARNING"), ("notes","NOTE")):
        for m in v.get(k, []):
            print(f"  [{sym}] {m}")
    if ERRORS:
        print("-" * 66)
        for e in ERRORS:
            print(f"  [inspect-error] {e}")
    print("-" * 66)
    print(f"  Written: {out}")
    print("=" * 66)

if __name__ == "__main__":
    main()
