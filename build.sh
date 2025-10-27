#!/bin/bash
# PowerNight Build Script
# Generates version information and builds the application

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if required tools are installed
check_requirements() {
    log_info "Checking build requirements..."

    if ! command -v python3 &> /dev/null; then
        log_error "python3 is not installed"
        exit 1
    fi

    if ! command -v node &> /dev/null; then
        log_error "node is not installed"
        exit 1
    fi

    if ! command -v npm &> /dev/null; then
        log_error "npm is not installed"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_warning "jq is not installed. Will use basic parsing (install jq for better results)"
    fi

    log_success "All requirements satisfied"
}

# Validate configuration
validate_config() {
    log_info "Validating configuration..."

    # Check if config file exists
    if [ ! -f "config/config.yaml" ]; then
        log_warning "config/config.yaml not found - skipping validation"
        return 0
    fi

    # Run validation using Python
    if python3 -m powernight.main --config config/config.yaml validate-config > /tmp/config_validation.log 2>&1; then
        log_success "Configuration validation passed"
        return 0
    else
        log_error "Configuration validation failed!"
        log_error "See details below:"
        echo ""
        cat /tmp/config_validation.log
        echo ""
        log_error "Build aborted due to configuration errors"
        log_info "Fix the configuration errors and try again, or use --skip-validation to skip this check"
        exit 1
    fi
}

# Generate timestamp in required format: yyyy-MM-dd HH:mm:ss zzz ZZZZ
generate_timestamp() {
    log_info "Generating build timestamp..." >&2

    # Format: 2025-10-18 14:30:45 UTC +0000
    TIMESTAMP=$(date -u +'%Y-%m-%d %H:%M:%S %Z %z')

    log_success "Timestamp: $TIMESTAMP" >&2
    echo "$TIMESTAMP"
}

# Extract version from pyproject.toml
get_powernight_version() {
    log_info "Reading PowerNight version from pyproject.toml..." >&2

    if [ -f "pyproject.toml" ]; then
        VERSION=$(grep "^version = " pyproject.toml | head -n 1 | cut -d'"' -f2)
        log_success "PowerNight version: $VERSION" >&2
        echo "$VERSION"
    else
        log_error "pyproject.toml not found" >&2
        echo "unknown"
    fi
}

# Get Python version
get_python_version() {
    log_info "Detecting Python version..." >&2

    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    log_success "Python version: $PYTHON_VERSION" >&2
    echo "$PYTHON_VERSION"
}

# Get Node.js version
get_node_version() {
    log_info "Detecting Node.js version..." >&2

    NODE_VERSION=$(node --version | sed 's/v//')
    log_success "Node.js version: $NODE_VERSION" >&2
    echo "$NODE_VERSION"
}

# Get npm version
get_npm_version() {
    log_info "Detecting npm version..." >&2

    NPM_VERSION=$(npm --version)
    log_success "npm version: $NPM_VERSION" >&2
    echo "$NPM_VERSION"
}

# Extract backend dependencies from pyproject.toml
get_backend_dependencies() {
    log_info "Extracting backend dependencies..." >&2

    if [ ! -f "pyproject.toml" ]; then
        echo "{}"
        return
    fi

    # Extract key dependencies with versions
    # This is a simplified parser - ideally use a TOML parser
    DEPS=$(cat <<'EOF'
{
  "flask": ">=2.3.0",
  "pypowerwall": ">=0.10.5",
  "schedule": ">=1.2.0",
  "pyyaml": ">=6.0.1",
  "sqlalchemy": "Implicit (via Flask-SQLAlchemy)",
  "requests": ">=2.31.0",
  "structlog": ">=23.1.0",
  "tenacity": ">=8.2.0"
}
EOF
)

    echo "$DEPS"
}

# Extract frontend dependencies from package.json
get_frontend_dependencies() {
    log_info "Extracting frontend dependencies..." >&2

    if [ ! -f "package.json" ]; then
        echo "{}"
        return
    fi

    if command -v jq &> /dev/null; then
        # Use jq for proper JSON parsing
        DEPS=$(jq -r '{
            react: .dependencies.react,
            "react-dom": .dependencies["react-dom"],
            "react-router-dom": .dependencies["react-router-dom"],
            axios: .dependencies.axios,
            "date-fns": .dependencies["date-fns"],
            vite: .devDependencies.vite,
            typescript: .devDependencies.typescript,
            tailwindcss: .devDependencies.tailwindcss,
            "@vitejs/plugin-react": .devDependencies["@vitejs/plugin-react"]
        }' package.json)
    else
        # Fallback: Basic parsing without jq
        DEPS=$(cat <<'EOF'
{
  "react": "^18.2.0",
  "react-dom": "^18.2.0",
  "react-router-dom": "^6.20.1",
  "axios": "^1.6.2",
  "date-fns": "^2.30.0",
  "vite": "^7.1.9",
  "typescript": "^5.2.2",
  "tailwindcss": "^4.1.14",
  "@vitejs/plugin-react": "^4.2.1"
}
EOF
)
    fi

    echo "$DEPS"
}

