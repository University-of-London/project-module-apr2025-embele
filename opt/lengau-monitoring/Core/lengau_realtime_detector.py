#!/usr/bin/env python3
"""
Lengau Real-time Anomaly Detection Engine
Production-ready anomaly detection for HPC cluster monitoring
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import logging
import joblib
import time
import threading
from collections import deque
import warnings
warnings.filterwarnings('ignore')

# Deep Learning Support
try:
    import tensorflow as tf
    TENSORFLOW_AVAILABLE = True
    print("✅ TensorFlow available for deep learning models")
except ImportError:
    TENSORFLOW_AVAILABLE = False
    print("⚠️ TensorFlow not available - deep learning models disabled")

class LengauRealTimeDetector:
    def __init__(self, base_dir="/opt/lengau-monitoring"):
        self.base_dir = Path(base_dir)
        self.setup_logging()
        
        # Detection configuration
        self.config = {
            'detection_interval': 60,  # seconds
            'alert_threshold': 0.7,    # confidence threshold for alerts
            'history_window': 100,     # number of recent detections to keep
            'model_reload_interval': 3600,  # reload models every hour
        }
        
        # Runtime state
        self.models = {}
        self.scalers = {}
        self.feature_names = []
        self.model_metadata = {}
        self.detection_history = deque(maxlen=self.config['history_window'])
        self.alert_history = deque(maxlen=50)
        self.running = False
        self.last_model_load = None
        
        # Load initial models
        self.load_latest_models()
        
    def setup_logging(self):
        """Setup logging for real-time detection"""
        log_dir = self.base_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "realtime_detection.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_latest_models(self):
        """Load the most recent trained models"""
        self.logger.info("🔧 Loading latest trained models...")
        
        models_dir = self.base_dir / "models"
        if not models_dir.exists():
            self.logger.error("No models directory found")
            return False
        
        # Find latest model metadata
        metadata_files = list(models_dir.glob("model_metadata_*.json"))
        if not metadata_files:
            self.logger.error("No model metadata found")
            return False
        
        latest_metadata_file = max(metadata_files, key=lambda x: x.name)
        
        try:
            with open(latest_metadata_file, 'r') as f:
                self.model_metadata = json.load(f)
            
            timestamp = self.model_metadata['timestamp']
            self.feature_names = self.model_metadata['feature_names']
            
            self.logger.info(f"📊 Loading models from timestamp: {timestamp}")
            
            # Load models - 5-MODEL ENSEMBLE + Deep Learning
            traditional_models = ['isolation_forest', 'random_forest', 'dbscan', 'pca']
            deep_learning_models = ['autoencoder', 'lstm']
            
            # Load traditional ML models (.joblib)
            for model_type in traditional_models:
                model_file = models_dir / f"{model_type}_{timestamp}.joblib"
                if model_file.exists():
                    self.models[model_type] = joblib.load(model_file)
                    self.logger.info(f"✅ Loaded {model_type}")
                else:
                    self.logger.warning(f"⚠️ Model not found: {model_file}")
            
            # Load deep learning models (.h5)
            if TENSORFLOW_AVAILABLE:
                # Define custom objects for TensorFlow model loading
                custom_objects = {
                    'mse': tf.keras.metrics.MeanSquaredError(),
                    'mean_squared_error': tf.keras.losses.MeanSquaredError(),
                    'adam': tf.keras.optimizers.Adam
                }
                
                for model_type in deep_learning_models:
                    model_file = models_dir / f"{model_type}_{timestamp}.h5"
                    if model_file.exists():
                        try:
                            # Load with custom objects to handle serialization issues
                            self.models[model_type] = tf.keras.models.load_model(
                                model_file, 
                                custom_objects=custom_objects,
                                compile=False  # Skip compilation to avoid custom function issues
                            )
                            self.logger.info(f"✅ Loaded {model_type} (TensorFlow)")
                        except Exception as e:
                            self.logger.warning(f"⚠️ Could not load {model_type}: {e}")
                            # Try alternative loading method
                            try:
                                self.models[model_type] = tf.keras.models.load_model(
                                    model_file, 
                                    compile=False
                                )
                                self.logger.info(f"✅ Loaded {model_type} (TensorFlow - alternative method)")
                            except Exception as e2:
                                self.logger.error(f"❌ Failed to load {model_type}: {e2}")
                    else:
                        self.logger.warning(f"⚠️ Deep learning model not found: {model_file}")
            else:
                self.logger.warning("⚠️ TensorFlow not available - skipping deep learning models")
            
            # Load scalers
            scaler_types = ['standard', 'robust']
            for scaler_type in scaler_types:
                scaler_file = models_dir / f"scaler_{scaler_type}_{timestamp}.joblib"
                if scaler_file.exists():
                    self.scalers[scaler_type] = joblib.load(scaler_file)
                    self.logger.info(f"✅ Loaded scaler_{scaler_type}")
            
            self.last_model_load = datetime.now()
            self.logger.info(f"🎯 Models loaded successfully! Features: {len(self.feature_names)}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading models: {e}")
            return False
    
    def collect_current_metrics(self):
        """Collect current system metrics for real-time detection"""
        try:
            # This would integrate with your lengau_comprehensive_log_processor
            # For now, we'll simulate getting the latest unified collection
            
            hpc_logs_dir = Path("/mnt/lustre/users/embele/hpc_logs")
            
            # Find the most recent unified collection
            unified_collections = []
            for item in hpc_logs_dir.iterdir():
                if item.is_dir() and item.name.startswith('system_logs_'):
                    unified_collections.append(item)
            
            if not unified_collections:
                self.logger.warning("No unified collections found")
                return None
            
            # Get the newest collection by modification time
            unified_collections.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            latest_collection = unified_collections[0]
            
            # Skip if we've already processed this collection recently
            collection_name = latest_collection.name
            if hasattr(self, '_last_processed_collection') and self._last_processed_collection == collection_name:
                self.logger.debug(f"⏭️ Skipping already processed collection: {collection_name}")
                return None
            
            # Check if collection is too old (more than 24 hours)
            try:
                # Handle both unified_ and system_logs_ formats
                if collection_name.startswith('unified_'):
                    collection_time_str = collection_name.replace('unified_', '')
                elif collection_name.startswith('system_logs_'):
                    collection_time_str = collection_name.replace('system_logs_', '')
                else:
                    # Try to extract timestamp from the end
                    parts = collection_name.split('_')
                    if len(parts) >= 2:
                        collection_time_str = '_'.join(parts[-2:])
                    else:
                        raise ValueError(f"Cannot parse collection name: {collection_name}")
                
                collection_time = datetime.strptime(collection_time_str, '%Y%m%d_%H%M%S')
                age_hours = (datetime.now() - collection_time).total_seconds() / 3600
                
                if age_hours > 24:
                    self.logger.warning(f"⚠️ Collection too old ({age_hours:.1f} hours): {collection_name}")
                elif age_hours > 1:
                    self.logger.info(f"📅 Processing collection from {age_hours:.1f} hours ago: {collection_name}")
                
            except Exception as e:
                self.logger.debug(f"Could not parse collection time: {e}")
            
            self._last_processed_collection = collection_name
            
            # Parse the collection (reuse logic from comprehensive processor)
            current_metrics = self.parse_current_collection(latest_collection)
            
            return current_metrics
            
        except Exception as e:
            self.logger.error(f"Error collecting current metrics: {e}")
            return None
    
    def parse_current_collection(self, collection_dir):
        """Parse current collection to extract features"""
        try:
            # Parse loadavg file (handle both formats)
            metrics = {}
            
            # Look for timestamped loadavg file first
            loadavg_files = list(collection_dir.glob("loadavg_*.txt"))
            if not loadavg_files:
                loadavg_files = list(collection_dir.glob("loadavg.txt"))
            
            if loadavg_files:
                loadavg_file = loadavg_files[0]
                with open(loadavg_file, 'r') as f:
                    loadavg_data = f.read().strip().split()
                    if len(loadavg_data) >= 3:
                        metrics.update({
                            'cpu_load_1min': float(loadavg_data[0]),
                            'cpu_load_5min': float(loadavg_data[1]),
                            'cpu_load_15min': float(loadavg_data[2]),
                            'cpu_load_trend': float(loadavg_data[0]) - float(loadavg_data[2])
                        })
            
            # Parse meminfo file (handle both formats)
            meminfo_files = list(collection_dir.glob("meminfo_*.txt"))
            if not meminfo_files:
                meminfo_files = list(collection_dir.glob("meminfo.txt"))
            
            if meminfo_files:
                meminfo_file = meminfo_files[0]
                memory_info = {}
                with open(meminfo_file, 'r') as f:
                    for line in f:
                        if ':' in line:
                            key, value = line.split(':', 1)
                            value_clean = ''.join(filter(str.isdigit, value))
                            if value_clean:
                                memory_info[key.strip()] = int(value_clean)
                
                if 'MemTotal' in memory_info:
                    total_mem = memory_info.get('MemTotal', 1)
                    used_mem = total_mem - memory_info.get('MemFree', 0)
                    metrics.update({
                        'memory_total_gb': total_mem / (1024 * 1024),
                        'memory_used_gb': used_mem / (1024 * 1024),
                        'memory_utilization_pct': (used_mem / total_mem) * 100 if total_mem > 0 else 0,
                        'memory_available_gb': memory_info.get('MemAvailable', 0) / (1024 * 1024),
                        'memory_cached_gb': memory_info.get('Cached', 0) / (1024 * 1024),
                        'memory_buffers_gb': memory_info.get('Buffers', 0) / (1024 * 1024)
                    })
            
            # Parse network file (handle both formats - net_dev or network_stats)
            network_files = list(collection_dir.glob("net_dev_*.txt"))
            if not network_files:
                network_files = list(collection_dir.glob("network_stats.txt"))
            
            if network_files:
                network_file = network_files[0]
                total_rx_bytes = 0
                total_tx_bytes = 0
                interface_count = 0
                
                with open(network_file, 'r') as f:
                    lines = f.readlines()
                    for line in lines[2:]:  # Skip headers
                        if ':' in line:
                            parts = line.split(':')
                            values = parts[1].split()
                            if len(values) >= 9:
                                total_rx_bytes += int(values[0])
                                total_tx_bytes += int(values[8])
                                interface_count += 1
                
                metrics.update({
                    'network_rx_bytes_total': total_rx_bytes,
                    'network_tx_bytes_total': total_tx_bytes,
                    'network_rx_gb_total': total_rx_bytes / (1024**3),
                    'network_tx_gb_total': total_tx_bytes / (1024**3),
                    'network_interfaces_count': interface_count,
                    'network_total_throughput_gb': (total_rx_bytes + total_tx_bytes) / (1024**3)
                })
            
            # Parse disk space file (handle both formats - df or diskspace)
            diskspace_files = list(collection_dir.glob("df_*.txt"))
            if not diskspace_files:
                diskspace_files = list(collection_dir.glob("diskspace.txt"))
            
            if diskspace_files:
                diskspace_file = diskspace_files[0]
                filesystem_count = 0
                lustre_count = 0
                local_count = 0
                
                with open(diskspace_file, 'r') as f:
                    lines = f.readlines()
                    for line in lines[1:]:  # Skip header
                        parts = line.split()
                        if len(parts) >= 6:
                            filesystem_count += 1
                            mount_point = parts[5]
                            if mount_point.startswith('/mnt/lustre'):
                                lustre_count += 1
                            elif mount_point.startswith('/'):
                                local_count += 1
                
                metrics.update({
                    'storage_total_filesystems': filesystem_count,
                    'storage_lustre_mounts': lustre_count,
                    'storage_local_mounts': local_count
                })
            
            # Add temporal features
            now = datetime.now()
            metrics.update({
                'hour_sin': np.sin(2 * np.pi * now.hour / 24),
                'hour_cos': np.cos(2 * np.pi * now.hour / 24),
                'day_sin': np.sin(2 * np.pi * now.weekday() / 7),
                'day_cos': np.cos(2 * np.pi * now.weekday() / 7)
            })
            
            # Add collection metadata
            try:
                # Handle both unified_ and system_logs_ formats for age calculation
                collection_name = collection_dir.name
                if collection_name.startswith('unified_'):
                    collection_time_str = collection_name.replace('unified_', '')
                elif collection_name.startswith('system_logs_'):
                    collection_time_str = collection_name.replace('system_logs_', '')
                else:
                    # Try to extract timestamp from the end
                    parts = collection_name.split('_')
                    collection_time_str = '_'.join(parts[-2:]) if len(parts) >= 2 else '19700101_000000'
                
                collection_time = datetime.strptime(collection_time_str, '%Y%m%d_%H%M%S')
                collection_age_minutes = (now - collection_time).total_seconds() / 60
            except:
                collection_age_minutes = 0
            
            metrics.update({
                'collection_name': collection_dir.name,
                'timestamp': now.isoformat(),
                'collection_age_minutes': collection_age_minutes
            })
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error parsing collection {collection_dir.name}: {e}")
            return None
    
    def detect_anomalies(self, current_metrics):
        """Run anomaly detection on current metrics"""
        if not self.models or not current_metrics:
            return None
        
        try:
            # Create feature vector matching training data
            feature_vector = []
            for feature_name in self.feature_names:
                if feature_name in current_metrics:
                    feature_vector.append(current_metrics[feature_name])
                else:
                    # Use default value for missing features
                    feature_vector.append(0.0)
            
            X = np.array(feature_vector).reshape(1, -1)
            
            # Handle missing/infinite values
            X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)
            
            # Scale features
            if 'standard' in self.scalers:
                X_std = self.scalers['standard'].transform(X)
            else:
                X_std = X
            
            if 'robust' in self.scalers:
                X_robust = self.scalers['robust'].transform(X)
            else:
                X_robust = X
            
            # Get predictions from each model
            predictions = {}
            scores = {}
            
            # Isolation Forest
            if 'isolation_forest' in self.models:
                if_pred = self.models['isolation_forest'].predict(X_std)
                if_score = self.models['isolation_forest'].decision_function(X_std)
                predictions['isolation_forest'] = (if_pred[0] == -1)
                scores['isolation_forest'] = float(if_score[0])
            
            # Random Forest
            if 'random_forest' in self.models:
                rf_pred = self.models['random_forest'].predict(X_std)
                rf_proba = self.models['random_forest'].predict_proba(X_std)
                predictions['random_forest'] = bool(rf_pred[0])
                scores['random_forest'] = float(rf_proba[0][1]) if len(rf_proba[0]) > 1 else 0.0
            
            # DBSCAN
            if 'dbscan' in self.models:
                try:
                    dbscan_pred = self.models['dbscan'].fit_predict(X_std)
                    predictions['dbscan'] = (dbscan_pred[0] == -1)  # -1 indicates anomaly
                    scores['dbscan'] = float(dbscan_pred[0])
                except:
                    predictions['dbscan'] = False
                    scores['dbscan'] = 0.0
            
            # PCA
            if 'pca' in self.models:
                X_pca = self.models['pca'].transform(X_std)
                X_reconstructed = self.models['pca'].inverse_transform(X_pca)
                reconstruction_error = np.mean((X_std[0] - X_reconstructed[0]) ** 2)
                predictions['pca'] = reconstruction_error > 0.1  # Threshold from training
                scores['pca'] = float(reconstruction_error)
            
            # Autoencoder (Deep Learning)
            if 'autoencoder' in self.models:
                try:
                    autoencoder_reconstructed = self.models['autoencoder'].predict(X_std, verbose=0)
                    autoencoder_error = np.mean((X_std[0] - autoencoder_reconstructed[0]) ** 2)
                    predictions['autoencoder'] = autoencoder_error > 0.05  # Threshold from training
                    scores['autoencoder'] = float(autoencoder_error)
                except:
                    predictions['autoencoder'] = False
                    scores['autoencoder'] = 0.0
            
            # LSTM (Deep Learning) - FIXED: Use correct sequence length from training
            if 'lstm' in self.models:
                try:
                    # Check model metadata for correct sequence length
                    sequence_length = self.model_metadata.get('lstm_sequence_length', 6)  # Default to 6 as per training
                    
                    # For real-time prediction, we need to either:
                    # 1. Maintain a sliding window of historical data, or
                    # 2. Repeat current features to match sequence length
                    # Option 2 is simpler for initial implementation
                    
                    # Repeat current features to create a sequence
                    X_sequence = np.repeat(X_std, sequence_length, axis=0)  # Shape: (sequence_length, features)
                    X_lstm = X_sequence.reshape(1, sequence_length, -1)  # Shape: (1, sequence_length, features)
                    
                    lstm_pred = self.models['lstm'].predict(X_lstm, verbose=0)
                    lstm_anomaly_score = float(lstm_pred[0][0])
                    predictions['lstm'] = lstm_anomaly_score > 0.5  # Threshold from training
                    scores['lstm'] = lstm_anomaly_score
                except Exception as e:
                    self.logger.debug(f"LSTM prediction error: {e}")
                    predictions['lstm'] = False
                    scores['lstm'] = 0.0
            
            # Ensemble decision
            anomaly_votes = sum(predictions.values())
            total_models = len(predictions)
            confidence = anomaly_votes / total_models if total_models > 0 else 0.0
            
            is_anomaly = confidence >= 0.5  # Majority vote
            
            detection_result = {
                'timestamp': datetime.now().isoformat(),
                'is_anomaly': is_anomaly,
                'confidence': confidence,
                'predictions': predictions,
                'scores': scores,
                'feature_values': dict(zip(self.feature_names, feature_vector)),
                'collection_info': {
                    'name': current_metrics.get('collection_name', 'unknown'),
                    'age_minutes': current_metrics.get('collection_age_minutes', 0)
                }
            }
            
            return detection_result
            
        except Exception as e:
            self.logger.error(f"Error in anomaly detection: {e}")
            return None
    
    def generate_alert(self, detection_result):
        """Generate alert for detected anomaly"""
        if not detection_result or not detection_result['is_anomaly']:
            return None
        
        confidence = detection_result['confidence']
        if confidence < self.config['alert_threshold']:
            return None
        
        # Determine alert severity
        if confidence >= 0.9:
            severity = "CRITICAL"
        elif confidence >= 0.8:
            severity = "HIGH"
        elif confidence >= 0.7:
            severity = "MEDIUM"
        else:
            severity = "LOW"
        
        # Analyze which metrics are most anomalous
        feature_values = detection_result['feature_values']
        scores = detection_result['scores']
        
        # Simple anomaly explanation (could be enhanced)
        anomalous_features = []
        for feature, value in feature_values.items():
            if 'cpu_load' in feature and value > 10:
                anomalous_features.append(f"High CPU load: {value:.2f}")
            elif 'memory_utilization' in feature and value > 95:
                anomalous_features.append(f"High memory usage: {value:.1f}%")
            elif 'network' in feature and 'gb' in feature and value > 100:
                anomalous_features.append(f"High network traffic: {value:.2f}GB")
        
        alert = {
            'alert_id': f"lengau_anomaly_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'timestamp': detection_result['timestamp'],
            'severity': severity,
            'confidence': confidence,
            'title': f"HPC Cluster Anomaly Detected (Confidence: {confidence:.1%})",
            'description': f"Anomaly detected in Lengau HPC cluster with {confidence:.1%} confidence",
            'anomalous_features': anomalous_features,
            'collection_info': detection_result['collection_info'],
            'model_predictions': detection_result['predictions'],
            'recommended_actions': self.get_recommended_actions(anomalous_features, severity)
        }
        
        return alert
    
    def get_recommended_actions(self, anomalous_features, severity):
        """Get recommended actions based on detected anomalies"""
        actions = []
        
        for feature in anomalous_features:
            if 'CPU load' in feature:
                actions.append("Check for runaway processes or excessive job submission")
            elif 'memory usage' in feature:
                actions.append("Monitor memory-intensive jobs and consider node maintenance")
            elif 'network traffic' in feature:
                actions.append("Investigate potential network bottlenecks or data transfers")
        
        if severity in ['CRITICAL', 'HIGH']:
            actions.append("Contact HPC administrators immediately")
        elif severity == 'MEDIUM':
            actions.append("Monitor situation closely for escalation")
        
        if not actions:
            actions = ["Monitor cluster state and investigate unusual activity"]
        
        return actions
    
    def save_detection_result(self, detection_result):
        """Save detection result to file"""
        if not detection_result:
            return
        
        # Save to detections directory
        detections_dir = self.base_dir / "data" / "detections"
        detections_dir.mkdir(parents=True, exist_ok=True)
        
        # Daily detection file
        date_str = datetime.now().strftime("%Y%m%d")
        detection_file = detections_dir / f"detections_{date_str}.jsonl"
        
        try:
            with open(detection_file, 'a') as f:
                f.write(json.dumps(detection_result, default=str) + '\n')
        except Exception as e:
            self.logger.error(f"Error saving detection result: {e}")
    
    def save_alert(self, alert):
        """Save alert to file and log"""
        if not alert:
            return
        
        # Log alert
        self.logger.warning(f"🚨 ALERT: {alert['title']}")
        self.logger.warning(f"   Severity: {alert['severity']}")
        self.logger.warning(f"   Confidence: {alert['confidence']:.1%}")
        
        # Save to alerts directory
        alerts_dir = self.base_dir / "data" / "alerts"
        alerts_dir.mkdir(parents=True, exist_ok=True)
        
        # Daily alert file
        date_str = datetime.now().strftime("%Y%m%d")
        alert_file = alerts_dir / f"alerts_{date_str}.jsonl"
        
        try:
            with open(alert_file, 'a') as f:
                f.write(json.dumps(alert, default=str) + '\n')
            
            # Add to alert history
            self.alert_history.append(alert)
            
        except Exception as e:
            self.logger.error(f"Error saving alert: {e}")
    
    def detection_loop(self):
        """Main detection loop"""
        self.logger.info("🚀 Starting real-time anomaly detection loop...")
        
        while self.running:
            try:
                start_time = time.time()
                
                # Check if models need reloading
                if (self.last_model_load and 
                    (datetime.now() - self.last_model_load).total_seconds() > self.config['model_reload_interval']):
                    self.logger.info("🔄 Reloading models...")
                    self.load_latest_models()
                
                # Collect current metrics
                current_metrics = self.collect_current_metrics()
                
                if current_metrics:
                    # Run anomaly detection
                    detection_result = self.detect_anomalies(current_metrics)
                    
                    if detection_result:
                        # Add to history
                        self.detection_history.append(detection_result)
                        
                        # Save detection result
                        self.save_detection_result(detection_result)
                        
                        # Generate alert if anomaly detected
                        if detection_result['is_anomaly']:
                            alert = self.generate_alert(detection_result)
                            if alert:
                                self.save_alert(alert)
                        
                        # Log detection
                        status = "ANOMALY" if detection_result['is_anomaly'] else "NORMAL"
                        confidence = detection_result['confidence']
                        collection = detection_result['collection_info']['name']
                        self.logger.info(f"🔍 Detection: {status} (confidence: {confidence:.1%}) - {collection}")
                else:
                    # No new data available
                    self.logger.debug("⏸️ No new data available for processing")
                
                # Wait for next detection cycle
                elapsed = time.time() - start_time
                sleep_time = max(0, self.config['detection_interval'] - elapsed)
                time.sleep(sleep_time)
                
            except KeyboardInterrupt:
                self.logger.info("🛑 Detection loop interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Error in detection loop: {e}")
                time.sleep(10)  # Wait before retrying
    
    def start_detection(self):
        """Start real-time detection"""
        if self.running:
            self.logger.warning("Detection already running")
            return
        
        if not self.models:
            self.logger.error("No models loaded - cannot start detection")
            return False
        
        self.running = True
        self.detection_thread = threading.Thread(target=self.detection_loop)
        self.detection_thread.daemon = True
        self.detection_thread.start()
        
        self.logger.info("✅ Real-time anomaly detection started!")
        return True
    
    def stop_detection(self):
        """Stop real-time detection"""
        self.running = False
        if hasattr(self, 'detection_thread'):
            self.detection_thread.join(timeout=5)
        self.logger.info("🛑 Real-time anomaly detection stopped!")
    
    def get_status(self):
        """Get current detection status"""
        recent_detections = list(self.detection_history)[-10:]  # Last 10 detections
        recent_alerts = list(self.alert_history)[-5:]  # Last 5 alerts
        
        status = {
            'running': self.running,
            'models_loaded': len(self.models),
            'features_count': len(self.feature_names),
            'last_model_load': self.last_model_load.isoformat() if self.last_model_load else None,
            'detection_history_size': len(self.detection_history),
            'alert_history_size': len(self.alert_history),
            'recent_detections': recent_detections,
            'recent_alerts': recent_alerts,
            'config': self.config
        }
        
        return status

def main():
    """Main function for real-time detection"""
    print("🔍 LENGAU REAL-TIME ANOMALY DETECTOR")
    print("===================================")
    print("🎯 Production HPC cluster anomaly detection")
    print("⚡ Real-time monitoring of 1,368 compute nodes")
    print()
    
    detector = LengauRealTimeDetector()
    
    try:
        # Start detection
        if detector.start_detection():
            print("✅ Real-time detection started!")
            print("🔍 Monitoring for anomalies... (Press Ctrl+C to stop)")
            print()
            
            # Keep running until interrupted
            while detector.running:
                time.sleep(1)
        else:
            print("❌ Failed to start detection")
            return 1
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping detection...")
        detector.stop_detection()
        print("✅ Detection stopped successfully!")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
