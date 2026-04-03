# pre_tool_enforcer/policies/skill_context.py
# Level 3.5+ Dynamic: inject skill/agent context based on target file type.
# Non-blocking: returns hints only, never blocks.
# Windows-safe: ASCII only, no Unicode characters.

# Extension -> (skill_or_agent_name, type, brief_context)
FILE_EXT_SKILL_MAP = {
    # Java ecosystem
    ".java": (
        "java-spring-boot-microservices",
        "skill",
        "Java/Spring Boot patterns, annotations, DI, REST controllers",
    ),
    ".gradle": ("java-spring-boot-microservices", "skill", "Gradle build config for Spring Boot"),
    ".kt": ("android-backend-engineer", "agent", "Kotlin/Android backend, API integration, data flow"),
    ".kts": ("android-backend-engineer", "agent", "Kotlin script/Gradle DSL"),
    # Python ecosystem
    ".py": ("python-system-scripting", "skill", "Python scripting, Windows-safe, ASCII-only, cp1252 compatible"),
    # JavaScript/TypeScript ecosystem
    ".ts": ("angular-engineer", "agent", "TypeScript/Angular components, services, modules, RxJS"),
    ".tsx": ("ui-ux-designer", "agent", "React TSX components, hooks, state management"),
    ".js": ("ui-ux-designer", "agent", "JavaScript UI logic, DOM, event handling"),
    ".jsx": ("ui-ux-designer", "agent", "React JSX components, hooks, state management"),
    ".vue": ("ui-ux-designer", "agent", "Vue.js SFC components, composition API"),
    # Web/Styling
    ".css": ("css-core", "skill", "CSS layout, flexbox, grid, responsive design, variables"),
    ".scss": ("css-core", "skill", "SCSS/Sass, mixins, nesting, variables, partials"),
    ".less": ("css-core", "skill", "Less CSS preprocessor, mixins, variables"),
    ".html": ("ui-ux-designer", "agent", "HTML structure, semantic elements, accessibility"),
    # iOS/macOS
    ".swift": ("swift-backend-engineer", "agent", "Swift backend, Vapor, REST APIs, async/await"),
    # Database
    ".sql": ("rdbms-core", "skill", "SQL queries, schema design, indexing, joins, transactions"),
    # Handled by filename check (could be K8s, Docker, Jenkins, etc.)
    ".yml": None,
    ".yaml": None,
    # Could be Android layout, Maven POM, or generic XML - check filename
    ".xml": None,
    # No specific skill needed
    ".md": None,
}

# Special filename patterns -> (skill_or_agent_name, type, brief_context)
# Checked BEFORE extension mapping (higher priority)
FILENAME_SKILL_MAP = [
    # Build files
    ("pom.xml", "java-spring-boot-microservices", "skill", "Maven POM, Spring Boot dependencies, plugins"),
    ("build.gradle", "java-spring-boot-microservices", "skill", "Gradle build for Spring Boot"),
    ("build.gradle.kts", "java-spring-boot-microservices", "skill", "Gradle Kotlin DSL for Spring Boot"),
    # Docker
    ("Dockerfile", "docker", "skill", "Dockerfile, multi-stage builds, layer optimization, security"),
    ("docker-compose.yml", "docker", "skill", "Docker Compose services, networks, volumes"),
    ("docker-compose.yaml", "docker", "skill", "Docker Compose services, networks, volumes"),
    (".dockerignore", "docker", "skill", "Docker build context exclusions"),
    # Kubernetes
    ("deployment.yaml", "kubernetes", "skill", "K8s Deployment spec, replicas, strategy, probes"),
    ("deployment.yml", "kubernetes", "skill", "K8s Deployment spec, replicas, strategy, probes"),
    ("service.yaml", "kubernetes", "skill", "K8s Service spec, ClusterIP, NodePort, LoadBalancer"),
    ("service.yml", "kubernetes", "skill", "K8s Service spec, ClusterIP, NodePort, LoadBalancer"),
    ("ingress.yaml", "kubernetes", "skill", "K8s Ingress rules, TLS, host/path routing"),
    ("ingress.yml", "kubernetes", "skill", "K8s Ingress rules, TLS, host/path routing"),
    ("configmap.yaml", "kubernetes", "skill", "K8s ConfigMap, environment config"),
    ("secret.yaml", "kubernetes", "skill", "K8s Secret, base64, encryption"),
    ("statefulset.yaml", "kubernetes", "skill", "K8s StatefulSet, persistent storage, ordered startup"),
    ("values.yaml", "kubernetes", "skill", "Helm chart values, templates, releases"),
    ("Chart.yaml", "kubernetes", "skill", "Helm Chart metadata, dependencies"),
    # Jenkins
    ("Jenkinsfile", "jenkins-pipeline", "skill", "Jenkins pipeline, stages, agents, post actions"),
    # Frontend configs
    ("angular.json", "angular-engineer", "agent", "Angular workspace config, build, serve"),
    ("tsconfig.json", "angular-engineer", "agent", "TypeScript compiler config"),
    ("package.json", None, None, None),
    # Android
    ("AndroidManifest.xml", "android-backend-engineer", "agent", "Android manifest, permissions, activities"),
    # iOS
    ("Podfile", "swiftui-designer", "agent", "CocoaPods dependencies for iOS"),
    ("Package.swift", "swift-backend-engineer", "agent", "Swift Package Manager, dependencies"),
    # SEO
    ("robots.txt", "seo-keyword-research-core", "skill", "SEO robots directives, crawl rules"),
    ("sitemap.xml", "seo-keyword-research-core", "skill", "SEO sitemap, URL priorities, change freq"),
    # Database
    ("schema.sql", "rdbms-core", "skill", "Database schema DDL, tables, constraints, indexes"),
    ("migration.sql", "rdbms-core", "skill", "Database migration, ALTER TABLE, data transforms"),
    ("init.sql", "rdbms-core", "skill", "Database initialization, seed data"),
]

