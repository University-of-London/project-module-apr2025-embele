#!/usr/bin/env python3
"""
Lengau AI-Powered Monitoring Dashboard
Advanced visualization for HPC anomaly detection
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import logging
import time
import threading
from lengau_realtime_detector import LengauRealTimeDetector

class LengauAIDashboard:
    def __init__(self, base_dir="/opt/lengau-monitoring"):
        self.base_dir = Path(base_dir)
        self.setup_logging()
        
        # Dashboard configuration
        self.config = {
            'refresh_interval': 30,  # seconds
            'max_history_display': 100,
            'alert_retention_days': 7,
            'detection_retention_days': 3
        }
        
        # Initialize detector for status monitoring
        self.detector = LengauRealTimeDetector(base_dir)
        
        # Dashboard state
        self.running = False
        self.last_update = None
        
    def setup_logging(self):
        """Setup logging for dashboard"""
        log_dir = self.base_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "ai_dashboard.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_recent_detections(self, days=3):
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
                    self.logger.error(f"Error loading detections from {detection_file}: {e}")
        
        # Sort by timestamp
        all_detections.sort(key=lambda x: x['timestamp'], reverse=True)
        return all_detections
    
    def load_recent_alerts(self, days=7):
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
                    self.logger.error(f"Error loading alerts from {alert_file}: {e}")
        
        # Sort by timestamp
        all_alerts.sort(key=lambda x: x['timestamp'], reverse=True)
        return all_alerts
    
    def calculate_dashboard_metrics(self, detections, alerts):
        """Calculate key dashboard metrics"""
        now = datetime.now()
        
        # Time windows
        last_hour = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)
        last_week = now - timedelta(days=7)
        
        # Convert timestamps for filtering
        detections_df = pd.DataFrame(detections)
        alerts_df = pd.DataFrame(alerts)
        
        # Clean up detection data - ensure numeric fields are numeric
        if not detections_df.empty:
            # Convert confidence to numeric
            if 'confidence' in detections_df.columns:
                def clean_confidence(val):
                    try:
                        if isinstance(val, str):
                            if val.endswith('%'):
                                return float(val[:-1]) / 100.0
                            return float(val)
                        return float(val)
                    except:
                        return 0.0
                detections_df['confidence'] = detections_df['confidence'].apply(clean_confidence)
            
            # Ensure is_anomaly is boolean
            if 'is_anomaly' in detections_df.columns:
                detections_df['is_anomaly'] = detections_df['is_anomaly'].astype(bool)
        
        if not detections_df.empty:
            detections_df['timestamp'] = pd.to_datetime(detections_df['timestamp'])
        if not alerts_df.empty:
            alerts_df['timestamp'] = pd.to_datetime(alerts_df['timestamp'])
        
        metrics = {
            'total_detections': len(detections),
            'total_alerts': len(alerts),
            'anomalies_last_hour': 0,
            'anomalies_last_24h': 0,
            'anomalies_last_week': 0,
            'alerts_last_hour': 0,
            'alerts_last_24h': 0,
            'alerts_last_week': 0,
            'avg_confidence_last_24h': 0.0,
            'anomaly_rate_last_24h': 0.0,
            'current_status': 'Unknown'
        }
        
        if not detections_df.empty:
            # Anomalies in different time windows
            anomalies = detections_df[detections_df['is_anomaly'] == True]
            
            metrics['anomalies_last_hour'] = len(anomalies[anomalies['timestamp'] >= last_hour])
            metrics['anomalies_last_24h'] = len(anomalies[anomalies['timestamp'] >= last_24h])
            metrics['anomalies_last_week'] = len(anomalies[anomalies['timestamp'] >= last_week])
            
            # Confidence and rates
            last_24h_detections = detections_df[detections_df['timestamp'] >= last_24h]
            if not last_24h_detections.empty:
                last_24h_anomalies = last_24h_detections[last_24h_detections['is_anomaly'] == True]
                if not last_24h_anomalies.empty and 'confidence' in last_24h_anomalies.columns:
                    # Confidence should already be cleaned up above
                    metrics['avg_confidence_last_24h'] = last_24h_anomalies['confidence'].mean()
                else:
                    metrics['avg_confidence_last_24h'] = 0.0
                try:
                    metrics['anomaly_rate_last_24h'] = len(last_24h_anomalies) / len(last_24h_detections)
                except:
                    metrics['anomaly_rate_last_24h'] = 0.0
        
        if not alerts_df.empty:
            metrics['alerts_last_hour'] = len(alerts_df[alerts_df['timestamp'] >= last_hour])
            metrics['alerts_last_24h'] = len(alerts_df[alerts_df['timestamp'] >= last_24h])
            metrics['alerts_last_week'] = len(alerts_df[alerts_df['timestamp'] >= last_week])
        
        # Determine current status
        if metrics['alerts_last_hour'] > 0:
            metrics['current_status'] = 'ALERT'
        elif metrics['anomalies_last_hour'] > 0:
            metrics['current_status'] = 'ANOMALY'
        elif metrics['anomalies_last_24h'] == 0:
            metrics['current_status'] = 'NORMAL'
        else:
            metrics['current_status'] = 'MONITORING'
        
        return metrics
    
    def generate_trend_analysis(self, detections):
        """Generate trend analysis for dashboard"""
        if not detections:
            return {}
        
        df = pd.DataFrame(detections)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Convert confidence to numeric
        def convert_confidence(conf):
            try:
                if isinstance(conf, str):
                    if conf.endswith('%'):
                        return float(conf[:-1]) / 100.0
                    else:
                        return float(conf)
                return float(conf)
            except:
                return 0.0
        
        df['confidence_numeric'] = df['confidence'].apply(convert_confidence)
        
        # Group by hour for trending
        df['hour'] = df['timestamp'].dt.floor('H')
        hourly_stats = df.groupby('hour').agg({
            'is_anomaly': ['count', 'sum'],
            'confidence_numeric': 'mean'
        }).reset_index()
        
        hourly_stats.columns = ['hour', 'total_detections', 'anomaly_count', 'avg_confidence']
        
        # Safe division for anomaly rate
        try:
            hourly_stats['anomaly_rate'] = hourly_stats['anomaly_count'] / hourly_stats['total_detections']
        except:
            hourly_stats['anomaly_rate'] = 0.0
        
        # Recent 24 hours trend
        last_24h = datetime.now() - timedelta(hours=24)
        recent_trend = hourly_stats[hourly_stats['hour'] >= last_24h]
        
        trend_analysis = {
            'hourly_anomaly_rates': recent_trend[['hour', 'anomaly_rate']].to_dict('records'),
            'hourly_confidence': recent_trend[['hour', 'avg_confidence']].to_dict('records'),
            'peak_anomaly_hour': str(recent_trend.loc[recent_trend['anomaly_rate'].idxmax(), 'hour']) if not recent_trend.empty and len(recent_trend) > 0 else None,
            'trend_direction': self.calculate_trend_direction(recent_trend['anomaly_rate'].tolist())
        }
        
        return trend_analysis
    
    def calculate_trend_direction(self, values):
        """Calculate if trend is increasing, decreasing, or stable"""
        if len(values) < 2:
            return 'stable'
        
        # Simple linear regression slope
        x = np.arange(len(values))
        y = np.array(values)
        
        if len(y) > 1:
            slope = np.polyfit(x, y, 1)[0]
            if slope > 0.01:
                return 'increasing'
            elif slope < -0.01:
                return 'decreasing'
        
        return 'stable'
    
    def generate_feature_analysis(self, detections):
        """Analyze which features are most commonly anomalous"""
        anomalous_detections = [d for d in detections if d.get('is_anomaly', False)]
        
        if not anomalous_detections:
            return {}
        
        # Analyze feature values in anomalous detections
        feature_stats = {}
        
        for detection in anomalous_detections:
            feature_values = detection.get('feature_values', {})
            for feature, value in feature_values.items():
                if feature not in feature_stats:
                    feature_stats[feature] = []
                feature_stats[feature].append(value)
        
        # Calculate statistics for each feature
        feature_analysis = {}
        for feature, values in feature_stats.items():
            if values:
                feature_analysis[feature] = {
                    'mean': np.mean(values),
                    'std': np.std(values),
                    'min': np.min(values),
                    'max': np.max(values),
                    'anomaly_frequency': len(values)
                }
        
        # Sort by anomaly frequency
        sorted_features = sorted(feature_analysis.items(), 
                               key=lambda x: x[1]['anomaly_frequency'], 
                               reverse=True)
        
        return dict(sorted_features[:10])  # Top 10 features
    
    def display_dashboard(self):
        """Display the main dashboard"""
        # Clear screen
        print("\033[2J\033[H")
        
        # Header
        print("🐆 LENGAU AI-POWERED HPC MONITORING DASHBOARD")
        print("=" * 80)
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Last Update: {self.last_update or 'Never'}")
        print()
        
        # Load data
        detections = self.load_recent_detections()
        alerts = self.load_recent_alerts()
        
        # Calculate metrics
        metrics = self.calculate_dashboard_metrics(detections, alerts)
        
        # System Status
        status_color = {
            'NORMAL': '🟢',
            'MONITORING': '🟡', 
            'ANOMALY': '🟠',
            'ALERT': '🔴',
            'Unknown': '⚪'
        }
        
        print(f"🚥 CLUSTER STATUS: {status_color.get(metrics['current_status'], '⚪')} {metrics['current_status']}")
        print()
        
        # Key Metrics
        print("📊 KEY METRICS")
        print("-" * 40)
        print(f"🔍 Total Detections: {metrics['total_detections']:,}")
        print(f"🚨 Total Alerts: {metrics['total_alerts']:,}")
        print(f"⚡ Anomalies (1h): {metrics['anomalies_last_hour']:,}")
        print(f"📈 Anomalies (24h): {metrics['anomalies_last_24h']:,}")
        print(f"📊 Anomaly Rate (24h): {metrics['anomaly_rate_last_24h']:.1%}")
        print(f"🎯 Avg Confidence (24h): {metrics['avg_confidence_last_24h']:.1%}")
        print()
        
        # Recent Alerts
        print("🚨 RECENT ALERTS")
        print("-" * 40)
        recent_alerts = alerts[:5]  # Last 5 alerts
        if recent_alerts:
            for alert in recent_alerts:
                try:
                    # Handle different timestamp formats
                    timestamp_str = alert.get('timestamp', '')
                    if 'T' in timestamp_str:
                        timestamp = pd.to_datetime(timestamp_str).strftime('%H:%M:%S')
                    else:
                        timestamp = timestamp_str[:8] if len(timestamp_str) >= 8 else timestamp_str
                    severity = alert.get('severity', 'UNKNOWN')
                    confidence = alert.get('confidence', 0)
                    # Ensure confidence is numeric
                    if isinstance(confidence, str):
                        try:
                            confidence = float(confidence) / 100.0 if confidence.endswith('%') else float(confidence)
                        except:
                            confidence = 0.0
                    elif not isinstance(confidence, (int, float)):
                        confidence = 0.0
                    title = alert.get('title', 'No title')[:50]
                    print(f"[{timestamp}] {severity} ({confidence:.1%}) - {title}")
                except:
                    print(f"Alert: {alert.get('severity', 'UNKNOWN')} - {alert.get('title', 'No title')[:50]}")
        else:
            print("✅ No recent alerts")
        print()
        
        # Trend Analysis
        trend_analysis = self.generate_trend_analysis(detections)
        print("📈 TREND ANALYSIS")
        print("-" * 40)
        if trend_analysis:
            direction = trend_analysis.get('trend_direction', 'stable')
            direction_emoji = {'increasing': '📈', 'decreasing': '📉', 'stable': '➡️'}
            print(f"📊 Anomaly Trend: {direction_emoji.get(direction, '➡️')} {direction.upper()}")
            
            peak_hour = trend_analysis.get('peak_anomaly_hour')
            if peak_hour:
                try:
                    peak_time = pd.to_datetime(peak_hour).strftime('%H:%M')
                    print(f"⚡ Peak Anomaly Time: {peak_time}")
                except:
                    print(f"⚡ Peak Anomaly Time: {str(peak_hour)[:5]}")
        else:
            print("📊 Insufficient data for trend analysis")
        print()
        
        # Feature Analysis
        feature_analysis = self.generate_feature_analysis(detections)
        print("🔍 TOP ANOMALOUS FEATURES")
        print("-" * 40)
        if feature_analysis:
            for i, (feature, stats) in enumerate(list(feature_analysis.items())[:5]):
                freq = stats['anomaly_frequency']
                mean_val = stats['mean']
                print(f"{i+1}. {feature}: {freq} occurrences (avg: {mean_val:.2f})")
        else:
            print("📊 No anomalous features detected")
        print()
        
        # Detector Status
        detector_status = self.detector.get_status()
        print("🤖 AI DETECTOR STATUS")
        print("-" * 40)
        print(f"🔧 Running: {'✅ YES' if detector_status['running'] else '❌ NO'}")
        print(f"🧠 Models Loaded: {detector_status['models_loaded']}")
        print(f"📊 Features: {detector_status['features_count']}")
        last_model_load = detector_status.get('last_model_load')
        if last_model_load:
            try:
                load_time = pd.to_datetime(last_model_load).strftime('%H:%M:%S')
                print(f"🔄 Last Model Load: {load_time}")
            except:
                print(f"🔄 Last Model Load: {str(last_model_load)[:8]}")
        print()
        
        # Footer
        print("=" * 80)
        print("🎯 Lengau HPC Cluster - Real-time AI Anomaly Detection")
        print("Press Ctrl+C to exit")
        
        self.last_update = datetime.now().strftime('%H:%M:%S')
    
    def dashboard_loop(self):
        """Main dashboard refresh loop"""
        while self.running:
            try:
                self.display_dashboard()
                time.sleep(self.config['refresh_interval'])
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Error in dashboard loop: {e}")
                time.sleep(5)
    
    def start_dashboard(self):
        """Start the dashboard"""
        self.running = True
        self.logger.info("🚀 Starting AI-powered dashboard...")
        
        try:
            self.dashboard_loop()
        except KeyboardInterrupt:
            self.logger.info("🛑 Dashboard stopped by user")
        finally:
            self.running = False
    
    def generate_dashboard_data(self):
        """Generate dashboard data for web interface"""
        detections = self.load_recent_detections()
        alerts = self.load_recent_alerts()
        metrics = self.calculate_dashboard_metrics(detections, alerts)
        trend_analysis = self.generate_trend_analysis(detections)
        feature_analysis = self.generate_feature_analysis(detections)
        detector_status = self.detector.get_status()
        
        dashboard_data = {
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics,
            'recent_alerts': alerts[:10],
            'recent_detections': [d for d in detections[:20] if d.get('is_anomaly', False)],
            'trend_analysis': trend_analysis,
            'feature_analysis': feature_analysis,
            'detector_status': detector_status,
            'config': self.config
        }
        
        # Save to dashboard data file
        dashboard_file = self.base_dir / "data" / "dashboard_data.json"
        dashboard_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(dashboard_file, 'w') as f:
                json.dump(dashboard_data, f, indent=2, default=str)
            self.logger.info(f"📊 Dashboard data saved: {dashboard_file}")
        except Exception as e:
            self.logger.error(f"Error saving dashboard data: {e}")
        
        return dashboard_data

def main():
    """Main function for dashboard"""
    print("📊 LENGAU AI DASHBOARD")
    print("======================")
    print("🎯 Advanced HPC cluster monitoring")
    print("🤖 Real-time AI anomaly detection visualization")
    print()
    
    dashboard = LengauAIDashboard()
    
    try:
        # Generate initial dashboard data
        dashboard.generate_dashboard_data()
        
        # Start interactive dashboard
        dashboard.start_dashboard()
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
