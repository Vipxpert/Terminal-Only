# /llm_harness/adapters/claude-code/harness_project.py
"""Finds the Terminal-Only project a folder belongs to: the nearest folder at or above it that has the project's memory (.llm_harness/) or the harness's machine state (.git/llm_harness/). The harness's own install folder (~/.llm_harness, which holds harness.py) and the home folder itself never count, so a project that merely sits under the home folder is not mistaken for one."""
import os


def harness_root(start):
    try:
        cur = os.path.abspath(start)
    except (TypeError, ValueError):
        return None
    home = os.path.normcase(os.path.abspath(os.path.expanduser("~")))
    while True:
        marker = os.path.join(cur, ".llm_harness")
        memory = os.path.isdir(marker) and not os.path.isfile(os.path.join(marker, "harness.py"))
        state = os.path.isdir(os.path.join(cur, ".git", "llm_harness"))
        if (memory or state) and os.path.normcase(cur) != home:
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
