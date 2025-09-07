#!/bin/bash

# Lengau AI System Production Deployment Script
# Complete deployment of HPC anomaly detection system

echo "🐆 LENGAU AI SYSTEM DEPLOYMENT"
echo "==============================="
echo "🎯 Deploying production HPC anomaly detection system"
echo "🤖 AI-powered monitoring for 1,368 compute nodes"
echo ""

# Configuration
LENGAU_DIR="/opt/lengau-monitoring"
SCRIPTS_DIR="$LENGAU_DIR/scripts"
DATA_DIR="$LENGAU_DIR/data"
MODELS_DIR="$LENGAU_DIR/models"
LOGS_DIR="$LENGAU_DIR/logs"
SERVICE_DIR="/etc/systemd/system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log_message() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error_message() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success_message() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning_message() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        error_message "This script must be run as root"
        exit 1
    fi
}

# Create directory structure
setup_directories() {
    log_message "📁 Setting up directory structure..."
    
    mkdir -p "$LENGAU_DIR"
    mkdir -p "$SCRIPTS_DIR"
    mkdir -p "$DATA_DIR"/{comprehensive,detections,alerts,models}
    mkdir -p "$MODELS_DIR"
    mkdir -p "$LOGS_DIR"
    mkdir -p "$LENGAU_DIR/config"
    mkdir -p "$LENGAU_DIR/backup"
    
    # Set permissions
    chown -R embele:embele "$LENGAU_DIR"
    chmod -R 755 "$LENGAU_DIR"
    
    success_message "Directory structure created"
}

# Install Python dependencies
install_dependencies() {
    log_message "🐍 Installing Python dependencies..."
    
    # Check if pip is available
    if ! command -v pip3 &> /dev/null; then
        error_message "pip3 not found. Please install python3-pip"
        exit 1
    fi
    
    # Install required packages
    pip3 install --upgrade pip
    pip3 install numpy pandas scikit-learn joblib pathlib
    
    success_message "Python dependencies installed"
}

# Copy scripts to production directory
deploy_scripts() {
    log_message "📋 Deploying scripts to production directory..."
    
    # Core scripts
    CORE_SCRIPTS=(
        "lengau_comprehensive_log_processor.py"
        "lengau_comprehensive_ai_trainer.py"
        "lengau_realtime_detector.py"
        "lengau_ai_dashboard.py"
        "automated_log_collection.sh"
        "collect_system_logs.sh"
        "collect_pbs_logs.sh"
        "test_comprehensive_processor.py"
        "test_updated_processor.py"
        "investigate_unified_structure.py"
    )
    
    for script in "${CORE_SCRIPTS[@]}"; do
        if [ -f "$script" ]; then
            cp "$script" "$SCRIPTS_DIR/"
            chmod +x "$SCRIPTS_DIR/$script"
            success_message "Deployed $script"
        else
            warning_message "Script not found: $script"
        fi
    done
    
    # Set ownership
    chown -R embele:embele "$SCRIPTS_DIR"
}

# Create systemd services
create_services() {
    log_message "⚙️ Creating systemd services..."
    
    # Real-time detector service
    cat > "$SERVICE_DIR/lengau-detector.service" << EOF
[Unit]
Description=Lengau Real-time Anomaly Detector
After=network.target
Wants=network.target

[Service]
Type=simple
User=embele
Group=embele
WorkingDirectory=$SCRIPTS_DIR
ExecStart=/usr/bin/python3 $SCRIPTS_DIR/lengau_realtime_detector.py
Restart=always
RestartSec=10
StandardOutput=append:$LOGS_DIR/detector_service.log
StandardError=append:$LOGS_DIR/detector_service.log

[Install]
WantedBy=multi-user.target
EOF

    # Dashboard service
    cat > "$SERVICE_DIR/lengau-dashboard.service" << EOF
[Unit]
Description=Lengau AI Dashboard
After=network.target
Wants=network.target

[Service]
Type=simple
User=embele
Group=embele
WorkingDirectory=$SCRIPTS_DIR
ExecStart=/usr/bin/python3 $SCRIPTS_DIR/lengau_ai_dashboard.py
Restart=always
RestartSec=10
StandardOutput=append:$LOGS_DIR/dashboard_service.log
StandardError=append:$LOGS_DIR/dashboard_service.log

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    systemctl daemon-reload
    
    success_message "Systemd services created"
}

# Setup cron jobs
setup_cron() {
    log_message "📅 Setting up cron jobs..."
    
    # Add to embele user's crontab
    (su - embele -c "crontab -l" 2>/dev/null; cat << EOF
# Lengau HPC Log Collection - every 4 hours
0 */4 * * * $SCRIPTS_DIR/automated_log_collection.sh >> $LOGS_DIR/automated_collection.log 2>&1

# AI Model Training - daily at 2 AM
0 2 * * * $SCRIPTS_DIR/lengau_comprehensive_ai_trainer.py >> $LOGS_DIR/ai_training.log 2>&1

# Dashboard data generation - every 5 minutes
*/5 * * * * cd $SCRIPTS_DIR && python3 -c "from lengau_ai_dashboard import LengauAIDashboard; LengauAIDashboard().generate_dashboard_data()" >> $LOGS_DIR/dashboard_cron.log 2>&1
EOF
    ) | su - embele -c "crontab -"
    
    success_message "Cron jobs configured"
}

