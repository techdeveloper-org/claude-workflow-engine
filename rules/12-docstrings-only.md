---
description: "Level 2.2 - Docstring-only documentation: ban inline explanatory comments, require docstrings across Python/Java/TypeScript/Kotlin"
priority: high
---

# Docstrings Only — No Inline Explanatory Comments (Level 2.2)

**PURPOSE:** All explanatory text belongs in docstrings at the function/class/module level. Inline comments that narrate what individual lines of code do are noise — they duplicate what readable code already expresses. This rule applies to Python, Java, TypeScript/JavaScript, and Kotlin.

---

## 1. Principle

| Category | Rule |
|----------|------|
| **Docstrings** | Required on every public/protected function, class, and module |
| **Inline comments** | Banned when they explain *what* a line does |
| **Inline comments** | Allowed when they explain *why* (non-obvious reasoning, algorithm notes, TODOs) |

✅ **Docstrings describe the CONTRACT (what + why at API level):**
- What does this function do?
- What are the parameters and return value?
- What exceptions can it raise?
- Why does this function exist?

❌ **Inline comments that narrate code execution are banned:**
- `// Block until at least one log is available`
- `// Drain remaining logs up to batch size`
- `// Send remaining logs on shutdown`
- `# multiply y by 2`

---

## 2. Banned: Inline Explanatory Comments

Inline comments that explain *what* the immediately following line(s) do are **not permitted** on new or modified functions.

❌ **WRONG — comments narrating code steps:**
```java
while (!Thread.currentThread().isInterrupted()) {
    try {
        // Block until at least one log is available
        LogEntryDto log = logQueue.poll(1, TimeUnit.SECONDS);
        if (log != null) {
            batch.add(log);

            // Drain remaining logs up to batch size
            logQueue.drainTo(batch, batchSize - batch.size());

            // Send batch if it reaches the configured size
            if (batch.size() >= batchSize) {
                sendBatch(batch);
                batch.clear();
            }
        }
    }
}

// Send remaining logs on shutdown
if (!batch.isEmpty()) {
    sendBatch(batch);
}
```

The code is self-explanatory. The comments add zero information beyond what the method names and conditions already communicate.

---

## 3. Allowed Inline Comment Types

The following inline comments are **permitted** even under this rule:

| Type | Pattern | Example |
|------|---------|---------|
| TODO | `# TODO:`, `// TODO:` | `// TODO: replace with async queue` |
| FIXME | `# FIXME:`, `// FIXME:` | `// FIXME: race condition under high load` |
| Lint suppression | `# noqa`, `# type: ignore`, `// eslint-disable-line` | `some_call()  # noqa: E501` |
| Non-obvious algorithm | Bit tricks, regex, O(n) notes | `// XOR swap — avoids temp allocation` |
| Mandatory annotation | Framework-required markers | `// @SuppressWarnings("unchecked")` |

✅ **Allowed because it explains WHY, not WHAT:**
```java
// XOR swap avoids a temporary variable at the cost of readability
a ^= b;
b ^= a;
a ^= b;
```

✅ **Allowed TODO:**
```python
result = process(data)  # TODO: cache this result (PROJ-456)
```

---

## 4. Language-Specific Docstring Format

### Python (PEP 257 / Google Style)

**Docstring location:** Module, class, `__init__`, every public/protected method.

❌ **WRONG — inline comments explaining steps:**
```python
def process_batches(self):
    batch = []
    while not self._stop_event.is_set():
        # Poll queue for next item
        item = self._queue.get(timeout=1)
        if item:
            batch.append(item)
            # Drain remaining items up to batch size
            while len(batch) < self.batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            # Flush when batch is full
            if len(batch) >= self.batch_size:
                self._send(batch)
                batch.clear()
    # Flush remaining on shutdown
    if batch:
        self._send(batch)
```

✅ **CORRECT — docstring at function level, no inline narration:**
```python
def process_batches(self):
    """Continuously drain the queue and flush in configured batch sizes.

    Blocks on each poll cycle and drains up to batch_size items per
    iteration. Any remaining items are flushed on clean shutdown.
    """
    batch = []
    while not self._stop_event.is_set():
        item = self._queue.get(timeout=1)
        if item:
            batch.append(item)
            while len(batch) < self.batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            if len(batch) >= self.batch_size:
                self._send(batch)
                batch.clear()
    if batch:
        self._send(batch)
```

**Google-style docstring template:**
```python
def function_name(param1: Type, param2: Type) -> ReturnType:
    """One-line summary.

    Longer description if needed. Explains WHY this function exists
    and any non-obvious behavior.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param1 is invalid.
        RuntimeError: When the operation cannot complete.
    """
```

---

### Java (Javadoc)

**Docstring location:** Every class, every public/protected method, every public field.

