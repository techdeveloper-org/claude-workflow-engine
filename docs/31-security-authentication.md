---
description: "Level 2.2 - Spring Security stateless config, JWT filter chain, CORS, public endpoints"
paths:
  - "src/**/config/SecurityConfig.java"
  - "src/**/security/**/*.java"
  - "src/**/filter/**/*.java"
priority: critical
conditional: "Spring Boot project detected (pom.xml with spring-boot-starter)"
---

# Security Authentication (Level 2.2 - Spring Boot)

**PURPOSE:** Enforce stateless Spring Security configuration with JWT-based authentication,
explicit CORS configuration loaded from Config Server, and a clearly defined set of public
endpoints. Prevents accidentally securing actuator endpoints (breaks Kubernetes health probes)
and accidentally exposing authenticated endpoints as public.

**APPLIES WHEN:** Spring Boot project with spring-boot-starter-security.

---

## 1. Stateless Session Management and CSRF Disabled

### What We Follow
REST APIs that authenticate via JWT do not use server-side session state. Session creation
is `STATELESS` and CSRF protection is disabled because CSRF attacks target browser-based
session cookies, which do not apply to JWT in the Authorization header.

### How To Implement

```java
// CORRECT -- stateless JWT security configuration
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/actuator/health",
                    "/actuator/health/**",
                    "/actuator/info",
                    "/api/v1/auth/register",
                    "/api/v1/auth/login",
                    "/api/v1/auth/refresh",
                    "/v3/api-docs/**",
                    "/swagger-ui/**"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .addFilterBefore(
                jwtAuthenticationFilter,
                UsernamePasswordAuthenticationFilter.class
            )
            .build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}

// WRONG -- session-based security for REST API
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));
// Creates sessions for each client -- not scalable horizontally
```

### Why This Matters
A session-creating REST API cannot scale horizontally without sticky sessions or distributed
session storage. JWT carries all state in the token itself -- any instance can validate it.

---

## 2. JWT Authentication Filter

### What We Follow
A custom `JwtAuthenticationFilter` extends `OncePerRequestFilter`. It extracts the JWT from
the `Authorization: Bearer {token}` header, validates it, and sets the
`SecurityContextHolder` authentication. It never throws exceptions directly -- filter
failures fall through to the 401 response from the security filter chain.

### How To Implement

```java
// CORRECT -- JWT filter
@Component
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtTokenProvider jwtTokenProvider;
    private final UserDetailsService userDetailsService;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String authHeader = request.getHeader(HttpHeaders.AUTHORIZATION);

        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            filterChain.doFilter(request, response);
            return;
        }

        String token = authHeader.substring(7);

        try {
            if (jwtTokenProvider.isValid(token)
                    && SecurityContextHolder.getContext().getAuthentication() == null) {

                String username = jwtTokenProvider.extractUsername(token);
                UserDetails userDetails = userDetailsService.loadUserByUsername(username);

                UsernamePasswordAuthenticationToken authentication =
                    new UsernamePasswordAuthenticationToken(
                        userDetails, null, userDetails.getAuthorities());
                authentication.setDetails(
                    new WebAuthenticationDetailsSource().buildDetails(request));

                SecurityContextHolder.getContext().setAuthentication(authentication);
            }
        } catch (JwtException | UsernameNotFoundException e) {
            // Invalid token -- clear context, let security chain return 401
            SecurityContextHolder.clearContext();
        }

        filterChain.doFilter(request, response);
    }
}

// WRONG -- throwing exceptions from filter (bypasses Spring Security's 401 handling)
try {
    jwtTokenProvider.validate(token);
} catch (JwtException e) {
    throw new RuntimeException("Invalid JWT");  // Results in 500, not 401
}
```

### Why This Matters
Throwing from within a filter produces an unhandled `FilterChainInterruptedException` that
returns 500 Internal Server Error instead of 401 Unauthorized, confusing clients.

---

## 3. CORS Configuration from Config Server

### What We Follow
Allowed CORS origins are loaded from Config Server as a property, not hardcoded in
`SecurityConfig`. This allows per-environment origin lists (localhost for dev, specific
domain for production) without code changes.

### How To Implement

```java
// CORRECT -- CORS origins from property
@Value("${cors.allowed-origins}")
private List<String> allowedOrigins;

@Bean
public CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(allowedOrigins);  // from Config Server
    configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    configuration.setAllowedHeaders(List.of("*"));
    configuration.setAllowCredentials(true);
    configuration.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", configuration);
    return source;
}

// In Config Server: {service}.yml
// cors:
//   allowed-origins:
//     - http://localhost:3000
//     - https://{frontend-domain}

// WRONG -- hardcoded CORS origins
configuration.setAllowedOrigins(List.of("http://localhost:3000", "https://example.com"));
// Different origins per environment require code change and redeploy
```

### Why This Matters
Hardcoded CORS origins mean that adding a new frontend URL requires a code change, a PR,
a review cycle, and a deployment to all services -- a Config Server property change requires none.

---

## 4. @EnableMethodSecurity for Role-Based Authorization

### What We Follow
Method-level authorization uses `@PreAuthorize` annotations enabled by `@EnableMethodSecurity`.
Role checks are on service interface methods, not controller methods.

### How To Implement

```java
// CORRECT -- method security on service interface
public interface {Entity}AdminServices {

    @PreAuthorize("hasRole('ADMIN')")
    ApiResponseDto<Void> deleteAllExpired{Entity}();

    @PreAuthorize("hasAnyRole('ADMIN', 'MANAGER')")
    ApiResponseDto<Page<{Entity}Dto>> listAll{Entity}(Pageable pageable);
}

// CORRECT -- SecurityConfig has @EnableMethodSecurity
@Configuration
@EnableWebSecurity
@EnableMethodSecurity   // enables @PreAuthorize, @PostAuthorize, @Secured
public class SecurityConfig { ... }

// WRONG -- role check in controller via manual inspection
@DeleteMapping("/expired")
public ResponseEntity<?> deleteExpired(Principal principal) {
    if (!principal.getName().contains("admin")) {  // fragile string check
        return ResponseEntity.status(403).build();
    }
    // ...
}
```

### Why This Matters
Manual role checks in controllers bypass Spring Security's `AccessDeniedException` handling,
which produces the correct 403 response. Manual checks produce inconsistent HTTP responses.

---

**ENFORCEMENT:** Level 2 loading -- security scan in CI: `mvn dependency-check:check` for
known vulnerable JWT library versions. Code review: no `permitAll()` added to paths outside
the explicitly listed public endpoint set. Pen test validates that all non-public endpoints
return 401 without a valid JWT.

**SEE ALSO:**
- 13-spring-cloud-infrastructure.md -- CORS origins stored in Config Server
- 29-container-deployment.md -- /actuator/health must be public for Kubernetes probes
- 26-openapi-documentation.md -- JWT bearer auth scheme in OpenAPI config