# Test installation
test_installation() {
    log_message "🧪 Testing installation..."
    
    # Test comprehensive log processor
    if [ -f "$SCRIPTS_DIR/test_comprehensive_processor.py" ]; then
        cd "$SCRIPTS_DIR"
        if su - embele -c "cd $SCRIPTS_DIR && python3 test_comprehensive_processor.py" > /dev/null 2>&1; then
            success_message "Comprehensive processor test passed"
        else
            warning_message "Comprehensive processor test failed"
        fi
    fi
    
    # Check if unified collections exist
    if [ -d "/mnt/lustre/users/embele/hpc_logs" ]; then
        collection_count=$(find /mnt/lustre/users/embele/hpc_logs -maxdepth 1 -type d -name "unified_*" | wc -l)
        if [ "$collection_count" -gt 0 ]; then
            success_message "Found $collection_count unified collections"
        else
            warning_message "No unified collections found"
        fi
    else
        warning_message "HPC logs directory not accessible"
    fi
    
    # Test Python imports
    if su - embele -c "python3 -c 'import numpy, pandas, sklearn; print(\"All imports successful\")'" > /dev/null 2>&1; then
        success_message "Python dependencies verified"
    else
        warning_message "Python dependency issues detected"
    fi
}

# Create management scripts
create_management_scripts() {
    log_message "🔧 Creating management scripts..."
    
    # Start script
    cat > "$SCRIPTS_DIR/start_lengau_ai.sh" << 'EOF'
#!/bin/bash
echo "🚀 Starting Lengau AI System..."
sudo systemctl start lengau-detector
sudo systemctl start lengau-dashboard
echo "✅ System started!"
systemctl status lengau-detector lengau-dashboard
EOF
    
    # Stop script
    cat > "$SCRIPTS_DIR/stop_lengau_ai.sh" << 'EOF'
#!/bin/bash
echo "🛑 Stopping Lengau AI System..."
sudo systemctl stop lengau-detector
sudo systemctl stop lengau-dashboard
echo "✅ System stopped!"
EOF
    
    # Status script
    cat > "$SCRIPTS_DIR/status_lengau_ai.sh" << 'EOF'
#!/bin/bash
echo "📊 Lengau AI System Status"
echo "=========================="
echo ""
echo "🤖 Services:"
systemctl status lengau-detector --no-pager -l
echo ""
systemctl status lengau-dashboard --no-pager -l
echo ""
echo "📁 Recent logs:"
echo "Detector: $(tail -1 /opt/lengau-monitoring/logs/detector_service.log 2>/dev/null || echo 'No logs')"
echo "Dashboard: $(tail -1 /opt/lengau-monitoring/logs/dashboard_service.log 2>/dev/null || echo 'No logs')"
echo ""
echo "📊 Data status:"
echo "Detections today: $(find /opt/lengau-monitoring/data/detections -name "*$(date +%Y%m%d)*" -type f | wc -l)"
echo "Alerts today: $(find /opt/lengau-monitoring/data/alerts -name "*$(date +%Y%m%d)*" -type f | wc -l)"
EOF
    
    # Train AI script
    cat > "$SCRIPTS_DIR/train_lengau_ai.sh" << 'EOF'
#!/bin/bash
echo "🧠 Training Lengau AI Models..."
cd /opt/lengau-monitoring/scripts
python3 lengau_comprehensive_ai_trainer.py
echo "✅ AI training completed!"
EOF
    
    # Make scripts executable
    chmod +x "$SCRIPTS_DIR"/*.sh
    chown embele:embele "$SCRIPTS_DIR"/*.sh
    
    success_message "Management scripts created"
}

# Main deployment function
main_deployment() {
    log_message "🚀 Starting Lengau AI System deployment..."
    
    # Check prerequisites
    check_root
    
    # Setup
    setup_directories
    install_dependencies
    deploy_scripts
    create_services
    setup_cron
    create_management_scripts
    
    # Test
    test_installation
    
    echo ""
    success_message "🎉 Lengau AI System deployment completed!"
    echo ""
    echo "📋 DEPLOYMENT SUMMARY"
    echo "===================="
    echo "📁 Installation directory: $LENGAU_DIR"
    echo "🤖 Services created: lengau-detector, lengau-dashboard"
    echo "📅 Cron jobs: Log collection every 4h, AI training daily"
    echo "🔧 Management scripts: start/stop/status/train"
    echo ""
    echo "🚀 NEXT STEPS"
    echo "============"
    echo "1. Train initial AI models:"
    echo "   cd $SCRIPTS_DIR && ./train_lengau_ai.sh"
    echo ""
    echo "2. Start the system:"
    echo "   ./start_lengau_ai.sh"
    echo ""
    echo "3. Enable auto-start:"
    echo "   sudo systemctl enable lengau-detector lengau-dashboard"
    echo ""
    echo "4. Monitor status:"
    echo "   ./status_lengau_ai.sh"
    echo ""
    echo "5. View dashboard:"
    echo "   cd $SCRIPTS_DIR && python3 lengau_ai_dashboard.py"
    echo ""
    success_message "🐆 Lengau HPC AI Anomaly Detection System is ready!"
}

# Run deployment
main_deployment
