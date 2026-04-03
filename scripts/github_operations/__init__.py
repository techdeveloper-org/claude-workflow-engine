"""GitHub operations package.

Refactored from monolithic github_issue_manager.py.
All public symbols re-exported for backward compatibility.
"""

from .branch_manager import create_issue_branch, get_session_branch, is_on_issue_branch  # noqa: F401
from .client import GH_TIMEOUT, MAX_OPS_PER_SESSION, _run_gh_cmd, is_gh_available  # noqa: F401
from .issue_manager import (  # noqa: F401
    _build_close_comment,
    close_github_issue,
    create_github_issue,
    extract_task_id_from_response,
)
from .labels import LABEL_DEFINITIONS, _build_issue_labels  # noqa: F401
from .session_integration import (  # noqa: F401
    _get_current_session_id,
    _get_mapping_file,
    _get_ops_count,
    _get_session_id,
    _increment_ops_count,
    _load_issues_mapping,
    _save_issues_mapping,
)
