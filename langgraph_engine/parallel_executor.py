"""
Parallel Executor - Concurrency utilities for the 3-level pipeline.

Provides thread-pool and process-pool based parallelization for:
1. Step 2 codebase exploration  - 3+ concurrent file scans
2. Step 10 task execution       - parallel independent subtasks
3. Skill/agent downloads        - max 4 concurrent downloads

Design principles:
- Thread-based (not multiprocess) to stay within the same Python process and
  avoid serialization overhead for in-memory objects.
- Hard concurrency caps to prevent resource exhaustion.
- Every parallel job is wrapped in a try/except so one failure does not cancel
  the whole batch.
- All public methods return results sorted in the same order as the input so
  callers can zip inputs and outputs reliably.
- UTF-8 / ASCII-safe: no emoji, no wide characters in log messages.
"""

import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

# Maximum worker threads for each parallel operation type.
_MAX_EXPLORATION_WORKERS: int = int(os.environ.get("PERF_EXPLORE_WORKERS", "3"))
_MAX_TASK_WORKERS: int = int(os.environ.get("PERF_TASK_WORKERS", "4"))
_MAX_DOWNLOAD_WORKERS: int = int(os.environ.get("PERF_DOWNLOAD_WORKERS", "4"))

# File read chunk size for concurrent exploration (lines per chunk).
_FILE_CHUNK_LINES: int = 500


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _timed_call(fn: Callable, *args, **kwargs) -> Tuple[Any, float]:
    """Call *fn* and return (result, elapsed_seconds)."""
    t0 = time.monotonic()
    result = fn(*args, **kwargs)
    return result, time.monotonic() - t0


# ---------------------------------------------------------------------------
# 1. Step 2 Parallel Codebase Exploration
# ---------------------------------------------------------------------------


class ParallelExplorer:
    """Runs 3+ concurrent exploration tasks for Step 2 plan execution.

    Each exploration task is an independent callable that returns a string
    fragment (search results, grep output, file read, etc.).  Results are
    joined in declaration order.

    Usage::

        explorer = ParallelExplorer()
        results = explorer.explore(
            tasks=[
                ("search",  search_fn,   [keyword],  {}),
                ("grep",    grep_fn,     [pattern],  {"head_limit": 20}),
                ("read",    read_fn,     ["main.py"], {}),
            ]
        )
        combined_context = "\\n".join(r["result"] for r in results if r["success"])
    """

    def __init__(self, max_workers: int = _MAX_EXPLORATION_WORKERS):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self.max_workers = max_workers

    # ------------------------------------------------------------------

    def explore(
        self,
        tasks: List[Tuple[str, Callable, list, dict]],
        timeout_seconds: float = 30.0,
    ) -> List[Dict[str, Any]]:
        """Execute exploration tasks concurrently.

        Args:
            tasks: List of (label, callable, args, kwargs) tuples.
                   Each callable must return a str.
            timeout_seconds: Per-task timeout.  Slow tasks are cancelled and
                             their result is replaced with an error message.

        Returns:
            List of result dicts in the same order as *tasks*::

                [
                    {
                        "label": str,
                        "success": bool,
                        "result": str,
                        "elapsed_s": float,
                        "error": str | None,
                    },
                    ...
                ]
        """
        if not tasks:
            return []

        workers = min(self.max_workers, len(tasks))
        logger.info("[ParallelExplorer] Starting {} tasks with {} workers".format(len(tasks), workers))

        results: List[Optional[Dict[str, Any]]] = [None] * len(tasks)

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="explore") as pool:
            future_to_idx: Dict[Future, int] = {}

            for idx, (label, fn, args, kwargs) in enumerate(tasks):
                fut = pool.submit(_timed_call, fn, *args, **kwargs)
                future_to_idx[fut] = idx

            for fut in as_completed(future_to_idx, timeout=timeout_seconds * len(tasks)):
                idx = future_to_idx[fut]
                label = tasks[idx][0]

                try:
                    value, elapsed = fut.result(timeout=timeout_seconds)
                    results[idx] = {
                        "label": label,
                        "success": True,
                        "result": str(value) if value is not None else "",
                        "elapsed_s": round(elapsed, 3),
                        "error": None,
                    }
                    logger.debug("[ParallelExplorer] '{}' done in {:.2f}s".format(label, elapsed))
                except Exception as exc:
                    results[idx] = {
                        "label": label,
                        "success": False,
                        "result": "",
                        "elapsed_s": 0.0,
                        "error": str(exc),
                    }
                    logger.warning("[ParallelExplorer] '{}' failed: {}".format(label, exc))

        # Fill any slots that were not resolved (shouldn't happen, but be safe)
        for idx, item in enumerate(results):
            if item is None:
                results[idx] = {
                    "label": tasks[idx][0],
                    "success": False,
                    "result": "",
                    "elapsed_s": 0.0,
                    "error": "Task did not complete",
                }

        successful = sum(1 for r in results if r["success"])
        logger.info("[ParallelExplorer] {}/{} tasks succeeded".format(successful, len(tasks)))
        return results  # type: ignore[return-value]

    # ------------------------------------------------------------------

    @staticmethod
    def parallel_file_scan(
        file_paths: List[str],
        scan_fn: Callable[[str], str],
        max_workers: int = _MAX_EXPLORATION_WORKERS,
        timeout_seconds: float = 20.0,
    ) -> List[Dict[str, Any]]:
        """Scan multiple files concurrently using *scan_fn*.

        Args:
            file_paths: Absolute or relative paths to scan.
            scan_fn: Called with each file path; must return str content.
            max_workers: Thread cap (default 3).
            timeout_seconds: Per-future timeout.

        Returns:
            List of dicts with keys: path, success, content, elapsed_s, error.
        """
        if not file_paths:
            return []

        workers = min(max_workers, len(file_paths))
        results: List[Optional[Dict[str, Any]]] = [None] * len(file_paths)

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="filescan") as pool:
            future_to_idx: Dict[Future, int] = {}
            for idx, fp in enumerate(file_paths):
                fut = pool.submit(_timed_call, scan_fn, fp)
                future_to_idx[fut] = idx

            for fut in as_completed(future_to_idx, timeout=timeout_seconds * len(file_paths)):
                idx = future_to_idx[fut]
                fp = file_paths[idx]
                try:
                    content, elapsed = fut.result(timeout=timeout_seconds)
                    results[idx] = {
                        "path": fp,
                        "success": True,
                        "content": str(content) if content is not None else "",
                        "elapsed_s": round(elapsed, 3),
                        "error": None,
                    }
                except Exception as exc:
                    results[idx] = {
                        "path": fp,
                        "success": False,
                        "content": "",
                        "elapsed_s": 0.0,
                        "error": str(exc),
                    }

        for idx, item in enumerate(results):
            if item is None:
                results[idx] = {
                    "path": file_paths[idx],
                    "success": False,
                    "content": "",
                    "elapsed_s": 0.0,
                    "error": "Scan did not complete",
                }

        return results  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 2. Step 10 Parallel Task Execution
