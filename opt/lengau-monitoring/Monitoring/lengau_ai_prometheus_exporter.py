#!/usr/bin/env python3
"""
Lengau AI Anomaly Detection Prometheus Exporter
Exports AI detection metrics for Prometheus/Grafana monitoring
"""

import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import socket

class LengauAIPrometheusExporter:
    def __init__(self, base_dir="/opt/lengau-monitoring", port=8090):
        self.base_dir = Path(base_dir)
        self.port = port
        self.setup_logging()
        
        # Metrics cache
        self.metrics_cache = {}
        self.last_update = None
        self.cache_ttl = 30  # seconds
        
    def setup_logging(self):
        """Setup logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def load_recent_detections(self, days=1):
        """Load recent detection results"""
        detections_dir = self.base_dir / "data" / "detections"
        if not detections_dir.exists():
            return []
        
        all_detections = []
        
        # Load detections from last N days
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y%m%d")
            detection_file = detections_dir / f"detections_{date_str}.jsonl"
            
            if detection_file.exists():
                try:
                    with open(detection_file, 'r') as f:
                        for line in f:
                            if line.strip():
                                detection = json.loads(line)
                                all_detections.append(detection)
                except Exception as e:
                    self.logger.error(f"Error loading detections: {e}")
        
        return all_detections
    
    def load_recent_alerts(self, days=1):
        """Load recent alerts"""
        alerts_dir = self.base_dir / "data" / "alerts"
        if not alerts_dir.exists():
            return []
        
        all_alerts = []
        
        # Load alerts from last N days
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y%m%d")
            alert_file = alerts_dir / f"alerts_{date_str}.jsonl"
            
            if alert_file.exists():
                try:
                    with open(alert_file, 'r') as f:
                        for line in f:
                            if line.strip():
                                alert = json.loads(line)
                                all_alerts.append(alert)
                except Exception as e:
                    self.logger.error(f"Error loading alerts: {e}")
        
        return all_alerts
    
    def get_model_status(self):
        """Get AI model status"""
        models_dir = self.base_dir / "models"
        if not models_dir.exists():
            return {"models_count": 0, "latest_timestamp": None}
        
        # Find latest model files
        model_files = list(models_dir.glob("*.joblib"))
        metadata_files = list(models_dir.glob("model_metadata_*.json"))
        
        latest_timestamp = None
        if metadata_files:
            # Get latest timestamp from metadata files
            timestamps = []
            for meta_file in metadata_files:
                try:
                    timestamp = meta_file.stem.split('_')[-1]
                    timestamps.append(timestamp)
                except:
                    continue
            if timestamps:
                latest_timestamp = max(timestamps)
        
        return {
            "models_count": len(model_files),
            "latest_timestamp": latest_timestamp
        }
    
    def convert_confidence(self, confidence):
        """Convert confidence to numeric value"""
        try:
            if isinstance(confidence, str):
                if confidence.endswith('%'):
                    return float(confidence[:-1]) / 100.0
                return float(confidence)
            return float(confidence)
        except:
            return 0.0
    
    def calculate_metrics(self):
        """Calculate AI metrics"""
        now = datetime.now()
        
        # Time windows
        last_hour = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)
        
        # Load data
        detections = self.load_recent_detections()
        alerts = self.load_recent_alerts()
        model_status = self.get_model_status()
        
        # Calculate metrics
        metrics = {
            "lengau_ai_detections_total": len(detections),
            "lengau_ai_alerts_total": len(alerts),
            "lengau_ai_models_count": model_status["models_count"],
            "lengau_ai_anomalies_total": 0,
            "lengau_ai_anomalies_last_hour": 0,
            "lengau_ai_anomalies_last_24h": 0,
            "lengau_ai_avg_confidence": 0.0,
            "lengau_ai_max_confidence": 0.0,
            "lengau_ai_min_confidence": 0.0,
            "lengau_ai_detector_status": 0,  # 0 = unknown, 1 = running
            "lengau_ai_anomaly_rate": 0.0,
        }
        
        if detections:
            # Process detections
            anomalies = [d for d in detections if d.get('is_anomaly', False)]
            metrics["lengau_ai_anomalies_total"] = len(anomalies)
            
            # Time-based anomaly counts
            for detection in detections:
                try:
                    det_time = datetime.fromisoformat(detection['timestamp'].replace('Z', '+00:00'))
                    if det_time >= last_hour and detection.get('is_anomaly', False):
                        metrics["lengau_ai_anomalies_last_hour"] += 1
                    if det_time >= last_24h and detection.get('is_anomaly', False):
                        metrics["lengau_ai_anomalies_last_24h"] += 1
                except:
                    continue
            
            # Confidence metrics
            if anomalies:
                confidences = [self.convert_confidence(d.get('confidence', 0)) for d in anomalies]
                confidences = [c for c in confidences if c > 0]  # Filter out invalid values
                
                if confidences:
                    metrics["lengau_ai_avg_confidence"] = sum(confidences) / len(confidences)
                    metrics["lengau_ai_max_confidence"] = max(confidences)
                    metrics["lengau_ai_min_confidence"] = min(confidences)
            
            # Anomaly rate
            if len(detections) > 0:
                metrics["lengau_ai_anomaly_rate"] = len(anomalies) / len(detections)
        
        # Check if detector is running (check if recent detections exist)
        if detections:
            try:
                latest_detection = max(detections, key=lambda x: x['timestamp'])
                latest_time = datetime.fromisoformat(latest_detection['timestamp'].replace('Z', '+00:00'))
                if (now - latest_time).total_seconds() < 300:  # Last 5 minutes
                    metrics["lengau_ai_detector_status"] = 1
            except:
                pass
        
        return metrics
    
    def generate_prometheus_metrics(self):
        """Generate Prometheus metrics format"""
        # Check cache
        if (self.last_update and 
            (datetime.now() - self.last_update).total_seconds() < self.cache_ttl):
            return self.metrics_cache.get('prometheus_text', '')
        
        # Calculate fresh metrics
        metrics = self.calculate_metrics()
        
        # Generate Prometheus format
        prometheus_lines = []
        
        # Add help and type information
        prometheus_lines.extend([
            "# HELP lengau_ai_detections_total Total number of AI detections",
            "# TYPE lengau_ai_detections_total counter",
            f"lengau_ai_detections_total {metrics['lengau_ai_detections_total']}",
            "",
            "# HELP lengau_ai_alerts_total Total number of AI alerts",
            "# TYPE lengau_ai_alerts_total counter", 
            f"lengau_ai_alerts_total {metrics['lengau_ai_alerts_total']}",
            "",
            "# HELP lengau_ai_models_count Number of trained AI models",
            "# TYPE lengau_ai_models_count gauge",
            f"lengau_ai_models_count {metrics['lengau_ai_models_count']}",
            "",
            "# HELP lengau_ai_anomalies_total Total number of anomalies detected",
            "# TYPE lengau_ai_anomalies_total counter",
            f"lengau_ai_anomalies_total {metrics['lengau_ai_anomalies_total']}",
            "",
            "# HELP lengau_ai_anomalies_last_hour Anomalies detected in the last hour",
            "# TYPE lengau_ai_anomalies_last_hour gauge",
            f"lengau_ai_anomalies_last_hour {metrics['lengau_ai_anomalies_last_hour']}",
            "",
            "# HELP lengau_ai_anomalies_last_24h Anomalies detected in the last 24 hours",
            "# TYPE lengau_ai_anomalies_last_24h gauge",
            f"lengau_ai_anomalies_last_24h {metrics['lengau_ai_anomalies_last_24h']}",
            "",
            "# HELP lengau_ai_avg_confidence Average confidence of anomaly detections",
            "# TYPE lengau_ai_avg_confidence gauge",
            f"lengau_ai_avg_confidence {metrics['lengau_ai_avg_confidence']:.4f}",
            "",
            "# HELP lengau_ai_max_confidence Maximum confidence of anomaly detections",
            "# TYPE lengau_ai_max_confidence gauge",
            f"lengau_ai_max_confidence {metrics['lengau_ai_max_confidence']:.4f}",
            "",
            "# HELP lengau_ai_min_confidence Minimum confidence of anomaly detections",
            "# TYPE lengau_ai_min_confidence gauge",
            f"lengau_ai_min_confidence {metrics['lengau_ai_min_confidence']:.4f}",
            "",
            "# HELP lengau_ai_detector_status AI detector service status (1=running, 0=not running)",
            "# TYPE lengau_ai_detector_status gauge",
            f"lengau_ai_detector_status {metrics['lengau_ai_detector_status']}",
            "",
            "# HELP lengau_ai_anomaly_rate Rate of anomaly detection (anomalies/total detections)",
            "# TYPE lengau_ai_anomaly_rate gauge",
            f"lengau_ai_anomaly_rate {metrics['lengau_ai_anomaly_rate']:.4f}",
            ""
        ])
        
        # Add feature-specific metrics
        detections = self.load_recent_detections()
        if detections:
            anomalous_detections = [d for d in detections if d.get('is_anomaly', False)]
            
            # Track top anomalous features
            feature_counts = {}
            for detection in anomalous_detections:
                feature_values = detection.get('feature_values', {})
                for feature in feature_values.keys():
                    feature_counts[feature] = feature_counts.get(feature, 0) + 1
            
            # Add feature metrics
            prometheus_lines.extend([
                "# HELP lengau_ai_feature_anomaly_count Number of times each feature was anomalous",
                "# TYPE lengau_ai_feature_anomaly_count counter"
            ])
            
            for feature, count in feature_counts.items():
                # Clean feature name for Prometheus
                clean_feature = feature.replace('-', '_').replace('.', '_')
                prometheus_lines.append(f'lengau_ai_feature_anomaly_count{{feature="{clean_feature}"}} {count}')
            
            prometheus_lines.append("")
        
        prometheus_text = '\n'.join(prometheus_lines)
        
        # Update cache
        self.metrics_cache['prometheus_text'] = prometheus_text
        self.metrics_cache['metrics'] = metrics
        self.last_update = datetime.now()
        
        return prometheus_text

class PrometheusHandler(BaseHTTPRequestHandler):
    def __init__(self, exporter, *args, **kwargs):
        self.exporter = exporter
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/metrics':
            try:
                metrics_text = self.exporter.generate_prometheus_metrics()
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(metrics_text.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Error: {str(e)}".encode('utf-8'))
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Not Found")
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

def make_handler(exporter):
    return lambda *args, **kwargs: PrometheusHandler(exporter, *args, **kwargs)

def main():
    print("🤖 LENGAU AI PROMETHEUS EXPORTER")
    print("=" * 50)
    print("🎯 Exporting AI anomaly detection metrics")
    print("📊 Prometheus endpoint: http://localhost:8090/metrics")
    print("💓 Health check: http://localhost:8090/health")
    print()
    
    # Initialize exporter
    exporter = LengauAIPrometheusExporter()
    
    # Create HTTP server
    handler = make_handler(exporter)
    httpd = HTTPServer(('', exporter.port), handler)
    
    print(f"🚀 Starting Prometheus exporter on port {exporter.port}")
    print("Press Ctrl+C to stop")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Stopping exporter...")
        httpd.shutdown()
        print("✅ Exporter stopped!")

if __name__ == "__main__":
    main()
