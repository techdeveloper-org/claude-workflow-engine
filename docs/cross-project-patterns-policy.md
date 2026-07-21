# Cross-Project Pattern Detection Policy (v1.0)

**Status:** ACTIVE | **Priority:** MEDIUM | **Auto-Active:** PERIODIC

---

## 🎯 Purpose

**Learn from your work across ALL projects and detect consistent patterns.**

Unlike User Preferences (which track explicit choices), this system detects **implicit patterns** from actual work done across multiple projects.

**Example:**
- User Preference: "User chooses JWT 3 times" → Remember choice
- Cross-Project Pattern: "User implements JWT in 5 projects" → Detect pattern

---

## 📋 What Gets Detected

### Technology Stack Patterns:

**Languages:**
- Python, JavaScript, TypeScript, Java, Go, Rust, Kotlin, Swift

**Frontend Frameworks:**
- React, Angular, Vue, Svelte

**Databases:**
- PostgreSQL, MySQL, MongoDB, Redis, SQLite, Elasticsearch

**API Styles:**
- REST, GraphQL, gRPC

**Authentication:**
- JWT, OAuth, Session-based, Basic Auth

**Testing:**
- Unit testing, Integration testing, TDD approach

**DevOps:**
- Docker, Kubernetes, CI/CD (GitHub Actions, Jenkins, GitLab CI)

---

## ⚙️ How It Works

### Detection Process:

**Step 1: Content Analysis**
```python
# Scan all projects
for project in sessions/:
    Read project-summary.md
    Read recent session-*.md files
    Extract keywords (technologies, decisions, approaches)
```

**Step 2: Pattern Identification**
```python
# Find commonalities
if technology appears in 3+ projects:
    Detected as pattern
    Calculate confidence (% of projects using it)
```

**Step 3: Pattern Storage**
```json
{
  "id": "authentication-jwt",
  "type": "authentication",
  "name": "jwt",
  "confidence": 0.75,  // 75% of projects
  "projects": ["proj1", "proj2", "proj3"],
  "occurrences": 3,
  "total_mentions": 12
}
```

---

## 🔧 Usage

### 1. Detect Patterns (Periodic Analysis)

**Run analysis across all projects:**
```bash
python ~/.claude/memory/detect-patterns.py
```

**Output:**
```
🔍 Analyzing 8 projects for patterns...

✅ Pattern detected: JWT (authentication)
   Confidence: 75%
   Found in: 6 projects
   Projects: app1, app2, app3, app4, app5, app6

✅ Pattern detected: POSTGRESQL (databases)
   Confidence: 62%
   Found in: 5 projects
   Projects: app1, app3, app5, app6, app7

📊 Summary:
   Projects analyzed: 8
   Patterns detected: 12
```

---

### 2. View Detected Patterns

**Show all patterns:**
```bash
python ~/.claude/memory/detect-patterns.py --show
```

**Output:**
```
🎯 Cross-Project Patterns Detected
======================================================================

📁 AUTHENTICATION
  ✓ JWT
    Confidence: [███████   ] 75%
    Found in 6 projects: app1, app2, app3...

  ✓ SESSION
    Confidence: [█████     ] 50%
    Found in 4 projects: app4, app5, app6...

📁 LANGUAGES
  ✓ PYTHON
    Confidence: [████████  ] 87%
    Found in 7 projects: app1, app2, app3...
```

---

### 3. Apply Patterns (During Work)

**Get pattern suggestions for a topic:**
```bash
python ~/.claude/memory/apply-patterns.py authentication
```

**Output:**
```
💡 Based on your past projects, here are relevant patterns:
======================================================================

1. JWT (STRONG PATTERN)
   Confidence: [███████   ] 75%
   Used in: 6 of your projects
   Projects: app1, app2, app3...

   💡 Suggestion: Consider using JWT authentication
      You've successfully used this in 6 projects

======================================================================
📝 Note: These are suggestions based on your patterns.
   You can always choose a different approach!
```

---

### 4. Specific Topic Suggestions

**Examples:**
```bash
# Get authentication patterns
python ~/.claude/memory/apply-patterns.py authentication

# Get API style patterns
python ~/.claude/memory/apply-patterns.py "rest api"

# Get database patterns
python ~/.claude/memory/apply-patterns.py database

# Get language patterns
python ~/.claude/memory/apply-patterns.py language

# Get frontend patterns
python ~/.claude/memory/apply-patterns.py frontend
```

---

## 🔍 Integration Points

