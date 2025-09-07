#!/usr/bin/env python3
"""
Convert cluster_wide_logs to AI-readable system_logs format
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
import argparse

def convert_cluster_to_system_format(cluster_timestamp):
    """Convert cluster_wide_logs to system_logs format for AI processing"""
    
    logs_dir = Path("/mnt/lustre/users/embele/hpc_logs")
    cluster_dir = logs_dir / f"cluster_wide_logs/{cluster_timestamp}"
    
    if not cluster_dir.exists():
        print(f"❌ Cluster directory not found: {cluster_dir}")
        return False
    
    # Create AI-compatible system_logs directory
    ai_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    system_dir = logs_dir / f"system_logs_{ai_timestamp}"
    system_dir.mkdir(exist_ok=True)
    
    print(f"🔄 Converting {cluster_dir} to {system_dir}")
    
    # Aggregate cluster data into system_logs format
    aggregate_data = {
        'loadavg': [],
        'meminfo': [],
        'network': [],
        'processes': [],
        'node_status': {'success': 0, 'failed': 0, 'unreachable': 0}
    }
    
    success_nodes = []
    failed_nodes = []
    unreachable_nodes = []
    
    # Process each node directory
    for node_dir in cluster_dir.glob("*"):
        if not node_dir.is_dir():
            continue
            
        node_name = node_dir.name
        status_file = node_dir / "status.txt"
        
        if not status_file.exists():
            continue
            
        status = status_file.read_text().strip()
        
        if status == "SUCCESS":
            success_nodes.append(node_name)
            aggregate_data['node_status']['success'] += 1
            
            # Aggregate node data
            if (node_dir / "loadavg.txt").exists():
                loadavg_data = (node_dir / "loadavg.txt").read_text().strip()
                aggregate_data['loadavg'].append(f"{node_name}: {loadavg_data}")
                
            if (node_dir / "meminfo.txt").exists():
                # Extract key memory metrics
                meminfo = (node_dir / "meminfo.txt").read_text()
                for line in meminfo.split('\n')[:5]:  # First 5 lines
                    if line.strip():
                        aggregate_data['meminfo'].append(f"{node_name}: {line}")
                        
            if (node_dir / "network.txt").exists():
                network_data = (node_dir / "network.txt").read_text()
                # Extract key network interfaces
                for line in network_data.split('\n')[1:4]:  # Skip header, get 3 lines
                    if line.strip():
                        aggregate_data['network'].append(f"{node_name}: {line}")
                        
            if (node_dir / "top_processes.txt").exists():
                processes = (node_dir / "top_processes.txt").read_text()
                # Get first process line (highest CPU)
                for line in processes.split('\n')[1:2]:  # Skip header
                    if line.strip():
                        aggregate_data['processes'].append(f"{node_name}: {line}")
                        
        elif status == "FAILED":
            failed_nodes.append(node_name)
            aggregate_data['node_status']['failed'] += 1
        elif status == "UNREACHABLE":
            unreachable_nodes.append(node_name)
            aggregate_data['node_status']['unreachable'] += 1
    
    # Write aggregated data in system_logs format (clean data for AI processing)
    timestamp_suffix = f"_{ai_timestamp}"
    
    # Load average aggregation - extract numeric data only
    with open(system_dir / f"loadavg{timestamp_suffix}.txt", 'w') as f:
        for line in aggregate_data['loadavg']:
            # Extract just the numeric parts from "nodename: 0.05 0.15 0.20 1/234 12345"
            if ':' in line:
                load_data = line.split(':', 1)[1].strip()
                f.write(load_data + "\n")
    
    # Memory aggregation - extract key memory metrics
    with open(system_dir / f"meminfo{timestamp_suffix}.txt", 'w') as f:
        for line in aggregate_data['meminfo']:
            if ':' in line and any(key in line for key in ['MemTotal:', 'MemFree:', 'MemAvailable:', 'Buffers:', 'Cached:']):
                # Extract just the value part: "MemTotal: 8192000 kB" -> "8192000"
                parts = line.split(':', 1)[1].strip().split()
                if parts and parts[0].isdigit():
                    f.write(parts[0] + "\n")
    
    # Network aggregation - extract interface stats
    with open(system_dir / f"net_dev{timestamp_suffix}.txt", 'w') as f:
        for line in aggregate_data['network']:
            if ':' in line and not line.strip().startswith('Inter-'):
                # Extract network numbers from interface lines
                parts = line.split(':')
                if len(parts) >= 2:
                    stats = parts[1].strip().split()
                    # Write RX bytes and TX bytes (first and 9th fields typically)
                    if len(stats) >= 9 and stats[0].isdigit() and stats[8].isdigit():
                        f.write(f"{stats[0]} {stats[8]}\n")
    
    # Process aggregation - extract CPU usage
    with open(system_dir / f"processes{timestamp_suffix}.txt", 'w') as f:
        for line in aggregate_data['processes']:
            if ':' in line:
                # Extract CPU percentage from ps aux output
                parts = line.split(':', 1)[1].strip().split()
                if len(parts) >= 3 and parts[2].replace('.', '').isdigit():
                    f.write(parts[2] + "\n")  # CPU percentage
    
    # Cluster status summary - pure numeric data for AI
    with open(system_dir / f"cluster_status{timestamp_suffix}.txt", 'w') as f:
        f.write(f"{aggregate_data['node_status']['success']}\n")
        f.write(f"{aggregate_data['node_status']['failed']}\n")
        f.write(f"{aggregate_data['node_status']['unreachable']}\n")
        f.write(f"{len(success_nodes) + len(failed_nodes) + len(unreachable_nodes)}\n")
        success_rate = aggregate_data['node_status']['success'] / max(1, len(success_nodes) + len(failed_nodes) + len(unreachable_nodes)) * 100
        f.write(f"{success_rate:.1f}\n")
    
    # Create metadata for AI system
    metadata = {
        'timestamp': ai_timestamp,
        'source': f'cluster_wide_logs/{cluster_timestamp}',
        'nodes_processed': len(success_nodes) + len(failed_nodes) + len(unreachable_nodes),
        'successful_nodes': len(success_nodes),
        'failed_nodes': len(failed_nodes), 
        'unreachable_nodes': len(unreachable_nodes),
        'success_rate': aggregate_data['node_status']['success'] / max(1, len(success_nodes) + len(failed_nodes) + len(unreachable_nodes)) * 100,
        'ai_features_available': ['cluster_node_status', 'aggregated_load', 'aggregated_memory', 'aggregated_network', 'aggregated_processes'],
        'cluster_wide_anomalies': {
            'low_success_rate': aggregate_data['node_status']['success'] / max(1, len(success_nodes) + len(failed_nodes) + len(unreachable_nodes)) < 0.8,
            'high_failure_count': len(failed_nodes) > 50,
            'unreachable_nodes_detected': len(unreachable_nodes) > 0
        }
    }
    
    with open(system_dir / f"ai_metadata{timestamp_suffix}.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✅ Converted cluster data to AI format:")
    print(f"   📁 Output: {system_dir}")
    print(f"   📊 Nodes: {len(success_nodes)} success, {len(failed_nodes)} failed, {len(unreachable_nodes)} unreachable")
    print(f"   🎯 Success rate: {metadata['success_rate']:.1f}%")
    print(f"   🤖 AI-ready numeric data (no comments or headers)")
    print(f"   📈 Generated clean data files for real-time detection")
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert cluster_wide_logs to AI-readable format")
    parser.add_argument("cluster_timestamp", help="Timestamp of cluster_wide_logs directory")
    
    args = parser.parse_args()
    
    success = convert_cluster_to_system_format(args.cluster_timestamp)
    exit(0 if success else 1)
