#!/bin/bash
# =============================================================================
# Live Alpha Runner - Training Wheels Mode
# =============================================================================
# Runs the bot fleet with strict micro-limits for initial live trading.
#
# Safety Features:
# - $5 max position size
# - $15 daily stop loss
# - Pre-flight checks before starting
# - Kill switch file monitoring
# - All output logged to file
#
# Usage: ./run_live_alpha.sh
# Emergency Stop: touch KILL_SWITCH.txt
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/live_session_${DATE}.log"

echo ""
echo "=================================================="
echo " 🎓 POLYMARKET HFT - LIVE ALPHA MODE"
echo "=================================================="
echo ""

# Check for kill switch file
if [ -f "KILL_SWITCH.txt" ]; then
    echo -e "${RED}ERROR: KILL_SWITCH.txt exists!${NC}"
    echo "Remove this file to start trading: rm KILL_SWITCH.txt"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}"
    echo "Copy .env.example to .env and fill in your credentials."
    exit 1
fi

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo -e "${RED}ERROR: venv not found!${NC}"
    echo "Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

source venv/bin/activate

# Create logs directory
mkdir -p logs

# Export Alpha configuration
export POLYMARKET_MODE=alpha

echo -e "${YELLOW}⚠️  WARNING: This will use REAL money!${NC}"
echo ""
echo "Configuration:"
echo "  - Max Position: \$5.00"
echo "  - Daily Stop:   \$15.00"
echo "  - Log File:     ${LOG_FILE}"
echo ""
echo "Emergency Stop: Create KILL_SWITCH.txt"
echo ""

read -p "Type 'ALPHA' to confirm and start: " confirm
if [ "$confirm" != "ALPHA" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Running pre-flight checks..."
echo ""

# Run pre-flight checks
python -c "
import asyncio
from utils.startup_check import perform_safety_checks
success, issues = asyncio.run(perform_safety_checks())
if not success:
    exit(1)
"

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}Pre-flight checks FAILED. Resolve issues before trading.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Pre-flight checks PASSED!${NC}"
echo ""
echo "Starting Live Alpha Trading..."
echo "Logging to: ${LOG_FILE}"
echo ""

# Run with output to both console and log file
python main.py --mode live-alpha 2>&1 | tee "${LOG_FILE}"

echo ""
echo "Session ended. Log saved to: ${LOG_FILE}"
