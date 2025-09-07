#!/usr/bin/env python3
"""
Lengau System Status Checker - Comprehensive health check
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import glob
import os

def check_service_status(service_name):
    """Check systemd service status"""
    try:
        result = subprocess.run(['systemctl', 'is-active', service_name], 
                              capture_output=True, text=True, timeout=10)
        status = result.stdout.strip()
        return status == 'active'
    except Exception as e:
        # Debug: try alternate method
        try:
            result = subprocess.run(['systemctl', 'status', service_name], 
                                  capture_output=True, text=True, timeout=10)
            return 'Active: active (running)' in result.stdout
        except:
            return False

def check_recent_logs():
    """Check for recent log collections"""
    logs_dir = Path("/mnt/lustre/users/embele/hpc_logs")
    
    if not logs_dir.exists():
        return False, "Logs directory not found"
    
    # Check system_logs collections
    system_logs = list(logs_dir.glob("system_logs_*"))
    if not system_logs:
        return False, "No system_logs collections found"
    
    # Get most recent collection
    latest_system_log = max(system_logs, key=lambda x: x.stat().st_mtime)
    
    # Check age
    age_hours = (datetime.now().timestamp() - latest_system_log.stat().st_mtime) / 3600
    
    return age_hours < 24, f"Latest: {latest_system_log.name} ({age_hours:.1f}h ago)"

def check_ai_detections():
    """Check recent AI detections"""
    detections_dir = Path("/opt/lengau-monitoring/data/detections")
    
    if not detections_dir.exists():
        return False, "Detections directory not found"
    
    today = datetime.now().strftime("%Y%m%d")
    detection_file = detections_dir / f"detections_{today}.jsonl"
    
    if not detection_file.exists():
        return False, "No detections today"
    
    try:
        # Count lines in detection file
        with open(detection_file, 'r') as f:
            count = sum(1 for line in f if line.strip())
        
        # Get last detection
        with open(detection_file, 'r') as f:
            lines = f.readlines()
            if lines:
                last_detection = json.loads(lines[-1])
                confidence = last_detection.get('confidence', 0) * 100
                collection = last_detection.get('collection_info', {}).get('name', 'unknown')
                return True, f"{count} detections today, latest: {confidence:.1f}% confidence ({collection})"
    except:
        pass
    
    return False, "Error reading detections"

def check_ai_alerts():
    """Check recent AI alerts"""
    alerts_dir = Path("/opt/lengau-monitoring/data/alerts")
    
    if not alerts_dir.exists():
        return False, "Alerts directory not found"
    
    today = datetime.now().strftime("%Y%m%d")
    alert_file = alerts_dir / f"alerts_{today}.jsonl"
    
    if not alert_file.exists():
        return False, "No alerts today"
    
    try:
        with open(alert_file, 'r') as f:
            count = sum(1 for line in f if line.strip())
        return True, f"{count} alerts today"
    except:
        return False, "Error reading alerts"

def check_models():
    """Check AI model files"""
    models_dir = Path("/opt/lengau-monitoring/models")
    
    if not models_dir.exists():
        return False, "Models directory not found"
    
    model_files = list(models_dir.glob("*.joblib"))
    metadata_files = list(models_dir.glob("model_metadata_*.json"))
    
    if not model_files or not metadata_files:
        return False, "No model files found"
    
    # Get latest metadata
    latest_metadata = max(metadata_files, key=lambda x: x.name)
    
    try:
        with open(latest_metadata, 'r') as f:
            metadata = json.load(f)
            features = len(metadata.get('feature_names', []))
            timestamp = metadata.get('timestamp', 'unknown')
        
        return True, f"{len(model_files)} models, {features} features, version: {timestamp}"
    except:
        return False, "Error reading model metadata"

def check_disk_space():
    """Check disk space for monitoring directories"""
    paths_to_check = [
        "/opt/lengau-monitoring",
        "/mnt/lustre/users/embele/hpc_logs"
    ]
    
    results = []
    for path in paths_to_check:
        if os.path.exists(path):
            try:
                statvfs = os.statvfs(path)
                total = statvfs.f_frsize * statvfs.f_blocks
                free = statvfs.f_frsize * statvfs.f_bavail
                used_pct = ((total - free) / total) * 100
                
                status = "🟢" if used_pct < 80 else "🟡" if used_pct < 90 else "🔴"
                results.append(f"{status} {path}: {used_pct:.1f}% used")
            except:
                results.append(f"❌ {path}: Error checking space")
        else:
            results.append(f"❌ {path}: Not found")
    
    return results

def check_system_status():
    """Comprehensive system status check"""
    print("🐆 LENGAU SYSTEM STATUS CHECK")
    print("=" * 50)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    overall_status = True
    
    # Check AI services
    print("🤖 AI SERVICES")
    print("-" * 20)
    
    detector_status = check_service_status('lengau-detector')
    dashboard_status = check_service_status('lengau-dashboard')
    
    # Debug: also check with direct systemctl call
    try:
        debug_result = subprocess.run(['systemctl', 'is-active', 'lengau-detector'], 
                                    capture_output=True, text=True, timeout=5)
        debug_status = debug_result.stdout.strip()
    except:
        debug_status = "error"
    
    print(f"{'✅' if detector_status else '❌'} Anomaly Detector: {'Running' if detector_status else 'Stopped'}")
    if not detector_status:
        print(f"    Debug: systemctl says '{debug_status}'")
    
    print(f"{'✅' if dashboard_status else '❌'} AI Dashboard: {'Running' if dashboard_status else 'Stopped'}")
    
    if not detector_status:
        overall_status = False
    
    print()
    
    # Check data collection
    print("📊 DATA COLLECTION")
    print("-" * 20)
    
    logs_ok, logs_msg = check_recent_logs()
    print(f"{'✅' if logs_ok else '❌'} Log Collections: {logs_msg}")
    
    if not logs_ok:
        overall_status = False
    
    print()
    
    # Check AI system
    print("🧠 AI DETECTION SYSTEM")
    print("-" * 25)
    
    models_ok, models_msg = check_models()
    print(f"{'✅' if models_ok else '❌'} AI Models: {models_msg}")
    
    detections_ok, detections_msg = check_ai_detections()
    print(f"{'✅' if detections_ok else '❌'} Detections: {detections_msg}")
    
    alerts_ok, alerts_msg = check_ai_alerts()
    print(f"{'✅' if alerts_ok else '❌'} Alerts: {alerts_msg}")
    
    if not models_ok:
        overall_status = False
    
    print()
    
    # Check disk space
    print("💾 DISK SPACE")
    print("-" * 15)
    disk_results = check_disk_space()
    for result in disk_results:
        print(result)
    
    print()
    
    # Overall status
    print("🎯 OVERALL STATUS")
    print("-" * 20)
    if overall_status:
        print("✅ System is operational and healthy")
        print("🚀 Lengau AI monitoring is working correctly!")
    else:
        print("❌ System issues detected")
        print("🔧 Check failed services and data collection")
    
    print()
    
    # Quick commands
    print("📋 QUICK COMMANDS")
    print("-" * 20)
    print("Status:     sudo systemctl status lengau-detector")
    print("Logs:       sudo journalctl -u lengau-detector -f")
    print("AI Status:  ./simple_ai_status.py")
    print("Full Status: ./status_lengau_ai.sh")
    
    return overall_status

if __name__ == "__main__":
    check_system_status()

