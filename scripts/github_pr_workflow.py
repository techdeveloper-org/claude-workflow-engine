#!/usr/bin/env python
# BACKWARD-COMPAT SHIM
# PR workflow logic moved to scripts/github_pr_workflow/
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from github_pr_workflow.versioning import main  # noqa: E402

if __name__ == "__main__":
    main()
