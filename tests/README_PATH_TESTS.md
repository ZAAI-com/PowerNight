# Path-Related Tests

This directory contains comprehensive tests to prevent Docker container path bugs in the PowerNight application.

## Problem Solved

The original issue was that the application was trying to use Docker container paths (`/app/data`, `/app/logs`) when running in development mode, causing permission errors and preventing the web UI from working.

## Test Coverage

### 1. Configuration Path Tests (`test_config_paths.py`)
- **Purpose**: Ensure configuration system uses proper development paths
- **Key Tests**:
  - Config manager finds local config files before Docker paths
  - Configuration uses relative log paths by default
  - Environment variable overrides work correctly
  - No hardcoded Docker paths in default configurations

### 2. Auth API Path Tests (`test_auth_api_paths.py`)
- **Purpose**: Ensure auth API uses proper development paths
- **Key Tests**:
  - Auth API uses relative data path by default
  - Environment variable `POWERNIGHT_DATA_PATH` is respected
  - No Docker paths (`/app/data`) are used by default
  - Graceful handling of missing directories

### 3. Web App Path Tests (`test_web_app_paths_simple.py`)
- **Purpose**: Ensure web application uses proper development paths
- **Key Tests**:
  - Web app does not use Docker paths by default
  - Environment variable `POWERNIGHT_STATIC_PATH` is respected when path exists
  - Fallback to calculated paths when environment path doesn't exist
  - Consistent path handling across multiple calls

### 4. Integration Tests (`test_application_startup_paths.py`)
- **Purpose**: Ensure full application startup uses proper development paths
- **Key Tests**:
  - Application initializes with relative paths
  - No Docker paths are used during startup
  - Web interface starts successfully with relative paths
  - Consistent path usage across all components

## Running the Tests

### Quick Run
```bash
python run_path_tests.py
```

### Verbose Output
```bash
python run_path_tests.py --verbose
```

### With Coverage
```bash
python run_path_tests.py --coverage
```

### Run Specific Test File
```bash
python run_path_tests.py --specific tests/unit/test_config_paths.py
```

### Manual Run
```bash
python -m pytest tests/unit/test_config_paths.py tests/unit/test_auth_api_paths.py tests/unit/test_web_app_paths_simple.py tests/integration/test_application_startup_paths.py -v
```

## What These Tests Prevent

1. **Docker Path Hardcoding**: Ensures no hardcoded `/app/*` paths are used in development
2. **Permission Errors**: Prevents attempts to create directories in read-only Docker paths
3. **Path Resolution Issues**: Ensures proper path calculation from file locations
4. **Environment Variable Ignorance**: Ensures environment variables are respected when appropriate
5. **Inconsistent Path Usage**: Ensures all components use consistent path handling

## Key Behaviors Tested

### ✅ Correct Behaviors
- Uses relative paths (`logs/powernight.log`, `data/`) by default
- Respects environment variables when paths exist
- Falls back to calculated paths when environment paths don't exist
- Calculates paths based on actual file locations, not working directory
- Handles missing directories gracefully

### ❌ Prevented Behaviors
- Using Docker container paths (`/app/data`, `/app/logs`) in development
- Failing when directories don't exist
- Ignoring environment variables
- Using inconsistent path resolution across components

## Test Structure

Each test file follows a consistent structure:

1. **Basic Functionality Tests**: Test core path handling behavior
2. **Edge Case Tests**: Test error conditions and boundary cases  
3. **Integration Tests**: Test full application startup and component interaction

## Maintenance

These tests should be run:
- Before any changes to path handling code
- As part of the CI/CD pipeline
- When adding new components that handle file paths
- When modifying configuration or environment variable handling

## Adding New Tests

When adding new path-related functionality:

1. Add tests to the appropriate existing test file
2. Follow the existing test patterns and naming conventions
3. Test both success and failure cases
4. Ensure tests work in different working directories
5. Test environment variable handling
6. Run the full test suite to ensure no regressions

## Dependencies

These tests require:
- `pytest` for test framework
- `unittest.mock` for mocking
- `tempfile` for temporary directories
- `pathlib` for path handling

All dependencies are included in the project's requirements.
