---
description: "Level 2.2 - L1+L2 hybrid cache, TTL tiers, financial data exceptions, serialization"
paths:
  - "src/**/config/*CacheConfig.java"
  - "src/**/config/*Cache*.java"
priority: high
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Caching Strategy (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce a consistent L1 (Caffeine in-process) + L2 (Redis distributed) hybrid
cache architecture with TTL tiers by data volatility, special handling for financial data,
and JSON serialization for debuggability. Prevents unlimited cache sizes that cause OOM and
prevents financial data from being cached too aggressively.

**APPLIES WHEN:** Spring Boot project with spring-boot-starter-cache and Caffeine + Redis dependencies.

---

## 1. L1 + L2 Hybrid Architecture

### What We Follow
Every service that caches data uses a two-level hierarchy:
- L1: Caffeine (in-process, bounded size, ~2 minute TTL per pod instance)
- L2: Redis (shared across all pods, longer TTL, source of truth for invalidation)

A `BaseCacheConfig` abstract class in common-lib provides the hybrid configuration.
Services override only `getRedisCacheTtlOverrides()` to customize TTLs per cache name.

### How To Implement

```java
// CORRECT -- BaseCacheConfig in common-lib
@EnableCaching
public abstract class BaseCacheConfig {

    @Autowired
    private RedisConnectionFactory redisConnectionFactory;

    protected abstract Map<String, Long> getRedisCacheTtlOverrides();

    @Bean
    public CacheManager cacheManager() {
        Map<String, CacheConfig<Object, Object>> caffeineConfigs = buildCaffeineConfigs();
        CaffeineCacheManager l1 = new CaffeineCacheManager();
        l1.setCaffeineSpec(CaffeineSpec.parse("maximumSize=500,expireAfterWrite=120s"));

        // Redis (L2)
        RedisCacheConfiguration defaultConfig = RedisCacheConfiguration
            .defaultCacheConfig()
            .serializeValuesWith(RedisSerializationContext.SerializationPair
                .fromSerializer(new GenericJacksonJsonRedisSerializer()))
            .entryTtl(Duration.ofMinutes(30));

        Map<String, RedisCacheConfiguration> redisCacheConfigs = new HashMap<>();
        getRedisCacheTtlOverrides().forEach((name, ttlSeconds) ->
            redisCacheConfigs.put(name, defaultConfig.entryTtl(Duration.ofSeconds(ttlSeconds))));

        RedisCacheManager l2 = RedisCacheManager.builder(redisConnectionFactory)
            .cacheDefaults(defaultConfig)
            .withInitialCacheConfigurations(redisCacheConfigs)
            .enableStatistics()
            .build();

        return new CompositeCacheManager(l1, l2);
    }
}

// CORRECT -- service overrides TTLs
@Configuration
public class {Service}CacheConfig extends BaseCacheConfig {

    public static final String {ENTITY}_BY_ID      = "{entity}ById";
    public static final String {ENTITY}_LIST        = "{entity}List";
    public static final String {ENTITY}_COUNT       = "{entity}Count";

    @Override
    protected Map<String, Long> getRedisCacheTtlOverrides() {
        return Map.of(
            {ENTITY}_BY_ID,   1800L,  // 30 min
            {ENTITY}_LIST,     900L,  // 15 min
            {ENTITY}_COUNT,    600L   // 10 min
        );
    }
}

// WRONG -- no BaseCacheConfig; each service defines its own CacheManager from scratch
@Bean
public CacheManager cacheManager() {
    return new RedisCacheManager(...);  // L1 missing; no standard TTL tiers
}
```

### Why This Matters
Without L1 in-process cache, every cache lookup requires a network round-trip to Redis.
For endpoints that execute 10 cache lookups per request at 1000 RPS, that is 10,000 Redis
calls/second that could be served locally.

---

## 2. TTL Tiers by Data Volatility

### What We Follow
Cache TTLs are determined by how frequently the underlying data changes:

```
By-ID lookups:                    1800 seconds (30 minutes)
List/collection queries:           900 seconds (15 minutes)
Count/aggregate results:           600 seconds (10 minutes)
External service existence checks: 300 seconds (5 minutes)
```

### How To Implement

```java
// CORRECT -- service method cached at appropriate TTL tier
@Service
@RequiredArgsConstructor
class {Entity}ServicesImpl extends {Entity}ServiceHelper implements {Entity}Services {

    // TTL defined by Redis config (1800s for by-ID)
    @Cacheable(value = {Service}CacheConfig.{ENTITY}_BY_ID, key = "#id")
    @Transactional(propagation = Propagation.NEVER, readOnly = true)
    public ApiResponseDto<{Entity}Dto> get{Entity}ById(Long id) {
        return ApiResponseDto.<{Entity}Dto>builder()
            .data(mapToDto(findById(id)))
            .message(ServiceMessageConstants.{ENTITY}_FETCHED_SUCCESS)
            .success(true)
            .status(200)
            .timestamp(LocalDateTime.now())
            .build();
    }

    // Evict on write
    @CacheEvict(value = {
        {Service}CacheConfig.{ENTITY}_BY_ID,
        {Service}CacheConfig.{ENTITY}_LIST,
        {Service}CacheConfig.{ENTITY}_COUNT
    }, allEntries = true)
    @Transactional(rollbackFor = DataAccessException.class, propagation = Propagation.REQUIRES_NEW)
    public ApiResponseDto<{Entity}Dto> update{Entity}(Long id, {Entity}UpdateForm form) {
        // ... update logic
    }

// WRONG -- no TTL tiers; using same TTL for volatile and stable data
@Cacheable(value = "cache", key = "#id")  // single cache name, default TTL for everything
```

### Why This Matters
Caching frequently-changing list data at a 30-minute TTL means users see stale data after
updates. Caching stable lookup data at 5 minutes means unnecessary Redis round-trips.

---

## 3. Financial Data: Redis-Only, Short TTL, Immediate Evict

### What We Follow
Data involving money, payments, balances, or financial calculations must NOT use L1
Caffeine cache. It must use Redis-only with a maximum TTL of 60 seconds and must be
immediately evicted on any write operation.

### How To Implement

```java
// CORRECT -- financial data Redis-only with short TTL
// In CacheConfig:
public static final String PAYMENT_{ENTITY} = "payment{Entity}";

@Override
protected Map<String, Long> getRedisCacheTtlOverrides() {
    return Map.of(
        PAYMENT_{ENTITY}, 60L   // 60 seconds max for financial data
    );
}

// Caffeine (L1) must NOT cache this -- exclude from L1:
// Configure L1 cache manager with explicit cache names to cache; payment_ caches excluded

// Service method
@Cacheable(value = {Service}CacheConfig.PAYMENT_{ENTITY},
           key = "#transactionId",
           cacheManager = "redisCacheManager")  // explicit L2 only
@Transactional(propagation = Propagation.NEVER, readOnly = true)
public ApiResponseDto<PaymentDto> getPayment(Long transactionId) { ... }

// Evict immediately on any state change
@CacheEvict(value = {Service}CacheConfig.PAYMENT_{ENTITY},
            key = "#transactionId",
            cacheManager = "redisCacheManager")
@Transactional(rollbackFor = DataAccessException.class, propagation = Propagation.REQUIRES_NEW)
public ApiResponseDto<PaymentDto> processPayment(Long transactionId, ...) { ... }

// WRONG -- L1 caching financial data
@Cacheable(value = "paymentData", key = "#id")
// L1 Caffeine cache is per-pod; pod A shows updated balance, pod B shows stale balance
// Financial inconsistency across instances
```

### Why This Matters
L1 (in-process) caches are not shared across pod replicas. Pod A processes a payment that
changes the balance; Pod B still serves the pre-payment balance from its local L1 cache.
A user checking their balance on Pod B sees incorrect data.

---

## 4. JSON Serialization for Redis

### What We Follow
Redis values are serialized using `GenericJacksonJsonRedisSerializer`. This stores values
as human-readable JSON in Redis, making debugging and inspection via `redis-cli` possible.

### How To Implement

```java
// CORRECT -- JSON serialization
RedisCacheConfiguration defaultConfig = RedisCacheConfiguration
    .defaultCacheConfig()
    .serializeValuesWith(RedisSerializationContext.SerializationPair
        .fromSerializer(new GenericJacksonJsonRedisSerializer()));

// Redis CLI inspection:
// GET "{service}::payment{Entity}::1234"
// -> {"@class":"com.{org}.{project}.dto.PaymentDto","id":1234,"amount":99.99,...}
// Immediately readable; class info included for deserialization

// WRONG -- JDK serialization (default)
// RedisCacheConfiguration.defaultCacheConfig()  // No .serializeValuesWith()
// Redis stores binary: \xac\xed\x00\x05sr\x00...  -- unreadable in redis-cli
// Version changes break deserialization silently
```

### Why This Matters
JDK serialization embeds the class's `serialVersionUID`. If the Dto class changes and the
UID changes, existing Redis entries throw `InvalidClassException` on deserialization --
a production cache poison that clears itself only when entries expire.

---

**ENFORCEMENT:** Level 2 loading -- code review: no `@Cacheable` on methods that touch
financial data without explicit `cacheManager = "redisCacheManager"`. Cache name constants
must be `public static final String` (not inline strings).

**SEE ALSO:**
- 14-entity-design-patterns.md -- Serializable entities required for Redis caching
- 22-common-library-design.md -- BaseCacheConfig in common-lib
- 15-dto-form-separation.md -- Dto classes implementing Serializable for Redis
