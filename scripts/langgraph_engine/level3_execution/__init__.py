"""Level 3 Execution System -- 15-step execution pipeline modules.

Canonical location for Level 3 code analysis, quality gates, testing,
documentation, GitHub/Jira/Figma workflows, code review, and step execution.

Sub-packages:
- steps/: v1 step implementations (DEPRECATED - use v2_nodes/ instead)
- v2_nodes/: v2 step wrapper nodes (ACTIVE)
- sonarqube/: SonarQube integration (api_client, scanner, auto_fixer)
- architecture/: Architecture analysis scripts
- policies/: Level 3 execution policies

Level-specific modules:
- call_graph_analyzer: Pipeline impact analysis
- test_generator: Template-based unit test generation
- quality_gate: 4-gate merge enforcement
- github_code_review: GitHub PR review integration
- documentation_generator: Doc generation
- documentation_manager: Circular SDLC doc cycle
- figma_workflow: Figma design-to-code
- steps8to12_github: GitHub workflow steps
- steps8to12_jira: Jira workflow steps
- review_criteria: Code review criteria
- step1_planner: Plan mode logic
- remaining_steps: Steps 8-14 helpers
- code_explorer: Code exploration utilities
- llm_retry: LLM retry logic
- sonarqube_scanner: Legacy SonarQube entry point
- sonar_auto_fixer: SonarQube auto-fix
- integration_test_generator: Integration test generation
- execution_v2: v2 subgraph builder bridge
"""
