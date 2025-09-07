#!/usr/bin/env python3
"""
Lengau Optimized PBS Prometheus Exporter
Consolidated, high-performance PBS scheduler metrics exporter
"""

import subprocess
import time
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from prometheus_client import start_http_server, Gauge, Counter, Info, Histogram
import logging
import threading
import signal
import sys
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LengauPBSExporter:
    def __init__(self, port=8085, collection_interval=30, timeout=15):
        self.port = port
        self.collection_interval = collection_interval
        self.timeout = timeout
        self.running = True
        
        # PBS Metrics
        self.pbs_jobs_total = Gauge('pbs_jobs_total', 'Total PBS jobs')
        self.pbs_jobs_running = Gauge('pbs_jobs_running', 'Running PBS jobs')
        self.pbs_jobs_queued = Gauge('pbs_jobs_queued', 'Queued PBS jobs')
        self.pbs_jobs_held = Gauge('pbs_jobs_held', 'Held PBS jobs')
        self.pbs_jobs_completed = Counter('pbs_jobs_completed_total', 'Completed PBS jobs')
        
        # Job details by queue and user
        self.pbs_queue_jobs = Gauge('pbs_queue_jobs', 'Jobs by queue', ['queue', 'state'])
        self.pbs_user_jobs = Gauge('pbs_user_jobs', 'Jobs by user', ['user', 'state'])
        self.pbs_job_walltime = Histogram('pbs_job_walltime_seconds', 'Job walltime distribution', ['queue'])
        
        # Node Metrics
        self.pbs_nodes_total = Gauge('pbs_nodes_total', 'Total PBS nodes')
        self.pbs_nodes_free = Gauge('pbs_nodes_free', 'Free PBS nodes')
        self.pbs_nodes_busy = Gauge('pbs_nodes_busy', 'Busy PBS nodes')
        self.pbs_nodes_down = Gauge('pbs_nodes_down', 'Down PBS nodes')
        self.pbs_nodes_offline = Gauge('pbs_nodes_offline', 'Offline PBS nodes')
        self.pbs_node_state = Gauge('pbs_node_state', 'Node state by name', ['node', 'state'])
        
        # Resource Metrics
        self.pbs_processors_total = Gauge('pbs_processors_total', 'Total processors')
        self.pbs_processors_used = Gauge('pbs_processors_used', 'Used processors')
        self.pbs_processors_available = Gauge('pbs_processors_available', 'Available processors')
        self.pbs_memory_total_gb = Gauge('pbs_memory_total_gb', 'Total memory in GB')
        self.pbs_memory_used_gb = Gauge('pbs_memory_used_gb', 'Used memory in GB')
        
        # Queue Metrics
        self.pbs_queue_enabled = Gauge('pbs_queue_enabled', 'Queue enabled status', ['queue'])
        self.pbs_queue_started = Gauge('pbs_queue_started', 'Queue started status', ['queue'])
        self.pbs_queue_max_running = Gauge('pbs_queue_max_running', 'Max running jobs in queue', ['queue'])
        
        # Performance Metrics
        self.pbs_collection_duration = Histogram('pbs_collection_duration_seconds', 'Time spent collecting PBS metrics')
        self.pbs_collection_success = Gauge('pbs_collection_success', 'PBS collection success flag')
        self.pbs_last_update = Gauge('pbs_last_update_timestamp', 'Last successful update timestamp')
        
        # System Info
        self.pbs_info = Info('pbs_system', 'PBS system information')
        
        # Cache for performance
        self._cache = {}
        self._cache_time = 0
        self._cache_ttl = 20  # 20 second cache
        
    def run_command(self, cmd, timeout=None):
        """Execute command with timeout and error handling"""
        if timeout is None:
            timeout = self.timeout
            
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout,
                check=False
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out: {' '.join(cmd)}")
            return 1, "", "Command timed out"
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return 1, "", str(e)
    
    def get_cached_data(self, key, fetch_func, *args):
        """Get cached data or fetch new data"""
        current_time = time.time()
        cache_key = f"{key}_{args}"
        
        if (cache_key in self._cache and 
            current_time - self._cache_time < self._cache_ttl):
            return self._cache[cache_key]
        
        data = fetch_func(*args)
        self._cache[cache_key] = data
        self._cache_time = current_time
        return data
    
    def collect_job_metrics(self):
        """Collect PBS job metrics"""
        try:
            # Get job information in JSON format for faster parsing
            returncode, stdout, stderr = self.run_command(['qstat', '-f', '-F', 'json'])
            
            if returncode != 0:
                logger.warning(f"qstat failed: {stderr}")
                return {}
            
            try:
                data = json.loads(stdout)
                jobs = data.get('Jobs', {})
            except json.JSONDecodeError:
                # Fallback to XML format
                returncode, stdout, stderr = self.run_command(['qstat', '-fx'])
                if returncode != 0:
                    return {}
                jobs = self._parse_qstat_xml(stdout)
            
            # Reset counters
            job_counts = defaultdict(int)
            queue_jobs = defaultdict(lambda: defaultdict(int))
            user_jobs = defaultdict(lambda: defaultdict(int))
            
            for job_id, job_info in jobs.items():
                state = job_info.get('job_state', 'U')
                queue = job_info.get('queue', 'unknown')
                user = job_info.get('euser', 'unknown')
                
                # Count by state
                if state == 'R':
                    job_counts['running'] += 1
                elif state == 'Q':
                    job_counts['queued'] += 1
                elif state == 'H':
                    job_counts['held'] += 1
                
                job_counts['total'] += 1
                
                # Count by queue and user
                queue_jobs[queue][state] += 1
                user_jobs[user][state] += 1
                
                # Walltime analysis
                if 'Resource_List' in job_info and 'walltime' in job_info['Resource_List']:
                    walltime_str = job_info['Resource_List']['walltime']
                    walltime_seconds = self._parse_walltime(walltime_str)
                    if walltime_seconds:
                        self.pbs_job_walltime.labels(queue=queue).observe(walltime_seconds)
            
            # Update metrics
            self.pbs_jobs_total.set(job_counts['total'])
            self.pbs_jobs_running.set(job_counts['running'])
            self.pbs_jobs_queued.set(job_counts['queued'])
            self.pbs_jobs_held.set(job_counts['held'])
            
            # Update queue and user metrics
            for queue, states in queue_jobs.items():
                for state, count in states.items():
                    self.pbs_queue_jobs.labels(queue=queue, state=state).set(count)
            
            for user, states in user_jobs.items():
                for state, count in states.items():
                    self.pbs_user_jobs.labels(user=user, state=state).set(count)
            
            return job_counts
            
        except Exception as e:
            logger.error(f"Error collecting job metrics: {e}")
            return {}
    
    def collect_node_metrics(self):
        """Collect PBS node metrics"""
        try:
            returncode, stdout, stderr = self.run_command(['pbsnodes', '-av'])
            
            if returncode != 0:
                logger.warning(f"pbsnodes failed: {stderr}")
                return {}
            
            node_counts = defaultdict(int)
            total_processors = 0
            used_processors = 0
            total_memory = 0
            used_memory = 0
            
            current_node = None
            node_info = {}
            
            for line in stdout.split('\n'):
                line = line.strip()
                
                # Node name line
                if line and not line.startswith(' ') and not line.startswith('\t'):
                    if current_node and node_info:
                        self._process_node_info(current_node, node_info, node_counts)
                        total_processors += node_info.get('processors', 0)
                        used_processors += node_info.get('used_processors', 0)
                        total_memory += node_info.get('memory_gb', 0)
                        used_memory += node_info.get('used_memory_gb', 0)
                    
                    current_node = line
                    node_info = {}
                
                # Node attributes
                elif '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'state':
                        node_info['state'] = value
                    elif key == 'np':
                        node_info['processors'] = int(value)
                    elif key == 'properties':
                        node_info['properties'] = value
                    elif key == 'jobs':
                        node_info['jobs'] = value.split(',') if value else []
                        node_info['used_processors'] = len(node_info['jobs'])
                    elif key == 'resources_available.mem':
                        node_info['memory_gb'] = self._parse_memory(value)
                    elif key == 'resources_assigned.mem':
                        node_info['used_memory_gb'] = self._parse_memory(value)
            
            # Process last node
            if current_node and node_info:
                self._process_node_info(current_node, node_info, node_counts)
                total_processors += node_info.get('processors', 0)
                used_processors += node_info.get('used_processors', 0)
                total_memory += node_info.get('memory_gb', 0)
                used_memory += node_info.get('used_memory_gb', 0)
            
            # Update metrics
            self.pbs_nodes_total.set(sum(node_counts.values()))
            self.pbs_nodes_free.set(node_counts['free'])
            self.pbs_nodes_busy.set(node_counts['job-busy'] + node_counts['job-exclusive'])
            self.pbs_nodes_down.set(node_counts['down'])
            self.pbs_nodes_offline.set(node_counts['offline'])
            
            self.pbs_processors_total.set(total_processors)
            self.pbs_processors_used.set(used_processors)
            self.pbs_processors_available.set(total_processors - used_processors)
            
            self.pbs_memory_total_gb.set(total_memory)
            self.pbs_memory_used_gb.set(used_memory)
            
            return node_counts
            
        except Exception as e:
            logger.error(f"Error collecting node metrics: {e}")
            return {}
    
    def collect_queue_metrics(self):
        """Collect PBS queue metrics"""
        try:
            returncode, stdout, stderr = self.run_command(['qmgr', '-c', 'print queue'])
            
            if returncode != 0:
                logger.warning(f"qmgr failed: {stderr}")
                return
            
            current_queue = None
            queue_info = {}
            
            for line in stdout.split('\n'):
                line = line.strip()
                
                if line.startswith('Queue: '):
                    if current_queue and queue_info:
                        self._process_queue_info(current_queue, queue_info)
                    
                    current_queue = line.split('Queue: ')[1]
                    queue_info = {}
                
                elif 'enabled' in line:
                    queue_info['enabled'] = 'True' in line
                elif 'started' in line:
                    queue_info['started'] = 'True' in line
                elif 'max_running' in line and '=' in line:
                    try:
                        queue_info['max_running'] = int(line.split('=')[1].strip())
                    except:
                        pass
            
            # Process last queue
            if current_queue and queue_info:
                self._process_queue_info(current_queue, queue_info)
                
        except Exception as e:
            logger.error(f"Error collecting queue metrics: {e}")
    
    def _process_node_info(self, node_name, node_info, node_counts):
        """Process individual node information"""
        state = node_info.get('state', 'unknown')
        
        # Normalize state
        if 'free' in state:
            normalized_state = 'free'
        elif 'job-busy' in state or 'busy' in state:
            normalized_state = 'job-busy'
        elif 'job-exclusive' in state:
            normalized_state = 'job-exclusive'
        elif 'down' in state:
            normalized_state = 'down'
        elif 'offline' in state:
            normalized_state = 'offline'
        else:
            normalized_state = 'unknown'
        
        node_counts[normalized_state] += 1
        self.pbs_node_state.labels(node=node_name, state=normalized_state).set(1)
    
    def _process_queue_info(self, queue_name, queue_info):
        """Process individual queue information"""
        self.pbs_queue_enabled.labels(queue=queue_name).set(1 if queue_info.get('enabled', False) else 0)
        self.pbs_queue_started.labels(queue=queue_name).set(1 if queue_info.get('started', False) else 0)
        if 'max_running' in queue_info:
            self.pbs_queue_max_running.labels(queue=queue_name).set(queue_info['max_running'])
    
    def _parse_walltime(self, walltime_str):
        """Parse PBS walltime format (HH:MM:SS) to seconds"""
        try:
            if ':' in walltime_str:
                parts = walltime_str.split(':')
                if len(parts) == 3:
                    hours, minutes, seconds = map(int, parts)
                    return hours * 3600 + minutes * 60 + seconds
            return None
        except:
            return None
    
    def _parse_memory(self, memory_str):
        """Parse memory string to GB"""
        try:
            if memory_str.endswith('gb'):
                return float(memory_str[:-2])
            elif memory_str.endswith('mb'):
                return float(memory_str[:-2]) / 1024
            elif memory_str.endswith('kb'):
                return float(memory_str[:-2]) / (1024 * 1024)
            else:
                return float(memory_str) / (1024 * 1024 * 1024)  # Assume bytes
        except:
            return 0
    
    def _parse_qstat_xml(self, xml_content):
        """Parse qstat XML output as fallback"""
        try:
            root = ET.fromstring(xml_content)
            jobs = {}
            
            for job in root.findall('.//Job'):
                job_id = job.find('Job_Id').text if job.find('Job_Id') is not None else 'unknown'
                job_info = {}
                
                for elem in job:
                    if elem.tag == 'job_state':
                        job_info['job_state'] = elem.text
                    elif elem.tag == 'queue':
                        job_info['queue'] = elem.text
                    elif elem.tag == 'euser':
                        job_info['euser'] = elem.text
                
                jobs[job_id] = job_info
            
            return jobs
        except:
            return {}
    
    def collect_metrics(self):
        """Main metrics collection function"""
        start_time = time.time()
        
        try:
            # Collect all metrics
            job_metrics = self.get_cached_data('jobs', self.collect_job_metrics)
            node_metrics = self.get_cached_data('nodes', self.collect_node_metrics)
            self.collect_queue_metrics()
            
            # Update system info
            self.pbs_info.info({
                'version': 'PBS Pro',
                'collection_time': datetime.now().isoformat(),
                'total_jobs': str(job_metrics.get('total', 0)),
                'total_nodes': str(sum(node_metrics.values()) if node_metrics else 0)
            })
            
            # Update success metrics
            self.pbs_collection_success.set(1)
            self.pbs_last_update.set(time.time())
            
            collection_time = time.time() - start_time
            self.pbs_collection_duration.observe(collection_time)
            
            logger.info(f"✅ PBS metrics collected successfully in {collection_time:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Failed to collect PBS metrics: {e}")
            self.pbs_collection_success.set(0)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("🛑 Received shutdown signal")
        self.running = False
    
    def run(self):
        """Main run loop"""
        logger.info(f"🚀 Starting Lengau PBS Exporter on port {self.port}")
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # Start HTTP server
        start_http_server(self.port)
        logger.info(f"📊 Metrics available at http://localhost:{self.port}/metrics")
        
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
        
        logger.info("👋 PBS Exporter stopped")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Lengau PBS Prometheus Exporter')
    parser.add_argument('--port', type=int, default=8085, help='Port to serve metrics on')
    parser.add_argument('--interval', type=int, default=30, help='Collection interval in seconds')
    parser.add_argument('--timeout', type=int, default=15, help='Command timeout in seconds')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    exporter = LengauPBSExporter(
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
