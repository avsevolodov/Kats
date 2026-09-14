"""Stderr progress logs for the runner process. Never log secrets or raw prompts."""
import logging
import os
import sys

LOG = logging.getLogger("agent-runner")


def configure():
    level_name = os.environ.get("RUNNER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    LOG.setLevel(level)