❌ **WRONG — inline comments narrating execution steps:**
```java
/**
 * Continuously processes log batches from the queue
 */
private void processBatches() {
    List<LogEntryDto> batch = new ArrayList<>(batchSize);

    while (!Thread.currentThread().isInterrupted()) {
        try {
            // Block until at least one log is available
            LogEntryDto log = logQueue.poll(1, TimeUnit.SECONDS);
            if (log != null) {
                batch.add(log);

                // Drain remaining logs up to batch size
                logQueue.drainTo(batch, batchSize - batch.size());

                // Send batch if it reaches the configured size
                if (batch.size() >= batchSize) {
                    sendBatch(batch);
                    batch.clear();
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            break;
        } catch (Exception e) {
            addError("Error processing log batch", e);
        }
    }

    // Send remaining logs on shutdown
    if (!batch.isEmpty()) {
        sendBatch(batch);
    }
}
```

✅ **CORRECT — Javadoc explains the contract, no inline narration:**
```java
/**
 * Continuously processes log batches from the queue.
 *
 * <p>Polls the queue on a 1-second timeout and drains up to {@code batchSize}
 * entries per cycle. Flushes any remaining entries on clean shutdown before
 * returning. Interruption is handled by restoring the interrupt flag and
 * exiting the loop.
 */
private void processBatches() {
    List<LogEntryDto> batch = new ArrayList<>(batchSize);
    while (!Thread.currentThread().isInterrupted()) {
        try {
            LogEntryDto log = logQueue.poll(1, TimeUnit.SECONDS);
            if (log != null) {
                batch.add(log);
                logQueue.drainTo(batch, batchSize - batch.size());
                if (batch.size() >= batchSize) {
                    sendBatch(batch);
                    batch.clear();
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            break;
        } catch (Exception e) {
            addError("Error processing log batch", e);
        }
    }
    if (!batch.isEmpty()) {
        sendBatch(batch);
    }
}
```

**Javadoc template:**
```java
/**
 * One-line summary ending with a period.
 *
 * <p>Optional longer description. Explains WHY this method exists
 * and any non-obvious contracts or side effects.
 *
 * @param paramName description of parameter
 * @return description of return value
 * @throws IllegalArgumentException when paramName is null or invalid
 * @throws IOException on underlying I/O failure
 */
public ReturnType methodName(ParamType paramName) {
```

---

### TypeScript / JavaScript (JSDoc)

**Docstring location:** Every exported function, class, interface, and type alias.

❌ **WRONG — inline comments narrating steps:**
```typescript
async function processBatches(queue: Queue<LogEntry>): Promise<void> {
    const batch: LogEntry[] = [];

    while (!isStopped) {
        // Wait for next item from queue
        const item = await queue.poll(1000);
        if (item) {
            batch.push(item);

            // Drain up to batch size
            while (batch.length < BATCH_SIZE) {
                const next = queue.tryPoll();
                if (!next) break;
                batch.push(next);
            }

            // Flush full batch
            if (batch.length >= BATCH_SIZE) {
                await sendBatch(batch);
                batch.length = 0;
            }
        }
    }

    // Flush remainder on shutdown
    if (batch.length > 0) {
        await sendBatch(batch);
    }
}
```

✅ **CORRECT — JSDoc at function level, no inline narration:**
```typescript
/**
 * Continuously drains the queue and sends log entries in batches.
 *
 * Polls with a 1-second timeout per cycle and drains up to BATCH_SIZE
 * entries before flushing. Remaining entries are flushed on shutdown.
 *
 * @param queue - Source queue of log entries to process
 * @returns Resolves when the processing loop exits cleanly
 */
async function processBatches(queue: Queue<LogEntry>): Promise<void> {
    const batch: LogEntry[] = [];
    while (!isStopped) {
        const item = await queue.poll(1000);
        if (item) {
            batch.push(item);
            while (batch.length < BATCH_SIZE) {
                const next = queue.tryPoll();
                if (!next) break;
                batch.push(next);
            }
            if (batch.length >= BATCH_SIZE) {
                await sendBatch(batch);
                batch.length = 0;
            }
        }
    }
    if (batch.length > 0) {
        await sendBatch(batch);
    }
}
```

**JSDoc template:**
```typescript
/**
 * One-line summary.
 *
 * Optional longer explanation of WHY this function exists and
 * any non-obvious behavior or side effects.
 *
 * @param paramName - Description of parameter
 * @returns Description of return value
 * @throws {ErrorType} When this condition occurs
 */
```

---

### Kotlin (KDoc)

**Docstring location:** Every class, every public/internal function, every public property.