### 1. Periodic Analysis (Recommended)

**Monthly or after major milestones:**
```bash
# Detect new patterns
python ~/.claude/memory/detect-patterns.py

# Review patterns
python ~/.claude/memory/detect-patterns.py --show
```

---

### 2. Project Start (Proactive)

**When starting new work:**

**Scenario:** User asks to implement authentication

**Claude's Action:**
```bash
# Check for patterns
python ~/.claude/memory/apply-patterns.py authentication

# Output shows: JWT used in 6 projects (75% confidence)

# Claude suggests:
"Based on your project history, you consistently use JWT
authentication (found in 6 of your projects). Should I
implement JWT auth for this project too?"
```

---

### 3. Technology Decisions

**When choosing technologies:**

**Scenario:** User asks which database to use

**Claude's Action:**
```bash
python ~/.claude/memory/apply-patterns.py database

# Shows: PostgreSQL (5 projects, 62%)
#        MongoDB (3 projects, 37%)

# Claude suggests:
"Your projects show a strong preference for PostgreSQL
(used in 62% of projects). Should I plan for PostgreSQL?"
```

---

## 📊 Pattern Confidence Levels

### Confidence Thresholds:

**STRONG (80-100%):**
- Pattern appears in 80%+ of projects
- High consistency across work
- Strong recommendation

**MODERATE (60-79%):**
- Pattern appears in 60-79% of projects
- Good consistency
- Solid suggestion

**WEAK (50-59%):**
- Pattern appears in 50-59% of projects
- Some consistency
- Mild suggestion

**Below 50%:**
- Not considered a pattern
- No strong preference detected

---

## 🎯 Detection Rules

### Rule 1: Occurrence Threshold
**Pattern must appear in 3+ projects minimum**

Why? 1-2 projects could be coincidence

### Rule 2: Confidence Calculation
**Confidence = (Projects with pattern) / (Total projects analyzed)**

Example:
- JWT found in 6 projects
- Total projects: 8
- Confidence: 6/8 = 75%

### Rule 3: Keyword Matching
**Multiple keywords per technology**

Example for Python:
- "python", "py", "django", "flask", "fastapi", "pytest"

---

## 📝 Pattern Categories

### 1. Languages
**What:** Programming languages used
**Examples:** Python, JavaScript, Java, Go
**Confidence:** Based on consistent usage

### 2. Frontend Frameworks
**What:** UI framework choices
**Examples:** React, Angular, Vue
**Confidence:** Based on project type

### 3. Databases
**What:** Data storage choices
**Examples:** PostgreSQL, MongoDB, Redis
**Confidence:** Based on data requirements

### 4. Authentication
**What:** Auth implementation approach
**Examples:** JWT, OAuth, Session
**Confidence:** Based on security decisions

### 5. API Style
**What:** API architecture choice
**Examples:** REST, GraphQL, gRPC
**Confidence:** Based on API design

### 6. Testing
**What:** Testing approach
**Examples:** Unit tests, Integration tests, TDD
**Confidence:** Based on quality practices

### 7. DevOps
**What:** Deployment & infrastructure
**Examples:** Docker, Kubernetes, CI/CD tools
**Confidence:** Based on deployment patterns

---

## 🔄 Workflow Integration

### Scenario 1: New Project - Authentication

**User:** "I need to add authentication to my new app"

**Claude checks patterns:**
```bash
python apply-patterns.py authentication
# Result: JWT (6 projects, 75%)
```

**Claude responds:**
```
"I noticed you consistently use JWT authentication across 6 of
your projects (75% confidence). Should I implement JWT auth with
refresh tokens, similar to your other projects?

(This is based on your pattern - you can choose differently!)"
```

---

### Scenario 2: New Project - Database Choice

**User:** "What database should I use?"

**Claude checks patterns:**
```bash
python apply-patterns.py database
# Result: PostgreSQL (5 projects, 62%)
#         MongoDB (3 projects, 37%)
```

**Claude responds:**
```
"Based on your project history:

1. PostgreSQL (MODERATE PATTERN - 62%)
   - Used in 5 projects
   - Good fit for relational data

2. MongoDB (WEAK - 37%)
   - Used in 3 projects
   - Good fit for document data

Your data seems relational, so PostgreSQL matches your established
pattern. Shall I plan for PostgreSQL?"
```

---

### Scenario 3: API Design

**User:** "Build a REST API for user management"

**Claude checks patterns:**
```bash
python apply-patterns.py "rest api"
# Result: REST (4 projects, 50%)
```

