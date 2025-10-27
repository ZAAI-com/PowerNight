#!/bin/bash
# PowerNight Development Setup Script

set -e

echo "🚀 Setting up PowerNight development environment..."

# Check if Python 3.10+ is available
python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python 3.10+ is required. Found: $python_version"
    exit 1
fi

echo "✅ Python version: $python_version"

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install development dependencies
echo "📚 Installing dependencies..."
pip install -e .
pip install -r requirements-dev.txt

# Install pre-commit hooks
echo "🔧 Setting up pre-commit hooks..."
pre-commit install

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs
mkdir -p config
mkdir -p docker-volumes/{config,data,logs,backups}

# Copy example configuration
echo "⚙️ Setting up configuration..."
if [ ! -f "config/config.yaml" ]; then
    cp config/examples/config.example.yaml config/config.yaml
    echo "📝 Created config/config.yaml from example"
fi

if [ ! -f ".env" ]; then
    cp config/examples/powernight.env.example .env
    echo "📝 Created .env from example"
fi

# Run tests
echo "🧪 Running tests..."
python -m pytest tests/ -v

echo "✅ Development environment setup complete!"
echo ""
echo "To activate the virtual environment:"
echo "  source venv/bin/activate"
echo ""
echo "To run the application:"
echo "  powernight"
echo ""
echo "To run tests:"
echo "  pytest"
echo ""
echo "To run linting:"
echo "  black src/ tests/"
echo "  isort src/ tests/"
echo "  flake8 src/ tests/"
echo "  mypy src/"
