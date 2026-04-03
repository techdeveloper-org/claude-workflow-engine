"""Level -1 Auto-Fix System package.

Canonical location for all Level -1 node functions, merge logic,
and recovery/interactive fix nodes.

Public API:
- node_unicode_fix, node_encoding_validation, node_windows_path_check
- level_minus1_merge_node, MAX_LEVEL_MINUS1_ATTEMPTS
- ask_level_minus1_fix, fix_level_minus1_issues
"""

from .merge import MAX_LEVEL_MINUS1_ATTEMPTS, level_minus1_merge_node  # noqa: F401
from .nodes import node_encoding_validation, node_unicode_fix, node_windows_path_check  # noqa: F401
from .recovery import ask_level_minus1_fix, fix_level_minus1_issues  # noqa: F401
