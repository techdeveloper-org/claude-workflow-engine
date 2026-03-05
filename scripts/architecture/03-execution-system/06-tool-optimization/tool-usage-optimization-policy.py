#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool Usage Optimization Policy
=================================
Consolidated enterprise-grade tool optimization system.

Consolidates all 6 tool optimization scripts into one comprehensive module:
  1. tool-usage-optimizer.py      - Core optimizer with caching and batching
  2. tool-call-interceptor.py     - Intercept and optimize tool calls
  3. auto-tool-wrapper.py         - Automatic tool parameter wrapping
  4. pre-execution-optimizer.py   - Pre-execution optimization
  5. ast-code-navigator.py        - AST-based code analysis
  6. smart-read.py                - Smart file reading optimization

Architecture:
  - ToolUsageOptimizer:    Core optimizer with caching, batching, metrics
  - ToolCallInterceptor:   Intercept and optimize all tool calls
  - AutoToolWrapper:       Auto-wrap parameters intelligently
  - PreExecutionOptimizer: Optimize before tool execution
  - ASTCodeNavigator:      AST-based code analysis for smart operations
  - SmartReadOptimizer:    Smart file reading with caching
  - ToolOptimizationPolicy: Unified policy interface (enforce/validate/report)

CLI Modes:
  --enforce    Initialize all optimization subsystems
  --validate   Run compliance check
  --report     Generate optimization statistics
  --optimize   Optimize a specific tool call (requires --tool and --params)
  --intercept  Intercept a tool call (requires --tool and --params)
  --analyze    AST-analyze a code file (requires --file)
  --stats      Print cumulative session statistics

Usage Examples:
  python tool-usage-optimization-policy.py --enforce
  python tool-usage-optimization-policy.py --validate
  python tool-usage-optimization-policy.py --report
  python tool-usage-optimization-policy.py --optimize --tool Read --params '{"file_path": "/path/to/file.py"}'
  python tool-usage-optimization-policy.py --intercept --tool Grep --params '{"pattern": "class.*Service"}'
  python tool-usage-optimization-policy.py --analyze --file /path/to/code.java
  python tool-usage-optimization-policy.py --stats