❌ **WRONG — inline comments narrating execution:**
```kotlin
private fun processBatches() {
    val batch = mutableListOf<LogEntry>()

    while (!Thread.currentThread().isInterrupted) {
        // Poll queue for next entry
        val entry = logQueue.poll(1, TimeUnit.SECONDS)
        if (entry != null) {
            batch.add(entry)

            // Drain remaining up to batch size
            logQueue.drainTo(batch, batchSize - batch.size)

            // Flush when batch is full
            if (batch.size >= batchSize) {
                sendBatch(batch)
                batch.clear()
            }
        }
    }

    // Flush remainder on shutdown
    if (batch.isNotEmpty()) {
        sendBatch(batch)
    }
}
```

✅ **CORRECT — KDoc at function level, no inline narration:**
```kotlin
/**
 * Continuously drains the queue and flushes log entries in configured batch sizes.
 *
 * Polls with a 1-second timeout per cycle. Drains up to [batchSize] entries before
 * flushing. Any remaining entries are flushed on clean shutdown when the thread
 * interrupt flag is set.
 */
private fun processBatches() {
    val batch = mutableListOf<LogEntry>()
    while (!Thread.currentThread().isInterrupted) {
        val entry = logQueue.poll(1, TimeUnit.SECONDS)
        if (entry != null) {
            batch.add(entry)
            logQueue.drainTo(batch, batchSize - batch.size)
            if (batch.size >= batchSize) {
                sendBatch(batch)
                batch.clear()
            }
        }
    }
    if (batch.isNotEmpty()) {
        sendBatch(batch)
    }
}
```

**KDoc template:**
```kotlin
/**
 * One-line summary.
 *
 * Optional longer description explaining WHY this function exists.
 *
 * @param paramName description of parameter
 * @return description of return value
 * @throws IllegalStateException when this condition occurs
 */
```

---

## 5. Linter / Tool Enforcement Per Language

| Language | Tool | Rule / Config |
|----------|------|--------------|
| Python | `flake8` + `flake8-bugbear` | `B006`, `D100`-`D107` (pydocstyle) — missing docstrings |
| Python | `pylint` | `C0114` (missing-module-docstring), `C0116` (missing-function-docstring) |
| Java | `Checkstyle` | `JavadocMethod`, `JavadocType`, `JavadocVariable` checks |
| Java | `PMD` | `CommentRequired` rule — requires Javadoc on public members |
| TypeScript | `eslint` | `jsdoc/require-jsdoc`, `jsdoc/require-description` |
| TypeScript | `eslint` | `no-inline-comments` — flag or warn on inline comment density |
| Kotlin | `detekt` | `CommentOverPrivateFunction`, `UndocumentedPublicClass`, `UndocumentedPublicFunction` |
| All | Pre-commit hook | Custom script counts `//` or `#` inside function bodies, warns if > threshold |

**Recommended `.pylintrc` addition:**
```ini
[MESSAGES CONTROL]
disable=C0301
enable=C0114,C0115,C0116
```

**Recommended `detekt.yml` addition:**
```yaml
comments:
  UndocumentedPublicClass:
    active: true
  UndocumentedPublicFunction:
    active: true
  CommentOverPrivateFunction:
    active: true
```

---

## 6. CI Gate Threshold

| Metric | New Functions | Legacy Functions |
|--------|--------------|-----------------|
| Missing docstrings | 0 allowed (hard fail) | Warn only (grace period) |
| Inline comment density | 0 per new/modified function | <= 3 per 100 lines (warn) |
| TODOs without ticket ref | Warn (soft gate) | Warn |

✅ **CI gate passes when:**
```
New/modified function → has docstring → inline comment count inside function body == 0
```

❌ **CI gate fails when:**
```
New/modified function → missing docstring
New/modified function → contains inline comment that is not TODO/FIXME/noqa/algorithm note
```

**Inline comment density check (shell snippet for CI):**
```bash
# Count inline comments inside function bodies of modified files
# Excludes: TODO, FIXME, noqa, type: ignore, eslint-disable, @Suppress
git diff --name-only HEAD~1 | xargs grep -n "^\s*//\|^\s*#" \
  | grep -v "TODO\|FIXME\|noqa\|type: ignore\|eslint-disable\|@Suppress" \
  | wc -l
```

---

## 7. Enforcement in Level 2

This rule is evaluated by Level 2 Standards Loading on every session start and before every Write/Edit tool call.

```
Level 2 Check (new or modified files):
  1. Verify every public/protected function has a docstring
     → Fail if missing
  2. Count inline comments inside modified function bodies
     → Fail if count > 0 (excluding allowed types)
  3. Inject rule into prompt context for implementation steps
     → Agent uses docstring-first pattern when generating new code
```

---

**ENFORCEMENT:** This is Level 2.2 - ACTIVE for all new and modified functions. Inline explanatory comments in new code are a hard block. Legacy file grace threshold is 3 inline comments per 100 lines (warning only).