**Claude responds:**
```
"Perfect! REST API design aligns with your pattern (used in 4
projects). I'll design a RESTful API with standard conventions
you've used before:

- GET /users - List users
- POST /users - Create user
- GET /users/:id - Get user
- PUT /users/:id - Update user
- DELETE /users/:id - Delete user

This matches your established API structure."
```

---

## 📊 Monitoring

### View Pattern Logs:
```bash
tail -f ~/.claude/memory/logs/policy-hits.log | grep pattern-detection
```

**Output:**
```
[2026-01-26 22:58:35] pattern-detection | analyzed | 6 projects | 7 patterns detected
[2026-01-26 23:05:12] pattern-detection | applied | topic=authentication | 1 patterns suggested
[2026-01-26 23:15:45] pattern-detection | applied | topic=database | 2 patterns suggested
```

---

### View Pattern File:
```bash
cat ~/.claude/memory/cross-project-patterns.json
```

**Or use formatted view:**
```bash
python ~/.claude/memory/detect-patterns.py --show
```

---

## ⚠️ Important Notes

### This is NOT:
❌ A strict requirement system
❌ Limiting your choices
❌ Forcing old approaches

### This IS:
✅ Pattern awareness
✅ Consistency suggestions
✅ Experience-based recommendations
✅ Informed decision-making

### User Always Decides:
- Patterns are suggestions, not rules
- User can override anytime
- Different approaches are valid
- Patterns help, don't constrain

---

## 🛠️ Configuration

### Detection Threshold:
```json
{
  "metadata": {
    "detection_threshold": 3  // Require 3+ projects (default)
  }
}
```

**Options:**
- 2: More patterns detected (less strict)
- 3: Balanced (default)
- 4+: Fewer patterns (more strict)

### Confidence Threshold:
```json
{
  "metadata": {
    "confidence_threshold": 0.6  // 60% confidence (default)
  }
}
```

**Options:**
- 0.5: Include weak patterns
- 0.6: Balanced (default)
- 0.8: Only strong patterns

---

## 📅 Maintenance

### When to Re-analyze:

**Monthly (Recommended):**
```bash
# After completing significant work
python ~/.claude/memory/detect-patterns.py
```

**After Major Projects:**
```bash
# New patterns may have emerged
python ~/.claude/memory/detect-patterns.py
```

**When Patterns Feel Outdated:**
```bash
# Refresh pattern detection
python ~/.claude/memory/detect-patterns.py
```

---

## 🧪 Examples

### Example 1: Strong JWT Pattern

**Analysis Result:**
```
✅ Pattern detected: JWT (authentication)
   Confidence: 85%
   Found in: 7 projects
```

**When Applied:**
```
User: "Add authentication"
Claude: "You have a STRONG pattern of using JWT (85% confidence,
        7 projects). Implement JWT auth?"
```

---

### Example 2: Moderate PostgreSQL Pattern

**Analysis Result:**
```
✅ Pattern detected: POSTGRESQL (databases)
   Confidence: 65%
   Found in: 5 projects
```

**When Applied:**
```
User: "Need a database"
Claude: "You have a MODERATE pattern with PostgreSQL (65%
        confidence, 5 projects). Use PostgreSQL?"
```

---

### Example 3: Weak React Pattern

**Analysis Result:**
```
✅ Pattern detected: REACT (frontend)
   Confidence: 55%
   Found in: 4 projects
```

**When Applied:**
```
User: "Build frontend"
Claude: "You've used React in 55% of projects (4 total).
        Would you like to use React again, or try something
        different?"
```

---

## 📁 Files

- **Storage:** `~/.claude/memory/cross-project-patterns.json`
- **Detector:** `~/.claude/memory/detect-patterns.py`
- **Applicator:** `~/.claude/memory/apply-patterns.py`
- **Policy:** `~/.claude/memory/cross-project-patterns-policy.md`
- **Logs:** `~/.claude/memory/logs/policy-hits.log`

---

## ✅ Summary

**What it does:**
- Detects patterns across all your projects
- Identifies consistent technology choices
- Suggests approaches based on history
- Helps maintain consistency (when desired)

**When to use:**
- Run detection monthly
- Apply patterns when starting new work
- Check patterns for technology decisions
- Review patterns to understand your own style

**Key principle:**
**Patterns inform, not enforce. User always decides!**

---

**Version:** 1.0 | **Status:** ACTIVE | **Frequency:** Monthly Detection