Version: 1.0.0
"""

# ---------------------------------------------------------------------------
# Windows encoding fix - must be applied before any output
# ---------------------------------------------------------------------------
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ---------------------------------------------------------------------------
# Standard library imports
# ---------------------------------------------------------------------------
import ast
import json
import logging
import os
import re
import subprocess
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from policy_tracking_helper import record_policy_execution, record_sub_operation
    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('ToolOptimizationPolicy')

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------
MEMORY_DIR = Path.home() / '.claude' / 'memory'
CACHE_DIR = MEMORY_DIR / '.cache'
LOGS_DIR = MEMORY_DIR / 'logs'
TOKEN_LOG = LOGS_DIR / 'token-optimization.log'
OPTIMIZATION_LOG = LOGS_DIR / 'tool-optimization.log'
ACCESS_COUNT_FILE = CACHE_DIR / 'access_counts.json'
SUMMARY_CACHE_DIR = CACHE_DIR / 'summaries'

# File size thresholds (lines)
SMALL_FILE_THRESHOLD = 100
MEDIUM_FILE_THRESHOLD = 500
LARGE_FILE_THRESHOLD = 2000

# Access count before suggesting cache
CACHE_THRESHOLD = 3

# Default limits applied by optimizer
DEFAULT_READ_LIMIT = 100
DEFAULT_GREP_LIMIT = 100
LARGE_FILE_READ_LIMIT = 500

# Supported code languages for AST navigation
AST_SUPPORTED_EXTENSIONS = {'.java', '.py', '.ts', '.tsx', '.js'}


# ===========================================================================
# ToolUsageOptimizer
# Consolidated from: tool-usage-optimizer.py
# ===========================================================================

class ToolUsageOptimizer:
    """
    Core tool usage optimizer.

    Optimizes tool parameters before execution to reduce token consumption.
    Applies per-tool optimization strategies including:
      - Read: offset/limit for large files, cache checking
      - Grep: head_limit enforcement, output_mode selection, type filters
      - Glob: path restriction, pattern narrowing
      - Bash: command combining, output limiting, tree suggestions
      - Edit/Write: uniqueness validation, parent directory checks
    """

    def __init__(self):
        """Initialize optimizer with cache directory and empty log."""
        self.optimization_log: List[Dict[str, Any]] = []
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug('ToolUsageOptimizer initialized. Cache: %s', self.cache_dir)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def optimize(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main optimization entry point.

        Args:
            tool_name: Name of the Claude tool (Read, Grep, Glob, Bash, Edit, Write).
            params:    Original tool parameters dictionary.
            context:   Optional contextual hints (looking_for, file_type, directory, etc.).

        Returns:
            Optimized parameters dictionary (may include additional keys applied by optimizer).
        """
        context = context or {}
        original_params = params.copy()

        logger.info('[ToolUsageOptimizer] Optimizing: %s', tool_name)

        tool_dispatch = {
            'Read':  self._optimize_read,
            'Grep':  self._optimize_grep,
            'Glob':  self._optimize_glob,
            'Bash':  self._optimize_bash,
            'Edit':  lambda p, c: p,
            'Write': lambda p, c: p,
        }

        optimizer_fn = tool_dispatch.get(tool_name)
        if optimizer_fn:
            optimized = optimizer_fn(params, context)
        else:
            optimized = params

        changes = self._get_parameter_changes(original_params, optimized)
        savings = self._estimate_savings(tool_name, original_params, optimized)

        self._log_optimization(tool_name, original_params, optimized, savings)

        if changes:
            logger.info('[ToolUsageOptimizer] Changes applied to %s: %s', tool_name, changes)
        if savings > 0:
            logger.info('[ToolUsageOptimizer] Estimated token savings: ~%d%%', savings)

        return optimized

    # ------------------------------------------------------------------
    # Per-tool optimization strategies
    # ------------------------------------------------------------------

    def _optimize_read(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize Read tool parameters.

        Strategy:
          - Detect file size in lines.
          - For files > MEDIUM_FILE_THRESHOLD lines, inject offset/limit unless already set.
          - Context-aware positioning: 'imports/top' -> offset=0, 'recent/bottom' -> tail.
          - Detect frequent access and flag for cache use.
        """
        file_path = params.get('file_path', '')
        file_size = self._get_file_size(file_path)

        if file_size and file_size > MEDIUM_FILE_THRESHOLD:
            if 'offset' not in params and 'limit' not in params:
                looking_for = context.get('looking_for', '').lower()
                if 'imports' in looking_for or 'top' in looking_for:
                    params['offset'] = 0
                    params['limit'] = 50
                elif 'recent' in looking_for or 'bottom' in looking_for:
                    params['offset'] = max(0, file_size - 50)
                    params['limit'] = 50
                else:
                    params['offset'] = 0
                    params['limit'] = DEFAULT_READ_LIMIT

        access_count = self._get_access_count(file_path)
        if access_count >= CACHE_THRESHOLD:
            cached_content = self._get_from_cache(file_path)
            if cached_content:
                params['_use_cache'] = True

        return params

    def _optimize_grep(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize Grep tool parameters.

        Strategy:
          - Always enforce head_limit (default 100).
          - Select output_mode based on context need.
          - Apply file type filter if known from context.
          - Restrict path if directory is known.
          - Limit context lines (-A/-B) when content mode is needed.
        """
        if 'head_limit' not in params:
            params['head_limit'] = DEFAULT_GREP_LIMIT

        if 'output_mode' not in params:
            if context.get('need_content'):
                params['output_mode'] = 'content'
                params['head_limit'] = min(params.get('head_limit', DEFAULT_GREP_LIMIT), 50)
                params['-A'] = 2
                params['-B'] = 1
            else:
                params['output_mode'] = 'files_with_matches'

        if context.get('file_type') and 'type' not in params:
            params['type'] = context['file_type']

        if context.get('directory') and 'path' not in params:
            params['path'] = context['directory']

        return params

    def _optimize_glob(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize Glob tool parameters.

        Strategy:
          - Restrict path to service directory if service_name is in context.
          - Narrow broad wildcard patterns using known file extensions.
        """
        pattern = params.get('pattern', '')

        if context.get('service_name') and 'path' not in params:
            service = context['service_name']
            params['path'] = 'backend/' + service + '/'

        if '**/*' in pattern and not context.get('need_deep_search'):
            if context.get('file_extension'):
                ext = context['file_extension']
                if '*.' + ext not in pattern:
                    params['pattern'] = pattern.replace('*', '*.' + ext)

        return params

    def _optimize_bash(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize Bash tool parameters.

        Strategy:
          - Suggest tree/find for directory exploration.
          - Combine sequential commands with &&.
          - Limit find output with | head -20.
          - Convert ls -l to ls -1 for concise output.
          - Apply -q to mvn build commands when only success matters.
          - Enforce -L 3 depth limit for tree commands.
        """
        command = params.get('command', '')

        if context.get('first_time_in_directory'):
            directory = context.get('directory', '')
            if directory and 'tree' not in command:
                suggestion = "find " + directory + " -maxdepth 3 -type d ! -path '*/.*' | sort"
                logger.info('[ToolUsageOptimizer] Bash suggestion: %s', suggestion)

        if context.get('commands') and len(context['commands']) > 1:
            if context.get('sequential'):
                params['command'] = ' && '.join(context['commands'])

        if 'find' in command and '| head' not in command:
            params['command'] = command + ' | head -20'

        if 'ls' in command and '-l' in command:
            params['command'] = params['command'].replace('ls -l', 'ls -1')

        if context.get('just_check_success'):
            if 'mvn' in command and '-q' not in command:
                params['command'] = params['command'] + ' -q'

        if 'tree' in params.get('command', ''):
            if '-L' not in params['command'] and '--level' not in params['command']:
                params['command'] = params['command'] + ' -L 3'

        return params

    # ------------------------------------------------------------------
    # Cache and file introspection helpers
    # ------------------------------------------------------------------

    def _get_file_size(self, file_path: str) -> Optional[int]:
        """
        Count lines in file.

        Args:
            file_path: Absolute or relative path to file.

        Returns:
            Line count as integer, or None if file cannot be read.
        """
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return sum(1 for _ in f)
        except Exception as exc:
            logger.debug('Could not count lines in %s: %s', file_path, exc)
        return None

    def _get_access_count(self, file_path: str) -> int:
        """
        Return how many times a file has been accessed in this session.

        Args:
            file_path: File path to check.

        Returns:
            Integer access count (0 if never accessed).
        """
        if ACCESS_COUNT_FILE.exists():
            try:
                with open(ACCESS_COUNT_FILE, 'r', encoding='utf-8') as f:
                    counts: Dict[str, int] = json.load(f)
                return counts.get(file_path, 0)
            except Exception as exc:
                logger.debug('Could not read access count: %s', exc)
        return 0

    def _increment_access_count(self, file_path: str) -> int:
        """
        Increment and persist the access count for a file.

        Args:
            file_path: File path to increment.

        Returns:
            New access count after increment.
        """
        ACCESS_COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
        counts: Dict[str, int] = {}
        if ACCESS_COUNT_FILE.exists():
            try:
                with open(ACCESS_COUNT_FILE, 'r', encoding='utf-8') as f:
                    counts = json.load(f)
            except Exception:
                counts = {}
        counts[file_path] = counts.get(file_path, 0) + 1
        with open(ACCESS_COUNT_FILE, 'w', encoding='utf-8') as f:
            json.dump(counts, f, indent=2)
        return counts[file_path]

    def _get_from_cache(self, file_path: str) -> Optional[str]:
        """
        Attempt to retrieve cached file summary.

        Args:
            file_path: File path to look up in cache.

        Returns:
            Cached summary string or None if not cached.
        """
        cache_file = SUMMARY_CACHE_DIR / (Path(file_path).name + '.json')
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                return cached.get('summary')
            except Exception as exc:
                logger.debug('Cache read failed for %s: %s', file_path, exc)
        return None

    # ------------------------------------------------------------------
    # Change detection and savings estimation
    # ------------------------------------------------------------------

    def _get_parameter_changes(
        self,
        original: Dict[str, Any],
        optimized: Dict[str, Any]
    ) -> List[str]:
        """
        Diff original and optimized parameter dicts.

        Args:
            original:  Original parameters before optimization.
            optimized: Parameters after optimization.

        Returns:
            List of human-readable change descriptions.
        """
        changes: List[str] = []
        for key, value in optimized.items():
            if key not in original:
                changes.append('Added: ' + key + '=' + str(value))
            elif original[key] != value:
                changes.append('Changed: ' + key + '=' + str(original[key]) + ' -> ' + str(value))
        return changes

    def _estimate_savings(
        self,
        tool_name: str,
        original: Dict[str, Any],
        optimized: Dict[str, Any]
    ) -> int:
        """
        Estimate token savings percentage based on parameter changes.

        Args:
            tool_name: Name of the tool being optimized.
            original:  Original parameters.
            optimized: Optimized parameters.

        Returns:
            Estimated savings as integer percentage (0-100).
        """
        if tool_name == 'Read':
            if 'limit' in optimized and 'limit' not in original:
                return 70
        elif tool_name == 'Grep':
            if 'head_limit' in optimized:
                if optimized.get('output_mode') == 'files_with_matches':
                    return 80
                return 50
        elif tool_name == 'Glob':
            if 'path' in optimized and 'path' not in original:
                return 40
        elif tool_name == 'Bash':
            if '&&' in optimized.get('command', ''):
                return 30
        return 0

    def _log_optimization(
        self,
        tool: str,
        original: Dict[str, Any],
        optimized: Dict[str, Any],
        savings: int
    ) -> None:
        """
        Append optimization event to in-memory log.

        Args:
            tool:      Tool name.
            original:  Original parameters.
            optimized: Optimized parameters.
            savings:   Estimated savings percentage.
        """
        self.optimization_log.append({
            'timestamp': datetime.now().isoformat(),
            'tool': tool,
            'original_params': original,
            'optimized_params': optimized,
            'estimated_savings_pct': savings
        })

    def get_session_stats(self) -> Dict[str, Any]:
        """
        Return aggregated statistics from all optimization events this session.

        Returns:
            Dictionary with total optimizations, savings, and per-tool breakdown.
        """
        total = len(self.optimization_log)
        total_savings = sum(e['estimated_savings_pct'] for e in self.optimization_log)
        by_tool: Dict[str, int] = {}
        for entry in self.optimization_log:
            by_tool[entry['tool']] = by_tool.get(entry['tool'], 0) + 1
        return {
            'total_optimizations': total,
            'average_savings_pct': round(total_savings / total, 1) if total else 0,
            'by_tool': by_tool,
        }


# ===========================================================================
# ToolCallInterceptor
# Consolidated from: tool-call-interceptor.py
# ===========================================================================

class ToolCallInterceptor:
    """
    Intercepts all tool calls and applies automatic optimizations.

    Provides a unified entry point for pre-use optimization with:
      - Per-tool strategy application
      - Unique string duplicate detection for Edit calls
      - Parent directory validation for Write calls
      - Structured result objects with suggestions and token savings
      - Persistent optimization log on disk
    """

    def __init__(self):
        """Initialize interceptor, create log directories."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.file_access_count: Dict[str, int] = {}
        logger.debug('ToolCallInterceptor initialized. Log: %s', OPTIMIZATION_LOG)

    # ------------------------------------------------------------------
    # Per-tool intercept strategies
    # ------------------------------------------------------------------

    def _intercept_bash(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercept and analyze Bash commands.

        Detects:
          - Structure exploration commands that could use find/tree instead.
          - Long sequential && chains that may benefit from parallelism.
          - Unquoted paths containing spaces.
        """
        command = params.get('command', '')
        suggestions: List[str] = []
        optimized_command = command

        structure_commands = ['find', 'ls -R', 'dir /s']
        if any(cmd in command for cmd in structure_commands):
            suggestions.append(
                "Optimization: Use 'find . -maxdepth 2 -type d' instead for better structure view"
            )

        if '&&' in command:
            parts = [p.strip() for p in command.split('&&')]
            if len(parts) > 2:
                suggestions.append(
                    'Optimization: ' + str(len(parts)) + ' sequential commands - consider parallelizing independent ones'
                )

        if ('cd ' in command or 'ls ' in command) and ' ' in command and '"' not in command:
            suggestions.append('Warning: Path may have spaces - consider using quotes')

        return {
            'tool': 'Bash',
            'original_params': params,
            'optimized_params': dict(
                command=optimized_command,
                **{k: v for k, v in params.items() if k != 'command'}
            ),
            'suggestions': suggestions,
            'token_savings': 0
        }

    def _intercept_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercept Read calls and apply auto-limit for large files.

        Also tracks access count per file and suggests caching at threshold.
        """
        file_path = params.get('file_path', '')
        offset = params.get('offset')
        limit = params.get('limit')
        optimized_params = params.copy()
        suggestions: List[str] = []
        token_savings = 0

        self.file_access_count[file_path] = self.file_access_count.get(file_path, 0) + 1

        path = Path(file_path)
        if path.exists():
            try:
                line_count = sum(1 for _ in open(path, 'r', encoding='utf-8', errors='replace'))

                if line_count > MEDIUM_FILE_THRESHOLD and offset is None and limit is None:
                    optimized_params['offset'] = 0
                    optimized_params['limit'] = DEFAULT_READ_LIMIT
                    suggestions.append(
                        'Auto-optimized: File has ' + str(line_count) + ' lines -> Using offset=0, limit=' + str(DEFAULT_READ_LIMIT)
                    )
                    token_savings = (line_count - DEFAULT_READ_LIMIT) * 100

                access_n = self.file_access_count[file_path]
                if access_n >= CACHE_THRESHOLD:
                    suggestions.append(
                        'Cache opportunity: File accessed ' + str(access_n) + ' times'
                    )
                    suggestions.append(
                        "Consider: python " + str(MEMORY_DIR) + "/utilities/context-cache.py --cache '" + file_path + "'"
                    )

            except Exception as exc:
                suggestions.append('Could not optimize: ' + str(exc))

        return {
            'tool': 'Read',
            'original_params': params,
            'optimized_params': optimized_params,
            'suggestions': suggestions,
            'token_savings': token_savings
        }

    def _intercept_grep(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercept Grep calls and enforce sensible defaults.

        Applies:
          - head_limit=100 when not specified.
          - output_mode='files_with_matches' when not specified.
          - Warning for very short (broad) patterns.
        """
        pattern = params.get('pattern', '')
        optimized_params = params.copy()
        suggestions: List[str] = []
        token_savings = 0

        if 'head_limit' not in params:
            optimized_params['head_limit'] = DEFAULT_GREP_LIMIT
            suggestions.append('Auto-optimized: Added head_limit=' + str(DEFAULT_GREP_LIMIT) + ' (default)')
            token_savings += 1000

        if 'output_mode' not in params:
            optimized_params['output_mode'] = 'files_with_matches'
            suggestions.append("Auto-optimized: Using output_mode='files_with_matches' for initial search")
            token_savings += 2000

        if len(pattern) < 3:
            suggestions.append(
                "Pattern '" + pattern + "' is very broad - consider more specific search"
            )

        return {
            'tool': 'Grep',
            'original_params': params,
            'optimized_params': optimized_params,
            'suggestions': suggestions,
            'token_savings': token_savings
        }

    def _intercept_glob(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercept Glob calls and flag broad patterns.

        Suggests path restriction when service context is unavailable.
        Warns on patterns without extension filters.
        """
        pattern = params.get('pattern', '')
        path = params.get('path')
        optimized_params = params.copy()
        suggestions: List[str] = []
        token_savings = 0

        if path is None:
            suggestions.append('Optimization: Consider restricting path if service is known')
            suggestions.append("Or use: tree -P '*.java' -L 3 for structure view first")

        if '**/*' in pattern and '.' not in pattern:
            suggestions.append(
                "Pattern '" + pattern + "' is very broad - may return too many results. Consider adding file extension filter"
            )

        return {
            'tool': 'Glob',
            'original_params': params,
            'optimized_params': optimized_params,
            'suggestions': suggestions,
            'token_savings': token_savings
        }

    def _intercept_edit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercept Edit calls and validate old_string uniqueness.

        Warns when old_string appears multiple times in the target file,
        which would cause the Edit tool to fail at runtime.
        """
        file_path = params.get('file_path', '')
        old_string = params.get('old_string', '')
        optimized_params = params.copy()
        suggestions: List[str] = []
        token_savings = 50

        suggestions.append("Optimization: Use brief confirmation (e.g., 'filepath:line -> change')")

        path = Path(file_path)
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                count = content.count(old_string)
                if count > 1:
                    suggestions.append(
                        'Warning: old_string appears ' + str(count) + ' times - Edit will fail! '
                        'Provide more context or use replace_all=True'
                    )
            except Exception:
                pass

        return {
            'tool': 'Edit',
            'original_params': params,
            'optimized_params': optimized_params,
            'suggestions': suggestions,
            'token_savings': token_savings
        }

    def _intercept_write(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercept Write calls and validate parent directory existence.

        Warns when the parent directory does not exist so the caller
        can create it before the Write tool is invoked.
        """
        file_path = params.get('file_path', '')
        optimized_params = params.copy()
        suggestions: List[str] = []
        token_savings = 50

        suggestions.append("Optimization: Use brief confirmation (e.g., 'filepath')")

        path = Path(file_path)
        if not path.parent.exists():
            suggestions.append(
                'Warning: Parent directory does not exist: ' + str(path.parent) + '. '
                'Create with: mkdir -p ' + str(path.parent)
            )

        return {
            'tool': 'Write',
            'original_params': params,
            'optimized_params': optimized_params,
            'suggestions': suggestions,
            'token_savings': token_savings
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def intercept_and_optimize(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Main entry point. Intercept and optimize any tool call.

        Args:
            tool_name: Name of the Claude tool.
            params:    Parameters dict. If None, kwargs are used as params.
            **kwargs:  Alternative way to supply parameters.

        Returns:
            Result dict with keys: tool, original_params, optimized_params,
            suggestions (list), token_savings (int).
        """
        if params is None:
            params = kwargs
        tool_lower = tool_name.lower()

        dispatch = {
            'bash':  self._intercept_bash,
            'read':  self._intercept_read,
            'grep':  self._intercept_grep,
            'glob':  self._intercept_glob,
            'edit':  self._intercept_edit,
            'write': self._intercept_write,
        }

        handler = dispatch.get(tool_lower)
        if handler:
            result = handler(params)
        else:
            result = {
                'tool': tool_name,
                'original_params': params,
                'optimized_params': params,
                'suggestions': [],
                'token_savings': 0
            }

        self._log_to_disk(result)
        return result

    def _log_to_disk(self, result: Dict[str, Any]) -> None:
        """
        Append optimization result as a JSON line to the tool optimization log.

        Args:
            result: The result dict returned by an intercept handler.
        """
        try:
            OPTIMIZATION_LOG.parent.mkdir(parents=True, exist_ok=True)
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'tool': result['tool'],
                'optimized': result['original_params'] != result['optimized_params'],
                'token_savings': result['token_savings'],
                'suggestions_count': len(result['suggestions'])
            }
            with open(OPTIMIZATION_LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as exc:
            logger.warning('Could not write optimization log: %s', exc)

    def format_result(self, result: Dict[str, Any]) -> str:
        """
        Format a result dict as a human-readable string for console output.

        Args:
            result: Result dict from intercept_and_optimize.

        Returns:
            Multi-line formatted string.
        """
        lines = [
            '',
            '=' * 70,
            'Tool Call Interceptor',
            '=' * 70,
            '',
            'Tool: ' + result['tool'],
        ]

        if result['original_params'] != result['optimized_params']:
            lines.append('Optimizations Applied:')
            for key in result['optimized_params']:
                orig_val = result['original_params'].get(key)
                opt_val = result['optimized_params'].get(key)
                if orig_val != opt_val:
                    lines.append('   ' + key + ': ' + str(orig_val) + ' -> ' + str(opt_val))
        else:
            lines.append('No optimizations needed (already optimal)')

        if result['suggestions']:
            lines.append('\nSuggestions (' + str(len(result['suggestions'])) + '):')
            for suggestion in result['suggestions']:
                lines.append('   ' + suggestion)

        if result['token_savings'] > 0:
            lines.append('\nToken Savings: ~' + str(result['token_savings']) + ' tokens')

        lines.append('')
        lines.append('=' * 70)
        lines.append('')
        return '\n'.join(lines)


# ===========================================================================
# AutoToolWrapper
# Consolidated from: auto-tool-wrapper.py
# ===========================================================================

class AutoToolWrapper:
    """
    Automatic tool parameter wrapper with tiered cache and AST integration.

    Applies a multi-strategy optimization pipeline for Read calls:
      1. HOT cache hit -> return cached content directly
      2. WARM cache hit -> return cached summary
      3. AST navigation for code files -> return structure instead of content
      4. Smart summarization for very large files
      5. File-type-specific optimization hints
      6. offset/limit injection for large files

    For Grep calls:
      - Conservative head_limit (start at 10 for progressive refinement)
      - File type filter suggestions
    """

    def __init__(self):
        """Initialize wrapper and create log directories."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug('AutoToolWrapper initialized.')

    # ------------------------------------------------------------------
    # Cache and external service helpers
    # ------------------------------------------------------------------

    def _check_tiered_cache(self, filepath: str) -> Optional[Dict[str, Any]]:
        """
        Query tiered cache script for a file.

        Falls back to local summary cache if the tiered cache script is unavailable.

        Args:
            filepath: Absolute path to the file to look up.

        Returns:
            Cache data dict with 'cache_hit' and optional 'tier' keys, or None.
        """
        try:
            tiered_cache_script = MEMORY_DIR / 'tiered-cache.py'
            if tiered_cache_script.exists():
                result = subprocess.run(
                    ['python', str(tiered_cache_script), '--get-file', filepath],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    if data.get('cache_hit'):
                        return data
        except Exception as exc:
            logger.debug('Tiered cache check failed: %s', exc)

        # Local summary cache fallback
        cache_file = SUMMARY_CACHE_DIR / (Path(filepath).name + '.json')
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data:
                    return {'cache_hit': True, 'tier': 'WARM', 'cached_data': data.get('summary')}
            except Exception:
                pass

        return None

    def _get_file_type_optimization(
        self,
        filepath: str,
        purpose: str = 'general'
    ) -> Optional[Dict[str, Any]]:
        """
        Query the file-type-optimizer script for reading strategy.

        Args:
            filepath: File to analyze.
            purpose:  Reading purpose hint (general, imports, structure, etc.).

        Returns:
            Optimization hint dict or None.
        """
        try:
            optimizer_script = MEMORY_DIR / 'file-type-optimizer.py'
            if optimizer_script.exists():
                result = subprocess.run(
                    ['python', str(optimizer_script), '--file', filepath, '--purpose', purpose],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return json.loads(result.stdout)
        except Exception as exc:
            logger.debug('File type optimization failed: %s', exc)
        return None

    def _should_summarize(self, filepath: str) -> bool:
        """
        Determine whether a file is large enough to warrant summarization.

        Args:
            filepath: File to evaluate.

        Returns:
            True if file has more than MEDIUM_FILE_THRESHOLD lines.
        """
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                line_count = sum(1 for _ in f)
            return line_count > MEDIUM_FILE_THRESHOLD
        except Exception:
            return False

    def _get_summary(self, filepath: str) -> Optional[Dict[str, Any]]:
        """
        Invoke the smart-file-summarizer script to summarize a large file.

        Args:
            filepath: File to summarize.

        Returns:
            Summary result dict or None.
        """
        try:
            summarizer_script = MEMORY_DIR / 'smart-file-summarizer.py'
            if summarizer_script.exists():
                result = subprocess.run(
                    ['python', str(summarizer_script), '--file', filepath, '--strategy', 'auto'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return json.loads(result.stdout)
        except Exception as exc:
            logger.debug('Smart summarizer failed: %s', exc)
        return None

    def _should_use_ast(self, filepath: str) -> bool:
        """
        Return True when the file extension is supported for AST navigation.

        Args:
            filepath: File path to check.

        Returns:
            True for .java, .ts, .tsx, .js, .py files.
        """
        ext = os.path.splitext(filepath)[1].lower()
        return ext in AST_SUPPORTED_EXTENSIONS

    def _get_ast_structure(self, filepath: str) -> Optional[Dict[str, Any]]:
        """
        Delegate AST navigation to the embedded ASTCodeNavigator.

        Args:
            filepath: Code file to analyze.

        Returns:
            AST structure dict or None on error.
        """
        try:
            navigator = ASTCodeNavigator()
            result = navigator.navigate(filepath, show_methods=False)
            if 'error' not in result:
                return result
        except Exception as exc:
            logger.debug('AST navigation failed: %s', exc)
        return None

    # ------------------------------------------------------------------
    # Per-tool wrapping
    # ------------------------------------------------------------------

    def wrap_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply multi-strategy optimization pipeline to a Read call.

        Pipeline order:
          1. HOT cache -> return immediately
          2. WARM cache -> note and continue
          3. AST navigation for code files
          4. Smart summarization for large files
          5. File-type hint
          6. offset/limit injection for large files

        Args:
            params: Original Read parameters dict.

        Returns:
            Result dict with 'optimized', 'strategy', and relevant data keys.
        """
        filepath = params.get('file_path', '')

        if not filepath or not os.path.exists(filepath):
            return {
                'optimized': False,
                'original_params': params,
                'message': 'File not found or invalid'
            }

        optimizations: List[Dict[str, Any]] = []

        # 1. Tiered cache
        cache_data = self._check_tiered_cache(filepath)
        if cache_data and cache_data.get('cache_hit'):
            tier = cache_data.get('tier', 'WARM')
            if tier == 'HOT':
                optimizations.append({
                    'type': 'cache_hit_hot',
                    'tokens_saved': 1500,
                    'message': 'Using cached full content (HOT tier)'
                })
                self._log_token_optimization('Read', 'cache_hit_hot', 1500, filepath)
                return {
                    'optimized': True,
                    'strategy': 'cache_hot',
                    'use_cache': True,
                    'cache_data': cache_data.get('cached_data'),
                    'optimizations': optimizations
                }
            elif tier == 'WARM':
                optimizations.append({
                    'type': 'cache_hit_warm',
                    'tokens_saved': 1000,
                    'message': 'Using cached summary (WARM tier)'
                })

        # 2. AST navigation
        if self._should_use_ast(filepath):
            ast_data = self._get_ast_structure(filepath)
            if ast_data:
                optimizations.append({
                    'type': 'ast_navigation',
                    'tokens_saved': 1800,
                    'message': 'Using AST structure instead of full read'
                })
                self._log_token_optimization('Read', 'ast_navigation', 1800, filepath)
                return {
                    'optimized': True,
                    'strategy': 'ast',
                    'ast_data': ast_data,
                    'optimizations': optimizations
                }

        # 3. Smart summarization
        if self._should_summarize(filepath):
            summary_data = self._get_summary(filepath)
            if summary_data and not summary_data.get('error'):
                raw_savings = summary_data.get('token_savings', '70%')
                if isinstance(raw_savings, str):
                    raw_savings = int(raw_savings.replace('%', '')) * 20
                optimizations.append({
                    'type': 'smart_summary',
                    'tokens_saved': raw_savings,
                    'message': 'Using ' + str(summary_data.get('strategy')) + ' summary'
                })
                self._log_token_optimization('Read', 'smart_summary', raw_savings, filepath)
                return {
                    'optimized': True,
                    'strategy': 'summary',
                    'summary_data': summary_data,
                    'optimizations': optimizations
                }

        # 4. File-type optimization hint
        file_opt = self._get_file_type_optimization(filepath)
        if file_opt:
            optimizations.append({
                'type': 'file_type_optimization',
                'tokens_saved': 500,
                'message': file_opt.get('recommended_strategy', '')
            })

        # 5. offset/limit injection
        if self._should_summarize(filepath) and 'offset' not in params:
            params['offset'] = 0
            params['limit'] = LARGE_FILE_READ_LIMIT
            optimizations.append({
                'type': 'offset_limit',
                'tokens_saved': 1000,
                'message': 'Applied offset=0, limit=' + str(LARGE_FILE_READ_LIMIT) + ' for large file'
            })

        for opt in optimizations:
            self._log_token_optimization('Read', opt['type'], opt['tokens_saved'], opt['message'])

        return {
            'optimized': len(optimizations) > 0,
            'strategy': 'optimized_read',
            'optimized_params': params,
            'optimizations': optimizations,
            'total_tokens_saved': sum(opt['tokens_saved'] for opt in optimizations)
        }

    def wrap_grep(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply conservative defaults to a Grep call.

        Starts with head_limit=10 for progressive refinement, then lets
        the user widen the search incrementally.

        Args:
            params: Original Grep parameters dict.

        Returns:
            Result dict with 'optimized' flag and 'optimized_params'.
        """
        optimizations: List[Dict[str, Any]] = []

        if 'head_limit' not in params:
            params['head_limit'] = 10
            optimizations.append({
                'type': 'smart_grep_limit',
                'tokens_saved': 360,
                'message': 'Applied head_limit=10 (progressive refinement)'
            })

        pattern = params.get('pattern', '')
        if pattern and 'type' not in params and 'glob' not in params:
            optimizations.append({
                'type': 'grep_suggestion',
                'tokens_saved': 0,
                'message': 'Consider adding --type or --glob to narrow search'
            })

        for opt in optimizations:
            self._log_token_optimization('Grep', opt['type'], opt['tokens_saved'], opt['message'])

        return {
            'optimized': len(optimizations) > 0,
            'optimized_params': params,
            'optimizations': optimizations,
            'total_tokens_saved': sum(opt['tokens_saved'] for opt in optimizations)
        }

    def wrap(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main wrapping entry point.

        Args:
            tool:   Tool name (Read, Grep, Glob).
            params: Tool parameters dict.

        Returns:
            Optimization result dict.
        """
        if tool == 'Read':
            return self.wrap_read(params)
        elif tool == 'Grep':
            return self.wrap_grep(params)
        else:
            return {'optimized': False, 'message': 'Tool ' + tool + ' not supported by AutoToolWrapper'}

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def _log_token_optimization(
        self,
        tool: str,
        optimization_type: str,
        tokens_saved: int,
        details: str = ''
    ) -> None:
        """
        Append a token optimization event to the token log file.

        Args:
            tool:              Tool name.
            optimization_type: Short label for the optimization applied.
            tokens_saved:      Estimated tokens saved.
            details:           Additional detail string.
        """
        try:
            TOKEN_LOG.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_entry = (
                '[' + timestamp + '] ' + tool + ' | ' + optimization_type + ' | '
                'Saved: ' + str(tokens_saved) + ' tokens | ' + details + '\n'
            )
            with open(TOKEN_LOG, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as exc:
            logger.warning('Could not write token log: %s', exc)


# ===========================================================================
# PreExecutionOptimizer
# Consolidated from: pre-execution-optimizer.py
# ===========================================================================

class PreExecutionOptimizer:
    """
    Pre-execution parameter optimizer.

    Validates and transforms tool parameters immediately before tool execution:
      - Read: file size check with offset/limit injection and cache suggestion
      - Grep: head_limit and output_mode defaults
      - Glob: pass-through (already efficient)
      - Bash: detects anti-patterns and recommends dedicated tools

    This optimizer persists access counts to disk so cache suggestions survive
    across multiple calls in the same session.
    """

    def __init__(self):
        """Initialize with default thresholds."""
        self.max_file_lines = MEDIUM_FILE_THRESHOLD
        self.max_grep_results = DEFAULT_GREP_LIMIT
        self.cache_threshold = CACHE_THRESHOLD

    # ------------------------------------------------------------------
    # Per-tool optimization
    # ------------------------------------------------------------------

    def optimize_read(
        self,
        file_path: str,
        full_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Inject offset/limit for files that exceed the line threshold.

        Args:
            file_path:   Absolute path to the file.
            full_params: Complete Read parameters dict.

        Returns:
            Either the original params dict (small file) or a new dict
            with 'optimized', 'warning', and 'total_lines' keys.
        """
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            return full_params

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                line_count = sum(1 for _ in f)
        except Exception:
            return full_params

        if line_count > self.max_file_lines:
            optimized = full_params.copy()
            optimized['limit'] = self.max_file_lines
            optimized['offset'] = 0
            return {
                'optimized': optimized,
                'warning': (
                    'File has ' + str(line_count) + ' lines, reading first ' + str(self.max_file_lines) + '. '
                    'Use offset to read more.'
                ),
                'total_lines': line_count
            }

        return full_params

    def optimize_grep(self, full_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enforce head_limit and output_mode defaults for Grep.

        Args:
            full_params: Original Grep parameters dict.

        Returns:
            Dict with 'optimized' key containing updated params, and 'note'.
        """
        optimized = full_params.copy()

        if 'head_limit' not in optimized or optimized['head_limit'] == 0:
            optimized['head_limit'] = self.max_grep_results

        if 'output_mode' not in optimized:
            optimized['output_mode'] = 'files_with_matches'

        return {
            'optimized': optimized,
            'note': 'Limited to ' + str(optimized['head_limit']) + ' results'
        }

    def optimize_glob(self, full_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pass-through for Glob (already efficient by design).

        Args:
            full_params: Glob parameters dict.

        Returns:
            The same params dict unchanged.
        """
        return full_params

    def optimize_bash(self, command: str) -> Dict[str, Any]:
        """
        Detect anti-patterns in Bash commands and suggest alternatives.

        Detects:
          - cat/head/tail -> suggest Read tool
          - grep/rg       -> suggest Grep tool
          - find          -> suggest Glob tool
          - Complex pipes (> 2) -> warn about inefficiency

        Args:
            command: The bash command string.

        Returns:
            Dict with 'command' and optional 'warnings' list.
        """
        warnings: List[str] = []

        if any(cmd in command for cmd in ['cat ', 'head ', 'tail ']):
            warnings.append('Consider using Read tool instead of cat/head/tail')

        if 'grep ' in command or 'rg ' in command:
            warnings.append('Consider using Grep tool instead of grep/rg')

        if 'find ' in command:
            warnings.append('Consider using Glob tool instead of find')

        if command.count('|') > 2:
            warnings.append('Complex piped command may be inefficient')

        result: Dict[str, Any] = {'command': command}
        if warnings:
            result['warnings'] = warnings
        return result

    def _check_cache_eligibility(self, file_path: str) -> bool:
        """
        Increment access count and return True when count >= cache_threshold.

        Args:
            file_path: File to track.

        Returns:
            True if file should now be cached.
        """
        ACCESS_COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)

        try:
            if ACCESS_COUNT_FILE.exists():
                access_count = json.loads(ACCESS_COUNT_FILE.read_text(encoding='utf-8'))
            else:
                access_count = {}
        except Exception:
            access_count = {}

        access_count[str(file_path)] = access_count.get(str(file_path), 0) + 1
        ACCESS_COUNT_FILE.write_text(json.dumps(access_count, indent=2), encoding='utf-8')

        return access_count[str(file_path)] >= self.cache_threshold

    def _check_summary_cache(self, file_path: str) -> Optional[str]:
        """
        Look up a cached file summary.

        Args:
            file_path: File path to look up.

        Returns:
            Cached summary string or None.
        """
        cache_file = SUMMARY_CACHE_DIR / (Path(file_path).name + '.json')
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding='utf-8'))
                return cached.get('summary')
            except Exception:
                pass
        return None

    def optimize(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main pre-execution optimization entry point.

        Args:
            tool:   Tool name (Read, Grep, Glob, Bash).
            params: Tool parameters dict.

        Returns:
            Optimized parameters dict or enriched result dict.
        """
        if tool == 'Read':
            file_path = params.get('file_path')
            if file_path:
                if self._check_cache_eligibility(file_path):
                    cached_summary = self._check_summary_cache(file_path)
                    if cached_summary:
                        return {
                            'use_cache': True,
                            'cached_summary': cached_summary,
                            'note': 'Using cached summary (file accessed 3+ times)'
                        }
                return self.optimize_read(file_path, params)

        elif tool == 'Grep':
            return self.optimize_grep(params)

        elif tool == 'Glob':
            return self.optimize_glob(params)

        elif tool == 'Bash':
            command = params.get('command', '')
            return self.optimize_bash(command)

        return params


# ===========================================================================
# ASTCodeNavigator
# Consolidated from: ast-code-navigator.py
# ===========================================================================

class ASTCodeNavigator:
    """
    AST-based code structure extractor.

    Extracts class/method/function signatures from source files without
    requiring a full file read. Supports Java, TypeScript, JavaScript, and Python.

    Provides 95%+ token savings vs full file reads for large code files.
    """

    def __init__(self):
        """Initialize navigator (stateless, no setup required)."""
        logger.debug('ASTCodeNavigator initialized.')

    # ------------------------------------------------------------------
    # Language-specific parsers
    # ------------------------------------------------------------------

    def _navigate_java(self, filepath: str, show_methods: bool = False) -> Dict[str, Any]:
        """
        Extract Java file structure using regex-based parsing.

        Extracts:
          - Package declaration
          - Import statements (first 10)
          - Class declarations
          - Interface declarations
          - Method signatures (optional, when show_methods=True)

        Args:
            filepath:     Path to .java file.
            show_methods: When True, extract method signatures.

        Returns:
            Structure dict or {'error': message} on failure.
        """
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            package = re.search(r'package\s+([\w.]+);', content)
            imports = re.findall(r'import\s+([\w.]+);', content)
            classes = re.findall(r'(?:public\s+)?class\s+(\w+)', content)
            interfaces = re.findall(r'(?:public\s+)?interface\s+(\w+)', content)
            enums = re.findall(r'(?:public\s+)?enum\s+(\w+)', content)
            annotations = re.findall(r'@(\w+)', content)

            result: Dict[str, Any] = {
                'file': filepath,
                'language': 'java',
                'package': package.group(1) if package else None,
                'imports': imports[:10],
                'classes': classes,
                'interfaces': interfaces,
                'enums': enums,
                'annotations': list(set(annotations))[:10],
            }

            if show_methods:
                methods = re.findall(
                    r'(public|private|protected)\s+(?:static\s+)?(?:final\s+)?(\w+)\s+(\w+)\s*\([^)]*\)',
                    content
                )
                result['methods'] = [
                    {'visibility': m[0], 'return_type': m[1], 'name': m[2]}
                    for m in methods
                ]

            return result

        except Exception as exc:
            return {'error': str(exc)}

    def _navigate_typescript(
        self,
        filepath: str,
        show_methods: bool = False
    ) -> Dict[str, Any]:
        """
        Extract TypeScript/JavaScript file structure using regex-based parsing.

        Extracts:
          - Import sources
          - Exported classes, interfaces, functions, constants, types

        Args:
            filepath:     Path to .ts, .tsx, or .js file.
            show_methods: When True, extract method signatures from classes.

        Returns:
            Structure dict or {'error': message} on failure.
        """
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            imports = re.findall(r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]', content)
            classes = re.findall(r'export\s+(?:default\s+)?class\s+(\w+)', content)
            interfaces = re.findall(r'export\s+interface\s+(\w+)', content)
            functions = re.findall(r'export\s+(?:async\s+)?function\s+(\w+)', content)
            consts = re.findall(r'export\s+const\s+(\w+)', content)
            types = re.findall(r'export\s+type\s+(\w+)', content)

            result: Dict[str, Any] = {
                'file': filepath,
                'language': 'typescript',
                'imports': imports[:10],
                'classes': classes,
                'interfaces': interfaces,
                'functions': functions,
                'constants': consts,
                'types': types,
            }

            if show_methods:
                class_methods = re.findall(
                    r'(\w+)\s*\([^)]*\)\s*:\s*(\w+)',
                    content
                )
                result['methods'] = [
                    {'name': m[0], 'return_type': m[1]}
                    for m in class_methods
                ]

            return result

        except Exception as exc:
            return {'error': str(exc)}

    def _navigate_python(
        self,
        filepath: str,
        show_methods: bool = False
    ) -> Dict[str, Any]:
        """
        Extract Python file structure using the built-in ast module.

        Extracts:
          - Import statements (first 10)
          - Class definitions with optional method lists
          - Top-level function definitions

        Args:
            filepath:     Path to .py file.
            show_methods: When True, include method names inside classes.

        Returns:
            Structure dict or {'error': message} on failure.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source, filename=filepath)
        except Exception as exc:
            return {'error': str(exc)}

        imports: List[str] = []
        classes: List[Dict[str, Any]] = []
        functions: List[Dict[str, Any]] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
            elif isinstance(node, ast.ClassDef):
                class_entry: Dict[str, Any] = {
                    'name': node.name,
                    'line': node.lineno,
                }
                if show_methods:
                    class_entry['methods'] = [
                        {'name': m.name, 'line': m.lineno}
                        for m in node.body
                        if isinstance(m, ast.FunctionDef)
                    ]
                classes.append(class_entry)
            elif isinstance(node, ast.FunctionDef):
                functions.append({'name': node.name, 'line': node.lineno})

        return {
            'file': filepath,
            'language': 'python',
            'imports': imports[:10],
            'classes': classes,
            'functions': functions,
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def navigate(
        self,
        filepath: str,
        show_methods: bool = False
    ) -> Dict[str, Any]:
        """
        Extract code structure from a file based on its extension.

        Args:
            filepath:     Path to source code file.
            show_methods: When True, include method/function signatures.

        Returns:
            Structure dict appropriate for the file type, or {'error': ...}.
        """
        ext = os.path.splitext(filepath)[1].lower()

        if ext == '.java':
            return self._navigate_java(filepath, show_methods)
        elif ext in ('.ts', '.tsx', '.js'):
            return self._navigate_typescript(filepath, show_methods)
        elif ext == '.py':
            return self._navigate_python(filepath, show_methods)
        else:
            return {
                'error': 'Unsupported file type: ' + ext,
                'supported': list(AST_SUPPORTED_EXTENSIONS)
            }

    def is_supported(self, filepath: str) -> bool:
        """
        Check whether AST navigation is supported for a file.

        Args:
            filepath: File path to check.

        Returns:
            True if the file extension is in AST_SUPPORTED_EXTENSIONS.
        """
        ext = os.path.splitext(filepath)[1].lower()
        return ext in AST_SUPPORTED_EXTENSIONS

    def format_structure(self, structure: Dict[str, Any]) -> str:
        """
        Format a navigation result as a compact human-readable string.

        Args:
            structure: Result dict from navigate().

        Returns:
            Multi-line string summarizing the code structure.
        """
        if 'error' in structure:
            return '[ERROR] ' + structure['error']

        lang = structure.get('language', 'unknown').upper()
        filepath = structure.get('file', '?')
        lines = ['[' + lang + '] ' + filepath]

        if structure.get('package'):
            lines.append('  Package: ' + structure['package'])

        classes = structure.get('classes', [])
        if classes:
            class_names = [
                c['name'] if isinstance(c, dict) else c
                for c in classes
            ]
            lines.append('  Classes: ' + ', '.join(class_names))

        interfaces = structure.get('interfaces', [])
        if interfaces:
            lines.append('  Interfaces: ' + ', '.join(interfaces))

        functions = structure.get('functions', [])
        if functions:
            fn_names = [
                f['name'] if isinstance(f, dict) else f
                for f in functions
            ]
            lines.append('  Functions: ' + ', '.join(fn_names))

        methods = structure.get('methods', [])
        if methods:
            method_names = [
                m['name'] if isinstance(m, dict) else str(m)
                for m in methods[:10]
            ]
            suffix = ' (+' + str(len(methods) - 10) + ' more)' if len(methods) > 10 else ''
            lines.append('  Methods: ' + ', '.join(method_names) + suffix)

        imports = structure.get('imports', [])
        if imports:
            lines.append('  Imports (' + str(len(imports)) + '): ' + ', '.join(imports[:5]) + '...')

        return '\n'.join(lines)


# ===========================================================================
# SmartReadOptimizer
# Consolidated from: smart-read.py
# ===========================================================================

class SmartReadOptimizer:
    """
    Smart file reading strategy advisor.

    Analyzes a file's size and type to recommend the most token-efficient
    reading approach:
      - binary    : Skip reading, use file metadata only
      - small     : Read full content
      - medium    : Read full or with limit=500
      - large     : Read with offset=0, limit=500
      - very_large: Use Grep instead; offer chunked Read as alternative

    Also provides batch recommendations when multiple files are queued,
    deduplicating and prioritizing by importance.
    """

    def __init__(self):
        """Initialize smart read optimizer."""
        self._analysis_cache: Dict[str, Dict[str, Any]] = {}
        logger.debug('SmartReadOptimizer initialized.')

    # ------------------------------------------------------------------
    # File analysis
    # ------------------------------------------------------------------

    def analyze_file(self, filepath: str) -> Dict[str, Any]:
        """
        Analyze a file and produce a reading strategy recommendation.

        Args:
            filepath: Absolute or relative path to the file.

        Returns:
            Analysis dict with keys: filepath, size_bytes, size_kb, size_mb,
            lines, strategy (sub-dict with type, recommendation, command,
            read bool, and optional params/alternative).
        """
        if filepath in self._analysis_cache:
            return self._analysis_cache[filepath]

        if not os.path.exists(filepath):
            return {'error': 'File not found: ' + filepath}

        size = os.path.getsize(filepath)
        size_kb = size / 1024
        size_mb = size_kb / 1024

        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                lines = sum(1 for _ in f)
        except Exception:
            lines = 0

        strategy = self._determine_strategy(filepath, lines)

        result: Dict[str, Any] = {
            'filepath': filepath,
            'size_bytes': size,
            'size_kb': round(size_kb, 2),
            'size_mb': round(size_mb, 4),
            'lines': lines,
            'strategy': strategy
        }

        self._analysis_cache[filepath] = result
        return result

    def _determine_strategy(self, filepath: str, lines: int) -> Dict[str, Any]:
        """
        Select the reading strategy based on line count and file type.

        Args:
            filepath: File path (used for extension check).
            lines:    Number of lines in the file.

        Returns:
            Strategy dict with type, recommendation, command, read flag,
            and optional params/alternative.
        """
        ext = os.path.splitext(filepath)[1].lower()
        is_code = ext in AST_SUPPORTED_EXTENSIONS

        if lines == 0:
            return {
                'type': 'binary',
                'recommendation': 'Binary file - use file metadata only',
                'command': 'file ' + filepath,
                'read': False
            }

        if lines < SMALL_FILE_THRESHOLD:
            return {
                'type': 'small',
                'recommendation': 'Small file - read full content',
                'command': 'Read ' + filepath,
                'read': True,
                'params': {}
            }

        if lines < MEDIUM_FILE_THRESHOLD:
            if is_code:
                return {
                    'type': 'medium_code',
                    'recommendation': 'Medium code file - consider AST navigation first',
                    'command': 'ASTCodeNavigator.navigate(' + filepath + ')',
                    'read': True,
                    'params': {'limit': MEDIUM_FILE_THRESHOLD}
                }
            return {
                'type': 'medium',
                'recommendation': 'Medium file - read full or with limit',
                'command': 'Read ' + filepath,
                'read': True,
                'params': {'limit': MEDIUM_FILE_THRESHOLD}
            }

        if lines < LARGE_FILE_THRESHOLD:
            if is_code:
                return {
                    'type': 'large_code',
                    'recommendation': 'Large code file - use AST navigation or offset/limit',
                    'command': 'ASTCodeNavigator.navigate(' + filepath + ', show_methods=True)',
                    'read': True,
                    'params': {'offset': 0, 'limit': LARGE_FILE_READ_LIMIT}
                }
            return {
                'type': 'large',
                'recommendation': 'Large file - use offset/limit',
                'command': 'Read ' + filepath + ' (offset=0, limit=' + str(LARGE_FILE_READ_LIMIT) + ')',
                'read': True,
                'params': {'offset': 0, 'limit': LARGE_FILE_READ_LIMIT}
            }

        return {
            'type': 'very_large',
            'recommendation': 'Very large file - read in chunks or use Grep',
            'command': 'Grep pattern ' + filepath + ' --head_limit ' + str(DEFAULT_GREP_LIMIT),
            'read': False,
            'alternative': 'Read ' + filepath + ' (offset=0, limit=' + str(LARGE_FILE_READ_LIMIT) + ') for first chunk'
        }

    def get_read_params(self, filepath: str) -> Dict[str, Any]:
        """
        Convenience method: return only the recommended Read parameters.

        Args:
            filepath: File to analyze.

        Returns:
            Params dict (may be empty for small files or contain offset/limit).
        """
        analysis = self.analyze_file(filepath)
        if 'error' in analysis:
            return {}
        return analysis['strategy'].get('params', {})

    def format_analysis(self, analysis: Dict[str, Any]) -> str:
        """
        Format an analysis result as a human-readable console report.

        Args:
            analysis: Result dict from analyze_file().

        Returns:
            Multi-line formatted string.
        """
        if 'error' in analysis:
            return 'ERROR: ' + analysis['error']

        strategy = analysis['strategy']
        lines = [
            '',
            '=' * 60,
            'SMART READ ANALYSIS',
            '=' * 60,
            '',
            'File:  ' + analysis['filepath'],
            'Size:  ' + str(analysis['size_kb']) + ' KB (' + str(analysis['size_bytes']) + ' bytes)',
            'Lines: ' + str(analysis['lines']),
            'Type:  ' + strategy['type'].upper(),
            '',
            'RECOMMENDATION:',
            '  ' + strategy['recommendation'],
            '',
            'COMMAND:',
            '  ' + strategy['command'],
        ]

        if 'alternative' in strategy:
            lines += ['', 'ALTERNATIVE:', '  ' + strategy['alternative']]

        if strategy.get('read') and strategy.get('params'):
            params = strategy['params']
            if params:
                lines += ['', 'PARAMETERS:']
                for key, value in params.items():
                    lines.append('  ' + key + ': ' + str(value))

        lines += ['', '=' * 60, '']
        return '\n'.join(lines)

    def batch_analyze(self, filepaths: List[str]) -> List[Dict[str, Any]]:
        """
        Analyze multiple files and return sorted recommendations.

        Files are deduplicated and sorted by size descending so that the
        most impactful optimizations are surfaced first.

        Args:
            filepaths: List of file paths to analyze.

        Returns:
            List of analysis dicts sorted by size_bytes descending.
        """
        unique_paths = list(dict.fromkeys(filepaths))
        results = [self.analyze_file(fp) for fp in unique_paths]
        valid = [r for r in results if 'error' not in r]
        valid.sort(key=lambda r: r['size_bytes'], reverse=True)
        return valid


# ===========================================================================
# ToolOptimizationPolicy
# The unified policy interface
# ===========================================================================

class ToolOptimizationPolicy:
    """
    Unified tool optimization policy.

    Composes all six optimization subsystems into a single interface
    that conforms to the claude-insight policy contract:

      enforce()  - Initialize all subsystems and run startup validation
      validate() - Check compliance against all optimization rules
      report()   - Generate a comprehensive optimization statistics report

    Also provides CLI dispatch for all interactive modes.
    """

    VERSION = '1.0.0'
    POLICY_NAME = 'ToolUsageOptimizationPolicy'

    def __init__(self):
        """Initialize all optimization subsystems."""
        self.optimizer = ToolUsageOptimizer()
        self.interceptor = ToolCallInterceptor()
        self.wrapper = AutoToolWrapper()
        self.pre_optimizer = PreExecutionOptimizer()
        self.ast_navigator = ASTCodeNavigator()
        self.smart_reader = SmartReadOptimizer()
        self._session_start = datetime.now()
        logger.info('[%s] Initialized (v%s)', self.POLICY_NAME, self.VERSION)

    # ------------------------------------------------------------------
    # Policy interface
    # ------------------------------------------------------------------

    def enforce(self) -> Dict[str, Any]:
        """
        Initialize all optimization subsystems and validate readiness.

        Performs:
          - Directory creation for cache and logs
          - Subsystem health checks
          - Baseline configuration validation

        Returns:
            Result dict with 'status', 'subsystems', and 'checks' lists.
        """
        _track_start_time = datetime.now()
        _sub_operations = []
        print('\n' + '=' * 65)
        print('[ENFORCE] ' + self.POLICY_NAME + ' v' + self.VERSION)
        print('=' * 65)

        checks: List[Dict[str, Any]] = []

        # Ensure required directories exist
        _op_start = datetime.now()
        for directory in [CACHE_DIR, LOGS_DIR, SUMMARY_CACHE_DIR]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                checks.append({'check': 'Directory: ' + directory.name, 'status': 'OK'})
            except Exception as exc:
                checks.append({'check': 'Directory: ' + directory.name, 'status': 'FAIL', 'error': str(exc)})
        try:
            _sub_operations.append(record_sub_operation(
                "init_directories", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000)
            ))
        except Exception:
            pass

        # Validate subsystem initialization
        _op_start = datetime.now()
        subsystems = [
            ('ToolUsageOptimizer', self.optimizer),
            ('ToolCallInterceptor', self.interceptor),
            ('AutoToolWrapper', self.wrapper),
            ('PreExecutionOptimizer', self.pre_optimizer),
            ('ASTCodeNavigator', self.ast_navigator),
            ('SmartReadOptimizer', self.smart_reader),
        ]

        subsystem_status: List[Dict[str, str]] = []
        for name, obj in subsystems:
            status = 'OK' if obj is not None else 'FAIL'
            subsystem_status.append({'subsystem': name, 'status': status})
            icon = '[OK]' if status == 'OK' else '[FAIL]'
            print('  ' + icon + ' ' + name)
        try:
            _sub_operations.append(record_sub_operation(
                "validate_subsystems", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {"subsystem_count": len(subsystems)}
            ))
        except Exception:
            pass

        # Validate configuration thresholds
        _op_start = datetime.now()
        config_checks = [
            ('SMALL_FILE_THRESHOLD', SMALL_FILE_THRESHOLD, 50, 500),
            ('MEDIUM_FILE_THRESHOLD', MEDIUM_FILE_THRESHOLD, 100, 2000),
            ('LARGE_FILE_THRESHOLD', LARGE_FILE_THRESHOLD, 500, 10000),
            ('CACHE_THRESHOLD', CACHE_THRESHOLD, 1, 10),
            ('DEFAULT_GREP_LIMIT', DEFAULT_GREP_LIMIT, 10, 1000),
        ]

        for name, value, min_val, max_val in config_checks:
            ok = min_val <= value <= max_val
            icon = '[OK]' if ok else '[WARN]'
            checks.append({'check': name, 'value': value, 'status': 'OK' if ok else 'WARN'})
            print('  ' + icon + ' ' + name + '=' + str(value))
        try:
            _sub_operations.append(record_sub_operation(
                "validate_config_thresholds", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000)
            ))
        except Exception:
            pass

        all_ok = all(s['status'] == 'OK' for s in subsystem_status)
        overall = 'OK' if all_ok else 'DEGRADED'
        print('\n  Overall: ' + overall)
        print('=' * 65 + '\n')

        result = {
            'status': overall,
            'version': self.VERSION,
            'policy': self.POLICY_NAME,
            'subsystems': subsystem_status,
            'checks': checks
        }
        try:
            if HAS_TRACKING:
                record_policy_execution(
                    session_id=os.environ.get('CLAUDE_SESSION_ID', 'unknown'),
                    policy_name="tool-usage-optimization-policy",
                    policy_script="tool-usage-optimization-policy.py",
                    policy_type="Policy Script",
                    input_params={},
                    output_results={"status": overall, "subsystem_count": len(subsystems)},
                    decision=f"tool optimization subsystems initialized status={overall}",
                    duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                    sub_operations=_sub_operations if _sub_operations else None
                )
        except Exception:
            pass
        return result

    def validate(self) -> Dict[str, Any]:
        """
        Run a compliance check against all optimization rules.

        Validates:
          - Cache directory accessibility
          - Log directory write permission
          - AST support for common file types
          - Threshold sanity (no inversion)
          - Optimization log integrity

        Returns:
            Validation result dict with 'passed', 'failed', and 'warnings' lists.
        """
        print('\n' + '=' * 65)
        print('[VALIDATE] ' + self.POLICY_NAME)
        print('=' * 65)

        passed: List[str] = []
        failed: List[str] = []
        warnings: List[str] = []

        # Rule 1: Cache directory writable
        test_file = CACHE_DIR / '.write_test'
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            test_file.write_text('test', encoding='utf-8')
            test_file.unlink()
            passed.append('Cache directory is writable')
        except Exception as exc:
            failed.append('Cache directory not writable: ' + str(exc))

        # Rule 2: Logs directory writable
        test_log = LOGS_DIR / '.write_test'
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            test_log.write_text('test', encoding='utf-8')
            test_log.unlink()
            passed.append('Logs directory is writable')
        except Exception as exc:
            failed.append('Logs directory not writable: ' + str(exc))

        # Rule 3: AST navigation functional
        try:
            import ast as ast_module
            test_src = 'class Foo:\n    def bar(self): pass\n'
            ast_module.parse(test_src)
            passed.append('Python AST module functional')
        except Exception as exc:
            failed.append('Python AST module failed: ' + str(exc))

        # Rule 4: Threshold sanity
        if SMALL_FILE_THRESHOLD < MEDIUM_FILE_THRESHOLD < LARGE_FILE_THRESHOLD:
            passed.append('File size thresholds are correctly ordered')
        else:
            failed.append('File size thresholds are incorrectly ordered')

        # Rule 5: grep limit is positive
        if DEFAULT_GREP_LIMIT > 0:
            passed.append('Default grep limit is positive (' + str(DEFAULT_GREP_LIMIT) + ')')
        else:
            failed.append('Default grep limit must be positive')

        # Rule 6: Cache threshold is positive
        if CACHE_THRESHOLD > 0:
            passed.append('Cache threshold is positive (' + str(CACHE_THRESHOLD) + ')')
        else:
            failed.append('Cache threshold must be positive')

        # Rule 7: Optimization log integrity (if log exists)
        if OPTIMIZATION_LOG.exists():
            try:
                corrupt_lines = 0
                with open(OPTIMIZATION_LOG, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                json.loads(line)
                            except json.JSONDecodeError:
                                corrupt_lines += 1
                if corrupt_lines == 0:
                    passed.append('Optimization log integrity OK')
                else:
                    warnings.append('Optimization log has ' + str(corrupt_lines) + ' corrupt entries')
            except Exception as exc:
                warnings.append('Could not validate optimization log: ' + str(exc))
        else:
            passed.append('Optimization log not yet created (will be created on first use)')

        # Print results
        for item in passed:
            print('  [PASS] ' + item)
        for item in warnings:
            print('  [WARN] ' + item)
        for item in failed:
            print('  [FAIL] ' + item)

        overall = 'PASS' if not failed else 'FAIL'
        print('\n  Result: ' + overall + ' (' + str(len(passed)) + ' passed, ' + str(len(warnings)) + ' warnings, ' + str(len(failed)) + ' failed)')
        print('=' * 65 + '\n')

        return {
            'result': overall,
            'passed': passed,
            'warnings': warnings,
            'failed': failed
        }

    def report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive optimization statistics report.

        Reads:
          - In-memory session statistics from ToolUsageOptimizer
          - On-disk optimization log from ToolCallInterceptor
          - Token optimization log from AutoToolWrapper

        Returns:
            Report dict with session_stats, disk_stats, token_stats, and summary.
        """
        print('\n' + '=' * 65)
        print('[REPORT] ' + self.POLICY_NAME)
        print('=' * 65)

        # Session stats from in-memory optimizer
        session_stats = self.optimizer.get_session_stats()

        # Parse on-disk optimization log
        disk_stats: Dict[str, Any] = {
            'total_logged': 0,
            'total_optimized': 0,
            'total_token_savings': 0,
            'by_tool': {}
        }

        if OPTIMIZATION_LOG.exists():
            try:
                with open(OPTIMIZATION_LOG, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            disk_stats['total_logged'] += 1
                            if entry.get('optimized'):
                                disk_stats['total_optimized'] += 1
                            disk_stats['total_token_savings'] += entry.get('token_savings', 0)
                            tool = entry.get('tool', 'unknown')
                            disk_stats['by_tool'][tool] = disk_stats['by_tool'].get(tool, 0) + 1
                        except json.JSONDecodeError:
                            pass
            except Exception as exc:
                logger.warning('Could not read optimization log: %s', exc)

        # Parse token log
        token_stats: Dict[str, Any] = {
            'total_logged': 0,
            'total_tokens_saved': 0,
            'by_type': {}
        }

        if TOKEN_LOG.exists():
            try:
                with open(TOKEN_LOG, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        token_stats['total_logged'] += 1
                        saved_match = re.search(r'Saved:\s*(\d+)\s*tokens', line)
                        if saved_match:
                            token_stats['total_tokens_saved'] += int(saved_match.group(1))
                        type_match = re.search(r'\|\s*([^|]+)\s*\|', line)
                        if type_match:
                            opt_type = type_match.group(1).strip()
                            token_stats['by_type'][opt_type] = (
                                token_stats['by_type'].get(opt_type, 0) + 1
                            )
            except Exception as exc:
                logger.warning('Could not read token log: %s', exc)

        # Print report
        session_duration = (datetime.now() - self._session_start).total_seconds()
        print('  Session Duration:        ' + str(int(session_duration)) + 's')
        print('  In-Memory Optimizations: ' + str(session_stats['total_optimizations']))
        print('  Avg Savings (session):   ' + str(session_stats['average_savings_pct']) + '%')
        print('  Per-tool (session):      ' + str(session_stats['by_tool']))
        print()
        print('  [Disk] Total Logged:     ' + str(disk_stats['total_logged']))
        print('  [Disk] Total Optimized:  ' + str(disk_stats['total_optimized']))
        print('  [Disk] Token Savings:    ~' + str(disk_stats['total_token_savings']) + ' tokens')
        print('  [Disk] By Tool:          ' + str(disk_stats['by_tool']))
        print()
        print('  [Token Log] Entries:     ' + str(token_stats['total_logged']))
        print('  [Token Log] Total Saved: ~' + str(token_stats['total_tokens_saved']) + ' tokens')
        print('  [Token Log] By Type:     ' + str(token_stats['by_type']))
        print('=' * 65 + '\n')

        return {
            'policy': self.POLICY_NAME,
            'version': self.VERSION,
            'session_stats': session_stats,
            'disk_stats': disk_stats,
            'token_stats': token_stats,
        }

    # ------------------------------------------------------------------
    # Convenience delegation methods
    # ------------------------------------------------------------------

    def optimize_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Delegate a tool optimization request to ToolUsageOptimizer.

        Args:
            tool_name: Name of the tool to optimize.
            params:    Original parameters dict.
            context:   Optional context hints.

        Returns:
            Optimized parameters dict.
        """
        return self.optimizer.optimize(tool_name, params, context)

    def intercept_tool(
        self,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Delegate a tool intercept request to ToolCallInterceptor.

        Args:
            tool_name: Name of the tool to intercept.
            params:    Tool parameters dict.

        Returns:
            Intercept result dict with optimized_params and suggestions.
        """
        return self.interceptor.intercept_and_optimize(tool_name, params)

    def analyze_file(
        self,
        filepath: str,
        show_methods: bool = False
    ) -> Dict[str, Any]:
        """
        AST-navigate a code file via ASTCodeNavigator.

        Args:
            filepath:     Path to code file.
            show_methods: When True, include method signatures.

        Returns:
            Code structure dict.
        """
        return self.ast_navigator.navigate(filepath, show_methods=show_methods)

    def smart_read_analysis(self, filepath: str) -> Dict[str, Any]:
        """
        Analyze a file's reading strategy via SmartReadOptimizer.

        Args:
            filepath: Path to the file to analyze.

        Returns:
            Analysis dict with strategy recommendation.
        """
        return self.smart_reader.analyze_file(filepath)


# ===========================================================================
# CLI entry point
# ===========================================================================

def _build_arg_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog='tool-usage-optimization-policy.py',
        description='Tool Usage Optimization Policy - Consolidated enterprise optimizer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  python tool-usage-optimization-policy.py --enforce\n'
            '  python tool-usage-optimization-policy.py --validate\n'
            '  python tool-usage-optimization-policy.py --report\n'
            '  python tool-usage-optimization-policy.py --optimize --tool Read --params \'{"file_path": "/path/to/file.py"}\'\n'
            '  python tool-usage-optimization-policy.py --intercept --tool Grep --params \'{"pattern": "class.*Service"}\'\n'
            '  python tool-usage-optimization-policy.py --analyze --file /path/to/MyClass.java --show-methods\n'
            '  python tool-usage-optimization-policy.py --stats\n'
        )
    )

    mode_group = parser.add_argument_group('Policy Modes')
    mode_group.add_argument('--enforce',   action='store_true', help='Initialize all subsystems')
    mode_group.add_argument('--validate',  action='store_true', help='Run compliance check')
    mode_group.add_argument('--report',    action='store_true', help='Generate statistics report')
    mode_group.add_argument('--stats',     action='store_true', help='Print session statistics')

    tool_group = parser.add_argument_group('Tool Optimization')
    tool_group.add_argument('--optimize',  action='store_true', help='Optimize a specific tool call')
    tool_group.add_argument('--intercept', action='store_true', help='Intercept a tool call')
    tool_group.add_argument('--tool',   type=str, help='Tool name (Read, Grep, Glob, Bash, Edit, Write)')
    tool_group.add_argument('--params', type=str, help='Tool parameters as JSON string')
    tool_group.add_argument('--context', type=str, help='Context hints as JSON string (for --optimize)')

    ast_group = parser.add_argument_group('AST Analysis')
    ast_group.add_argument('--analyze',      action='store_true', help='AST-analyze a code file')
    ast_group.add_argument('--smart-read',   action='store_true', dest='smart_read', help='Smart read strategy for a file')
    ast_group.add_argument('--file',         type=str, help='File path for --analyze or --smart-read')
    ast_group.add_argument('--show-methods', action='store_true', dest='show_methods', help='Include method signatures in AST output')

    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    parser.add_argument('--version', action='version', version='%(prog)s ' + ToolOptimizationPolicy.VERSION)

    return parser


def main() -> int:
    """
    CLI entry point for tool-usage-optimization-policy.py.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    # No arguments -> print usage summary and exit successfully
    if len(sys.argv) < 2:
        print('=' * 65)
        print('Tool Usage Optimization Policy v' + ToolOptimizationPolicy.VERSION)
        print('=' * 65)
        print('\nUsage:')
        print("  python tool-usage-optimization-policy.py --enforce")
        print("  python tool-usage-optimization-policy.py --validate")
        print("  python tool-usage-optimization-policy.py --report")
        print("  python tool-usage-optimization-policy.py --optimize --tool Read --params '{\"file_path\":\"...\"}'")
        print("  python tool-usage-optimization-policy.py --intercept --tool Grep --params '{\"pattern\":\"...\"}'")
        print("  python tool-usage-optimization-policy.py --analyze --file /path/to/code.java")
        print("  python tool-usage-optimization-policy.py --smart-read --file /path/to/file.py")
        print("  python tool-usage-optimization-policy.py --stats")
        print('\nSubsystems:')
        print('  ToolUsageOptimizer     - Core optimizer with caching, batching, metrics')
        print('  ToolCallInterceptor    - Intercept and optimize all tool calls')
        print('  AutoToolWrapper        - Auto-wrap parameters intelligently')
        print('  PreExecutionOptimizer  - Optimize before tool execution')
        print('  ASTCodeNavigator       - AST-based code analysis for smart operations')
        print('  SmartReadOptimizer     - Smart file reading with caching')
        print()
        return 0

    parser = _build_arg_parser()
    args = parser.parse_args()

    policy = ToolOptimizationPolicy()
    output_json = getattr(args, 'json', False)

    # ------------------------------------------------------------------
    # Mode: --enforce
    # ------------------------------------------------------------------
    if args.enforce:
        result = policy.enforce()
        if output_json:
            print(json.dumps(result, indent=2))
        return 0

    # ------------------------------------------------------------------
    # Mode: --validate
    # ------------------------------------------------------------------
    if args.validate:
        result = policy.validate()
        if output_json:
            print(json.dumps(result, indent=2))
        return 0 if result['result'] == 'PASS' else 1

    # ------------------------------------------------------------------
    # Mode: --report
    # ------------------------------------------------------------------
    if args.report:
        result = policy.report()
        if output_json:
            print(json.dumps(result, indent=2))
        return 0

    # ------------------------------------------------------------------
    # Mode: --stats
    # ------------------------------------------------------------------
    if args.stats:
        stats = policy.optimizer.get_session_stats()
        print('\n' + '=' * 60)
        print('SESSION STATISTICS')
        print('=' * 60)
        print('  Total optimizations:  ' + str(stats['total_optimizations']))
        print('  Average savings:      ' + str(stats['average_savings_pct']) + '%')
        print('  Breakdown by tool:    ' + str(stats['by_tool']))
        print('=' * 60 + '\n')
        if output_json:
            print(json.dumps(stats, indent=2))
        return 0

    # ------------------------------------------------------------------
    # Mode: --optimize
    # ------------------------------------------------------------------
    if args.optimize:
        if not args.tool or not args.params:
            print('ERROR: --optimize requires --tool and --params', file=sys.stderr)
            return 1
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as exc:
            print('ERROR: Invalid JSON in --params: ' + str(exc), file=sys.stderr)
            return 1
        context: Optional[Dict[str, Any]] = None
        if args.context:
            try:
                context = json.loads(args.context)
            except json.JSONDecodeError as exc:
                print('ERROR: Invalid JSON in --context: ' + str(exc), file=sys.stderr)
                return 1

        result = policy.optimize_tool(args.tool, params, context)
        print('\n' + '=' * 60)
        print('OPTIMIZED PARAMETERS: ' + args.tool)
        print('=' * 60)
        print(json.dumps(result, indent=2))
        return 0

    # ------------------------------------------------------------------
    # Mode: --intercept
    # ------------------------------------------------------------------
    if args.intercept:
        if not args.tool or not args.params:
            print('ERROR: --intercept requires --tool and --params', file=sys.stderr)
            return 1
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as exc:
            print('ERROR: Invalid JSON in --params: ' + str(exc), file=sys.stderr)
            return 1

        result = policy.intercept_tool(args.tool, params)
        print(policy.interceptor.format_result(result))
        if output_json:
            print(json.dumps(result, indent=2))
        return 0

    # ------------------------------------------------------------------
    # Mode: --analyze (AST)
    # ------------------------------------------------------------------
    if args.analyze:
        if not args.file:
            print('ERROR: --analyze requires --file', file=sys.stderr)
            return 1
        show_methods = getattr(args, 'show_methods', False)
        result = policy.analyze_file(args.file, show_methods=show_methods)

        if output_json:
            print(json.dumps(result, indent=2))
        else:
            print(policy.ast_navigator.format_structure(result))
        return 0 if 'error' not in result else 1

    # ------------------------------------------------------------------
    # Mode: --smart-read
    # ------------------------------------------------------------------
    if getattr(args, 'smart_read', False):
        if not args.file:
            print('ERROR: --smart-read requires --file', file=sys.stderr)
            return 1
        result = policy.smart_read_analysis(args.file)

        if output_json:
            print(json.dumps(result, indent=2))
        else:
            print(policy.smart_reader.format_analysis(result))
        return 0 if 'error' not in result else 1

    # ------------------------------------------------------------------
    # No valid mode selected
    # ------------------------------------------------------------------
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
