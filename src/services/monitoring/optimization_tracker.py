"""
Tool Optimization Tracker - Track the 15 token optimization strategies.

Monitors and quantifies the application of 15 token optimization strategies
derived from ADVANCED-TOKEN-OPTIMIZATION.md. Derives counts by analyzing
flow-trace.json session data and inferring which strategies were applied
based on context usage, complexity, and execution mode.

The 15 strategies tracked:
  1. Response Compression   - Ultra-brief responses
  2. Diff-Based Editing     - Show only changed lines
  3. Smart Tool Selection   - tree vs Glob/Grep
  4. Smart Grep Optimization - head_limit, files_with_matches
  5. Tiered Caching         - Hot/Warm/Cold cache
  6. Session State          - Aggressive external state
  7. Incremental Updates    - Partial updates only
  8. File Type Optimization - Language-specific strategies
  9. Lazy Context Loading   - Load only when needed
  10. Smart Summarization   - Intelligent summaries
  11. Batch Operations      - Combine multiple operations
  12. MCP Filtering         - Filter MCP responses
  13. Conversation Pruning  - Remove old messages
  14. AST Navigation        - AST-based code navigation
  15. Parallel Tool Calls   - Parallel tool execution

Also tracks coding standards enforcement per session (tech stack, standards count).

Reads from:
  - ~/.claude/memory/logs/sessions/*/flow-trace.json

Classes:
  OptimizationTracker: Tracks optimization strategy application and token savings.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add path resolver for portable paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.path_resolver import get_data_dir, get_logs_dir
from collections import defaultdict


class OptimizationTracker:
    """Track tool optimization strategies and estimated token savings.

    Analyzes flow-trace.json session data to count how often each of the 15
    token optimization strategies was applied, and estimates the tokens saved.
    Also tracks coding standards enforcement patterns by tech stack.

    Attributes:
        memory_dir (Path): Root data directory (~/.claude/memory).
        logs_dir (Path): Path to the logs subdirectory.
        docs_dir (Path): Path to the docs subdirectory.
        sessions_dir (Path): Path to the sessions log directory.
    """

    def __init__(self):
        self.memory_dir = get_data_dir()
        self.logs_dir = self.memory_dir / 'logs'
        self.docs_dir = self.memory_dir / 'docs'
        self.sessions_dir = self.logs_dir / 'sessions'

    def _load_flow_traces(self, max_files=200):
        """Load and parse flow-trace.json files from the sessions directory.

        Reads up to max_files most-recent flow-trace.json files.

        Args:
            max_files (int): Maximum number of trace files to load (default 200).

        Returns:
            list[dict]: Parsed trace data dicts. Returns an empty list if the
                sessions directory does not exist or no files can be parsed.
        """
        traces = []
        if not self.sessions_dir.exists():
            return traces
        try:
            trace_files = sorted(
                self.sessions_dir.glob('*/flow-trace.json'),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:max_files]
            for tf in trace_files:
                try:
                    data = json.loads(tf.read_text(encoding='utf-8', errors='ignore'))
                    traces.append(data)
                except Exception:
                    continue
        except Exception:
            pass
        return traces

    def get_tool_optimization_metrics(self):
        """Track application of 15 token optimization strategies across sessions.

        Reads flow-trace.json files and infers which optimization strategies were
        applied based on context usage, complexity, execution mode, and whether the
        LEVEL_3_STEP_3_6 pipeline step ran. Estimates token savings per strategy.

        Returns:
            dict: Optimization metrics with keys:
                strategies (dict): Map of strategy name to
                    {count, tokens_saved, description}.
                total_optimizations (int): Sum of all strategy application counts.
                total_tokens_saved (int): Estimated total tokens saved.
                estimated_savings_percentage (float): Overall savings percentage (0-80).
                top_strategies (list[dict]): Top 5 strategies by tokens saved.
                sessions_analyzed (int): Number of session traces processed.
            On error: returns strategies dict with zeroed counts and error key.
        """
        # Define 15 optimization strategies with base application rates
        # These reflect strategies always applied by the enforcement system
        strategies = {
            'response_compression': {'count': 0, 'tokens_saved': 0, 'description': 'Ultra-brief responses'},
            'diff_based_editing': {'count': 0, 'tokens_saved': 0, 'description': 'Show only changed lines'},
            'smart_tool_selection': {'count': 0, 'tokens_saved': 0, 'description': 'tree vs Glob/Grep'},
            'smart_grep': {'count': 0, 'tokens_saved': 0, 'description': 'head_limit, files_with_matches'},
            'tiered_caching': {'count': 0, 'tokens_saved': 0, 'description': 'Hot/Warm/Cold cache'},
            'session_state': {'count': 0, 'tokens_saved': 0, 'description': 'Aggressive external state'},
            'incremental_updates': {'count': 0, 'tokens_saved': 0, 'description': 'Partial updates only'},
            'file_type_optimization': {'count': 0, 'tokens_saved': 0, 'description': 'Language-specific'},
            'lazy_context_loading': {'count': 0, 'tokens_saved': 0, 'description': 'Load only when needed'},
            'smart_summarization': {'count': 0, 'tokens_saved': 0, 'description': 'Intelligent summaries'},
            'batch_operations': {'count': 0, 'tokens_saved': 0, 'description': 'Combine multiple operations'},
            'mcp_filtering': {'count': 0, 'tokens_saved': 0, 'description': 'Filter MCP responses'},
            'conversation_pruning': {'count': 0, 'tokens_saved': 0, 'description': 'Remove old messages'},
            'ast_navigation': {'count': 0, 'tokens_saved': 0, 'description': 'AST-based code nav'},
            'parallel_tools': {'count': 0, 'tokens_saved': 0, 'description': 'Parallel tool calls'}
        }

        traces = self._load_flow_traces()
        if not traces:
            return {
                'strategies': strategies,
                'total_optimizations': 0,
                'total_tokens_saved': 0,
                'top_strategies': []
            }

        try:
            for trace in traces:
                fd = trace.get('final_decision', {})
                complexity = fd.get('complexity', 1)
                context_pct = fd.get('context_pct', 0)

                # Check if tool optimization step ran
                tool_opt_ran = False
                for step in trace.get('pipeline', []):
                    if step.get('step') == 'LEVEL_3_STEP_3_6' and step.get('duration_ms', 0) >= 0:
                        tool_opt_ran = True
                        break

                if not tool_opt_ran:
                    continue

                # Apply optimizations based on what the enforcement system always does:
                # Response compression is always applied
                strategies['response_compression']['count'] += 1
                strategies['response_compression']['tokens_saved'] += 100

                # Grep optimization is always applied (head_limit enforced)
                strategies['smart_grep']['count'] += 1
                strategies['smart_grep']['tokens_saved'] += 300

                # Context-based optimizations
                if context_pct >= 70:
                    strategies['session_state']['count'] += 1
                    strategies['session_state']['tokens_saved'] += 600
                    strategies['lazy_context_loading']['count'] += 1
                    strategies['lazy_context_loading']['tokens_saved'] += 350

                if context_pct >= 85:
                    strategies['conversation_pruning']['count'] += 1
                    strategies['conversation_pruning']['tokens_saved'] += 800

                # Complexity-based optimizations
                if complexity >= 5:
                    strategies['smart_tool_selection']['count'] += 1
                    strategies['smart_tool_selection']['tokens_saved'] += 500
                    strategies['batch_operations']['count'] += 1
                    strategies['batch_operations']['tokens_saved'] += 200

                if complexity >= 3:
                    strategies['diff_based_editing']['count'] += 1
                    strategies['diff_based_editing']['tokens_saved'] += 200

                # Execution mode based
                if fd.get('execution_mode') == 'parallel':
                    strategies['parallel_tools']['count'] += 1
                    strategies['parallel_tools']['tokens_saved'] += 150

                # Standards always loaded (summarization)
                standards = fd.get('standards_active', 0)
                if standards > 0:
                    strategies['smart_summarization']['count'] += 1
                    strategies['smart_summarization']['tokens_saved'] += 450

                # Tiered caching applied with cached context entries
                for step in trace.get('pipeline', []):
                    if step.get('step') == 'LEVEL_1_CONTEXT':
                        po = step.get('policy_output', {})
                        if po.get('cache_entries', 0) > 0:
                            strategies['tiered_caching']['count'] += 1
                            strategies['tiered_caching']['tokens_saved'] += 400
                        break

            # Calculate totals
            total_optimizations = sum(s['count'] for s in strategies.values())
            total_tokens_saved = sum(s['tokens_saved'] for s in strategies.values())

            # Get top 5 strategies
            top_strategies = sorted(
                [{'name': k, **v} for k, v in strategies.items()],
                key=lambda x: x['tokens_saved'],
                reverse=True
            )[:5]

            return {
                'strategies': strategies,
                'total_optimizations': total_optimizations,
                'total_tokens_saved': total_tokens_saved,
                'estimated_savings_percentage': min(80, round((total_tokens_saved / max(total_optimizations * 1000, 1)) * 80, 1)),
                'top_strategies': top_strategies,
                'sessions_analyzed': len(traces)
            }

        except Exception as e:
            return {
                'strategies': strategies,
                'total_optimizations': 0,
                'total_tokens_saved': 0,
                'error': str(e)
            }

    def get_standards_enforcement_stats(self):
        """Track coding standards loading and enforcement across sessions.

        Reads flow-trace.json final_decision.standards_active and rules_active
        to count total standards enforced and categorize by tech stack (Java/Spring,
        DevOps, Frontend, Database, General).

        Returns:
            dict: Standards enforcement stats with keys:
                total_enforcements (int): Sessions where standards were loaded.
                standards_by_type (dict): Map of tech category to enforcement count.
                violations_detected (int): Currently always 0 (not yet tracked).
                auto_fixes_applied (int): Currently always 0 (not yet tracked).
                recent_enforcements (list[dict]): Last 15 enforcement records with
                    timestamp, standards_active, rules_active, task_type, tech_stack.
                avg_standards_per_session (float): Average standards count per session.
                avg_rules_per_session (float): Average rules count per session.
                total_standards (int): Cumulative standards count across all sessions.
                total_rules (int): Cumulative rules count across all sessions.
        """
        stats = {
            'total_enforcements': 0,
            'standards_by_type': defaultdict(int),
            'violations_detected': 0,
            'auto_fixes_applied': 0,
            'recent_enforcements': [],
            'avg_standards_per_session': 0,
            'avg_rules_per_session': 0,
            'total_standards': 0,
            'total_rules': 0
        }

        traces = self._load_flow_traces()
        if not traces:
            stats['standards_by_type'] = {}
            return stats

        try:
            total_standards = 0
            total_rules = 0
            sessions_with_standards = 0

            for trace in traces:
                fd = trace.get('final_decision', {})
                standards_active = fd.get('standards_active', 0)
                rules_active = fd.get('rules_active', 0)

                if standards_active == 0:
                    continue

                stats['total_enforcements'] += 1
                sessions_with_standards += 1
                total_standards += standards_active
                total_rules += rules_active

                # Categorize based on tech stack detected
                tech_stack = fd.get('tech_stack', [])
                task_type = fd.get('task_type', '')

                for tech in tech_stack:
                    tech_lower = tech.lower()
                    if 'java' in tech_lower or 'spring' in tech_lower or 'maven' in tech_lower:
                        stats['standards_by_type']['java_spring_boot'] += 1
                    elif 'docker' in tech_lower or 'kubernetes' in tech_lower:
                        stats['standards_by_type']['devops'] += 1
                    elif 'angular' in tech_lower or 'react' in tech_lower or 'node' in tech_lower:
                        stats['standards_by_type']['frontend'] += 1
                    elif 'postgres' in tech_lower or 'mysql' in tech_lower or 'mongo' in tech_lower:
                        stats['standards_by_type']['database'] += 1

                if not tech_stack or tech_stack == ['unknown']:
                    stats['standards_by_type']['general'] += 1

                # Store recent (last 15)
                if len(stats['recent_enforcements']) < 15:
                    stats['recent_enforcements'].append({
                        'timestamp': trace.get('meta', {}).get('flow_start', datetime.now().isoformat()),
                        'standards_active': standards_active,
                        'rules_active': rules_active,
                        'task_type': task_type,
                        'tech_stack': tech_stack
                    })

            # Calculate averages
            if sessions_with_standards > 0:
                stats['avg_standards_per_session'] = round(total_standards / sessions_with_standards, 1)
                stats['avg_rules_per_session'] = round(total_rules / sessions_with_standards, 1)

            stats['total_standards'] = total_standards
            stats['total_rules'] = total_rules

            # Convert defaultdict
            stats['standards_by_type'] = dict(stats['standards_by_type'])

        except Exception as e:
            stats['error'] = str(e)
            stats['standards_by_type'] = dict(stats['standards_by_type'])

        return stats

    def get_context_savings(self):
        """Get a compact summary of context token savings.

        Extracts the top-level token savings metrics from
        get_tool_optimization_metrics() for quick dashboard display.

        Returns:
            dict: Context savings summary with keys:
                total_tokens_saved (int): Estimated total tokens saved.
                total_optimizations (int): Total strategy applications counted.
                estimated_savings_percentage (float): Savings percentage (0-80).
                top_strategies (list[dict]): Top 5 strategies by tokens saved.
                sessions_analyzed (int): Number of session traces analyzed.
        """
        metrics = self.get_tool_optimization_metrics()
        strategies = metrics.get('strategies', {})
        return {
            'total_tokens_saved': metrics.get('total_tokens_saved', 0),
            'total_optimizations': metrics.get('total_optimizations', 0),
            'estimated_savings_percentage': metrics.get('estimated_savings_percentage', 0),
            'top_strategies': metrics.get('top_strategies', []),
            'sessions_analyzed': metrics.get('sessions_analyzed', 0)
        }

    def get_optimization_summary(self):
        """Get a compact optimization summary combining tool and standards data.

        Returns:
            dict: Summary with keys:
                tool_optimization (dict): Output of get_tool_optimization_metrics().
                standards_enforcement (dict): Output of get_standards_enforcement_stats().
                timestamp (str): ISO-format current timestamp.
        """
        metrics = self.get_tool_optimization_metrics()
        standards = self.get_standards_enforcement_stats()
        return {
            'tool_optimization': metrics,
            'standards_enforcement': standards,
            'timestamp': datetime.now().isoformat()
        }

    def get_comprehensive_optimization_stats(self):
        """Get all optimization statistics aggregated in one call.

        Returns:
            dict: All optimization stats with keys:
                tool_optimization (dict): Output of get_tool_optimization_metrics().
                standards_enforcement (dict): Output of get_standards_enforcement_stats().
                timestamp (str): ISO-format current timestamp.
        """
        return {
            'tool_optimization': self.get_tool_optimization_metrics(),
            'standards_enforcement': self.get_standards_enforcement_stats(),
            'timestamp': datetime.now().isoformat()
        }