# Directory path patterns -> (skill_or_agent_name, type, brief_context)
DIR_PATTERN_SKILL_MAP = [
    ("/src/main/java/", "java-spring-boot-microservices", "skill", "Java source in Spring Boot project"),
    ("/src/test/java/", "java-spring-boot-microservices", "skill", "Java test in Spring Boot project"),
    (
        "/src/main/resources/",
        "java-spring-boot-microservices",
        "skill",
        "Spring Boot resources (application.yml, etc.)",
    ),
    ("/controller/", "java-spring-boot-microservices", "skill", "Spring MVC/REST controller layer"),
    ("/service/", "java-spring-boot-microservices", "skill", "Spring service/business logic layer"),
    ("/repository/", "java-spring-boot-microservices", "skill", "Spring Data JPA repository layer"),
    ("/entity/", "java-spring-boot-microservices", "skill", "JPA entity/model layer"),
    ("/dto/", "java-spring-boot-microservices", "skill", "Data Transfer Object pattern"),
    ("/config/", "java-spring-boot-microservices", "skill", "Spring configuration classes"),
    ("/k8s/", "kubernetes", "skill", "Kubernetes manifests directory"),
    ("/helm/", "kubernetes", "skill", "Helm chart directory"),
    ("/charts/", "kubernetes", "skill", "Helm charts directory"),
    ("/deploy/", "devops-engineer", "agent", "Deployment scripts/config"),
    ("/ci/", "devops-engineer", "agent", "CI/CD pipeline config"),
    ("/res/layout/", "android-ui-designer", "agent", "Android XML layout files"),
    ("/res/drawable/", "android-ui-designer", "agent", "Android drawable resources"),
    ("/res/values/", "android-ui-designer", "agent", "Android values (strings, colors, styles)"),
    ("/components/", "angular-engineer", "agent", "Frontend component directory"),
    ("/services/", "angular-engineer", "agent", "Frontend service directory"),
]

# Map technology names to file extensions and their corresponding skills/agents
_TECH_TO_FILE_SKILL = {
    "spring-boot": (".java", "java-spring-boot-microservices"),
    "java": (".java", "java-spring-boot-microservices"),
    "angular": (".ts", "angular-engineer"),
    "typescript": (".ts", "angular-engineer"),
    "react": (".tsx", "ui-ux-designer"),
    "vue": (".vue", "ui-ux-designer"),
    "css": (".css", "css-core"),
    "scss": (".scss", "css-core"),
    "html": (".html", "ui-ux-designer"),
    "python": (".py", "python-backend-engineer"),
    "flask": (".py", "python-backend-engineer"),
    "django": (".py", "python-backend-engineer"),
    "fastapi": (".py", "python-backend-engineer"),
    "docker": ("Dockerfile", "docker"),
    "kubernetes": (".yaml", "kubernetes"),
    "jenkins": ("Jenkinsfile", "jenkins-pipeline"),
    "postgresql": (".sql", "rdbms-core"),
    "mysql": (".sql", "rdbms-core"),
    "mongodb": (".json", "nosql-core"),
    "kotlin": (".kt", "android-backend-engineer"),
    "swift": (".swift", "swift-backend-engineer"),
}

# Track last printed skill to avoid spamming same hint repeatedly (module-level)
_last_skill_hint = ""


def _infer_skills_from_tech_stack(tech_stack, exclude_skill=None):
    """Build hint string showing other file types in the task's tech stack."""
    if not tech_stack or tech_stack == ["unknown"]:
        return ""

    parts = []
    for tech in tech_stack:
        if tech == "unknown" or tech not in _TECH_TO_FILE_SKILL:
            continue
        file_ext, skill = _TECH_TO_FILE_SKILL[tech]
        if skill == exclude_skill:
            continue
        parts.append(file_ext + " -> " + skill)

    return " | ".join(parts)


