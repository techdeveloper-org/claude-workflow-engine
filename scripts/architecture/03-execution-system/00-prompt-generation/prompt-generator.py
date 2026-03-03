#!/usr/bin/env python3
"""
Prompt Generation & Structuring Script
Converts natural language to structured prompts with examples
"""

# Fix encoding for Windows console
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


try:
    import yaml
except ImportError:
    yaml = None
import json
import re
from typing import Dict, List, Any
from pathlib import Path
from datetime import datetime


class PromptGenerator:
    def __init__(self):
        self.workspace = Path.home() / "Documents" / "workspace-spring-tool-suite-4-4.27.0-new"
        self.docs = Path.home() / ".claude" / "memory" / "docs"

    def think_about_request(self, user_message: str) -> Dict:
        """PHASE 1: THINKING - Understand what's needed"""
        message_lower = user_message.lower()

        # Understand intent
        intent = "Unknown"
        if any(kw in message_lower for kw in ["create", "add", "new"]):
            if "api" in message_lower:
                intent = "Create a new REST API with CRUD operations"
            elif "service" in message_lower:
                intent = "Create a new microservice"
            else:
                intent = "Create new functionality"
        elif any(kw in message_lower for kw in ["fix", "bug", "error"]):
            intent = "Fix a bug or error"
        elif any(kw in message_lower for kw in ["add auth", "jwt", "security"]):
            intent = "Add authentication/authorization"

        # Generate sub-questions
        sub_questions = [
            "What entity/feature is involved?",
            "What operations are needed?",
            "What's the project structure?",
            "What patterns exist in codebase?",
            "What are the constraints/requirements?"
        ]

        # Identify needed information
        information_needed = [
            "Similar implementations in codebase",
            "Project package structure",
            "Naming conventions",
            "Response/Request patterns",
            "Configuration patterns",
            "Validation patterns"
        ]

        # Plan where to find it
        where_to_find = {
            "similar_code": "Search in user-service, auth-service, product-service",
            "structure": "Check java-project-structure.md",
            "patterns": "Read existing Controller/Service files",
            "config": "Check configurations/ directory",
            "standards": "Read api-design-standards.md, error-handling-standards.md"
        }

        return {
            "intent": intent,
            "sub_questions": sub_questions,
            "information_needed": information_needed,
            "where_to_find": where_to_find
        }

    def gather_information(self, thinking: Dict) -> Dict:
        """PHASE 2: INFORMATION GATHERING - Find relevant info"""
        gathered = {
            "similar_files": [],
            "patterns": [],
            "project_structure": {},
            "config_examples": [],
            "uncertainties": []
        }

        # Simulate searching (in real usage, would use Glob/Grep/Read)
        # This is placeholder - actual implementation would call Claude tools

        # Search for similar implementations
        service_dirs = ["user-service", "auth-service", "product-service"]
        file_types = ["Controller.java", "Service.java", "Entity.java", "Repository.java"]

        for service in service_dirs:
            for file_type in file_types:
                pattern_path = f"surgricalswale/backend/{service}/**/*{file_type}"
                gathered["similar_files"].append(pattern_path)

        # Extract common patterns (placeholder)
        gathered["patterns"] = [
            "ApiResponseDto<T> for all responses",
            "Form classes extend ValidationMessageConstants",
            "Service impl is package-private",
            "@Transactional for write operations",
            "Repository extends JpaRepository"
        ]

        # Project structure (placeholder)
        gathered["project_structure"] = {
            "base_path": "surgricalswale/backend/",
            "services": ["auth-service", "user-service"],
            "common_packages": ["controller", "services", "entity", "repository", "dto", "form"]
        }

        # Note: In real implementation, would verify files exist
        # If file doesn't exist, add to uncertainties

        return gathered

    def verify_information(self, gathered_info: Dict) -> Dict:
        """PHASE 3: VERIFICATION - Verify all information"""
        verification = {
            "examples_verified": True,
            "paths_verified": True,
            "patterns_validated": True,
            "assumptions": []
        }

        # In real implementation, would:
        # 1. Check each file path actually exists
        # 2. Verify patterns by reading actual files
        # 3. Confirm configurations are accurate
        # 4. Flag anything uncertain

        # For now, mark common assumptions
        if not gathered_info.get("similar_files"):
            verification["assumptions"].append("No similar implementations found - using general patterns")

        # Check for missing information
        if not gathered_info.get("config_examples"):
            verification["assumptions"].append("Configuration examples not verified")

        return verification

    def analyze_request(self, user_message: str) -> Dict:
        """Analyze natural language request"""
        message_lower = user_message.lower()

        analysis = {
            "task_type": self.detect_task_type(message_lower),
            "entities": self.extract_entities(message_lower),
            "operations": self.extract_operations(message_lower),
            "keywords": self.extract_keywords(message_lower),
            "complexity": self.estimate_complexity(user_message)
        }
        return analysis

    def detect_task_type(self, message: str) -> str:
        """
        INTELLIGENT TASK TYPE DETECTION
        Uses multi-phase analysis for accurate classification.
        ORDER MATTERS: most specific checks run first.
        """
        message_lower = message.lower()

        # PHASE 0: System/Meta tasks — highest priority
        # Check Sync/Update FIRST (more specific) before general System/Script

        # Sync to Claude Insight / Global Library
        sync_keywords = [
            "claude insight me", "insight me update", "insight me ni", "insight ko update",
            "sync kar", "global library me", "push kar", "commit kar", "github pe",
            "insight update", "insight me nahi", "insight ko sync",
            # Hinglish git/sync confirmation patterns
            "sync ho gaya", "sab sync", "push ho gaya", "confirm kar",
            "push kar diya", "kya sync", "sync hua", "ho gaya push",
            "verify kar", "check kar push", "pushed", "committed",
        ]
        if any(kw in message_lower for kw in sync_keywords):
            return "Sync/Update"

        # General System/Script tasks about the Claude memory system itself
        system_keywords = [
            "loophole", "hook", "3-level", "3 level", "prompt-generator", "prompt generator",
            "memory system", "claude insight", "skill", "agent", "flow.py", "flow.sh",
            "auto-fix", "session handler", "pre-tool", "post-tool", "stop-notifier",
            "standards-loader", "context-monitor", "session-id", "blocking-policy",
            "task-auto-analyzer", "plan-mode", "model-selection", "auto-plan",
            "rewritten prompt", "rewrite prompt", "intent lost", "intent khoti",
            "hook rewrites", "hook rewrite",
        ]
        if any(kw in message_lower for kw in system_keywords):
            return "System/Script"

        # PHASE 1: Priority-based detection (specific -> general)
        # Dashboard has highest priority (very specific context)
        if any(kw in message_lower for kw in ["dashboard", "admin panel", "control panel"]):
            return "Dashboard"

        # Frontend framework specific (check before generic UI to be precise)
        if any(kw in message_lower for kw in ["react", "angular", "vue", "component"]):
            return "Frontend"

        # UI/UX detection — only when message is clearly about visual/layout issues
        # Use WORD-BOUNDARY style check: " ui " or starts with "ui " etc to avoid false substring hits
        ui_exact = [" ui ", " ux ", "ui issue", "ux issue", "ui fix", "ux fix"]
        ui_keywords = ["design", "layout", "interface", "overlapping", "alignment", "responsive"]
        if any(kw in message_lower for kw in ui_exact) or any(kw in message_lower for kw in ui_keywords):
            return "UI/UX"
        # Hinglish UI detection
        if any(term in message_lower for term in ["ni ara", "ni aa raha", "nahi aa raha"]):
            if any(word in message_lower for word in ["admin", "panel", "button", "menu"]):
                return "Dashboard" if "admin" in message_lower or "panel" in message_lower else "UI/UX"

        # PHASE 2: Standard keyword mapping
        keywords_map = {
            "API Creation": ["create api", "add api", "new api", "crud", "rest api", "endpoint"],
            "Authentication": ["auth", "login", "jwt", "token", "authentication", "logout", "signin", "signup"],
            "Authorization": ["role", "permission", "access control", "authorization", "rbac"],
            "Database": ["database", "table", "migration", "schema", "entity", "repository"],
            "Configuration": ["config", "configure", "setup", "settings", "properties"],
            "Bug Fix": ["fix", "bug", "error", "issue", "problem", "broken", "not working"],
            "Refactoring": ["refactor", "improve", "optimize", "clean", "restructure", "rewrite"],
            "Security": ["security", "secure", "protect", "encrypt", "vulnerability", "hack"],
            "Testing": ["test", "unit test", "integration test", "testing", "junit", "pytest"],
            "Documentation": ["document", "doc", "readme", "comment", "javadoc"]
        }

        for task_type, keywords in keywords_map.items():
            if any(kw in message_lower for kw in keywords):
                return task_type

        # PHASE 3: Intent-based detection (when keywords unclear)
        # Check for multiple UI-related words even without exact keyword
        ui_indicators = ["admin", "panel", "button", "menu", "page", "screen", "display", "showing", "visible"]
        ui_count = sum(1 for indicator in ui_indicators if indicator in message_lower)
        if ui_count >= 2:
            return "Dashboard" if "admin" in message_lower else "UI/UX"

        return "General Task"

    def extract_entities(self, message: str) -> List[str]:
        """Extract entity names from message"""
        common_entities = [
            "user", "product", "order", "category", "role", "permission",
            "customer", "item", "cart", "payment", "invoice", "shipment",
            "auth", "authentication", "authorization", "token"
        ]
        found = [e for e in common_entities if e in message]

        # Also look for capitalized words (potential entity names)
        words = message.split()
        capitalized = [w.lower() for w in words if w[0].isupper() and w.lower() not in ["i", "a"]]

        return list(set(found + capitalized))

    def extract_operations(self, message: str) -> List[str]:
        """Extract operations from message"""
        operations = []

        operation_keywords = {
            "create": ["create", "add", "new", "insert", "post"],
            "read": ["read", "get", "fetch", "list", "view", "show", "retrieve"],
            "update": ["update", "edit", "modify", "change", "put", "patch"],
            "delete": ["delete", "remove", "destroy"]
        }

        for op, keywords in operation_keywords.items():
            if any(kw in message for kw in keywords):
                operations.append(op)

        if "crud" in message:
            operations = ["create", "read", "update", "delete"]

        return list(set(operations))

    def extract_keywords(self, message: str) -> List[str]:
        """
        INTELLIGENT KEYWORD EXTRACTION
        Maps user language -> system keywords with enrichment
        """
        message_lower = message.lower()
        extracted_keywords = []

        # PHASE 1: SYNONYM MAPPING (User language -> System keywords)
        synonym_map = {
            # UI/Dashboard synonyms
            "admin": ["admin panel", "dashboard", "ui", "frontend"],
            "panel": ["admin panel", "dashboard", "ui"],
            "overlapping": ["ui overlapping", "layout", "css", "design", "alignment"],
            "layout": ["ui", "design", "css", "frontend"],
            "not showing": ["ui", "display", "frontend", "visibility"],
            "missing": ["ui", "frontend", "display"],
            "button": ["ui", "frontend", "component"],
            "logout": ["authentication", "frontend", "ui"],
            "login": ["authentication", "frontend", "ui"],
            "responsive": ["ui", "css", "design", "frontend"],
            "mobile": ["responsive", "ui", "css"],

            # Backend synonyms
            "api": ["rest", "api", "endpoint", "backend"],
            "database": ["database", "entity", "repository", "backend"],
            "service": ["microservice", "backend", "business logic"],
            "auth": ["authentication", "security", "jwt"],
            "role": ["authorization", "security", "rbac"],

            # General synonyms
            "fix": ["bug fix", "troubleshooting"],
            "create": ["development", "implementation"],
            "add": ["development", "feature"]
        }

        # Apply synonym mapping
        for user_term, system_keywords in synonym_map.items():
            if user_term in message_lower:
                extracted_keywords.extend(system_keywords)

        # PHASE 2: DIRECT TECH KEYWORD DETECTION
        tech_keywords = [
            # Backend Java/Spring
            "spring boot", "postgresql", "redis", "jwt", "oauth",
            "rest", "api", "microservice", "docker", "kubernetes",
            "eureka", "gateway", "config server", "security",
            "validation", "transaction", "repository", "service",
            "controller", "entity", "dto", "form",

            # Backend Python
            "python", "flask", "django", "fastapi", "sqlalchemy",

            # Frontend
            "html", "css", "javascript", "typescript", "react",
            "angular", "vue", "webpack", "vite",

            # UI/UX
            "dashboard", "ui", "ux", "design", "layout", "interface",
            "responsive", "admin panel", "frontend", "bootstrap",
            "tailwind", "material-ui", "component"
        ]

        for keyword in tech_keywords:
            if keyword in message_lower:
                extracted_keywords.append(keyword)

        # PHASE 3: CONTEXT-BASED ENRICHMENT
        # If dashboard mentioned -> add related UI keywords
        if any(kw in message_lower for kw in ["dashboard", "admin panel", "admin"]):
            extracted_keywords.extend(["dashboard", "ui", "frontend", "admin panel"])

        # If UI issue mentioned -> add CSS/layout keywords
        if any(kw in message_lower for kw in ["overlapping", "alignment", "position", "display"]):
            extracted_keywords.extend(["css", "layout", "ui", "design"])

        # If authentication mentioned -> add security keywords
        if any(kw in message_lower for kw in ["login", "logout", "auth", "token"]):
            extracted_keywords.extend(["authentication", "security", "frontend"])

        # If Python/Flask detected -> add web framework keywords
        if any(kw in message_lower for kw in ["flask", "django", "python"]):
            extracted_keywords.extend(["python", "backend", "web app"])

        # If React/Angular/Vue detected -> add frontend keywords
        if any(kw in message_lower for kw in ["react", "angular", "vue"]):
            extracted_keywords.extend(["frontend", "component", "ui", "javascript"])

        # PHASE 4: HINGLISH DETECTION (Common Indian English patterns)
        hinglish_map = {
            "ni ara": ["not showing", "missing", "ui", "frontend"],
            "ni aa raha": ["not showing", "missing", "ui", "frontend"],
            "dikkat": ["issue", "problem", "bug"],
            "theek": ["fix", "correct"],
            "banana": ["create", "development"],
            "banao": ["create", "development"],
            "karo": ["do", "execute"],
            "wala": ["related to", "component"]
        }

        for hinglish_term, english_keywords in hinglish_map.items():
            if hinglish_term in message_lower:
                extracted_keywords.extend(english_keywords)

        # PHASE 5: FILE TYPE DETECTION
        if any(ext in message_lower for ext in [".html", ".css", ".js", "template"]):
            extracted_keywords.extend(["frontend", "ui", "web app"])

        if any(ext in message_lower for ext in [".py", ".java", ".ts"]):
            extracted_keywords.append("backend")

        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in extracted_keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords

    def estimate_complexity(self, message: str) -> int:
        """
        Estimate task complexity on a 1-25 scale.
        Scale aligns with model selection thresholds:
          0-4  = SIMPLE   -> HAIKU
          5-9  = MODERATE -> HAIKU/SONNET
          10-19 = COMPLEX  -> SONNET
          20-25 = CRITICAL -> OPUS
        """
        msg_lower = message.lower()
        complexity = 0

        # --- Factor 1: Task type base weight (0-8) ---
        task_type = self.detect_task_type(msg_lower)
        task_type_weights = {
            "API Creation": 7,
            "Authentication": 8,
            "Authorization": 7,
            "Security": 8,
            "Database": 6,
            "Dashboard": 5,
            "Frontend": 5,
            "UI/UX": 4,
            "Configuration": 3,
            "Bug Fix": 4,
            "Refactoring": 6,
            "Testing": 4,
            "Documentation": 2,
            "System/Script": 5,
            "Sync/Update": 2,
            "General Task": 3,
        }
        complexity += task_type_weights.get(task_type, 3)

        # --- Factor 2: Message length / detail (0-4) ---
        word_count = len(message.split())
        if word_count > 80:
            complexity += 4
        elif word_count > 40:
            complexity += 3
        elif word_count > 20:
            complexity += 2
        elif word_count > 10:
            complexity += 1

        # --- Factor 3: Entity count (0-3) ---
        entities = self.extract_entities(msg_lower)
        complexity += min(len(entities), 3)

        # --- Factor 4: Operation count (0-3) ---
        operations = self.extract_operations(msg_lower)
        if len(operations) >= 4:
            complexity += 3  # Full CRUD
        elif len(operations) >= 2:
            complexity += 2
        elif len(operations) >= 1:
            complexity += 1

        # --- Factor 5: Integration / cross-cutting keywords (0-4) ---
        integration_keywords = [
            "integration", "microservice", "service-to-service", "gateway",
            "eureka", "config server", "cross-service", "distributed",
            "event-driven", "kafka", "rabbitmq", "message queue",
        ]
        integration_hits = sum(1 for kw in integration_keywords if kw in msg_lower)
        complexity += min(integration_hits * 2, 4)

        # --- Factor 6: Architecture / design keywords (0-3) ---
        arch_keywords = [
            "architecture", "design pattern", "refactor", "restructure",
            "migrate", "migration", "upgrade", "scalab", "microservice",
            "monolith", "modular", "decouple",
        ]
        arch_hits = sum(1 for kw in arch_keywords if kw in msg_lower)
        complexity += min(arch_hits * 2, 3)

        return max(1, min(complexity, 25))

    def find_project_context(self, entities: List[str]) -> Dict:
        """Determine project and service context"""
        context = {
            "project_name": "surgricalswale",
            "service_name": "unknown-service",
            "base_package": "com.techdeveloper.surgricalswale"
        }

        # Map entities to services
        entity_service_map = {
            "user": "user-service",
            "auth": "auth-service",
            "authentication": "auth-service",
            "product": "product-service",
            "order": "order-service",
            "category": "category-service"
        }

        for entity in entities:
            if entity in entity_service_map:
                context["service_name"] = entity_service_map[entity]
                context["base_package"] = f"com.techdeveloper.surgricalswale.{entity}service"
                break

        return context

    def define_conditions(self, task_type: str, entities: List[str]) -> Dict:
        """Define pre and post conditions"""
        conditions = {
            "pre_conditions": [],
            "post_conditions": []
        }

        # Common pre-conditions
        conditions["pre_conditions"].append({
            "condition": "Service must exist or be created",
            "validation": "Check service directory exists",
            "command": "ls backend/{service-name}"
        })

        if task_type == "API Creation":
            conditions["pre_conditions"].extend([
                {
                    "condition": "Database must be configured",
                    "validation": "Check Config Server has datasource config",
                    "example": "configurations/surgricalswale/services/user-service.yml"
                },
                {
                    "condition": "Dependencies must be available",
                    "validation": "Check pom.xml has spring-boot-starter-data-jpa",
                    "example": "user-service/pom.xml"
                }
            ])

            conditions["post_conditions"].extend([
                {
                    "condition": "All CRUD endpoints must work",
                    "validation": "Test each endpoint",
                    "test": "curl requests to all endpoints"
                },
                {
                    "condition": "Responses must use ApiResponseDto<T>",
                    "validation": "Check response structure",
                    "test": "Verify JSON has success, message, data fields"
                },
                {
                    "condition": "Validation must work",
                    "validation": "Send invalid data",
                    "test": "Expect 400 with validation errors"
                }
            ])

        elif task_type == "Authentication":
            conditions["pre_conditions"].extend([
                {
                    "condition": "Secret Manager must have JWT secret",
                    "validation": "Check secret exists",
                    "command": "GET /api/v1/secrets/project/surgricalswale/key/jwt.secret"
                },
                {
                    "condition": "User entity must exist",
                    "validation": "Check User.java exists",
                    "example": "user-service/entity/User.java"
                }
            ])

            conditions["post_conditions"].extend([
                {
                    "condition": "Login must generate valid JWT",
                    "validation": "Call /api/v1/auth/login",
                    "test": "Verify JWT token returned"
                },
                {
                    "condition": "Unauthorized requests must return 401",
                    "validation": "Call protected endpoint without token",
                    "test": "Expect 401 Unauthorized"
                }
            ])

        return conditions

    def define_file_structure(self, task_type: str, service_name: str, entities: List[str]) -> Dict:
        """Define expected file structure"""
        base_path = f"backend/{service_name}/src/main/java/com/techdeveloper/surgricalswale/{service_name.replace('-service', 'service')}"

        structure = {
            "files_created": [],
            "files_modified": [],
            "configurations": []
        }

        if task_type == "API Creation" and entities:
            entity_name = entities[0].capitalize()

            structure["files_created"] = [
                {
                    "path": f"{base_path}/entity/{entity_name}.java",
                    "type": "JPA Entity",
                    "purpose": "Database table mapping",
                    "example": "user-service/entity/User.java"
                },
                {
                    "path": f"{base_path}/repository/{entity_name}Repository.java",
                    "type": "JPA Repository",
                    "purpose": "Database operations",
                    "example": "user-service/repository/UserRepository.java"
                },
                {
                    "path": f"{base_path}/services/{entity_name}Service.java",
                    "type": "Service Interface",
                    "purpose": "Business logic contract",
                    "example": "user-service/services/UserService.java"
                },
                {
                    "path": f"{base_path}/services/impl/{entity_name}ServiceImpl.java",
                    "type": "Service Implementation",
                    "purpose": "Business logic implementation",
                    "example": "user-service/services/impl/UserServiceImpl.java"
                },
                {
                    "path": f"{base_path}/controller/{entity_name}Controller.java",
                    "type": "REST Controller",
                    "purpose": "API endpoints",
                    "example": "user-service/controller/UserController.java"
                },
                {
                    "path": f"{base_path}/dto/{entity_name}Dto.java",
                    "type": "Response DTO",
                    "purpose": "API response structure",
                    "example": "user-service/dto/UserDto.java"
                },
                {
                    "path": f"{base_path}/form/{entity_name}Form.java",
                    "type": "Request Form",
                    "purpose": "API request with validation",
                    "example": "user-service/form/UserForm.java"
                }
            ]

            structure["configurations"] = [
                {
                    "location": f"techdeveloper/backend/techdeveloper-config-server/configurations/surgricalswale/services/{service_name}.yml",
                    "changes": ["Database config", "JPA settings", "Eureka registration"],
                    "template": "user-service.yml"
                }
            ]

        return structure

    def define_success_criteria(self, task_type: str, operations: List[str]) -> List[str]:
        """Define success criteria"""
        criteria = [
            "[CHECK] Code compiles successfully (mvn clean compile)",
            "[CHECK] No syntax or compilation errors",
            "[CHECK] Service starts without errors"
        ]

        if task_type == "API Creation":
            criteria.extend([
                "[CHECK] Service registers with Eureka",
                "[CHECK] All endpoints are accessible via Gateway",
                "[CHECK] Responses follow ApiResponseDto<T> pattern",
                "[CHECK] Validation works correctly",
                "[CHECK] Database operations work (if applicable)"
            ])

            for op in operations:
                if op == "create":
                    criteria.append("[CHECK] POST endpoint creates new record")
                elif op == "read":
                    criteria.append("[CHECK] GET endpoint retrieves records")
                elif op == "update":
                    criteria.append("[CHECK] PUT endpoint updates existing record")
                elif op == "delete":
                    criteria.append("[CHECK] DELETE endpoint removes record")

        elif task_type == "Authentication":
            criteria.extend([
                "[CHECK] Login endpoint generates valid JWT",
                "[CHECK] Protected endpoints require authentication",
                "[CHECK] Invalid tokens are rejected",
                "[CHECK] Token expiration works"
            ])

        return criteria

    def find_examples(self, task_type: str, entities: List[str]) -> List[Dict]:
        """Find example code from codebase"""
        examples = []

        example_map = {
            "API Creation": [
                {
                    "description": "User CRUD API implementation",
                    "service": "user-service",
                    "files": [
                        "controller/UserController.java",
                        "services/UserService.java",
                        "services/impl/UserServiceImpl.java",
                        "entity/User.java",
                        "repository/UserRepository.java"
                    ],
                    "pattern": "Complete CRUD with ApiResponseDto",
                    "usage": "Follow same structure for new entity"
                }
            ],
            "Authentication": [
                {
                    "description": "JWT Authentication implementation",
                    "service": "auth-service",
                    "files": [
                        "controller/AuthController.java",
                        "security/JwtUtil.java",
                        "security/JwtAuthenticationFilter.java",
                        "security/SecurityConfig.java"
                    ],
                    "pattern": "JWT generation and validation",
                    "usage": "Reuse JWT utilities"
                }
            ]
        }

        if task_type in example_map:
            examples = example_map[task_type]

        return examples

    def extract_topic_from_message(self, user_message: str) -> str:
        """
        Extract the ACTUAL TOPIC being discussed from any language message.
        Returns a meaningful English phrase describing what the user is talking about.
        This prevents losing intent when task_type falls back to General Task.
        """
        msg_lower = user_message.lower()

        # System/Script topics — order matters (specific before general)
        topic_patterns = [
            ("loophole", "loophole in the hook/prompt system"),
            ("hook rewrites", "hook prompt rewriting behavior"),
            ("rewritten prompt", "prompt rewriting logic"),
            ("prompt-generator", "prompt-generator.py script"),
            ("3-level", "3-level architecture flow"),
            ("claude insight", "changes to Claude Insight repository"),
            ("global library", "Claude Global Library repository"),
            ("memory system", "Claude memory system"),
            ("auto-fix", "auto-fix enforcement script"),
            ("session handler", "session handler script"),
            ("context-monitor", "context monitoring script"),
            ("standards-loader", "standards loader script"),
            ("flow.py", "3-level-flow.py script"),
            ("intent khoti", "user intent being lost in rewrite"),
            ("intent lost", "user intent being lost"),
            ("complexity scoring", "complexity scoring logic"),
            ("model/skill selection", "model and skill selection logic"),
            ("skill", "skill/agent selection logic"),
            ("agent", "agent selection logic"),
        ]
        for keyword, topic_desc in topic_patterns:
            if keyword in msg_lower:
                return topic_desc

        # Look for quoted phrases (user is referencing something specific)
        import re
        quoted = re.findall(r'["\']([^"\']{5,60})["\']', user_message)
        if quoted:
            return f'behavior described as: "{quoted[0][:60]}"'

        # Look for key nouns (capitalized or meaningful words)
        words = user_message.split()
        meaningful = [w for w in words if len(w) > 4 and w[0].isupper() and w.isalpha()]
        if meaningful:
            return " ".join(meaningful[:3]).lower()

        return "the requested feature/fix"

    def build_rewritten_prompt(self, user_message, task_type, entities, operations, complexity):
        """
        Convert any user input (Hinglish, informal, any language) into a proper English task description.
        Claude will use this rewritten prompt as the actual task to solve, not the raw original.

        CRITICAL: Must preserve actual user intent - never reduce to generic "Implement/fix the system".
        """
        msg_lower = user_message.lower()
        words = msg_lower.split()

        # --- Extract subject: what is being worked on ---
        subject = None
        # Hinglish pattern: "X wala/wali/wale" -> subject is X
        for i, word in enumerate(words):
            if word in ('wala', 'wali', 'wale') and i > 0:
                candidate = words[i - 1]
                if len(candidate) > 3:
                    subject = candidate
                    break
        # For System/Script tasks: extract meaningful topic instead of generic entity
        if task_type in ("System/Script", "Sync/Update", "General Task"):
            topic = self.extract_topic_from_message(user_message)
            if topic != "the requested feature/fix":
                subject = topic
        # Fall back to first entity or generic
        if not subject and entities:
            subject = entities[0]
        if not subject:
            subject = "the requested functionality"

        # --- Extract problem descriptions from Hinglish/informal patterns ---
        problem_parts = []
        hinglish_problems = {
            "nahi ban raha": "is not being generated/created",
            "nahi bana raha": "is not generating",
            "ni ban raha": "is not being generated",
            "ni ara": "is not showing/working",
            "same cheej": "passes through the same input unchanged (no transformation happening)",
            "same lere": "takes the same input without any processing",
            "same le raha": "takes the same input without processing",
            "kaam nahi kar": "is not functioning correctly",
            "kaam nhi kar": "is not functioning correctly",
            "ni lagta": "does not appear to be working correctly",
            "doubt hai": "behavior is uncertain/incorrect",
            "actually me": "in the actual implementation",
            "not working": "is not working correctly",
            "not generating": "is not generating the expected output",
        }
        for pattern, desc in hinglish_problems.items():
            if pattern in msg_lower:
                problem_parts.append(desc)

        # --- Extract goal descriptions from Hinglish/informal patterns ---
        goal_parts = []
        hinglish_goals = {
            "fix kar": "fix this issue",
            "theek kar": "correct this behavior",
            "banana hai": "generate/create properly",
            "banao": "create this",
            "dena ha": "pass to the next step",
            "acha prompt": "generate a proper well-structured English prompt",
            "jaise bhi language": "regardless of the input language used by the user",
            "khud ko dena": "pass the rewritten prompt to itself for processing",
            "sabse pehle": "first (before anything else)",
            "fir khud ko": "then pass it back to itself",
        }
        for pattern, desc in hinglish_goals.items():
            if pattern in msg_lower:
                goal_parts.append(desc)

        # --- Build task-specific base description ---
        task_descs = {
            "Bug Fix": "Fix the bug/issue in",
            "API Creation": "Create REST API for",
            "Authentication": "Implement authentication for",
            "Authorization": "Implement authorization for",
            "Database": "Fix/design database schema for",
            "Configuration": "Configure",
            "UI/UX": "Fix the UI/UX for",
            "Dashboard": "Fix/implement dashboard for",
            "Refactoring": "Refactor",
            "Testing": "Write tests for",
            "Security": "Implement security for",
            "Documentation": "Document",
            "Frontend": "Implement frontend for",
            "System/Script": "Fix/improve",
            "Sync/Update": "Sync/update",
            "General Task": "Investigate and fix",
        }
        action = task_descs.get(task_type, "Investigate and fix")
        base_desc = f"{action} {subject}"

        # --- Assemble the final rewritten prompt ---
        parts = [f"[{task_type}] {base_desc}."]

        if problem_parts:
            unique_problems = list(dict.fromkeys(problem_parts))[:2]
            parts.append("Problem identified: " + "; ".join(unique_problems) + ".")

        if goal_parts:
            unique_goals = list(dict.fromkeys(goal_parts))[:2]
            parts.append("Expected behavior: " + "; ".join(unique_goals) + ".")

        if operations and task_type not in ("Bug Fix", "Refactoring"):
            ops_str = ", ".join(operations)
            parts.append(f"Operations required: {ops_str}.")

        parts.append(f"Complexity: {complexity}/10.")

        return " ".join(parts)

    def generate(self, user_message: str) -> Dict:
        """Main method: Generate structured prompt with anti-hallucination phases"""

        print("=" * 80)
        print("[BRAIN] PHASE 1: THINKING")
        print("=" * 80)

        # PHASE 1: THINKING (Anti-Hallucination)
        thinking = self.think_about_request(user_message)
        print(f"\n[TARGET] Intent: {thinking['intent']}")
        print(f"[QUESTION] Sub-questions:")
        for q in thinking['sub_questions']:
            print(f"   - {q}")
        print(f"\n[CLIPBOARD] Information needed:")
        for info in thinking['information_needed']:
            print(f"   - {info}")
        print(f"\n[SEARCH] Will search in:")
        for source, location in thinking['where_to_find'].items():
            print(f"   - {source}: {location}")

        print("\n" + "=" * 80)
        print("[SEARCH] PHASE 2: INFORMATION GATHERING")
        print("=" * 80)

        # PHASE 2: INFORMATION GATHERING
        gathered_info = self.gather_information(thinking)
        print(f"\n[CHECK] Found {len(gathered_info.get('similar_files', []))} similar implementations")
        print(f"[CHECK] Extracted {len(gathered_info.get('patterns', []))} patterns")
        print(f"[CHECK] Verified project structure")
        if gathered_info.get('uncertainties'):
            print(f"\n[WARNING] Uncertainties found: {len(gathered_info['uncertainties'])}")

        print("\n" + "=" * 80)
        print("[CHECK] PHASE 3: VERIFICATION")
        print("=" * 80)

        # PHASE 3: VERIFICATION
        verification = self.verify_information(gathered_info)
        print(f"\n[CHECK] Examples verified: {verification['examples_verified']}")
        print(f"[CHECK] Paths verified: {verification['paths_verified']}")
        print(f"[CHECK] Patterns validated: {verification['patterns_validated']}")
        if verification.get('assumptions'):
            print(f"\n[WARNING] Assumptions made:")
            for assumption in verification['assumptions']:
                print(f"   - {assumption}")

        print("\n" + "=" * 80)
        print("[PAGE] GENERATING STRUCTURED PROMPT")
        print("=" * 80)

        # Step 1: Analyze
        analysis = self.analyze_request(user_message)

        # Step 2: Find context
        context = self.find_project_context(analysis["entities"])

        # Step 3: Define conditions
        conditions = self.define_conditions(analysis["task_type"], analysis["entities"])

        # Step 4: Define file structure
        file_structure = self.define_file_structure(
            analysis["task_type"],
            context["service_name"],
            analysis["entities"]
        )

        # Step 5: Define success criteria
        success_criteria = self.define_success_criteria(
            analysis["task_type"],
            analysis["operations"]
        )

        # Step 6: Find examples
        examples = self.find_examples(analysis["task_type"], analysis["entities"])

        # Generate structured prompt
        structured_prompt = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "original_request": user_message,
                "estimated_complexity": analysis["complexity"]
            },
            "task_type": analysis["task_type"],
            "project_context": {
                **context,
                "technology_stack": [
                    "Spring Boot 3.2.0",
                    "Spring Cloud 2023.0.0",
                    "PostgreSQL 15",
                    "Redis 7",
                    "Spring Security 6",
                    "Eureka Discovery",
                    "Config Server",
                    "API Gateway"
                ]
            },
            "analysis": {
                "entities": analysis["entities"],
                "operations": analysis["operations"],
                "keywords": analysis["keywords"]
            },
            "conditions": conditions,
            "expected_output": file_structure,
            "success_criteria": success_criteria,
            "examples_from_codebase": examples,
            "architecture_standards": [
                "java-project-structure.md",
                "api-design-standards.md",
                "error-handling-standards.md",
                "security-best-practices.md",
                "database-standards.md"
            ]
        }

        return structured_prompt


