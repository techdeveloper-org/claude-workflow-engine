# MCP Tool Reference

Auto-generated from `src/mcp/*_mcp_server.py` via `scripts/generate-mcp-docs.py`.

## policy-enforcement (9 tools)

**File:** `enforcement_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `check_enforcement_status` | Check current policy enforcement status for all steps. | - |
| `enforce_policy_step` | Enforce a specific policy step in the execution pipeline. | step_number, step_name |
| `log_tool_usage` | Log a tool call made by Claude for tracking. | tool_name, operation, parameters, result |
| `verify_compliance` | Verify that all required policy steps have been enforced. | - |
| `list_policies` | List all policy files with their status. | level |
| `record_policy_execution` | Record a policy execution to flow-trace.json for tracking. | policy_name, policy_script, policy_type, decision, duration_ms, input_params, output_results, session_id, sub_operations |
| `get_session_id` | Get the current session ID from .current-session.json. | - |
| `get_flow_trace_summary` | Get summary statistics from a session's flow-trace. | session_id |
| `check_module_health` | Check health of all registered policy modules (existence + importability). | - |

## git-ops (14 tools)

**File:** `git_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `git_status` | Get repository status (modified, staged, untracked files). | repo_path |
| `git_branch_create` | Create a new branch from specified base with stash safety. | name, from_branch, repo_path |
| `git_branch_switch` | Switch to an existing branch. | name, repo_path |
| `git_branch_list` | List all local and remote branches. | repo_path |
| `git_branch_delete` | Delete a local branch. | name, force, repo_path |
| `git_commit` | Stage files and create a commit. | message, files, repo_path |
| `git_push` | Push branch to remote origin. | branch, set_upstream, force, repo_path |
| `git_pull` | Pull latest changes from remote origin. | branch, repo_path |
| `git_diff` | Get diff output. | staged, from_ref, repo_path |
| `git_stash` | Manage git stash. | action, message, repo_path |
| `git_log` | Get recent commit log. | count, repo_path |
| `git_fetch` | Fetch from remote. | remote, branch, prune, repo_path |
| `git_post_merge_cleanup` | Clean up after a PR merge: switch to main, pull, delete branch, prune. | merged_branch, main_branch, repo_path |
| `git_get_origin_url` | Get the remote origin URL of the repository. | repo_path |

## github-api (12 tools)

**File:** `github_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `github_create_issue` | Create a GitHub issue. | title, body, labels, assignee, repo_path |
| `github_close_issue` | Close a GitHub issue with optional closing comment. | number, comment, repo_path |
| `github_add_comment` | Add a comment to an issue or pull request. | number, body, type, repo_path |
| `github_create_pr` | Create a pull request. | title, body, head, base, labels, repo_path |
| `github_merge_pr` | Merge a pull request with gh CLI fallback for safety. | number, method, delete_branch, commit_message, repo_path |
| `github_list_issues` | List issues in the repository. | labels, state, repo_path |
| `github_get_pr_status` | Get pull request status and check details. | number, repo_path |
| `github_create_issue_branch` | Create a git branch linked to a GitHub issue. | issue_number, subject, issue_type, repo_path |
| `github_auto_commit_and_pr` | Auto-commit all changes and create a PR in one step. | title, body, base, labels, repo_path |
| `github_validate_build` | Run project build validation before PR. | repo_path |
| `github_label_issue` | Add labels to an issue or PR. | number, labels, repo_path |
| `github_full_merge_cycle` | Full merge cycle: validate build -> merge PR -> cleanup branch. | number, method, validate_build, repo_path |

## llm-provider (8 tools)

**File:** `llm_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `llm_generate` | Generate text using configured LLM providers. | prompt, model, provider, temperature, json_mode, timeout |
| `llm_list_models` | List all configured LLM providers and their available models. | - |
| `llm_health_check` | Check health and availability of all configured LLM providers. | - |
| `llm_git_commit_title` | Generate a meaningful git commit title using LLM from staged diff. | commit_type, cwd |
| `llm_classify_step` | Classify a pipeline step for optimal model routing. | step_name |
| `llm_select_model` | Intelligently select the best model for a task. | task_type, complexity, step_name |
| `llm_discover_models` | Discover all available local models (Ollama + local files). | - |
| `llm_hybrid_generate` | Generate text using hybrid GPU-first routing with Claude fallback. | prompt, step_name, complexity, temperature |

## post_tool_tracker (6 tools)

