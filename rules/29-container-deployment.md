---
description: "Level 2.2 - Dockerfile template, non-root user, JVM container flags, health checks"
paths:
  - "Dockerfile"
  - "docker-compose*.yml"
  - ".dockerignore"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Container Deployment (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce a consistent, secure Dockerfile structure for all Spring Boot services.
Ensures containers run as non-root users, respect container memory limits via JVM flags,
expose only the required port, and provide health check endpoints that orchestrators can use.

**APPLIES WHEN:** Spring Boot project being packaged into a Docker image for deployment.

---

## 1. Base Image Selection

### What We Follow
Use a JRE-only Alpine-based image. Do not use a JDK image in production containers --
JDK images are larger and contain compilation tools unnecessary at runtime.

### How To Implement

```dockerfile
# CORRECT -- JRE-only Alpine (minimal attack surface)
FROM eclipse-temurin:17-jre-alpine

# WRONG -- JDK image in production
FROM eclipse-temurin:17-jdk-alpine
# JDK adds ~200MB and includes javac, jshell -- not needed at runtime

# WRONG -- non-Alpine base
FROM eclipse-temurin:17-jre
# Full Debian base adds ~100MB vs Alpine; no advantage for Spring Boot
```

### Why This Matters
JDK images shipped to production include compilation tools that can be exploited in
container breakout attacks. Alpine reduces the attack surface and image pull time.

---

## 2. Non-Root User

### What We Follow
Every Dockerfile creates a dedicated group and user with UID/GID 1000 and runs the
JVM process as that user. Never run the JVM as root inside the container.

### How To Implement

```dockerfile
# CORRECT -- non-root user setup
FROM eclipse-temurin:17-jre-alpine

# Create group and user with explicit GID/UID
RUN addgroup --system --gid 1000 appgroup \
    && adduser --system --uid 1000 --ingroup appgroup --no-create-home appuser

WORKDIR /app

COPY target/{service}-*.jar app.jar

# Set ownership before switching user
RUN chown appuser:appgroup app.jar

USER appuser

# WRONG -- running as root (default if USER is omitted)
FROM eclipse-temurin:17-jre-alpine
COPY target/{service}-*.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
# Container process runs as root -- Kubernetes SecurityContext check fails
```

Kubernetes Pod security context to enforce this:
```yaml
# CORRECT -- PodSpec securityContext
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
```

### Why This Matters
A container escape vulnerability combined with root user access gives the attacker host-level
privileges. A non-root UID limits the blast radius to the container filesystem.

---

## 3. JVM Container-Aware Flags

### What We Follow
Every Spring Boot container sets five JVM flags that optimize for containerized execution.
These flags ensure the JVM respects container memory cgroups and uses low-latency GC.

### How To Implement

```dockerfile
# CORRECT -- container-aware JVM flags
ENTRYPOINT ["java", \
    "-XX:MaxRAMPercentage=75.0", \
    "-XX:+UseG1GC", \
    "-XX:+UseStringDeduplication", \
    "-XX:+DisableExplicitGC", \
    "-Djava.security.egd=file:/dev/./urandom", \
    "-jar", "app.jar"]

# Explanation of each flag:
# MaxRAMPercentage=75.0   -- JVM heap = 75% of container memory limit (respects cgroups)
# UseG1GC                 -- Low-pause GC; default in Java 11+, explicit for clarity
# UseStringDeduplication  -- G1GC can deduplicate identical String objects in heap
# DisableExplicitGC       -- Prevents System.gc() calls from triggering full GC
# java.security.egd       -- Faster random seed source; prevents slow startup on /dev/random

# WRONG -- no container memory awareness
ENTRYPOINT ["java", "-jar", "app.jar"]
# JVM reads host total RAM (e.g., 64GB) and sets heap to ~16GB
# Container with 512MB limit is OOMKilled before application starts
```

### Why This Matters
Without `MaxRAMPercentage`, the JVM reads the host machine's total RAM through cgroup v1
on some systems and allocates a heap far larger than the container memory limit, causing
immediate OOMKill at startup.

---

## 4. HEALTHCHECK Instruction

### What We Follow
Every Dockerfile includes a `HEALTHCHECK` instruction that calls Spring Boot Actuator's
`/actuator/health` endpoint. The interval, timeout, start period, and retries are explicit.

### How To Implement

```dockerfile
# CORRECT -- health check pointing to Actuator
EXPOSE {service-port}

HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=60s \
    --retries=3 \
    CMD curl --fail --silent http://localhost:{service-port}/actuator/health || exit 1

# WRONG -- no HEALTHCHECK
# Docker and Kubernetes have no way to know if the application is actually healthy
# vs just the process running; traffic is sent to unhealthy containers

# WRONG -- ping instead of actuator
HEALTHCHECK CMD ping -c 1 localhost || exit 1
# Ping only verifies the network stack is up, not that Spring context loaded successfully
```

Kubernetes liveness and readiness probes complement the Dockerfile HEALTHCHECK:
```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: {service-port}
  initialDelaySeconds: 60
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: {service-port}
  initialDelaySeconds: 30
  periodSeconds: 10
```

### Why This Matters
Without a readiness probe, Kubernetes sends traffic to the container before Spring's
application context has finished loading, resulting in 503 errors during rolling deployments.

---

## 5. Complete Dockerfile Template

```dockerfile
FROM eclipse-temurin:17-jre-alpine

RUN addgroup --system --gid 1000 appgroup \
    && adduser --system --uid 1000 --ingroup appgroup --no-create-home appuser

WORKDIR /app

COPY target/{service}-*.jar app.jar

RUN chown appuser:appgroup app.jar

USER appuser

EXPOSE {service-port}

HEALTHCHECK \
    --interval=30s \
    --timeout=10s \
    --start-period=60s \
    --retries=3 \
    CMD curl --fail --silent http://localhost:{service-port}/actuator/health || exit 1

ENTRYPOINT ["java", \
    "-XX:MaxRAMPercentage=75.0", \
    "-XX:+UseG1GC", \
    "-XX:+UseStringDeduplication", \
    "-XX:+DisableExplicitGC", \
    "-Djava.security.egd=file:/dev/./urandom", \
    "-jar", "app.jar"]
```

---

**ENFORCEMENT:** CI pipeline: `docker build` in pull request pipeline validates Dockerfile
syntax. Kubernetes admission controller (OPA/Kyverno) rejects pods running as root.
Security scan: Trivy scans the built image for vulnerabilities before push.

**SEE ALSO:**
- 30-maven-build-conventions.md -- spring-boot-maven-plugin producing the JAR that COPY uses
- 31-security-authentication.md -- Spring Security configuration for /actuator/health public access
- 13-spring-cloud-infrastructure.md -- Config Server properties that configure service port