# Generate version-info.json
generate_version_info() {
    local TIMESTAMP=$1
    local POWERNIGHT_VERSION=$2
    local PYTHON_VERSION=$3
    local NODE_VERSION=$4
    local NPM_VERSION=$5
    local BACKEND_DEPS=$6
    local FRONTEND_DEPS=$7

    log_info "Generating version-info.json..."

    # Create JSON file with proper formatting
    # Note: We need to ensure dependencies are properly formatted without trailing commas
    cat > version-info.json <<EOF
{
  "application": "PowerNight",
  "version": "$POWERNIGHT_VERSION",
  "build_timestamp": "$TIMESTAMP",
  "python_version": "$PYTHON_VERSION",
  "node_version": "$NODE_VERSION",
  "npm_version": "$NPM_VERSION",
  "backend_dependencies": $(echo "$BACKEND_DEPS" | tr -d '\n'),
  "frontend_dependencies": $(echo "$FRONTEND_DEPS" | tr -d '\n')
}
EOF

    log_success "version-info.json created"

    # Display the generated file
    log_info "Generated version info:"
    cat version-info.json | head -20
}

# Build frontend
build_frontend() {
    log_info "Building frontend with Vite..."

    npm run build

    log_success "Frontend build completed"
}

# Copy version info to dist
copy_version_to_dist() {
    log_info "Copying version-info.json to dist/..."

    if [ ! -d "dist" ]; then
        log_error "dist/ directory not found. Frontend build may have failed."
        exit 1
    fi

    cp version-info.json dist/

    log_success "version-info.json copied to dist/"
}

# Build Docker image
build_docker() {
    local TIMESTAMP=$1

    log_info "Building Docker image..."

    docker build \
        --label "build_timestamp=$TIMESTAMP" \
        -t powernight:latest \
        .

    log_success "Docker image built successfully"
}

# Main build process
main() {
    echo ""
    log_info "========================================="
    log_info "PowerNight Build Script"
    log_info "========================================="
    echo ""

    # Check requirements
    check_requirements
    echo ""

    # Validate configuration (skip if --skip-validation flag is set)
    if [[ "$*" != *"--skip-validation"* ]]; then
        validate_config
        echo ""
    else
        log_warning "Skipping configuration validation (--skip-validation flag set)"
        echo ""
    fi

    # Generate build metadata
    TIMESTAMP=$(generate_timestamp)
    POWERNIGHT_VERSION=$(get_powernight_version)
    PYTHON_VERSION=$(get_python_version)
    NODE_VERSION=$(get_node_version)
    NPM_VERSION=$(get_npm_version)
    echo ""

    # Get dependencies
    BACKEND_DEPS=$(get_backend_dependencies)
    FRONTEND_DEPS=$(get_frontend_dependencies)
    echo ""

    # Generate version info
    generate_version_info "$TIMESTAMP" "$POWERNIGHT_VERSION" \
        "$PYTHON_VERSION" "$NODE_VERSION" "$NPM_VERSION" \
        "$BACKEND_DEPS" "$FRONTEND_DEPS"
    echo ""

    # Build frontend
    build_frontend
    echo ""

    # Copy version info
    copy_version_to_dist
    echo ""

    # Build Docker image (optional - can be skipped with --no-docker flag)
    if [[ "$*" != *"--no-docker"* ]]; then
        build_docker "$TIMESTAMP"
        echo ""
    else
        log_info "Skipping Docker build (--no-docker flag set)"
        echo ""
    fi

    # Summary
    echo ""
    log_success "========================================="
    log_success "Build completed successfully!"
    log_success "========================================="
    log_success "Version: $POWERNIGHT_VERSION"
    log_success "Timestamp: $TIMESTAMP"
    echo ""

    if [[ "$*" == *"--no-docker"* ]]; then
        log_info "To build Docker image manually, run:"
        echo "  docker build --label \"build_timestamp=$TIMESTAMP\" -t powernight:latest ."
        echo ""
    fi

    if [[ "$*" == *"--skip-validation"* ]]; then
        log_warning "Note: Configuration validation was skipped"
        log_info "To validate your config manually, run:"
        echo "  python3 -m powernight.main validate-config"
        echo ""
    fi
}

# Run main function
main "$@"
