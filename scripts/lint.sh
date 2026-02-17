#!/bin/bash
# Lint Python code in the Shams project

set -e

echo "🔍 Linting Python code..."
echo "================================"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run linter
run_linter() {
    local name=$1
    local cmd=$2
    
    echo ""
    echo "Running $name..."
    if eval "$cmd"; then
        echo -e "${GREEN}✓ $name passed${NC}"
        return 0
    else
        echo -e "${RED}✗ $name found issues${NC}"
        return 1
    fi
}

# Check if we're in pipenv or need to install
if command -v pipenv &> /dev/null; then
    echo "Using pipenv environment"
    PYTHON_CMD="pipenv run python -m"
else
    echo "Using system python"
    PYTHON_CMD="python -m"
fi

# Track if any linter failed
FAILED=0

# Run Pylint on backend
if run_linter "Pylint (Backend)" "$PYTHON_CMD pylint backend/app --rcfile=.pylintrc"; then
    :
else
    FAILED=1
fi

# Run Pylint on tools
if run_linter "Pylint (Tools)" "$PYTHON_CMD pylint tools --rcfile=.pylintrc --ignore=tests"; then
    :
else
    FAILED=1
fi

# Run Pylint on commands
if run_linter "Pylint (Commands)" "$PYTHON_CMD pylint commands --rcfile=.pylintrc"; then
    :
else
    FAILED=1
fi

echo ""
echo "================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All linters passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some linters found issues${NC}"
    echo ""
    echo "To fix import issues automatically, run:"
    echo "  ${YELLOW}pipenv run isort backend/ tools/ commands/${NC}"
    echo ""
    echo "To format code automatically, run:"
    echo "  ${YELLOW}pipenv run black backend/ tools/ commands/${NC}"
    exit 1
fi