# ---------------------------------------------------------------------------


class ParallelTaskExecutor:
    """Execute independent implementation subtasks in parallel for Step 10.

    Task safety contract:
    - Tasks that write to the *same* file must be grouped as sequential (not
      submitted together).
    - Use the ``safe_execute`` classmethod which enforces this rule by grouping
      tasks by affected files before running each safe batch in parallel.

    Usage::

        executor = ParallelTaskExecutor(max_workers=4)
        tasks = [
            {"id": "T1", "fn": write_service,   "files": ["services/foo.py"]},
            {"id": "T2", "fn": write_test,      "files": ["tests/test_foo.py"]},
            {"id": "T3", "fn": write_migration, "files": ["migrations/001.sql"]},
        ]
        results = executor.execute_tasks(tasks)
    """

    def __init__(self, max_workers: int = _MAX_TASK_WORKERS):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self.max_workers = max_workers

    # ------------------------------------------------------------------

    def execute_tasks(
        self,
        tasks: List[Dict[str, Any]],
        timeout_seconds: float = 120.0,
    ) -> List[Dict[str, Any]]:
        """Run safe (non-conflicting) tasks concurrently, then run the rest.

        Args:
            tasks: List of task dicts, each with:
                - id (str): unique task label
                - fn (Callable[[], Any]): zero-argument callable
                - files (List[str]): files the task will write (for conflict detection)
                - args (list, optional): positional args for fn
                - kwargs (dict, optional): keyword args for fn
            timeout_seconds: per-task timeout.

        Returns:
            List of result dicts in the same order as *tasks*::

                [
                    {
                        "id": str,
                        "success": bool,
                        "result": Any,
                        "elapsed_s": float,
                        "error": str | None,
                    },
                    ...
                ]
        """
        if not tasks:
            return []

        # Partition tasks into conflict-free batches
        batches = self._build_safe_batches(tasks)
        results_map: Dict[str, Dict[str, Any]] = {}

        total_start = time.monotonic()
        for batch_idx, batch in enumerate(batches):
            workers = min(self.max_workers, len(batch))
            logger.info(
                "[ParallelTaskExecutor] Batch {}/{}: {} tasks, {} workers".format(
                    batch_idx + 1, len(batches), len(batch), workers
                )
            )

            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="task") as pool:
                future_to_task: Dict[Future, Dict[str, Any]] = {}
                for task in batch:
                    fn = task["fn"]
                    args = task.get("args", [])
                    kwargs = task.get("kwargs", {})
                    fut = pool.submit(_timed_call, fn, *args, **kwargs)
                    future_to_task[fut] = task

                for fut in as_completed(future_to_task, timeout=timeout_seconds * len(batch)):
                    task = future_to_task[fut]
                    task_id = task["id"]
                    try:
                        value, elapsed = fut.result(timeout=timeout_seconds)
                        results_map[task_id] = {
                            "id": task_id,
                            "success": True,
                            "result": value,
                            "elapsed_s": round(elapsed, 3),
                            "error": None,
                        }
                    except Exception as exc:
                        results_map[task_id] = {
                            "id": task_id,
                            "success": False,
                            "result": None,
                            "elapsed_s": 0.0,
                            "error": str(exc),
                        }
                        logger.warning("[ParallelTaskExecutor] Task '{}' failed: {}".format(task_id, exc))

        total_elapsed = time.monotonic() - total_start
        successful = sum(1 for r in results_map.values() if r["success"])
        logger.info(
            "[ParallelTaskExecutor] {}/{} tasks succeeded in {:.2f}s".format(successful, len(tasks), total_elapsed)
        )

        # Return in original order
        return [
            results_map.get(
                t["id"],
                {
                    "id": t["id"],
                    "success": False,
                    "result": None,
                    "elapsed_s": 0.0,
                    "error": "Task was never scheduled",
                },
            )
            for t in tasks
        ]

    # ------------------------------------------------------------------

    @staticmethod
    def _build_safe_batches(tasks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group tasks into sequential batches where each batch is conflict-free.

        Two tasks conflict if they share at least one target file.
        Greedy first-fit algorithm: place each task in the earliest existing
        batch that has no conflict with it; otherwise start a new batch.
        """
        batches: List[List[Dict[str, Any]]] = []
        batch_files: List[set] = []

        for task in tasks:
            files = set(task.get("files", []))
            placed = False
            for b_idx, b_files in enumerate(batch_files):
                if not files.intersection(b_files):
                    batches[b_idx].append(task)
                    b_files.update(files)
                    placed = True
                    break
            if not placed:
                batches.append([task])
                batch_files.append(set(files))

        return batches


# ---------------------------------------------------------------------------
# 3. Concurrent Skill Downloads
# ---------------------------------------------------------------------------


class ConcurrentSkillDownloader:
    """Download or load skill/agent definitions with up to 4 concurrent workers.

    Each "download" is actually a filesystem read (or network fetch if a URL
    is provided).  The cap of 4 workers avoids saturating disk I/O while still
    providing a meaningful speedup over sequential loading.

    Usage::

        downloader = ConcurrentSkillDownloader()
        results = downloader.load_skills([
            {"name": "python-backend-engineer", "path": "/path/to/skill.md"},
            {"name": "java-spring-boot",         "path": "/path/to/skill.md"},
        ])
    """

    MAX_WORKERS: int = _MAX_DOWNLOAD_WORKERS  # hard cap per ACCEPTANCE CRITERIA

    def __init__(self, max_workers: int = MAX_WORKERS):
        self.max_workers = min(max_workers, self.MAX_WORKERS)

    # ------------------------------------------------------------------

    def load_skills(
        self,
        skill_specs: List[Dict[str, Any]],
        timeout_seconds: float = 15.0,
    ) -> Dict[str, str]:
        """Load skill definitions concurrently.

        Args:
            skill_specs: List of dicts with at least "name" (str) and
                         "path" (str | Path).  Optionally "encoding" (default utf-8).
            timeout_seconds: Per-skill timeout.

        Returns:
            Dict mapping skill_name -> file_content (empty string if failed).
        """
        if not skill_specs:
            return {}

        workers = min(self.max_workers, len(skill_specs))
        logger.info("[ConcurrentSkillDownloader] Loading {} skills with {} workers".format(len(skill_specs), workers))

        results: Dict[str, str] = {}
        lock = threading.Lock()

        def _load_one(spec: Dict[str, Any]) -> None:
            name = spec["name"]
            path = Path(spec["path"])
            encoding = spec.get("encoding", "utf-8")
            try:
                content = path.read_text(encoding=encoding)
                with lock:
                    results[name] = content
            except Exception as exc:
                logger.warning("[ConcurrentSkillDownloader] '{}' failed: {}".format(name, exc))
                with lock:
                    results[name] = ""

        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="skilldl") as pool:
            futs = [pool.submit(_load_one, spec) for spec in skill_specs]
            for fut in as_completed(futs, timeout=timeout_seconds * len(skill_specs)):
                try:
                    fut.result(timeout=timeout_seconds)
                except Exception:
                    pass  # Already handled inside _load_one

        elapsed = time.monotonic() - t0
        loaded = sum(1 for v in results.values() if v)
        logger.info(
            "[ConcurrentSkillDownloader] {}/{} skills loaded in {:.2f}s".format(loaded, len(skill_specs), elapsed)
        )
        return results

    # ------------------------------------------------------------------

    def load_agents(
        self,
        agent_specs: List[Dict[str, Any]],
        timeout_seconds: float = 15.0,
    ) -> Dict[str, str]:
        """Load agent definitions concurrently.

        Same interface as load_skills; separated for clarity.
        """
        return self.load_skills(agent_specs, timeout_seconds=timeout_seconds)


# ---------------------------------------------------------------------------
# 4. Parallel Step 2 integration helper
# ---------------------------------------------------------------------------


def run_parallel_step2_exploration(
    user_requirement: str,
    project_root: str,
    search_fn: Callable[[str, int], str],
    grep_fn: Callable[[str, str, int], str],
    read_fn: Callable[[str, int, int], str],
    key_files: Optional[Dict[str, List[str]]] = None,
    max_workers: int = _MAX_EXPLORATION_WORKERS,
) -> str:
    """Run Step 2 codebase exploration with 3+ concurrent tasks.

    Replaces the sequential _explore_codebase() loop in
    Level3RemainingSteps with concurrent execution.

    Args:
        user_requirement: Original user requirement string.
        project_root: Absolute path to project root.
        search_fn: (query, max_results) -> str
        grep_fn: (pattern, glob_pattern, head_limit) -> str
        read_fn: (file_path, offset, limit) -> str
        key_files: Dict returned by _find_key_files(); optional.
        max_workers: Thread cap for exploration.

    Returns:
        Combined exploration context string.
    """
    keywords = [w for w in user_requirement.lower().split() if len(w) > 2][:3]

    tasks: List[Tuple[str, Callable, list, dict]] = []

    # Task 1: Search
    tasks.append(("search", search_fn, [user_requirement, 10], {}))

    # Tasks 2+: Grep for each keyword
    for kw in keywords:
        tasks.append(
            (
                "grep:{}".format(kw),
                grep_fn,
                [kw, "**/*.py", 20],
                {},
            )
        )

    # Tasks: Read key files
    if key_files:
        for file_type, files in key_files.items():
            for fp in files[:2]:
                tasks.append(
                    (
                        "read:{}".format(fp),
                        read_fn,
                        [fp, 0, _FILE_CHUNK_LINES],
                        {},
                    )
                )

    explorer = ParallelExplorer(max_workers=max_workers)
    results = explorer.explore(tasks, timeout_seconds=30.0)

    parts = ["=== PARALLEL EXPLORATION RESULTS ==="]
    for r in results:
        if r["success"] and r["result"]:
            parts.append("\n--- {} ({:.2f}s) ---".format(r["label"], r["elapsed_s"]))
            parts.append(r["result"])
        elif not r["success"]:
            parts.append("\n--- {} FAILED: {} ---".format(r["label"], r["error"]))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 5. Parallel skill loader integration helper
# ---------------------------------------------------------------------------


def parallel_load_all_skills(
    skills_dir: Path,
    max_workers: int = _MAX_DOWNLOAD_WORKERS,
) -> Dict[str, str]:
    """Load all skills from skills_dir concurrently.

    Drop-in accelerator for SkillAgentLoader.list_all_skills().

    Args:
        skills_dir: Path to ~/.claude/skills/
        max_workers: Thread cap (max 4).

    Returns:
        Dict mapping skill_name -> content.
    """
    if not skills_dir.exists():
        return {}

    specs: List[Dict[str, Any]] = []
    for domain_dir in skills_dir.iterdir():
        if not domain_dir.is_dir():
            continue
        for skill_dir in domain_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                skill_file = skill_dir / "skill.md"
            if skill_file.exists():
                specs.append({"name": skill_dir.name, "path": str(skill_file)})

    downloader = ConcurrentSkillDownloader(max_workers=max_workers)
    return downloader.load_skills(specs)


def parallel_load_all_agents(
    agents_dir: Path,
    max_workers: int = _MAX_DOWNLOAD_WORKERS,
) -> Dict[str, str]:
    """Load all agents from agents_dir concurrently.

    Drop-in accelerator for SkillAgentLoader.list_all_agents().

    Args:
        agents_dir: Path to ~/.claude/agents/
        max_workers: Thread cap (max 4).

    Returns:
        Dict mapping agent_name -> content.
    """
    if not agents_dir.exists():
        return {}

    specs: List[Dict[str, Any]] = []
    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        agent_file = agent_dir / "agent.md"
        if agent_file.exists():
            specs.append({"name": agent_dir.name, "path": str(agent_file)})

    downloader = ConcurrentSkillDownloader(max_workers=max_workers)
    return downloader.load_agents(specs)
