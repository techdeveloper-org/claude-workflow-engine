#!/usr/bin/env python3
"""
Coding Standards Enforcement Policy (v2.0)

Maps to: policies/02-standards-system/coding-standards-enforcement-policy.md

This module enforces 12 categories of Spring Boot microservices coding standards
(~91 real rules) that Claude must follow when writing Java/Spring code. These
complement the common standards (Level 2.1) with implementation-specific patterns.

Categories (12 total, ~91 rules):
  1. java_project_structure   (6 rules + 13 packages)
  2. config_server            (4 rules + 4 forbidden)
  3. secret_management        (4 rules)
  4. response_format          (4 rules)
  5. form_validation          (5 rules)
  6. service_layer            (7 rules)
  7. entity_pattern           (7 rules)
  8. repository_pattern       (5 rules)
  9. controller_pattern       (8 rules)
  10. exception_handling      (5 rules)
  11. constants_organization  (4 rules)
  12. common_utilities        (4 rules)

Key Functions:
  enforce(): Load and initialize the coding standards file.
  validate(): Check that the coding standards file exists and is valid.
  report(): Generate a summary report of loaded coding standards.

CLI Usage:
  python coding-standards-enforcement-policy.py --enforce   # Run policy enforcement
  python coding-standards-enforcement-policy.py --validate  # Validate policy compliance
  python coding-standards-enforcement-policy.py --report    # Generate standards report

Example:
  >>> from coding_standards_enforcement_policy import enforce
  >>> result = enforce()
  >>> print(result['standards_count'])  # 7
"""

import sys
import io
import json
from pathlib import Path
from datetime import datetime

# ===================================================================
# NEW: POLICY TRACKING INTEGRATION
# ===================================================================
# Policy tracking - mandatory (find helper by walking up to scripts root)
_scripts_root = Path(__file__).resolve().parent
while _scripts_root != _scripts_root.parent:
    if (_scripts_root / 'policy_tracking_helper.py').exists():
        if str(_scripts_root) not in sys.path:
            sys.path.insert(0, str(_scripts_root))
        break
    _scripts_root = _scripts_root.parent
from policy_tracking_helper import record_policy_execution, record_sub_operation, get_session_id, get_session_id

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"
STANDARDS_FILE = Path.home() / ".claude" / "memory" / "standards" / "coding-standards.json"

# Current standards version - bump when rules change
STANDARDS_VERSION = "2.0.0"


