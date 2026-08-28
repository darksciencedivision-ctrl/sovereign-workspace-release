"""Print effective Debate Table configuration as JSON (bootstrap helper).

Consumes debate/config_policy.py so bootstrap checks resolve configuration
identically to the runtime. Exit codes: 0 ok, 5 BADCONFIG|<reason>.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from debate.config_policy import ConfigurationError, effective_summary


def main() -> int:
    if len(sys.argv) != 2:
        print("BADCONFIG|usage: effective_config.py <config.json>")
        return 5
    try:
        summary = effective_summary(sys.argv[1])
    except ConfigurationError as exc:
        print("BADCONFIG|" + str(exc).replace("|", " "))
        return 5
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())