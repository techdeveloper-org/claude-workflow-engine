#!/bin/bash

# Claude Workflow Engine - Security Fixes Installation Script
# This script installs and configures all security fixes

set -e  # Exit on error

echo "================================================================"
echo "Claude Workflow Engine - Security Fixes Installation"
echo "================================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running in correct directory
if [ ! -f "requirements-secure.txt" ]; then
    echo -e "${RED}ERROR: requirements-secure.txt not found${NC}"
    echo "Please run this script from the claude-workflow-engine root directory"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found requirements-secure.txt"

# Step 1: Backup existing files
echo ""
echo "Step 1: Backing up existing files..."
if [ -f "src/app.py" ]; then
    cp src/app.py src/app.py.backup
    echo -e "${GREEN}✓${NC} Backed up src/app.py to src/app.py.backup"
fi

if [ -f "requirements.txt" ]; then
    cp requirements.txt requirements-old.txt
    echo -e "${GREEN}✓${NC} Backed up requirements.txt to requirements-old.txt"
fi

# Step 2: Install dependencies
echo ""
echo "Step 2: Installing security dependencies..."
pip install -r requirements-secure.txt

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Dependencies installed successfully"
else
    echo -e "${RED}✗${NC} Failed to install dependencies"
    exit 1
fi

# Step 3: Create .env file
echo ""
echo "Step 3: Creating environment configuration..."

if [ -f ".env" ]; then
    echo -e "${YELLOW}⚠${NC}  .env file already exists, skipping creation"
    echo "  If you want to recreate it, delete .env and run this script again"
else
    cp .env.example .env

    # Generate SECRET_KEY
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    # Update .env with generated key
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/SECRET_KEY=CHANGE_THIS_TO_A_SECURE_RANDOM_KEY_IN_PRODUCTION/SECRET_KEY=$SECRET_KEY/" .env
    else
        # Linux
        sed -i "s/SECRET_KEY=CHANGE_THIS_TO_A_SECURE_RANDOM_KEY_IN_PRODUCTION/SECRET_KEY=$SECRET_KEY/" .env
    fi

    echo -e "${GREEN}✓${NC} Created .env file with generated SECRET_KEY"
    echo -e "${YELLOW}⚠${NC}  IMPORTANT: Edit .env and set ADMIN_PASSWORD before running the application"
fi

# Step 4: Create necessary directories
echo ""
echo "Step 4: Creating necessary directories..."

mkdir -p data
mkdir -p logs
mkdir -p tests

echo -e "${GREEN}✓${NC} Created data/ and logs/ directories"

# Step 5: Run tests
echo ""
echo "Step 5: Running security tests..."

if command -v pytest &> /dev/null; then
    pytest tests/test_security.py -v

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} All security tests passed"
    else
        echo -e "${YELLOW}⚠${NC}  Some tests failed (may be expected if .env not configured)"
    fi
else
    echo -e "${YELLOW}⚠${NC}  pytest not installed, skipping tests"
    echo "  Install with: pip install pytest"
fi

# Step 6: Security scan (optional)
echo ""
echo "Step 6: Running security scan..."

if command -v bandit &> /dev/null; then
    bandit -r src/ -f json -o security-scan.json || true
    echo -e "${GREEN}✓${NC} Security scan complete (see security-scan.json)"
else
    echo -e "${YELLOW}⚠${NC}  bandit not installed, skipping security scan"
    echo "  Install with: pip install bandit"
fi

# Step 7: Final instructions
echo ""
echo "================================================================"
echo -e "${GREEN}Installation Complete!${NC}"
echo "================================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .env file and set ADMIN_PASSWORD:"
echo "   nano .env"
echo ""
echo "2. Review security configuration:"
echo "   cat SECURITY_HARDENING_GUIDE.md"
echo ""
echo "3. Test the secure application:"
echo "   python src/app_secure.py"
echo ""
echo "4. When ready, merge app_secure.py into app.py:"
echo "   mv src/app.py src/app.py.old"
echo "   mv src/app_secure.py src/app.py"
echo ""
echo "5. Review the security fixes summary:"
echo "   cat SECURITY_FIXES_SUMMARY.md"
echo ""
echo "================================================================"
echo -e "${YELLOW}⚠  IMPORTANT SECURITY REMINDERS:${NC}"
echo "================================================================"
echo ""
echo "✓ NEVER commit .env file to git"
echo "✓ Set a strong ADMIN_PASSWORD (min 12 chars, mixed case, numbers, special)"
echo "✓ Set FLASK_DEBUG=False in production"
echo "✓ Set DEVELOPMENT_MODE=False in production"
echo "✓ Use HTTPS in production (configure SSL/TLS)"
echo "✓ Regularly update dependencies"
echo "✓ Run security scans before deployment"
echo ""
echo "For production deployment, see: SECURITY_HARDENING_GUIDE.md"
echo ""
