#!/bin/bash
# =============================================================================
# Shadow Mode Runner - Paper Trading
# =============================================================================
# Runs the bot fleet in shadow mode for testing strategy logic
# without risking real capital.
#
# Usage: ./run_shadow.sh
# Stop:  Ctrl+C (generates performance report on exit)
# =============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "=================================================="
echo " 👻 POLYMARKET HFT - SHADOW MODE"
echo "=================================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Warning: venv not found. Creating...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Create logs directory if needed
mkdir -p logs

# Clear previous shadow trades (optional)
if [ -f "logs/shadow_trades.csv" ]; then
    echo -e "${YELLOW}Previous shadow trades found.${NC}"
    read -p "Clear previous trades? (y/N): " clear_choice
    if [[ "$clear_choice" =~ ^[Yy]$ ]]; then
        rm logs/shadow_trades.csv
        echo "Cleared previous shadow trades."
    fi
fi

echo ""
echo "Starting Shadow Mode..."
echo "Press Ctrl+C to stop and generate performance report."
echo ""

# Trap Ctrl+C to run cleanup and report
cleanup() {
    echo ""
    echo "=================================================="
    echo " Generating Performance Report..."
    echo "=================================================="
    
    # Run the performance report generator
    python -c "from strategy_layer.shadow_engine import generate_performance_report; generate_performance_report()"
    
    echo ""
    echo -e "${GREEN}Shadow session complete!${NC}"
    echo "Trades logged to: logs/shadow_trades.csv"
    echo "Report saved to: logs/shadow_report.txt"
    echo ""
    
    exit 0
}

trap cleanup SIGINT SIGTERM

# Run the bot in shadow mode
python main.py --mode shadow

# If bot exits normally (not interrupted), still generate report
cleanup
