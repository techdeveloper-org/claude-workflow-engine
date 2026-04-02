---
description: "Level 2.2 - Spring Cloud infrastructure: config server, service discovery, API gateway, retry/failover"
paths:
  - "src/**/*.java"
  - "**/application*.yml"
  - "**/application*.yaml"
  - "**/bootstrap*.yml"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Spring Cloud Infrastructure (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce consistent Spring Cloud topology so every microservice connects to centralized
configuration, registers with service discovery, and routes traffic through a single API gateway.
Prevents hard-coded URLs, scattered configuration, and direct service-to-service calls.

**APPLIES WHEN:** Spring Boot project with spring-cloud-starter dependencies in pom.xml.

---

## 1. Centralized Configuration Server

### What We Follow
Every microservice application.yml contains ONLY the config import pointer and retry settings.
ALL business properties (database URLs, Redis, feature flags, ports) live in the Config Server.

### How To Implement

```yaml
# CORRECT -- service application.yml (minimal bootstrap)
spring:
  application:
    name: {service}
  config:
    import: "optional:configserver:{config-server-url}"
  cloud:
    config:
      retry:
        initial-interval: 1000
        max-interval: 2000
        max-attempts: 6
        multiplier: 1.1
      fail-fast: true

# WRONG -- embedding business properties directly in service application.yml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/{schema}
    username: admin
    password: secret123
server:
  port: 8081
```

Secret references use the placeholder pattern:

```yaml
# CORRECT -- in Config Server's {service}.yml
spring:
  datasource:
    password: ${SECRET:db-password-key}

# WRONG -- hardcoded secret in any file
spring:
  datasource:
    password: plaintext-secret
```

### Why This Matters
Scattered configuration across service YAMLs makes environment-specific changes require
re-deploying every service. Centralized config enables zero-downtime property refresh.

---

## 2. Service Discovery with Eureka

### What We Follow
Every service registers itself with Eureka using `@EnableDiscoveryClient`. Services never
hardcode peer URLs; they resolve by service name through the registry.

### How To Implement

```java
// CORRECT -- main application class
@SpringBootApplication
@EnableDiscoveryClient
public class {Entity}ServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run({Entity}ServiceApplication.class, args);
    }
}

// WRONG -- omitting @EnableDiscoveryClient and hardcoding peer URLs
@SpringBootApplication
public class {Entity}ServiceApplication {
    // service will not register; other services cannot discover it
}
```

```yaml
# CORRECT -- in Config Server: {service}.yml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server/eureka/
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${server.port}
```

### Why This Matters
Without service discovery, changing the IP or port of a service requires updating every
dependent service's configuration — error-prone and requires coordinated deployments.

---

## 3. API Gateway as Single Entry Point

### What We Follow
All external client traffic AND inter-service traffic flows through the API gateway.
No service exposes ports directly to the network outside the cluster.

### How To Implement

```yaml
# CORRECT -- Gateway routing configuration in Config Server: gateway.yml
spring:
  cloud:
    gateway:
      routes:
        - id: {service}-route
          uri: lb://{service}
          predicates:
            - Path=/{service-path}/**
          filters:
            - StripPrefix=1
            - name: CircuitBreaker
              args:
                name: {service}CircuitBreaker
                fallbackUri: forward:/{service}/fallback

# WRONG -- client calling service directly
# http://product-service:8081/api/products  <-- bypasses gateway
```

```java
// CORRECT -- inter-service Feign client points to gateway
@FeignClient(
    name = "gateway",
    contextId = "{entity}Client",
    url = "${gateway.url}",
    configuration = FeignConfig.class
)
public interface {Entity}Client {
    @GetMapping("/{service-path}/{id}")
    ApiResponseDto<{Entity}Dto> get{Entity}ById(@PathVariable String id);
}

// WRONG -- Feign client pointing directly to another service
@FeignClient(name = "{service}", url = "http://{service}:8081")
```

### Why This Matters
Direct service-to-service calls bypass authentication, rate limiting, and circuit breaking.
The gateway is the single enforcement point for cross-cutting concerns.

---

## 4. Retry and Fail-Fast

### What We Follow
Config Server imports use `fail-fast: true` with bounded exponential backoff. Services fail
at startup if config cannot be fetched rather than starting with empty/stale configuration.

### How To Implement

```yaml
# CORRECT -- bounded retry with fail-fast
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        initial-interval: 1000
        max-interval: 4000
        max-attempts: 6
        multiplier: 2.0

# WRONG -- infinite retry or no fail-fast (service starts with defaults silently)
spring:
  cloud:
    config:
      fail-fast: false
```

Resilience4j circuit breaker on gateway routes:

```yaml
# CORRECT -- in Config Server: gateway.yml
resilience4j:
  circuitbreaker:
    instances:
      {service}CircuitBreaker:
        sliding-window-size: 10
        failure-rate-threshold: 50
        wait-duration-in-open-state: 10s
        permitted-number-of-calls-in-half-open-state: 3
        slow-call-duration-threshold: 2s
        slow-call-rate-threshold: 80
```

### Why This Matters
Without fail-fast, a service starts with missing configuration and silently uses defaults
(often null/empty), causing runtime failures that are hard to trace back to missing config.

---

**ENFORCEMENT:** Level 2 loading -- injected when Spring Cloud starter is detected in pom.xml.
Violations flagged during code review for any PR adding new service configuration.

**SEE ALSO:**
- 03-microservices-standards.md -- project structure and package conventions
- 20-inter-service-communication.md -- Feign client configuration and circuit breaker fallback details (expands Section 4)
- 21-caching-strategy.md -- Redis configuration via Config Server
- 27-centralized-logging.md -- log level governance via Config Server
- 31-security-authentication.md -- JWT filter and CORS configuration via Config Server
