#!/usr/bin/env python3
"""
Test Runner for Claude Workflow Engine

Runs all unit tests and generates coverage report.

Usage:
    python tests/run_all_tests.py
    python tests/run_all_tests.py --coverage
    python tests/run_all_tests.py --verbose
"""

import argparse
import sys
import time
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def discover_and_run_tests(verbosity=2, pattern="test_*.py"):
    """
    Discover and run all tests in the tests directory.

    Args:
        verbosity: Test output verbosity (0-2)
        pattern: Pattern to match test files

    Returns:
        bool: True if all tests passed
    """
    print("=" * 70)
    print("CLAUDE INSIGHT - TEST SUITE")
    print("=" * 70)
    print()

    # Discover tests
    loader = unittest.TestLoader()
    start_dir = Path(__file__).parent
    suite = loader.discover(start_dir, pattern=pattern)

    # Count tests
    def count_tests(suite_or_test):
        """Recursively count tests in suite"""
        try:
            count = 0
            for test in suite_or_test:
                count += count_tests(test)
            return count
        except TypeError:
            return 1

    test_count = count_tests(suite)
    print(f"Discovered {test_count} tests")
    print()

    # Run tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    start_time = time.time()
    result = runner.run(suite)
    elapsed_time = time.time() - start_time

    # Print summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures:  {len(result.failures)}")
    print(f"Errors:    {len(result.errors)}")
    print(f"Skipped:   {len(result.skipped)}")
    print(f"Time:      {elapsed_time:.2f}s")
    print()

    if result.wasSuccessful():
        print("[SUCCESS] All tests passed!")
        print("=" * 70)
        return True
    else:
        print("[FAILURE] Some tests failed!")
        print("=" * 70)
        return False


def run_with_coverage(verbosity=2):
    """
    Run tests with coverage reporting.

    Args:
        verbosity: Test output verbosity (0-2)

    Returns:
        bool: True if all tests passed
    """
    try:
        import coverage
    except ImportError:
        print("ERROR: coverage package not installed")
        print("Install with: pip install coverage")
        return False

    print("Running tests with coverage...")
    print()

    # Start coverage
    cov = coverage.Coverage(
        source=[str(Path(__file__).parent.parent / "src")],
        omit=["*/tests/*", "*/test_*", "*/__pycache__/*", "*/venv/*"],
    )
    cov.start()

    # Run tests
    success = discover_and_run_tests(verbosity=verbosity)

    # Stop coverage
    cov.stop()
    cov.save()

    # Generate report
    print()
    print("=" * 70)
    print("COVERAGE REPORT")
    print("=" * 70)
    print()

    cov.report()

    # Generate HTML report
    html_dir = Path(__file__).parent / "htmlcov"
    cov.html_report(directory=str(html_dir))

    print()
    print(f"HTML coverage report: {html_dir}/index.html")
    print("=" * 70)

    return success


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Run Claude Workflow Engine test suite")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage reporting")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--pattern", default="test_*.py", help="Test file pattern (default: test_*.py)")

    args = parser.parse_args()

    # Determine verbosity
    if args.quiet:
        verbosity = 0
    elif args.verbose:
        verbosity = 2
    else:
        verbosity = 1

    # Run tests
    if args.coverage:
        success = run_with_coverage(verbosity=verbosity)
    else:
        success = discover_and_run_tests(verbosity=verbosity, pattern=args.pattern)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
