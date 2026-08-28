"""Remove only verified cache directories from this project."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / ".pytest_cache",
    ROOT / "__pycache__",
    ROOT / "spike" / "__pycache__",
    ROOT / "tests" / "__pycache__",
)


for target in TARGETS:
    resolved = target.resolve()
    if ROOT.resolve() not in resolved.parents:
        raise RuntimeError(f"refusing out-of-project cache target: {resolved}")
    if target.exists():
        shutil.rmtree(target)

spike = ROOT / "spike"
if spike.exists() and not any(spike.iterdir()):
    spike.rmdir()
