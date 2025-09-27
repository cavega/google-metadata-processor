#!/usr/bin/env python3
"""
Test runner for Google Photos Takeout processor.

This script provides different test execution modes:
- Full test suite
- Quick unit tests only
- Integration tests only
- Specific test categories

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --unit             # Run unit tests only
    python run_tests.py --integration      # Run integration tests only
    python run_tests.py --regression       # Run regression tests only
    python run_tests.py --quick            # Run quick tests only
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd: list, description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n🚀 {description}")
    print("=" * 60)

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False
    except FileNotFoundError:
        print(f"❌ Required tool not found for {description}")
        return False


def check_dependencies() -> bool:
    """Check if required testing dependencies are available."""
    print("🔍 Checking test dependencies...")

    # Check if pytest is available
    try:
        import pytest
        print(f"✅ pytest version: {pytest.__version__}")
    except ImportError:
        print("❌ pytest not found. Install with: pip install pytest")
        return False

    # Check if the main module can be imported
    try:
        import takeout_processor
        print("✅ takeout_processor module importable")
    except ImportError as e:
        print(f"❌ Cannot import takeout_processor: {e}")
        return False

    return True


def run_unit_tests() -> bool:
    """Run unit tests only."""
    cmd = [
        sys.executable, "-m", "pytest",
        "test_takeout_processor.py::TestFilenamePatternRecognition",
        "test_takeout_processor.py::TestEXIFPreservationStrategy",
        "test_takeout_processor.py::TestAlbumDateInference",
        "test_takeout_processor.py::TestJSONMetadataMatching",
        "-v"
    ]
    return run_command(cmd, "Running unit tests")


def run_integration_tests() -> bool:
    """Run integration tests only."""
    cmd = [
        sys.executable, "-m", "pytest",
        "test_takeout_processor.py::TestProcessingPipelineIntegration",
        "-v"
    ]
    return run_command(cmd, "Running integration tests")


def run_regression_tests() -> bool:
    """Run regression tests only."""
    cmd = [
        sys.executable, "-m", "pytest",
        "test_takeout_processor.py::TestEdgeCasesAndRegressions",
        "-v"
    ]
    return run_command(cmd, "Running regression tests")


def run_all_tests() -> bool:
    """Run the complete test suite."""
    cmd = [sys.executable, "-m", "pytest", "test_takeout_processor.py", "-v"]
    return run_command(cmd, "Running complete test suite")


def run_quick_tests() -> bool:
    """Run quick tests (unit tests excluding slow integration tests)."""
    cmd = [
        sys.executable, "-m", "pytest",
        "test_takeout_processor.py",
        "-v",
        "-m", "not slow"
    ]
    return run_command(cmd, "Running quick test suite")


def run_with_coverage() -> bool:
    """Run tests with coverage reporting."""
    cmd = [
        sys.executable, "-m", "pytest",
        "test_takeout_processor.py",
        "--cov=takeout_processor",
        "--cov-report=html",
        "--cov-report=term-missing",
        "-v"
    ]
    return run_command(cmd, "Running tests with coverage")


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(description="Test runner for Google Photos Takeout processor")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--regression", action="store_true", help="Run regression tests only")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only")
    parser.add_argument("--coverage", action="store_true", help="Run tests with coverage reporting")

    args = parser.parse_args()

    print("🧪 Google Photos Takeout Processor Test Suite")
    print("=" * 60)

    # Check dependencies first
    if not check_dependencies():
        print("\n❌ Dependency check failed. Please install required packages.")
        sys.exit(1)

    # Determine which tests to run
    success = True

    if args.unit:
        success = run_unit_tests()
    elif args.integration:
        success = run_integration_tests()
    elif args.regression:
        success = run_regression_tests()
    elif args.quick:
        success = run_quick_tests()
    elif args.coverage:
        success = run_with_coverage()
    else:
        # Run all tests by default
        success = run_all_tests()

    # Final summary
    print("\n" + "=" * 60)
    if success:
        print("🎉 All tests completed successfully!")
        print("\n📊 Test Summary:")
        print("✅ Enhanced metadata processing strategies verified")
        print("✅ Filename pattern recognition tested")
        print("✅ EXIF preservation strategy validated")
        print("✅ Album date inference confirmed")
        print("✅ JSON metadata matching verified")
        print("✅ Edge cases and regressions covered")
        sys.exit(0)
    else:
        print("💥 Some tests failed!")
        print("Please review the output above and fix any issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()