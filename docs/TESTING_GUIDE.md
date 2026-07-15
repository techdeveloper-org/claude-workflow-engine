# Testing Guide for Claude Workflow Engine

This guide explains how to run and write tests for Claude Workflow Engine.

---

## Quick Start

### Install Test Dependencies

```bash
# Install testing tools
pip install coverage psutil

# Optional: Install all test tools
pip install -r requirements-test.txt
```

### Run All Tests

```bash
cd /path/to/claude-workflow-engine
python tests/run_all_tests.py
```

**Expected Output:**
```
======================================================================
CLAUDE INSIGHT - TEST SUITE
======================================================================

Discovered 68 tests

....................................................................
----------------------------------------------------------------------
Ran 68 tests in 1.592s

OK

======================================================================
TEST SUMMARY
======================================================================
Tests run: 68
Successes: 68
Failures:  0
Errors:    0
Skipped:   0
Time:      1.59s

[SUCCESS] All tests passed!
======================================================================
```

---

## Test Runner Options

### Verbosity Levels

```bash
# Minimal output (quiet mode)
python tests/run_all_tests.py --quiet

# Normal output (default)
python tests/run_all_tests.py

# Verbose output (shows each test)
python tests/run_all_tests.py --verbose
```

### Pattern Matching

```bash
# Run only policy tracker tests
python tests/run_all_tests.py --pattern "test_policy*.py"

# Run only logger tests
python tests/run_all_tests.py --pattern "test_*logger*.py"

# Run only MCP tests
python tests/run_all_tests.py --pattern "test_*mcp*.py"
```

### Coverage Reporting

```bash
# Run with coverage analysis
python tests/run_all_tests.py --coverage
```

**Coverage Output:**
```
Running tests with coverage...

======================================================================
COVERAGE REPORT
======================================================================

Name                                                Stmts   Miss  Cover
-----------------------------------------------------------------------
src/middleware/enforcement_logger.py                  89      5    94%
src/mcp/enforcement_server.py                        123      8    93%
src/services/monitoring/policy_execution_tracker.py  145     12    92%
-----------------------------------------------------------------------
TOTAL                                                 357     25    93%

HTML coverage report: tests/htmlcov/index.html
======================================================================
```

**View HTML Report:**
```bash
# Open in browser (Windows)
start tests/htmlcov/index.html

# Open in browser (Mac)
open tests/htmlcov/index.html

# Open in browser (Linux)
xdg-open tests/htmlcov/index.html
```

---

## Running Individual Test Files

### Using unittest

```bash
# Run specific test file
python -m unittest tests.test_policy_execution_tracker

# Run specific test class
python -m unittest tests.test_policy_execution_tracker.TestPolicyExecutionTracker

# Run specific test method
python -m unittest tests.test_policy_execution_tracker.TestPolicyExecutionTracker.test_get_enforcer_state_exists

# Run with verbose output
python -m unittest -v tests.test_enforcement_logger
```

### Direct Execution

```bash
# Most test files can be run directly
python tests/test_policy_execution_tracker.py
python tests/test_enforcement_logger.py
python tests/test_enforcement_mcp_server.py
```

---

## Test Structure

### Current Test Modules

| Test File | Module Tested | Tests | Description |
|-----------|---------------|-------|-------------|
| `test_policy_execution_tracker.py` | `PolicyExecutionTracker` | 28 | Policy execution tracking and metrics |
| `test_enforcement_logger.py` | `EnforcementLogger` | 24 | Policy logging middleware |
| `test_enforcement_mcp_server.py` | `EnforcementMCPServer` | 16 | MCP server for Claude integration |
| `test_policy_integration.py` | Integration | 5 | End-to-end policy integration |

### Test Organization

```
tests/
├── run_all_tests.py                    # Test runner
├── test_policy_execution_tracker.py    # Unit tests
├── test_enforcement_logger.py          # Unit tests
├── test_enforcement_mcp_server.py      # Unit tests
├── test_policy_integration.py          # Integration tests
└── htmlcov/                            # Coverage HTML reports (generated)
```

---

## Writing New Tests

### Test Template

```python
#!/usr/bin/env python3
"""
Unit Tests for YourModule

Description of what is being tested.
"""

import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from your_module import YourClass


class TestYourClass(unittest.TestCase):
    """Test suite for YourClass"""

    def setUp(self):
        """Set up test fixtures before each test"""
        # Create temporary directories
        self.temp_dir = tempfile.mkdtemp()

        # Patch system paths if needed
        self.patcher = patch('pathlib.Path.home')
        self.mock_home = self.patcher.start()
        self.mock_home.return_value = Path(self.temp_dir)

        # Create instance to test
        self.instance = YourClass()

    def tearDown(self):
        """Clean up after each test"""
        self.patcher.stop()

        # Clean up temp directory
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_basic_functionality(self):
        """Test basic functionality"""
        result = self.instance.some_method()
        self.assertEqual(result, expected_value)

    def test_error_handling(self):
        """Test error handling"""
        with self.assertRaises(ValueError):
            self.instance.invalid_operation()

    def test_edge_case(self):
        """Test edge case behavior"""
        result = self.instance.edge_case_method(None)
        self.assertIsNone(result)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestYourClass)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
```