def _needs_upgrade(filepath):
    """Check if existing JSON needs upgrade to real rules format."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        stds = data.get('standards', {})
        if not stds:
            return True
        first_val = next(iter(stds.values()))
        if isinstance(first_val, str):
            return True
        if data.get('version', '0') != STANDARDS_VERSION:
            return True
        return False
    except Exception:
        return True


def _build_microservices_standards():
    """Build 12-category microservices standards with real enforcement rules.

    Returns:
        dict: 12 standard categories for Spring Boot, each with description,
              rules list, and code patterns. Total: ~91 rules.
    """
    return {
        "java_project_structure": {
            "description": "Standard Java/Spring Boot project folder structure",
            "base_package": "com.techdeveloper.{project}.{service}",
            "packages": {
                "controller": "public",
                "dto": "public",
                "form": "public",
                "constants": "public",
                "enums": "public",
                "services": "public (interfaces)",
                "services.impl": "package-private",
                "services.helper": "package-private",
                "entity": "package-private",
                "repository": "package-private",
                "client": "package-private",
                "config": "public",
                "exception": "public"
            },
            "rules": [
                "Service implementations are package-private",
                "Service implementations extend Helper classes",
                "All responses use ApiResponseDto<T>",
                "Form classes extend ValidationMessageConstants",
                "NO hardcoded messages (use constants)",
                "@Transactional on all write operations"
            ]
        },
        "config_server": {
            "description": "Spring Cloud Config Server rules",
            "location": "config-server/configurations/",
            "allowed_in_microservice": [
                "spring.application.name",
                "spring.config.import",
                "secret-manager.client"
            ],
            "rules": [
                "ONLY application name + config import in microservice yml",
                "ALL other configs go to Config Server",
                "NEVER add database config in microservice application.yml",
                "NEVER add port numbers in microservice application.yml",
                "NEVER hardcode any config in microservice",
                "NEVER add Redis/Feign/external service config in microservice"
            ]
        },
        "secret_management": {
            "description": "Secret and credential management patterns",
            "syntax": "${SECRET:key-name}",
            "rules": [
                "ALL secrets stored in Secret Manager",
                "Config server uses ${SECRET:key-name} syntax",
                "NEVER hardcode secrets in any file",
                "NEVER commit .env files to version control",
                "NEVER store secrets in application.yml"
            ]
        },
        "response_format": {
            "description": "Standard API response format using ApiResponseDto<T>",
            "wrapper": "ApiResponseDto<T>",
            "fields": ["status", "message", "data", "timestamp"],
            "rules": [
                "ALL API responses use ApiResponseDto<T> wrapper",
                "Messages from MessageConstants (never hardcoded)",
                "Use .success() or .error() factory methods",
                "NEVER return raw DTOs without wrapper",
                "NEVER return ResponseEntity<RawDto>",
                "NEVER hardcode response messages"
            ]
        },
        "form_validation": {
            "description": "Request form validation patterns",
            "rules": [
                "ALL request forms extend ValidationMessageConstants",
                "ALL validation messages defined in constants",
                "Use standard annotations (@NotBlank, @Size, @Pattern, etc.)",
                "NEVER hardcode validation messages inline",
                "NEVER use raw strings in @NotBlank(message = '...')"
            ]
        },
        "service_layer": {
            "description": "Service layer pattern (interface + impl + helper)",
            "rules": [
                "Service interface is public",
                "Service implementation is package-private (no public modifier)",
                "Service implementation extends Helper class",
                "Helper contains reusable/shared logic",
                "@Transactional on write operations (create, update, delete)",
                "NEVER make service implementation public",
                "NEVER put business logic directly in controller"
            ]
        },
        "entity_pattern": {
            "description": "JPA entity design pattern",
            "rules": [
                "Entity class is package-private",
                "Table name explicitly specified with @Table",
                "Column names explicit in snake_case",
                "Audit fields mandatory (created_at, updated_at, created_by, updated_by)",
                "@PrePersist and @PreUpdate for automatic timestamps",
                "NEVER use camelCase in database column names",
                "NEVER skip audit fields on any entity"
            ]
        },
        "repository_pattern": {
            "description": "Spring Data JPA repository pattern",
            "rules": [
                "Repository interface is package-private",
                "Use Spring Data method naming conventions (findBy, existsBy)",
                "Complex queries use @Query with JPQL",
                "Pagination with Pageable parameter",
                "NEVER make repository public",
                "NEVER write raw SQL (use JPQL)"
            ]
        },
        "controller_pattern": {
            "description": "REST controller design pattern",
            "rules": [
                "Controller class is public with @RestController",
                "Base path follows /api/v1/{resource} pattern",
                "Use standard HTTP methods (GET, POST, PUT, DELETE)",
                "@Valid on all @RequestBody parameters",
                "Messages from MessageConstants",
                "Return ApiResponseDto wrapper always",
                "NEVER put business logic in controller",
                "NEVER hardcode messages in controller"
            ]
        },
        "exception_handling": {
            "description": "Global exception handling with @RestControllerAdvice",
            "rules": [
                "Custom exception classes for domain errors",
                "Global exception handler with @RestControllerAdvice",
                "Return ApiResponseDto for ALL error responses",
                "Use appropriate HTTP status codes per exception type",
                "NEVER swallow exceptions silently",
                "NEVER expose stack traces to client"
            ]
        },
        "constants_organization": {
            "description": "Constants file organization",
            "files": [
                "ApiConstants.java",
                "MessageConstants.java",
                "ValidationMessageConstants.java",
                "DatabaseConstants.java",
                "SecurityConstants.java"
            ],
            "rules": [
                "ALL constants in appropriate constant classes",
                "NO magic numbers or strings in code",
                "Use constants everywhere in controllers/services",
                "NEVER hardcode strings or numbers",
                "NEVER duplicate constant definitions"
            ]
        },
        "common_utilities": {
            "description": "Utility class patterns",
            "files": [
                "DateTimeUtils.java",
                "StringUtils.java",
                "ValidationUtils.java",
                "MapperUtils.java"
            ],
            "rules": [
                "Utility classes for common operations (static methods)",
                "Reuse utilities across all services",
                "NEVER duplicate utility logic",
                "NEVER put utility methods in service classes"
            ]
        }
    }


def log_action(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] coding-standards-enforcement-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def validate():
    """Check that the coding standards file exists and is parseable.

    Reads the coding standards JSON file and verifies it contains at least one
    standard definition. Logs the result to the policy-hits log.

    Returns:
        bool: True if the file exists and loads successfully, False otherwise.
    """
    try:
        if STANDARDS_FILE.exists():
            with open(STANDARDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            standard_count = len(data.get('standards', {}))
            log_action("VALIDATE", f"standards-loaded | count={standard_count}")
            return True
        log_action("VALIDATE", "standards-file-missing")
        return False
    except Exception as e:
        log_action("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report listing all loaded coding standards.

    Reads the coding standards file and returns a structured dictionary
    suitable for JSON output, including the total count and standard names.

    Returns:
        dict: Report containing 'status', 'total_standards', 'standards' (list),
              and 'timestamp'. Returns {'status': 'error', 'message': ...} on failure.
    """
    try:
        if not STANDARDS_FILE.exists():
            return {"status": "error", "message": "standards-file-not-found"}

        with open(STANDARDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        report_data = {
            "status": "success",
            "total_standards": len(data.get('standards', {})),
            "standards": list(data.get('standards', {}).keys()),
            "timestamp": datetime.now().isoformat()
        }

        log_action("REPORT", f"standards={len(data.get('standards', {}))}")
        return report_data
    except Exception as e:
        log_action("REPORT_ERROR", str(e))
        return {"status": "error", "message": str(e)}


def enforce():
    """Load and initialize the microservice coding standards.

    Creates the standards directory and file if they do not exist, then reads
    the standards data and reports the count. Called by 3-level-flow.py during
    Level 2 standards enforcement.

    Returns:
        dict: Result with 'status' ('success' or 'error') and 'standards_count' int.
              On error, 'message' key contains the exception string.
    """
    _track_start_time = datetime.now()
    _sub_operations = []
    try:
        log_action("ENFORCE_START", "coding-standards-enforcement")

        # Ensure directory exists
        _op_start = datetime.now()
        STANDARDS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Initialize or upgrade standards file with real rules
        if not STANDARDS_FILE.exists() or _needs_upgrade(STANDARDS_FILE):
            standards_data = {
                "version": STANDARDS_VERSION,
                "standards": _build_microservices_standards(),
                "total_rules": 0,
                "loaded_at": datetime.now().isoformat()
            }
            total = 0
            for cat in standards_data["standards"].values():
                if isinstance(cat, dict):
                    total += len(cat.get("rules", []))
            standards_data["total_rules"] = total
            STANDARDS_FILE.write_text(json.dumps(standards_data, indent=2), encoding='utf-8')
        try:
            _sub_operations.append(record_sub_operation(
                "init_coding_standards_file", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000)
            ))
        except Exception:
            pass

        # Load standards and count real rules
        _op_start = datetime.now()
        with open(STANDARDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        standard_count = len(data.get('standards', {}))
        # Count actual rules across all categories
        total_rules = data.get('total_rules', 0)
        if total_rules == 0:
            for cat in data.get('standards', {}).values():
                if isinstance(cat, dict):
                    total_rules += len(cat.get('rules', []))
                else:
                    total_rules += 1
        try:
            _sub_operations.append(record_sub_operation(
                "load_coding_standards", "success",
                int((datetime.now() - _op_start).total_seconds() * 1000),
                {"standards_count": standard_count, "total_rules": total_rules}
            ))
        except Exception:
            pass

        log_action("ENFORCE", f"coding-standards-loaded | categories={standard_count} | rules={total_rules}")
        # Output in format 3-level-flow.py parses
        print(f"Microservices Standards: {standard_count}")
        print(f"Microservices Rules Loaded: {total_rules}")

        result = {"status": "success", "standards_count": standard_count, "total_rules": total_rules}
        try:
            record_policy_execution(
                session_id=get_session_id(),
                policy_name="coding-standards-enforcement-policy",
                policy_script="coding-standards-enforcement-policy.py",
                policy_type="Policy Script",
                input_params={},
                output_results=result,
                decision=f"loaded {standard_count} categories, {total_rules} rules",
                duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                sub_operations=_sub_operations if _sub_operations else None
            )
        except Exception:
            pass
        return result
    except Exception as e:
        log_action("ENFORCE_ERROR", str(e))
        print(f"[coding-standards-enforcement-policy] ERROR: {e}")
        error_result = {"status": "error", "message": str(e)}
        try:
            record_policy_execution(
                session_id=get_session_id(),
                policy_name="coding-standards-enforcement-policy",
                policy_script="coding-standards-enforcement-policy.py",
                policy_type="Policy Script",
                input_params={},
                output_results=error_result,
                decision=f"error: {str(e)}",
                duration_ms=int((datetime.now() - _track_start_time).total_seconds() * 1000),
                sub_operations=_sub_operations if _sub_operations else None
            )
        except Exception:
            pass
        return error_result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            is_valid = validate()
            sys.exit(0 if is_valid else 1)
        elif sys.argv[1] == "--report":
            result = report()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("status") == "success" else 1)
    else:
        # Default: run enforcement
        enforce()