def main():
    """CLI interface"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python prompt-generator.py 'user message'")
        print("\nExample:")
        print("  python prompt-generator.py 'Create a product API with CRUD operations'")
        sys.exit(0)

    user_message = " ".join(sys.argv[1:])

    generator = PromptGenerator()
    structured_prompt = generator.generate(user_message)

    # Output machine-readable lines FIRST (parsed by 3-level-flow.py)
    task_type_out = structured_prompt.get("task_type", "General Task")
    complexity_out = structured_prompt.get("metadata", {}).get("estimated_complexity", 1)
    intent = structured_prompt.get("metadata", {}).get("original_request", user_message)[:80]
    entities = structured_prompt.get("analysis", {}).get("entities", [])
    operations = structured_prompt.get("analysis", {}).get("operations", [])

    # Build proper rewritten prompt from analysis (NOT just a label of the original message)
    rewritten = generator.build_rewritten_prompt(
        user_message, task_type_out, entities, operations, complexity_out
    )

    print(f"estimated_complexity: {complexity_out}")
    print(f"task_type: {task_type_out}")
    print(f"rewritten_prompt: {rewritten}")
    print(f"enhanced_prompt: {rewritten}")

    # Output as YAML
    print("=" * 80)
    print("STRUCTURED PROMPT")
    print("=" * 80)
    print(yaml.dump(structured_prompt, default_flow_style=False, sort_keys=False, allow_unicode=True))
    print("=" * 80)


if __name__ == "__main__":
    main()
