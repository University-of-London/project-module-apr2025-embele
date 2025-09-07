#!/usr/bin/env python3
"""
Lengau Optimized Storage Prometheus Exporter
High-performance storage metrics for HPC environments
"""

import os
import subprocess
import time
import glob
import re
from collections import defaultdict
from prometheus_client import start_http_server, Gauge, Counter, Histogram, Info
import logging
import signal
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LengauStorageExporter:
    def __init__(self, port=8082, collection_interval=30, timeout=15):
        self.port = port
        self.collection_interval = collection_interval
        self.timeout = timeout
        self.running = True
        
        # Storage Metrics
        self.disk_total_bytes = Gauge('disk_total_bytes', 'Total disk space', ['device', 'mountpoint', 'fstype'])
        self.disk_used_bytes = Gauge('disk_used_bytes', 'Used disk space', ['device', 'mountpoint', 'fstype'])
        self.disk_available_bytes = Gauge('disk_available_bytes', 'Available disk space', ['device', 'mountpoint', 'fstype'])
        self.disk_usage_percent = Gauge('disk_usage_percent', 'Disk usage percentage', ['device', 'mountpoint', 'fstype'])
        
        # Lustre Metrics
        self.lustre_total_bytes = Gauge('lustre_total_bytes', 'Total Lustre space', ['filesystem'])
        self.lustre_used_bytes = Gauge('lustre_used_bytes', 'Used Lustre space', ['filesystem'])
        self.lustre_available_bytes = Gauge('lustre_available_bytes', 'Available Lustre space', ['filesystem'])
        self.lustre_usage_percent = Gauge('lustre_usage_percent', 'Lustre usage percentage', ['filesystem'])
        self.lustre_inodes_total = Gauge('lustre_inodes_total', 'Total Lustre inodes', ['filesystem'])
        self.lustre_inodes_used = Gauge('lustre_inodes_used', 'Used Lustre inodes', ['filesystem'])
        self.lustre_inodes_percent = Gauge('lustre_inodes_usage_percent', 'Lustre inode usage percentage', ['filesystem'])
        
        # Lustre I/O Metrics
        self.lustre_read_bytes = Counter('lustre_read_bytes_total', 'Lustre bytes read', ['filesystem', 'client'])
        self.lustre_write_bytes = Counter('lustre_write_bytes_total', 'Lustre bytes written', ['filesystem', 'client'])
        self.lustre_read_ops = Counter('lustre_read_ops_total', 'Lustre read operations', ['filesystem', 'client'])
        self.lustre_write_ops = Counter('lustre_write_ops_total', 'Lustre write operations', ['filesystem', 'client'])
        self.lustre_open_ops = Counter('lustre_open_ops_total', 'Lustre open operations', ['filesystem', 'client'])
        
        # Storage I/O Metrics
        self.storage_read_ios = Counter('storage_read_ios_total', 'Storage read I/Os', ['device'])
        self.storage_write_ios = Counter('storage_write_ios_total', 'Storage write I/Os', ['device'])
        self.storage_read_bytes_total = Counter('storage_read_bytes_total', 'Storage bytes read', ['device'])
        self.storage_write_bytes_total = Counter('storage_write_bytes_total', 'Storage bytes written', ['device'])
        self.storage_io_time_ms = Counter('storage_io_time_ms_total', 'Storage I/O time', ['device'])
        self.storage_queue_depth = Gauge('storage_queue_depth', 'Storage queue depth', ['device'])
        
        # Storage Health Metrics
        self.storage_device_errors = Counter('storage_device_errors_total', 'Storage device errors', ['device', 'error_type'])
        self.lustre_health = Gauge('lustre_health_status', 'Lustre health status', ['filesystem', 'component'])
        self.storage_temperature = Gauge('storage_temperature_celsius', 'Storage device temperature', ['device'])
        
        # Performance Metrics
        self.storage_collection_duration = Histogram('storage_collection_duration_seconds', 'Time spent collecting storage metrics', ['component'])
        self.storage_collection_success = Gauge('storage_collection_success', 'Storage collection success flag')
        self.storage_last_update = Gauge('storage_last_update_timestamp', 'Last successful update timestamp')
        
        # System Info
        self.storage_info = Info('storage_system', 'Storage system information')
        
        # Cache
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 20
        
        # Device filters for performance
        self.monitored_devices = {'sd', 'nvme', 'vd', 'hd'}
        self.monitored_filesystems = {'/', '/boot', '/tmp', '/var', '/home', '/opt', '/mnt'}
        
    def run_command(self, cmd, timeout=None):
        """Execute command with timeout"""
        if timeout is None:
            timeout = self.timeout
            
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.warning(f"⏰ Command timed out: {' '.join(cmd)}")
            return 1, "", "Command timed out"
        except Exception as e:
            logger.error(f"❌ Command execution failed: {e}")
            return 1, "", str(e)
    
    def get_cached_data(self, key, fetch_func, *args):
        """Get cached data or fetch new"""
        current_time = time.time()
        
        if (key in self._cache and 
            key in self._cache_time and
            current_time - self._cache_time[key] < self._cache_ttl):
            return self._cache[key]
        
        data = fetch_func(*args)
        self._cache[key] = data
        self._cache_time[key] = current_time
        return data
    
    def collect_filesystem_metrics(self):
        """Collect general filesystem metrics"""
        start_time = time.time()
        
        try:
            returncode, stdout, stderr = self.run_command(['df', '-B1', '-T'])
            
            if returncode != 0:
                logger.warning(f"⚠️ df command failed: {stderr}")
                return
            
            for line in stdout.strip().split('\n')[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 7:
                    device = parts[0]
                    fstype = parts[1]
                    total_bytes = int(parts[2])
                    used_bytes = int(parts[3])
                    available_bytes = int(parts[4])
                    mountpoint = parts[6]
                    
                    # Filter monitored filesystems for performance
                    if not any(mountpoint.startswith(fs) for fs in self.monitored_filesystems):
                        if not mountpoint.startswith('/mnt/lustre'):
                            continue
                    
                    usage_percent = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0
                    
                    self.disk_total_bytes.labels(device=device, mountpoint=mountpoint, fstype=fstype).set(total_bytes)
                    self.disk_used_bytes.labels(device=device, mountpoint=mountpoint, fstype=fstype).set(used_bytes)
                    self.disk_available_bytes.labels(device=device, mountpoint=mountpoint, fstype=fstype).set(available_bytes)
                    self.disk_usage_percent.labels(device=device, mountpoint=mountpoint, fstype=fstype).set(usage_percent)
            
            self.storage_collection_duration.labels(component='filesystem').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting filesystem metrics: {e}")
    
    def collect_lustre_metrics(self):
        """Collect Lustre filesystem metrics"""
        start_time = time.time()
        
        try:
            # Check if Lustre is available
            if not os.path.exists('/proc/fs/lustre'):
                logger.debug("📁 Lustre not available")
                return
            
            # Collect Lustre space usage
            returncode, stdout, stderr = self.run_command(['lfs', 'df', '-h'], timeout=10)
            
            if returncode == 0:
                self._parse_lfs_df_output(stdout)
            else:
                logger.warning(f"⚠️ lfs df failed: {stderr}")
            
            # Collect Lustre client statistics
            self._collect_lustre_client_stats()
            
            # Collect Lustre health information
            self._collect_lustre_health()
            
            self.storage_collection_duration.labels(component='lustre').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting Lustre metrics: {e}")
    
    def _parse_lfs_df_output(self, output):
        """Parse lfs df output"""
        lines = output.strip().split('\n')
        for line in lines[1:]:  # Skip header
            if 'filesystem' in line.lower():
                continue
                
            parts = line.split()
            if len(parts) >= 6:
                filesystem = parts[0]
                total_str = parts[1]
                used_str = parts[2]
                available_str = parts[3]
                use_percent_str = parts[4]
                
                # Convert to bytes
                total_bytes = self._parse_size_string(total_str)
                used_bytes = self._parse_size_string(used_str)
                available_bytes = self._parse_size_string(available_str)
                
                if total_bytes and used_bytes and available_bytes:
                    usage_percent = float(use_percent_str.rstrip('%')) if use_percent_str.endswith('%') else 0
                    
                    self.lustre_total_bytes.labels(filesystem=filesystem).set(total_bytes)
                    self.lustre_used_bytes.labels(filesystem=filesystem).set(used_bytes)
                    self.lustre_available_bytes.labels(filesystem=filesystem).set(available_bytes)
                    self.lustre_usage_percent.labels(filesystem=filesystem).set(usage_percent)
    
    def _collect_lustre_client_stats(self):
        """Collect Lustre client I/O statistics"""
        try:
            llite_dirs = glob.glob('/proc/fs/lustre/llite/*')[:5]  # Limit for performance
            
            for llite_dir in llite_dirs:
                if not os.path.isdir(llite_dir):
                    continue
                
                filesystem = os.path.basename(llite_dir)
                stats_file = os.path.join(llite_dir, 'stats')
                
                if os.path.exists(stats_file):
                    with open(stats_file, 'r') as f:
                        for line in f:
                            self._parse_lustre_stat_line(line, filesystem)
                            
                # Collect OSC statistics
                osc_dirs = glob.glob(f'/proc/fs/lustre/osc/*{filesystem}*')
                for osc_dir in osc_dirs:
                    client_name = os.path.basename(osc_dir)
                    osc_stats_file = os.path.join(osc_dir, 'stats')
                    
                    if os.path.exists(osc_stats_file):
                        with open(osc_stats_file, 'r') as f:
                            for line in f:
                                self._parse_lustre_osc_stat_line(line, filesystem, client_name)
                                
        except Exception as e:
            logger.error(f"❌ Error collecting Lustre client stats: {e}")
    
    def _parse_lustre_stat_line(self, line, filesystem):
        """Parse Lustre statistics line"""
        try:
            if 'read_bytes' in line:
                parts = line.split()
                if len(parts) >= 7:
                    read_bytes = int(parts[6])
                    self.lustre_read_bytes.labels(filesystem=filesystem, client='local')._value._value = read_bytes
            elif 'write_bytes' in line:
                parts = line.split()
                if len(parts) >= 7:
                    write_bytes = int(parts[6])
                    self.lustre_write_bytes.labels(filesystem=filesystem, client='local')._value._value = write_bytes
            elif line.strip().startswith('read') and 'samples' in line:
                parts = line.split()
                if len(parts) >= 2:
                    read_ops = int(parts[1])
                    self.lustre_read_ops.labels(filesystem=filesystem, client='local')._value._value = read_ops
            elif line.strip().startswith('write') and 'samples' in line:
                parts = line.split()
                if len(parts) >= 2:
                    write_ops = int(parts[1])
                    self.lustre_write_ops.labels(filesystem=filesystem, client='local')._value._value = write_ops
            elif line.strip().startswith('open') and 'samples' in line:
                parts = line.split()
                if len(parts) >= 2:
                    open_ops = int(parts[1])
                    self.lustre_open_ops.labels(filesystem=filesystem, client='local')._value._value = open_ops
        except:
            pass
    
    def _parse_lustre_osc_stat_line(self, line, filesystem, client):
        """Parse Lustre OSC statistics line"""
        try:
            if 'read_bytes' in line:
                parts = line.split()
                if len(parts) >= 7:
                    read_bytes = int(parts[6])
                    self.lustre_read_bytes.labels(filesystem=filesystem, client=client)._value._value = read_bytes
            elif 'write_bytes' in line:
                parts = line.split()
                if len(parts) >= 7:
                    write_bytes = int(parts[6])
                    self.lustre_write_bytes.labels(filesystem=filesystem, client=client)._value._value = write_bytes
        except:
            pass
    
    def _collect_lustre_health(self):
        """Collect Lustre health information"""
        try:
            health_files = glob.glob('/proc/fs/lustre/*/health_check')
            for health_file in health_files:
                component = os.path.basename(os.path.dirname(health_file))
                
                try:
                    with open(health_file, 'r') as f:
                        health_status = f.read().strip()
                        health_value = 1 if health_status == 'healthy' else 0
                        self.lustre_health.labels(filesystem='lustre', component=component).set(health_value)
                except:
                    self.lustre_health.labels(filesystem='lustre', component=component).set(0)
                    
        except Exception as e:
            logger.debug(f"Error collecting Lustre health: {e}")
    
    def collect_storage_io_metrics(self):
        """Collect storage I/O metrics from /proc/diskstats"""
        start_time = time.time()
        
        try:
            with open('/proc/diskstats', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 14:
                        device = parts[2]
                        
                        # Filter devices for performance
                        if not any(device.startswith(prefix) for prefix in self.monitored_devices):
                            continue
                        
                        # Skip partitions (basic check)
                        if device[-1].isdigit() and len(device) > 3:
                            continue
                        
                        read_ios = int(parts[3])
                        read_sectors = int(parts[5])
                        write_ios = int(parts[7])
                        write_sectors = int(parts[9])
                        io_time_ms = int(parts[12])
                        weighted_io_time = int(parts[13]) if len(parts) > 13 else 0
                        
                        # Convert sectors to bytes (512 bytes per sector)
                        read_bytes = read_sectors * 512
                        write_bytes = write_sectors * 512
                        
                        self.storage_read_ios.labels(device=device)._value._value = read_ios
                        self.storage_write_ios.labels(device=device)._value._value = write_ios
                        self.storage_read_bytes_total.labels(device=device)._value._value = read_bytes
                        self.storage_write_bytes_total.labels(device=device)._value._value = write_bytes
                        self.storage_io_time_ms.labels(device=device)._value._value = io_time_ms
                        
                        # Calculate queue depth approximation
                        queue_depth = weighted_io_time / 1000 if io_time_ms > 0 else 0
                        self.storage_queue_depth.labels(device=device).set(queue_depth)
                        
            self.storage_collection_duration.labels(component='iostats').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting storage I/O metrics: {e}")
    
    def collect_storage_health_metrics(self):
        """Collect storage health and temperature metrics"""
        start_time = time.time()
        
        try:
            # Collect SMART data if available
            returncode, stdout, stderr = self.run_command(['smartctl', '--scan'], timeout=5)
            
            if returncode == 0:
                for line in stdout.strip().split('\n'):
                    if line.startswith('/dev/'):
                        device_path = line.split()[0]
                        device_name = os.path.basename(device_path)
                        
                        if any(device_name.startswith(prefix) for prefix in self.monitored_devices):
                            self._collect_smart_data(device_path, device_name)
                            
            self.storage_collection_duration.labels(component='health').observe(time.time() - start_time)
            
        except Exception as e:
            logger.debug(f"SMART data collection error: {e}")
    
    def _collect_smart_data(self, device_path, device_name):
        """Collect SMART data for a device"""
        try:
            returncode, stdout, stderr = self.run_command(['smartctl', '-A', device_path], timeout=5)
            
            if returncode in [0, 4]:  # 0 = OK, 4 = Some SMART errors but readable
                for line in stdout.split('\n'):
                    # Temperature
                    if 'Temperature_Celsius' in line or 'Airflow_Temperature_Cel' in line:
                        parts = line.split()
                        if len(parts) >= 10:
                            try:
                                temp = float(parts[9])
                                self.storage_temperature.labels(device=device_name).set(temp)
                            except:
                                pass
                    
                    # Error counts
                    elif 'Reallocated_Sector_Ct' in line:
                        parts = line.split()
                        if len(parts) >= 10:
                            try:
                                errors = int(parts[9])
                                self.storage_device_errors.labels(device=device_name, error_type='reallocated_sectors')._value._value = errors
                            except:
                                pass
                    elif 'Current_Pending_Sector' in line:
                        parts = line.split()
                        if len(parts) >= 10:
                            try:
                                errors = int(parts[9])
                                self.storage_device_errors.labels(device=device_name, error_type='pending_sectors')._value._value = errors
                            except:
                                pass
                                
        except Exception as e:
            logger.debug(f"SMART data collection failed for {device_name}: {e}")
    
    def _parse_size_string(self, size_str):
        """Parse size string like '1.2T' to bytes"""
        try:
            size_str = size_str.strip()
            if size_str.endswith('T'):
                return int(float(size_str[:-1]) * 1024**4)
            elif size_str.endswith('G'):
                return int(float(size_str[:-1]) * 1024**3)
            elif size_str.endswith('M'):
                return int(float(size_str[:-1]) * 1024**2)
            elif size_str.endswith('K'):
                return int(float(size_str[:-1]) * 1024)
            else:
                return int(size_str)
        except:
            return 0
    
    def collect_metrics(self):
        """Main metrics collection function"""
        start_time = time.time()
        
        try:
            # Collect cached filesystem metrics
            self.get_cached_data('filesystem', self.collect_filesystem_metrics)
            
            # Collect Lustre metrics
            self.collect_lustre_metrics()
            
            # Collect I/O metrics
            self.collect_storage_io_metrics()
            
            # Collect health metrics (less frequently)
            if int(time.time()) % 120 == 0:  # Every 2 minutes
                self.collect_storage_health_metrics()
            
            # Update system info
            self.storage_info.info({
                'collection_time': datetime.now().isoformat(),
                'lustre_available': str(os.path.exists('/proc/fs/lustre')),
                'smartctl_available': str(self._check_command_available('smartctl'))
            })
            
            # Update success metrics
            self.storage_collection_success.set(1)
            self.storage_last_update.set(time.time())
            
            collection_time = time.time() - start_time
            logger.info(f"✅ Storage metrics collected in {collection_time:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Failed to collect storage metrics: {e}")
            self.storage_collection_success.set(0)
    
    def _check_command_available(self, command):
        """Check if command is available"""
        try:
            subprocess.run([command, '--version'], capture_output=True, timeout=2)
            return True
        except:
            return False
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("🛑 Received shutdown signal")
        self.running = False
    
    def run(self):
        """Main run loop"""
        logger.info(f"🚀 Starting Lengau Storage Exporter on port {self.port}")
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # Start HTTP server
        start_http_server(self.port)
        logger.info(f"📊 Storage metrics available at http://localhost:{self.port}/metrics")
        
        # Main collection loop
        while self.running:
            try:
                self.collect_metrics()
                time.sleep(self.collection_interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                time.sleep(self.collection_interval)
        
        logger.info("👋 Storage Exporter stopped")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Lengau Storage Prometheus Exporter')
    parser.add_argument('--port', type=int, default=8082, help='Port to serve metrics on')
    parser.add_argument('--interval', type=int, default=30, help='Collection interval in seconds')
    parser.add_argument('--timeout', type=int, default=15, help='Command timeout in seconds')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    exporter = LengauStorageExporter(
        port=args.port,
        collection_interval=args.interval,
        timeout=args.timeout
    )
    
    try:
        exporter.run()
    except KeyboardInterrupt:
        logger.info("👋 Exporter stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
