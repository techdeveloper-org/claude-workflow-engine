---
description: "Level 2.2 - OpenFeign via gateway, client configuration, circuit breaking"
paths:
  - "src/**/client/**/*.java"
  - "src/**/config/FeignConfig.java"
  - "src/**/config/FeignClientConfig.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Inter-Service Communication (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce that all inter-service calls go through the API gateway using OpenFeign
clients defined in common-lib. Prevents direct service-to-service calls that bypass
authentication, circuit breaking, and centralized routing.

**APPLIES WHEN:** Spring Boot microservices ecosystem where services need to call each other.

---

## 1. All Inter-Service Calls Via Gateway

### What We Follow
Every Feign client points to the gateway URL (`${gateway.url}`), not to a peer service
URL directly. The `contextId` attribute differentiates multiple clients that all point
to the same gateway.

### How To Implement

```java
// CORRECT -- Feign client through gateway
@FeignClient(
    name = "gateway",
    contextId = "{entity}ServiceClient",
    url = "${gateway.url}",
    configuration = FeignClientConfig.class
)
public interface {Entity}ServiceClient {

    @GetMapping("/{service-path}/{id}")
    ApiResponseDto<{Entity}Dto> get{Entity}ById(@PathVariable("id") Long id);

    @GetMapping("/{service-path}/exists/{id}")
    ApiResponseDto<Boolean> {entity}Exists(@PathVariable("id") Long id);
}

// WRONG -- client pointing directly to peer service
@FeignClient(name = "{service}", url = "http://{service}:8081")
public interface {Entity}ServiceClient {
    // Bypasses gateway; no circuit breaking; hard-coded URL
}

// WRONG -- using RestTemplate or WebClient for inter-service calls
@Component
public class {Entity}ServiceCaller {
    @Autowired
    private RestTemplate restTemplate;

    public {Entity}Dto getEntity(Long id) {
        return restTemplate.getForObject(
            "http://{service}:8081/{service-path}/" + id,
            {Entity}Dto.class
        );
    }
}
```

### Why This Matters
Calls that bypass the gateway bypass all cross-cutting concerns: JWT validation, rate
limiting, and circuit breaking. One direct connection creates a security hole in the
authentication perimeter.

---

## 2. Feign Client Configuration

### What We Follow
A shared `FeignClientConfig` class (in common-lib) sets the Feign logger level to `FULL`
for debugging and sets timeouts. Services do not define their own Feign configurations
unless they need to override specific settings.

### How To Implement

```java
// CORRECT -- FeignClientConfig in common-lib
public class FeignClientConfig {

    @Bean
    public Logger.Level feignLoggerLevel() {
        return Logger.Level.FULL;
    }

    @Bean
    public Request.Options requestOptions() {
        return new Request.Options(
            5, TimeUnit.SECONDS,   // connect timeout
            10, TimeUnit.SECONDS,  // read timeout
            true                   // follow redirects
        );
    }
}

// Enable Feign clients on the service application class
@SpringBootApplication
@EnableDiscoveryClient
@EnableFeignClients(basePackages = "{org}.{project}.common.client")
public class {Entity}ServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run({Entity}ServiceApplication.class, args);
    }
}

// WRONG -- Logger.Level.NONE (silent failures in debug)
public class CustomFeignConfig {
    @Bean
    public Logger.Level feignLoggerLevel() {
        return Logger.Level.NONE;
    }
}
```

### Why This Matters
`Logger.Level.FULL` logs request headers, request body, response headers, and response body.
Without full logging, debugging a Feign call failure requires adding temporary instrumentation.

---

## 3. Feign Clients Defined in common-lib

### What We Follow
Feign client interfaces live in the `client/` package of the common-lib so that any service
in the ecosystem can consume any other service without duplicating the client definition.

### How To Implement

```
CORRECT -- Feign clients in common-lib
{project}-common-lib/
  src/main/java/{org}/{project}/common/
    client/
      {Entity}ServiceClient.java     <- Feign client for {service}
      {OtherEntity}ServiceClient.java
    dto/
      {Entity}Dto.java
      ApiResponseDto.java

WRONG -- Feign client duplicated in each consuming service
{service-a}/src/main/java/.../client/{Entity}ServiceClient.java
{service-b}/src/main/java/.../client/{Entity}ServiceClient.java
// Two copies diverge; one gets updated and the other silently calls wrong endpoint
```

```java
// CORRECT -- service imports client from common-lib
@Service
@RequiredArgsConstructor
class OrderServicesImpl extends OrderServiceHelper implements OrderServices {

    private final {Entity}ServiceClient {entity}Client;  // from common-lib

    private boolean verify{Entity}Exists(Long {entity}Id) {
        ApiResponseDto<Boolean> response = {entity}Client.{entity}Exists({entity}Id);
        return response.isSuccess() && Boolean.TRUE.equals(response.getData());
    }
}
```

### Why This Matters
Duplicated Feign client interfaces drift apart. When a target endpoint path changes,
only one copy gets updated; the other silently calls the wrong URL until a runtime error.

---

## 4. Circuit Breaker Fallback Methods

### What We Follow
Non-critical Feign calls that can degrade gracefully carry `@CircuitBreaker` with
a fallback method that returns a safe default or empty response.

### How To Implement

```java
// CORRECT -- service call with fallback
@Service
@RequiredArgsConstructor
class {Entity}ServicesImpl extends {Entity}ServiceHelper implements {Entity}Services {

    private final {RelatedEntity}ServiceClient {relatedEntity}Client;

    @CircuitBreaker(name = "{relatedEntity}Service", fallbackMethod = "get{RelatedEntity}Fallback")
    private {RelatedEntity}Dto fetch{RelatedEntity}(Long id) {
        ApiResponseDto<{RelatedEntity}Dto> response = {relatedEntity}Client.get{RelatedEntity}ById(id);
        return response.getData();
    }

    // Fallback: return empty/default if circuit is open
    private {RelatedEntity}Dto get{RelatedEntity}Fallback(Long id, Throwable t) {
        return {RelatedEntity}Dto.builder().id(id).build();
    }
}

// WRONG -- no fallback; one service down takes the calling service down
private {RelatedEntity}Dto fetch{RelatedEntity}(Long id) {
    return {relatedEntity}Client.get{RelatedEntity}ById(id).getData();
    // If {relatedEntity}Service is down: FeignException propagates up; request fails
}
```

### Why This Matters
Without a fallback, a transient failure in one service cascades to all services that
call it, turning a partial outage into a complete outage of the calling service.

---

**ENFORCEMENT:** Level 2 loading -- code review: no `RestTemplate` or `WebClient` beans
in service classes (all inter-service calls via Feign). ArchUnit: all classes in `client/`
must be interfaces annotated with `@FeignClient`.

**SEE ALSO:**
- 13-spring-cloud-infrastructure.md -- API gateway routing and circuit breaker configuration
- 22-common-library-design.md -- common-lib structure where Feign clients reside (client/ package)
- 15-dto-form-separation.md -- ApiResponseDto and DTOs shared via common-lib that Feign clients return
- 19-exception-handling-hierarchy.md -- Exception handling for Feign call failures (FeignException mapping)
