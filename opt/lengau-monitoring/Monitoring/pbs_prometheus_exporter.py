#!/usr/bin/env python3
"""
PBS Prometheus Exporter for Lengau HPC
Exports PBS job and node data as Prometheus metrics
"""

import subprocess
import re
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import argparse
import threading

class PBSMetricsCollector:
    def __init__(self, pbs_server="sched01"):
        self.pbs_server = pbs_server
        
    def get_pbs_queue_stats(self):
        """Get PBS queue statistics from showq"""
        try:
            result = subprocess.run(['showq'], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {}
                
            output = result.stdout
            stats = {}
            
            # Parse showq output
            for line in output.split('\n'):
                if 'Total' in line and 'Active Jobs' in line:
                    match = re.search(r'(\d+)\s+Active Jobs', line)
                    if match:
                        stats['active_jobs'] = int(match.group(1))
                        
                if 'Total' in line and 'Processors Used' in line:
                    match = re.search(r'(\d+)\s+of\s+(\d+)\s+Total\s+Processors Used', line)
                    if match:
                        stats['processors_used'] = int(match.group(1))
                        stats['processors_total'] = int(match.group(2))
                        
                if 'Total' in line and 'Nodes Used' in line:
                    match = re.search(r'(\d+)\s+of\s+(\d+)\s+Total\s+Nodes Used', line)
                    if match:
                        stats['nodes_used'] = int(match.group(1))
                        stats['nodes_total'] = int(match.group(2))
                        
                if 'Nodes Offline' in line:
                    match = re.search(r'(\d+)\s+of\s+\d+\s+Total\s+Nodes Offline', line)
                    if match:
                        stats['nodes_offline'] = int(match.group(1))
                        
                if 'Nodes Down' in line:
                    match = re.search(r'(\d+)\s+of\s+\d+\s+Total\s+Nodes Down', line)
                    if match:
                        stats['nodes_down'] = int(match.group(1))
                        
            return stats
        except Exception as e:
            print(f"Error getting PBS queue stats: {e}")
            return {}
    
    def get_node_states(self):
        """Get node state counts from pbsnodes"""
        try:
            result = subprocess.run(['pbsnodes', '-a'], capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return {}
                
            states = {}
            current_node = None
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line and not line.startswith(' '):
                    current_node = line
                elif line.startswith('state = '):
                    state = line.split('=')[1].strip()
                    states[state] = states.get(state, 0) + 1
                    
            return states
        except Exception as e:
            print(f"Error getting node states: {e}")
            return {}
    
    def generate_metrics(self):
        """Generate Prometheus metrics"""
        metrics = []
        
        # Get PBS queue statistics
        queue_stats = self.get_pbs_queue_stats()
        for metric, value in queue_stats.items():
            metrics.append(f'pbs_{metric} {value}')
        
        # Calculate utilization percentages
        if 'processors_used' in queue_stats and 'processors_total' in queue_stats:
            if queue_stats['processors_total'] > 0:
                util = (queue_stats['processors_used'] / queue_stats['processors_total']) * 100
                metrics.append(f'pbs_processor_utilization_percent {util:.2f}')
        
        if 'nodes_used' in queue_stats and 'nodes_total' in queue_stats:
            if queue_stats['nodes_total'] > 0:
                util = (queue_stats['nodes_used'] / queue_stats['nodes_total']) * 100
                metrics.append(f'pbs_node_utilization_percent {util:.2f}')
        
        # Get node state counts
        node_states = self.get_node_states()
        for state, count in node_states.items():
            # Clean state name for Prometheus
            clean_state = re.sub(r'[^a-zA-Z0-9_]', '_', state)
            metrics.append(f'pbs_nodes_by_state{{state="{state}"}} {count}')
        
        # Add timestamp
        metrics.append(f'pbs_last_update_timestamp {int(time.time())}')
        
        return '\n'.join(metrics) + '\n'

class MetricsHandler(BaseHTTPRequestHandler):
    def __init__(self, collector, *args, **kwargs):
        self.collector = collector
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        if self.path == '/metrics':
            try:
                metrics = self.collector.generate_metrics()
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(metrics.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f'Error generating metrics: {e}\n'.encode('utf-8'))
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK\n')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress default logging

def main():
    parser = argparse.ArgumentParser(description='PBS Prometheus Exporter')
    parser.add_argument('--port', type=int, default=8085, help='Port to listen on')
    parser.add_argument('--pbs-server', default='sched01', help='PBS server hostname')
    parser.add_argument('--test', action='store_true', help='Test mode - print metrics and exit')
    
    args = parser.parse_args()
    
    collector = PBSMetricsCollector(args.pbs_server)
    
    if args.test:
        print("Test mode - generating PBS metrics:")
        print("=" * 40)
        print(collector.generate_metrics())
        return
    
    # Create HTTP server
    handler = lambda *args, **kwargs: MetricsHandler(collector, *args, **kwargs)
    httpd = HTTPServer(('0.0.0.0', args.port), handler)
    
    print(f"PBS Prometheus Exporter running on port {args.port}")
    print(f"PBS Server: {args.pbs_server}")
    print(f"Metrics: http://localhost:{args.port}/metrics")
    print(f"Health: http://localhost:{args.port}/health")
    print("Press Ctrl+C to stop")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        httpd.shutdown()

if __name__ == '__main__':
    main()
