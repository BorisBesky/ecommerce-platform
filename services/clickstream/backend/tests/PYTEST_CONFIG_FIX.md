# Pytest Configuration Fix

## Issue

The pytest configuration included coverage options by default, but `pytest-cov` was not installed, causing this error:

```
pytest: error: unrecognized arguments: --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml
```

## Solution

### 1. Updated pytest.ini

Removed coverage options from default `addopts` to make them optional:

**Before:**
```ini
addopts =
    -v
    --strict-markers
    --tb=short
    --color=yes
    --cov=app
    --cov-report=term-missing
    --cov-report=html
    --cov-report=xml
```

**After:**
```ini
addopts =
    -v
    --strict-markers
    --tb=short
    --color=yes

# Coverage options (requires pytest-cov to be installed)
# To run with coverage: pytest --cov=app --cov-report=term-missing --cov-report=html
```

### 2. Updated requirements-test.txt

Made coverage and code quality tools optional (commented out by default):

```
# Core testing framework (required)
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2

# Optional: Coverage tools
# pytest-cov==4.1.0
```

### 3. Updated run_e2e_tests.sh

Added automatic detection of pytest-cov and conditional coverage:

```bash
# Check if pytest-cov is installed and add coverage if available
PYTEST_ARGS="-v --tb=short --color=yes"
if python3 -c "import pytest_cov" 2>/dev/null; then
    PYTEST_ARGS="$PYTEST_ARGS --cov=app --cov-report=term-missing"
fi
```

## Usage

### Run Tests Without Coverage

```bash
# Install minimal dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/ -v
```

### Run Tests With Coverage

```bash
# Install with coverage tools
pip install pytest pytest-asyncio httpx pytest-cov

# Run tests (coverage will be automatically included if pytest-cov is installed)
pytest tests/ --cov=app --cov-report=html
```

## Result

Tests now run successfully without requiring optional dependencies like `pytest-cov`. Coverage can be enabled by:
1. Installing `pytest-cov`
2. Adding `--cov=app` flags manually when running pytest

This makes the test suite more flexible and easier to use in different environments.