def check_dynamic_skill_context(tool_name, tool_input):
    """Level 3.5+ Dynamic: inject skill/agent context based on target file type.

    Non-blocking: emits [SKILL-CONTEXT] hints only.
    The hints are collected by core.py and printed to stdout.

    Args:
        tool_name (str): Name of the tool being called.
        tool_input (dict): Dict of tool parameters containing the file path key.

    Returns:
        tuple: (blocked: bool, message: str) - blocked is always False.
               message contains the hint (empty string if no match or dedup).
    """
    global _last_skill_hint

    if tool_name not in ("Read", "Write", "Edit", "NotebookEdit", "Grep", "Glob"):
        return False, ""

    # Extract file path from tool input
    file_path = ""
    if tool_name in ("Read", "Write", "Edit", "NotebookEdit"):
        file_path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "") or ""
    elif tool_name == "Grep":
        file_path = tool_input.get("path", "") or ""
        glob_pattern = tool_input.get("glob", "") or tool_input.get("type", "") or ""
        if glob_pattern and not file_path:
            file_path = glob_pattern
    elif tool_name == "Glob":
        file_path = tool_input.get("pattern", "") or ""

    if not file_path:
        return False, ""

    # Normalize path separators
    normalized = file_path.replace("\\", "/")

    # Extract filename and extension
    if "/" in normalized:
        filename = normalized.rsplit("/", 1)[1]
    else:
        filename = normalized

    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[1].lower()

    # STEP 1: Check special filenames first (highest priority)
    matched_skill = None
    matched_type = None
    matched_context = None

    for pattern_name, skill_name, skill_type, context in FILENAME_SKILL_MAP:
        if skill_name is None:
            continue
        if filename == pattern_name or filename.lower() == pattern_name.lower():
            matched_skill = skill_name
            matched_type = skill_type
            matched_context = context
            break

    # STEP 2: Check directory path patterns
    if not matched_skill:
        for dir_pattern, skill_name, skill_type, context in DIR_PATTERN_SKILL_MAP:
            if dir_pattern in normalized:
                matched_skill = skill_name
                matched_type = skill_type
                matched_context = context
                break

    # STEP 3: Check file extension
    if not matched_skill and ext:
        ext_entry = FILE_EXT_SKILL_MAP.get(ext)
        if ext_entry and ext_entry is not None:
            matched_skill, matched_type, matched_context = ext_entry

    # STEP 4: YAML files - detect K8s vs Docker vs generic
    if not matched_skill and ext in (".yml", ".yaml"):
        lower_name = filename.lower()
        if any(
            k in lower_name
            for k in [
                "deploy",
                "service",
                "ingress",
                "configmap",
                "secret",
                "stateful",
                "daemonset",
                "values",
                "chart",
                "namespace",
                "pv",
                "pvc",
                "hpa",
            ]
        ):
            matched_skill = "kubernetes"
            matched_type = "skill"
            matched_context = "Kubernetes manifest YAML"
        elif "docker-compose" in lower_name:
            matched_skill = "docker"
            matched_type = "skill"
            matched_context = "Docker Compose services"
        elif "jenkins" in lower_name or "pipeline" in lower_name:
            matched_skill = "jenkins-pipeline"
            matched_type = "skill"
            matched_context = "Jenkins pipeline YAML config"
        elif "application" in lower_name:
            matched_skill = "java-spring-boot-microservices"
            matched_type = "skill"
            matched_context = "Spring Boot application.yml config"

    # STEP 5: XML files - detect Android vs Maven vs generic
    if not matched_skill and ext == ".xml":
        lower_name = filename.lower()
        lower_path = normalized.lower()
        if "pom.xml" == lower_name:
            matched_skill = "java-spring-boot-microservices"
            matched_type = "skill"
            matched_context = "Maven POM dependencies and plugins"
        elif "/res/layout/" in lower_path or "/res/drawable/" in lower_path or "/res/values/" in lower_path:
            matched_skill = "android-ui-designer"
            matched_type = "agent"
            matched_context = "Android XML layout/resource"
        elif "AndroidManifest" in filename:
            matched_skill = "android-backend-engineer"
            matched_type = "agent"
            matched_context = "Android manifest, permissions, activities"

    if not matched_skill:
        return False, ""

    # Deduplicate consecutive identical hints
    hint_key = matched_skill + ":" + filename
    if hint_key == _last_skill_hint:
        return False, ""
    _last_skill_hint = hint_key

    type_label = "agent" if matched_type == "agent" else "skill"
    short_file = filename
    if len(normalized) > 60:
        parts = normalized.split("/")
        short_file = "/".join(parts[-3:]) if len(parts) > 3 else normalized

    hint_lines = [
        "[SKILL-CONTEXT] " + short_file + " -> " + matched_skill + " (" + type_label + ")",
        "  CONTEXT: " + (matched_context or ""),
        "  ACTION: Apply " + matched_skill + " patterns and best practices for this file.",
    ]

    return False, "\n".join(hint_lines)
