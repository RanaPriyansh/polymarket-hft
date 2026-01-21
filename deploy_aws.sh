#!/bin/bash
# =============================================================================
# AWS EC2 Deployment Script
# =============================================================================
# One-command deployment for a fresh Ubuntu server.
#
# Prerequisites:
# - Fresh Ubuntu 22.04 LTS EC2 instance
# - SSH access
# - This script uploaded to the server
#
# Usage:
#   scp deploy_aws.sh ubuntu@your-ec2-ip:~
#   ssh ubuntu@your-ec2-ip
#   chmod +x deploy_aws.sh
#   ./deploy_aws.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=================================================="
echo " 🚀 POLYMARKET HFT - AWS DEPLOYMENT"
echo "=================================================="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}Running as root. Recommend running as ubuntu user.${NC}"
fi

# Step 1: Update system
echo -e "${GREEN}[1/6] Updating system packages...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

# Step 2: Install Docker
echo -e "${GREEN}[2/6] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    # Install Docker
    sudo apt-get install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release
    
    # Add Docker's official GPG key
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # Set up repository
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker Engine
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    
    echo -e "${GREEN}Docker installed successfully!${NC}"
else
    echo "Docker already installed."
fi

# Step 3: Install Docker Compose (standalone)
echo -e "${GREEN}[3/6] Installing Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "Docker Compose installed."
else
    echo "Docker Compose already installed."
fi

# Step 4: Create app directory
echo -e "${GREEN}[4/6] Setting up application directory...${NC}"
APP_DIR="/home/$USER/polymarket-hft"

if [ -d "$APP_DIR" ]; then
    echo "App directory exists. Pulling latest changes..."
    cd "$APP_DIR"
    git pull || echo "Note: Not a git repo or no remote configured."
else
    echo -e "${YELLOW}App directory not found.${NC}"
    echo "Please either:"
    echo "  1. git clone your-repo-url $APP_DIR"
    echo "  2. scp -r your-local-project $APP_DIR"
    echo ""
    echo "Then re-run this script."
    
    # Create placeholder directory
    mkdir -p "$APP_DIR"
    exit 1
fi

cd "$APP_DIR"

# Step 5: Check for .env file
echo -e "${GREEN}[5/6] Checking configuration...${NC}"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}Created .env from .env.example${NC}"
        echo "IMPORTANT: Edit .env with your actual credentials!"
        echo "  nano .env"
        exit 1
    else
        echo -e "${RED}ERROR: No .env file found!${NC}"
        exit 1
    fi
else
    echo ".env file found."
fi

# Create logs directory
mkdir -p logs

# Step 6: Build and start
echo -e "${GREEN}[6/6] Building and starting container...${NC}"

# Set bot mode (default to dry-run for safety)
export BOT_MODE=${BOT_MODE:-dry-run}
export INSTANCE_ID=$(hostname)

echo "Building Docker image (this may take a few minutes)..."
docker-compose build

echo ""
echo "Starting bot in detached mode..."
docker-compose up -d

echo ""
echo "=================================================="
echo -e "${GREEN} ✅ DEPLOYMENT COMPLETE!${NC}"
echo "=================================================="
echo ""
echo "Useful commands:"
echo "  View logs:      docker-compose logs -f"
echo "  Stop bot:       docker-compose down"
echo "  Restart:        docker-compose restart"
echo "  Shell access:   docker-compose exec polymarket-hft bash"
echo ""
echo "Bot is running in mode: ${BOT_MODE}"
echo ""
echo "To switch to live trading:"
echo "  export BOT_MODE=live"
echo "  docker-compose up -d"
echo ""
echo "Emergency stop:"
echo "  touch KILL_SWITCH.txt"
echo "  docker-compose restart"
echo ""