### Best Practices

1. **Test Isolation**
   - Each test should be independent
   - Use setUp() to create fresh state
   - Use tearDown() to clean up resources

2. **Descriptive Names**
   - Test methods start with `test_`
   - Use descriptive names: `test_get_data_when_file_exists`
   - Add docstrings explaining what is tested

3. **Assertions**
   - Use specific assertions: `assertEqual`, `assertIn`, `assertRaises`
   - Include helpful failure messages
   - Test both success and failure cases

4. **Mocking**
   - Mock external dependencies (file system, network)
   - Use `patch` for temporary mocking
   - Clean up mocks in tearDown()

5. **Coverage**
   - Test happy paths
   - Test error conditions
   - Test edge cases
   - Test boundary conditions

---

## Continuous Integration

### GitHub Actions (Recommended)

Create `.github/workflows/tests.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11', '3.12']

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-test.txt

    - name: Run tests
      run: python tests/run_all_tests.py --verbose

    - name: Run tests with coverage
      run: python tests/run_all_tests.py --coverage

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

### Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

# Run tests before commit
echo "Running tests..."
python tests/run_all_tests.py

if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi

echo "All tests passed!"
exit 0
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## Troubleshooting

### Common Issues

#### 1. Import Errors

**Problem:** `ModuleNotFoundError: No module named 'src'`

**Solution:** Ensure you're running from the project root:
```bash
cd /path/to/claude-workflow-engine
python tests/run_all_tests.py
```

#### 2. Permission Errors (Windows)

**Problem:** `PermissionError: [WinError 32] The process cannot access the file`

**Solution:** This is handled automatically with retry logic. If persistent:
- Close any applications using the files
- Restart the terminal
- Disable antivirus temporarily

#### 3. Missing Dependencies

**Problem:** `ImportError: No module named 'coverage'`

**Solution:** Install test dependencies:
```bash
pip install -r requirements-test.txt
```

#### 4. Test Failures

**Problem:** Individual tests fail

**Solution:** Run specific test with verbose output:
```bash
python -m unittest -v tests.test_module.TestClass.test_method
```

Check test output for specific error messages.

---

## Test Coverage Goals

| Module | Current | Target | Status |
|--------|---------|--------|--------|
| `PolicyExecutionTracker` | 92% | 95% | 🟡 Good |
| `EnforcementLogger` | 94% | 95% | 🟢 Excellent |
| `EnforcementMCPServer` | 93% | 95% | 🟢 Excellent |
| `MetricsCollector` | 0% | 80% | 🔴 Need Tests |
| `AutomationTracker` | 0% | 80% | 🔴 Need Tests |
| `MemorySystemMonitor` | 0% | 80% | 🔴 Need Tests |

**Overall Target:** 80% code coverage across all modules

---

## Performance Testing

### Benchmarking Tests

```python
def test_performance_large_dataset(self):
    """Test performance with large dataset"""
    import time

    # Create large dataset
    large_data = [self.create_sample_entry() for _ in range(10000)]

    # Measure execution time
    start = time.time()
    result = self.tracker.process_data(large_data)
    elapsed = time.time() - start

    # Assert reasonable performance
    self.assertLess(elapsed, 5.0, "Processing took too long")
    self.assertEqual(len(result), 10000)
```

### Load Testing

```bash
# Run tests multiple times to check consistency
for i in {1..10}; do
    python tests/run_all_tests.py
done
```

---

## Resources

### Documentation
- [unittest documentation](https://docs.python.org/3/library/unittest.html)
- [coverage.py documentation](https://coverage.readthedocs.io/)
- [pytest documentation](https://docs.pytest.org/) (alternative)

### Tools
- [Coverage.py](https://coverage.readthedocs.io/) - Code coverage tool
- [pytest](https://docs.pytest.org/) - Alternative test framework
- [mock](https://docs.python.org/3/library/unittest.mock.html) - Mocking library

### Best Practices
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)
- [Test-Driven Development](https://en.wikipedia.org/wiki/Test-driven_development)

---

## Support

For issues or questions:
1. Check the [CODE_QUALITY_REPORT.md](CODE_QUALITY_REPORT.md)
2. Review existing test examples
3. Create an issue in the repository

---

**Last Updated:** 2026-02-16
**Test Suite Version:** 1.0.0
**Total Tests:** 68
**Success Rate:** 100%
