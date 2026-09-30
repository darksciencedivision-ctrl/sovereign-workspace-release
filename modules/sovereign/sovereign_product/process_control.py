"""Bounded invocations of Windows process/task control utilities."""
from __future__ import annotations

import logging
import subprocess
from typing import Any

from .runtime_contracts import RuntimeControlError


def run_control_command(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, timeout=20, **kwargs)
    except subprocess.TimeoutExpired as exc:
        message = f'{command[0]} timed out after 20 seconds; operation is unconfirmed'
        logging.getLogger(__name__).warning(message)
        raise RuntimeControlError(message) from exc
