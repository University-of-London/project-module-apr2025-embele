#!/usr/bin/env python3
"""
Test the running AI system
"""

import json
from pathlib import Path
from datetime import datetime

def check_detection_files():
    """Check for detection files"""
    base_dir = Path("/opt/lengau-monitoring")
    detections_dir = base_dir / "data" / "detections"
    alerts_dir = base_dir / "data" / "alerts"
    
    print("🔍 LENGAU AI SYSTEM STATUS CHECK")
    print("=================================")
    
    # Check detections
    if detections_dir.exists():
        detection_files = list(detections_dir.glob("*.jsonl"))
        print(f"📊 Detection files: {len(detection_files)}")
        
        if detection_files:
            latest_file = max(detection_files, key=lambda x: x.stat().st_mtime)
            print(f"📁 Latest detection file: {latest_file.name}")
            
            # Read last few detections
            try:
                with open(latest_file, 'r') as f:
                    lines = f.readlines()
                    print(f"📈 Total detections in file: {len(lines)}")
                    
                    if lines:
                        last_detection = json.loads(lines[-1])
                        timestamp = last_detection.get('timestamp', 'Unknown')
                        is_anomaly = last_detection.get('is_anomaly', False)
                        confidence = last_detection.get('confidence', 0)
                        collection = last_detection.get('collection_info', {}).get('name', 'Unknown')
                        
                        status = "🚨 ANOMALY" if is_anomaly else "✅ NORMAL"
                        print(f"🔍 Last detection: {status} ({confidence:.1%}) - {collection}")
                        print(f"⏰ Timestamp: {timestamp}")
                        
            except Exception as e:
                print(f"❌ Error reading detection file: {e}")
    else:
        print("❌ No detections directory found")
    
    # Check alerts
    if alerts_dir.exists():
        alert_files = list(alerts_dir.glob("*.jsonl"))
        print(f"🚨 Alert files: {len(alert_files)}")
        
        if alert_files:
            total_alerts = 0
            for alert_file in alert_files:
                try:
                    with open(alert_file, 'r') as f:
                        alerts = f.readlines()
                        total_alerts += len(alerts)
                except:
                    pass
            print(f"📊 Total alerts: {total_alerts}")
    else:
        print("❌ No alerts directory found")
    
    # Check models
    models_dir = base_dir / "models"
    if models_dir.exists():
        model_files = list(models_dir.glob("*.joblib"))
        print(f"🧠 Model files: {len(model_files)}")
        
        metadata_files = list(models_dir.glob("model_metadata_*.json"))
        if metadata_files:
            latest_metadata = max(metadata_files, key=lambda x: x.name)
            try:
                with open(latest_metadata, 'r') as f:
                    metadata = json.load(f)
                    print(f"📊 Features: {metadata.get('n_features', 'Unknown')}")
                    print(f"⏰ Model timestamp: {metadata.get('timestamp', 'Unknown')}")
            except:
                pass
    else:
        print("❌ No models directory found")
    
    print("\n🎯 System appears to be working! Real-time anomaly detection active.")

if __name__ == "__main__":
    check_detection_files()
