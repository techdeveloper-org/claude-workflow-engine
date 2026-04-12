# 🔍 Pattern Detection

**Part of:** 🔵 Sync System

**Purpose:** Detect and replicate patterns across projects for consistency

---

## 📋 What This Does

- Detect coding patterns used in existing services
- Extract architectural patterns from codebase
- Apply detected patterns to new services
- Ensure consistency across microservices
- Enable "do it like service X" functionality

---

## 📁 Files in This Folder

### **Policies:**
- `cross-project-patterns-policy.md` - Pattern detection and application policy

### **Detection:**
- `pattern-detection-daemon.py` - Auto-detect patterns (daemon)
- `detect-patterns.py` - Manual pattern detection

### **Application:**
- `apply-patterns.py` - Apply detected patterns to new code

---

## 🎯 Usage

### **Detect Patterns from Service:**
```bash
python detect-patterns.py --service user-service
```

**Output:**
```json
{
  "service": "user-service",
  "patterns": {
    "package_structure": "controller, dto, form, services.impl, entity, repository",
    "response_wrapper": "ApiResponseDto<T>",
    "service_pattern": "extends Helper, package-private impl",
    "error_handling": "GlobalExceptionHandler with @RestControllerAdvice",
    "validation": "Form classes extend ValidationMessageConstants",
    "database": "Audit fields (created_at, updated_at), @PrePersist/@PreUpdate"
  }
}
```

### **Apply Patterns to New Service:**
```bash
python apply-patterns.py --from user-service --to product-service
```

### **Start Pattern Detection Daemon:**
```bash
nohup python pattern-detection-daemon.py > /dev/null 2>&1 &
```

---

## 📊 Pattern Types

| Type | Description |
|------|-------------|
| **Package Structure** | Package organization, visibility rules |
| **Service Layer** | Interface + impl pattern, Helper usage |
| **Response Format** | ApiResponseDto<T>, error responses |
| **Validation** | Form classes, validation messages |
| **Database** | Entity patterns, audit fields, lifecycle hooks |
| **Error Handling** | Exception hierarchy, global handler |
| **Configuration** | Config server structure, secret management |
| **Testing** | Test patterns, mock patterns |

---

## ✅ Benefits

- **Consistency:** All services follow same patterns
- **Speed:** No need to explain patterns repeatedly
- **Quality:** Proven patterns from existing code
- **Onboarding:** New developers see consistent code

---

## 🔄 Integration with Execution

**When creating new service:**
1. Pattern detection detects patterns from existing services
2. Standards system loads coding standards
3. Execution system applies both patterns + standards
4. Result: New service matches existing services perfectly

---

**Location:** `~/.claude/memory/01-sync-system/pattern-detection/`