**File:** `post_tool_tracker_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `track_tool_usage` | Track a completed tool call with rich activity data. | tool_name, tool_input, is_error, response_chars |
| `increment_progress` | Manually increment session progress. | delta, reason |
| `clear_enforcement_flag` | Clear a specific enforcement flag for current session. | flag_name |
| `get_progress_status` | Get current session progress snapshot. | - |
| `get_tool_stats` | Get detailed tool usage statistics for current session. | - |
| `check_commit_readiness` | Check if auto-commit should be triggered based on modified files. | - |

## pre_tool_gate (8 tools)

**File:** `pre_tool_gate_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `validate_tool_call` | Run all policy checks for a tool call. Returns allow/block decision. | tool_name, tool_input |
| `check_task_breakdown` | Check if task breakdown is pending for current session. | - |
| `check_skill_selected` | Check if skill/agent selection is pending for current session. | - |
| `check_level_completion` | Check if pipeline levels are complete in flow-trace. | level |
| `get_enforcer_state` | Get current enforcer state snapshot (all flags + flow-trace status). | - |
| `check_failure_patterns` | Check known failure patterns from failure-kb.json for a tool call. | tool_name, tool_input |
| `get_dynamic_skill_hint` | Get skill/agent hint based on file extension. | file_path |
| `reset_enforcer_flags` | Reset enforcement flags for current session. | flag_name |

## session-mgr (14 tools)

**File:** `session_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `session_save` | Save session data to disk atomically. | session_id, data_type, content, project |
| `session_load` | Load session data from disk. | session_id, data_type, project |
| `session_list` | List available sessions. | project, limit |
| `session_archive` | Archive sessions older than specified days. | days_old |
| `session_query` | Query sessions with filters. | filters |
| `session_create` | Create a new session with unique ID and register it in the chain index. | project, task_type, skill, prompt, project_cwd |
| `session_link` | Link a child session to its parent (for /clear continuity). | child_id, parent_id |
| `session_tag` | Add tags and optional summary to a session. Auto-relates by shared tags. | session_id, tags, summary |
| `session_get_context` | Get chain context for a session (ancestors + related sessions). | session_id, max_ancestors, max_related |
| `session_search_tags` | Search sessions by tags. Returns sessions matching ANY of the given tags. | tags, limit |
| `session_accumulate` | Accumulate per-request data for session summary generation. | session_id, prompt, task_type, skill, complexity, model, cwd, plan_mode, context_pct, supplementary_skills, standards_count, rules_count |
| `session_finalize` | Generate comprehensive session summary on session close. | session_id |
| `session_add_work_item` | Add a work item to a session for tracking tasks within sessions. | session_id, description, work_type, metadata |
| `session_complete_work_item` | Mark a work item as completed. | session_id, work_id, status |

## skill_manager (8 tools)

**File:** `skill_manager_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `skill_load_all` | Load all available skills from ~/.claude/skills/ with metadata. | - |
| `skill_load` | Load full SKILL.md content for a specific skill. | skill_name |
| `skill_search` | Search skills by keyword, tags, or project type. | query, tags, project_type |
| `skill_validate` | Validate whether a skill satisfies required capabilities. | skill_name, required_capabilities |
| `skill_rank` | Rank available skills by relevance to task requirements. | task_type, project_type, complexity, required_capabilities |
| `skill_detect_conflicts` | Detect conflicts between selected skills. | skill_names |
| `agent_load_all` | Load all available agents from ~/.claude/agents/ with metadata. | - |
| `agent_load` | Load full agent.md content for a specific agent. | agent_name |

## standards_loader (6 tools)

**File:** `standards_loader_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `detect_project_type` | Detect the primary programming language of a project. | project_path |
| `detect_framework` | Detect the primary framework within a project type. | project_path, project_type |
| `load_standards` | Load all applicable standards for a project with full traceability. | project_path |
| `resolve_standard_conflicts` | Resolve conflicts in a list of standards (higher priority wins). | standards_json |
| `get_active_standards` | Get currently active standards summary for a project. | project_path |
| `list_available_standards` | List all available standard files across all sources. | source |

## token_optimization (10 tools)

**File:** `token_optimization_mcp_server.py`

| Tool | Description | Parameters |
|------|-------------|------------|
| `optimize_tool_call` | Intercept and optimize any Claude tool call before execution. | tool_name, params |
| `ast_navigate_code` | Extract code structure without reading full file content. | file_path, show_methods |
| `smart_read_analyze` | Analyze a file and recommend optimal reading strategy. | file_path |
| `deduplicate_context` | Remove duplicate content across SRS, README, and CLAUDE.md. | contexts |
| `dedup_estimate` | Estimate deduplication savings without actually deduplicating. | contexts |
| `context_budget_status` | Check current context budget usage (logs + sessions directories). | - |
| `get_optimization_stats` | Get optimization statistics from logged data. | date |
| `log_optimization` | Manually log an optimization event for tracking. | tool, optimized, token_savings, details |
| `optimize_read_params` | Get optimized Read parameters for a file. | file_path, offset, limit |
| `optimize_grep_params` | Get optimized Grep parameters. | pattern, path, head_limit, output_mode |

---

**Total: 10 servers, 95 tools**
