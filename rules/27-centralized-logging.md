---
description: "Level 2.2 - Logback HTTP appender, async batching, MDC tracing, log level governance"
paths:
  - "src/main/resources/logback-spring.xml"
  - "src/main/resources/logback*.xml"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Centralized Logging (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce a consistent logback-spring.xml structure across all services that
sends structured JSON logs to a central endpoint asynchronously without blocking request
processing. Log levels are not managed in logback.xml -- they come from Config Server.
Sensitive data is never logged.

**APPLIES WHEN:** Spring Boot project with logback-spring.xml for logging configuration.

---

## 1. Dual Appender: Console + HTTP

### What We Follow
Every service has two appenders:
- Console appender: for local development and container stdout
- HTTP appender: for centralized log aggregation (sends to a log collector endpoint)

Both are wrapped in an async wrapper. The async wrapper uses `neverBlock=true` so that
a slow or down log collector never blocks a request thread.

### How To Implement

```xml
<!-- CORRECT -- logback-spring.xml with dual async appenders -->
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <springProperty scope="context" name="SERVICE_NAME"
                    source="spring.application.name" defaultValue="unknown-service"/>

    <!-- Console appender for local dev and container stdout -->
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <customFields>{"service":"${SERVICE_NAME}"}</customFields>
        </encoder>
    </appender>

    <!-- HTTP appender for centralized log aggregation -->
    <appender name="HTTP_LOG" class="ch.qos.logback.classic.net.SyslogAppender">
        <!-- Replace with your centralized log collector appender class -->
        <!-- Example: custom HttpLogAppender, Loki appender, etc. -->
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <customFields>{"service":"${SERVICE_NAME}"}</customFields>
        </encoder>
    </appender>

    <!-- CORRECT -- async wrapper: never blocks, bounded queue -->
    <appender name="ASYNC_HTTP" class="ch.qos.logback.classic.AsyncAppender">
        <appender-ref ref="HTTP_LOG"/>
        <queueSize>512</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>true</neverBlock>
        <includeCallerData>false</includeCallerData>
    </appender>

    <appender name="ASYNC_CONSOLE" class="ch.qos.logback.classic.AsyncAppender">
        <appender-ref ref="CONSOLE"/>
        <queueSize>256</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>true</neverBlock>
    </appender>

    <!-- Root logger -- level managed via Config Server, not here -->
    <root level="INFO">
        <appender-ref ref="ASYNC_CONSOLE"/>
        <appender-ref ref="ASYNC_HTTP"/>
    </root>

</configuration>

<!-- WRONG -- synchronous appender directly in root -->
<root level="INFO">
    <appender-ref ref="HTTP_LOG"/>  <!-- Blocks request thread on slow collector -->
</root>
```

### Why This Matters
A synchronous HTTP appender calls the log collector on every log statement. If the collector
has a 100ms latency spike, every request thread is delayed 100ms per log call -- turning
a logging latency issue into a service latency regression.

---

## 2. MDC Pattern for Distributed Tracing

### What We Follow
Every request sets MDC (Mapped Diagnostic Context) fields for `traceId`, `spanId`, and
`correlationId`. These appear in every log line within the request scope without any
per-log call modification.

### How To Implement

```java
// CORRECT -- MDC set in filter, cleared in finally
@Component
@Order(1)
public class MdcLoggingFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request, ServletResponse response,
                         FilterChain chain) throws IOException, ServletException {
        HttpServletRequest httpRequest = (HttpServletRequest) request;

        String correlationId = Optional
            .ofNullable(httpRequest.getHeader("X-Correlation-ID"))
            .orElse(UUID.randomUUID().toString().replace("-", "").substring(0, 16));

        MDC.put("correlationId", correlationId);
        MDC.put("service", getServiceName());

        // If OpenTelemetry is active, trace/span IDs are set by the OTel agent
        // If not, set synthetic IDs for log correlation
        MDC.put("traceId", Optional.ofNullable(MDC.get("traceId"))
            .orElse(correlationId));

        try {
            ((HttpServletResponse) response).setHeader("X-Correlation-ID", correlationId);
            chain.doFilter(request, response);
        } finally {
            MDC.clear();  // MANDATORY: prevents MDC leak in thread pool
        }
    }
}
```

Logback pattern with MDC fields:
```xml
<!-- Pattern for console appender in dev -->
<pattern>%d{HH:mm:ss} %-5level [%X{correlationId},%X{traceId}] %logger{36} - %msg%n</pattern>
```

JSON appender includes MDC automatically via `LogstashEncoder`.

```java
// WRONG -- MDC without finally block
try {
    MDC.put("correlationId", id);
    chain.doFilter(request, response);
} catch (Exception e) {
    // MDC.clear() never called if exception thrown
    // Thread pool thread retains previous request's correlationId
}
```

### Why This Matters
A thread pool thread that processes request A sets MDC to `correlationId=A`. If the filter
does not call `MDC.clear()` in a finally block, request B processed on the same thread
logs with `correlationId=A` -- poisoning log correlation.

---

## 3. Log Level Governance via Config Server

### What We Follow
Log levels for all packages are defined in Config Server, not in logback-spring.xml.
The only level in logback-spring.xml is `<root level="INFO">` as the floor.
Package-level overrides (e.g., DEBUG for a specific module during investigation) are
changed in Config Server and refreshed without redeploy via Spring Cloud Config refresh.

### How To Implement

```yaml
# CORRECT -- in Config Server: {service}.yml
logging:
  level:
    root: INFO
    {org}.{project}.{service}: INFO
    org.springframework.web: WARN
    org.hibernate.SQL: WARN
    # During investigation: override temporarily
    # {org}.{project}.{service}.service: DEBUG

# WRONG -- levels hardcoded in logback-spring.xml
<logger name="{org}.{project}.{service}" level="DEBUG"/>
# Cannot change without file edit + redeploy
```

### Why This Matters
DEBUG logging hardcoded in logback.xml runs in production permanently, generating gigabytes
of logs and exposing internal state in the log aggregation system.

---

## 4. Sensitive Data Must Never Be Logged

### What We Follow
The following categories must never appear in any log message, parameter, or MDC field:
- Passwords and secrets (API keys, tokens, private keys)
- Full credit card numbers, CVV codes
- National ID numbers, passport numbers
- Authentication tokens (JWT, OAuth tokens)
- PII beyond what is required for the audit scope (email, phone number)

### How To Implement

```java
// CORRECT -- log only the user ID reference, not the credential
log.info("Login attempt for user {}", userId);  // OK -- ID only

// WRONG -- logging the credential
log.info("Login attempt with password {}", password);    // NEVER
log.debug("Request body: {}", requestBody);             // body may contain password
log.info("Authorization header: {}", authHeader);        // contains JWT token
```

Automatic masking in LogstashEncoder for field-level masking:
```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
    <fieldNames>
        <message>message</message>
    </fieldNames>
    <!-- Do NOT log MDC fields that may contain sensitive values -->
</encoder>
```

### Why This Matters
Credential logging creates a security audit finding in any compliance review (SOC2, ISO 27001,
PCI DSS). Log files are often retained for 90+ days and ship to external aggregation systems.

---

**ENFORCEMENT:** Level 2 loading -- CI: `grep -r "password\|token\|secret"` scan on log
statements in Java source. Code review: no `log.debug("... request body ...")` patterns.
LogstashEncoder in POM verified by automated dependency check.

**SEE ALSO:**
- 13-spring-cloud-infrastructure.md -- log level properties in Config Server
- 31-security-authentication.md -- JWT filter where token must not be logged
- 03-microservices-standards.md -- See also: 01-common-standards.md Section 6 (API Design)
