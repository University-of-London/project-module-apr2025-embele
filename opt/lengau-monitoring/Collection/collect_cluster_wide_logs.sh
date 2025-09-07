#!/bin/bash

# Lengau Cluster-Wide Log Collection Script
# Collects logs from all 1,368 compute nodes + GPU nodes

# Configuration
LOG_DIR="/mnt/lustre/users/embele/hpc_logs"
SCRIPT_DIR="/opt/lengau-monitoring/scripts"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
NODES_FILE="/opt/lengau-monitoring/scripts/compute_nodes.txt"
MAX_PARALLEL=20  # Reduced parallel collections to avoid overwhelming
TIMEOUT=60       # 1 minute timeout per node (much faster)
PING_TIMEOUT=3   # 3 second ping timeout
SSH_TIMEOUT=10   # 10 second SSH connection timeout

# Create cluster-wide log structure
mkdir -p "$LOG_DIR/cluster_wide_logs/$TIMESTAMP"
chown -R embele:embele "$LOG_DIR"

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/cluster_collection.log"
}

# Generate node list from PBS or inventory
generate_node_list() {
    log_message "Generating cluster node list..."
    
    # Always use the predefined list (PBS may not show all nodes)
    if [ -f "$NODES_FILE" ]; then
        # Force fresh copy with verification
        rm -f "$LOG_DIR/active_nodes_$TIMESTAMP.txt"
        cp "$NODES_FILE" "$LOG_DIR/active_nodes_$TIMESTAMP.txt"
        
        # Verify copy was successful
        original_count=$(wc -l < "$NODES_FILE")
        copied_count=$(wc -l < "$LOG_DIR/active_nodes_$TIMESTAMP.txt")
        
        log_message "Node list source: $NODES_FILE (${original_count} nodes)"
        log_message "Active nodes file: $LOG_DIR/active_nodes_$TIMESTAMP.txt (${copied_count} nodes)"
        
        if [ "$original_count" -eq "$copied_count" ]; then
            log_message "✅ Node list copied successfully: $copied_count nodes"
        else
            log_message "❌ ERROR: Node list copy failed! Original: $original_count, Copied: $copied_count"
            log_message "File details - Original: $(ls -lh "$NODES_FILE")"
            log_message "File details - Copy: $(ls -lh "$LOG_DIR/active_nodes_$TIMESTAMP.txt")"
            exit 1
        fi
    else
        log_message "ERROR: Node list file not found: $NODES_FILE"
        exit 1
    fi
}

# Collect logs from a single node
collect_from_node() {
    local node=$1
    local node_log_dir="$LOG_DIR/cluster_wide_logs/$TIMESTAMP/$node"
    
    mkdir -p "$node_log_dir"
    
    log_message "Collecting from $node..."
    
    # Test connectivity first with aggressive timeout
    if ! timeout $PING_TIMEOUT ping -c 1 "$node" >/dev/null 2>&1; then
        echo "UNREACHABLE" > "$node_log_dir/status.txt"
        log_message "🔌 Node $node unreachable (ping timeout)"
        return 1
    fi
    
    # Collect system metrics via SSH with aggressive timeouts
    timeout $TIMEOUT ssh -o ConnectTimeout=$SSH_TIMEOUT -o StrictHostKeyChecking=no -o BatchMode=yes "$node" "
        # System info
        hostname > /tmp/hostname.txt
        uptime > /tmp/uptime.txt
        cat /proc/loadavg > /tmp/loadavg.txt
        cat /proc/meminfo > /tmp/meminfo.txt
        free -h > /tmp/free.txt
        df -h > /tmp/df.txt
        
        # CPU info
        cat /proc/cpuinfo | head -50 > /tmp/cpuinfo.txt
        lscpu > /tmp/lscpu.txt 2>/dev/null
        
        # Process info
        ps aux | head -20 > /tmp/top_processes.txt
        
        # Network info
        cat /proc/net/dev > /tmp/network.txt
        
        # GPU info (if available)
        if command -v nvidia-smi &> /dev/null; then
            nvidia-smi -q > /tmp/nvidia.txt 2>/dev/null
        fi
        
        # InfiniBand info (if available)
        if command -v ibstat &> /dev/null; then
            ibstat > /tmp/ibstat.txt 2>/dev/null
        fi
        
        # Lustre client info (if available)
        if [ -d /proc/fs/lustre ]; then
            find /proc/fs/lustre/llite -name stats -exec cat {} \; > /tmp/lustre.txt 2>/dev/null
        fi
        
        # System errors
        dmesg | tail -100 > /tmp/dmesg.txt 2>/dev/null
        
        # Create tarball
        tar -czf /tmp/node_logs_$node.tar.gz /tmp/*.txt 2>/dev/null
        
    " 2>/dev/null
    
    SSH_EXIT_CODE=$?
    if [ $SSH_EXIT_CODE -ne 0 ]; then
        echo "FAILED" > "$node_log_dir/status.txt"
        log_message "❌ $node SSH failed (exit code: $SSH_EXIT_CODE)"
        return 1
    fi
    
    # Copy logs back with aggressive timeout
    if timeout 30 scp -o ConnectTimeout=$SSH_TIMEOUT -o StrictHostKeyChecking=no -o BatchMode=yes "$node:/tmp/node_logs_$node.tar.gz" "$node_log_dir/" 2>/dev/null; then
        # Extract logs
        cd "$node_log_dir"
        tar -xzf "node_logs_$node.tar.gz" --strip-components=1 2>/dev/null
        rm -f "node_logs_$node.tar.gz"
        echo "SUCCESS" > status.txt
        log_message "✅ $node completed"
        
        # Cleanup remote files (non-blocking)
        timeout 10 ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes "$node" "rm -f /tmp/node_logs_$node.tar.gz /tmp/*.txt" 2>/dev/null &
    else
        echo "FAILED" > "$node_log_dir/status.txt"
        log_message "❌ $node failed (SCP timeout or error)"
    fi
}

# Parallel collection function
collect_parallel() {
    local nodes_file="$1"
    local batch_size=$MAX_PARALLEL
    
    log_message "Starting parallel collection with $batch_size concurrent jobs..."
    
    local processed=0
    local total=$(wc -l < "$nodes_file")
    
    # Use file descriptor to avoid stdin consumption by background processes
    exec 3< "$nodes_file"
    
    # Process nodes in batches
    while IFS= read -r node <&3 || [ -n "$node" ]; do
        # Skip empty lines
        [ -z "$node" ] && continue
        
        processed=$((processed + 1))
        
        # Debug: Log every 10 nodes for first 50, then every 100
        if [ $processed -le 50 ] && [ $((processed % 10)) -eq 0 ]; then
            log_message "DEBUG: Processed $processed/$total nodes so far"
        elif [ $processed -gt 50 ] && [ $((processed % 100)) -eq 0 ]; then
            log_message "Progress: $processed/$total nodes processed"
        fi
        
        # Wait if we have too many background jobs
        local current_jobs=$(jobs -r | wc -l)
        while [ $current_jobs -ge $batch_size ]; do
            sleep 2
            current_jobs=$(jobs -r | wc -l)
        done
        
        # Start collection in background (with stdin redirected to /dev/null)
        collect_from_node "$node" </dev/null &
        local bg_pid=$!
        
        # Debug: Log background job started
        if [ $processed -le 50 ]; then
            log_message "DEBUG: Started job $bg_pid for node $node (total processed: $processed)"
        fi
        
    done
    
    # Close file descriptor
    exec 3<&-
    
    log_message "Launched collection for $processed nodes total"
    
    # Wait for all background jobs to complete
    wait
    log_message "All parallel collections completed"
}

# Create cluster summary
create_cluster_summary() {
    log_message "Creating cluster-wide summary..."
    
    local summary_file="$LOG_DIR/cluster_summary_$TIMESTAMP.txt"
    local success_count=0
    local failed_count=0
    local unreachable_count=0
    
    # Count results
    for status_file in "$LOG_DIR/cluster_wide_logs/$TIMESTAMP"/*/status.txt; do
        if [ -f "$status_file" ]; then
            case $(cat "$status_file") in
                "SUCCESS") success_count=$((success_count + 1)) ;;
                "FAILED") failed_count=$((failed_count + 1)) ;;
                "UNREACHABLE") unreachable_count=$((unreachable_count + 1)) ;;
            esac
        fi
    done
    
    cat > "$summary_file" << EOF
Lengau Cluster-Wide Log Collection Summary
==========================================
Collection Time: $(date)
Timestamp: $TIMESTAMP
Collection Method: Parallel SSH (max $MAX_PARALLEL concurrent, ${TIMEOUT}s timeout)

Results:
========
✅ Successful: $success_count nodes
❌ Failed: $failed_count nodes  
🔌 Unreachable: $unreachable_count nodes
📊 Total Attempted: $((success_count + failed_count + unreachable_count)) nodes

Success Rate: $(( success_count * 100 / (success_count + failed_count + unreachable_count) ))%

Storage Usage:
==============
$(du -sh "$LOG_DIR/cluster_wide_logs/$TIMESTAMP")

Successful Nodes:
=================
$(find "$LOG_DIR/cluster_wide_logs/$TIMESTAMP" -name "status.txt" -exec grep -l "SUCCESS" {} \; | sed 's|.*/\([^/]*\)/status.txt|\1|' | sort)

Failed Nodes:
=============
$(find "$LOG_DIR/cluster_wide_logs/$TIMESTAMP" -name "status.txt" -exec grep -l "FAILED" {} \; | sed 's|.*/\([^/]*\)/status.txt|\1|' | sort)

Unreachable Nodes:
==================
$(find "$LOG_DIR/cluster_wide_logs/$TIMESTAMP" -name "status.txt" -exec grep -l "UNREACHABLE" {} \; | sed 's|.*/\([^/]*\)/status.txt|\1|' | sort)

Data Collected Per Node:
========================
- System metrics (CPU, memory, load, disk)
- Process information
- Network statistics
- GPU metrics (V100 nodes)
- InfiniBand statistics
- Lustre client statistics
- System error logs (dmesg)

Next Steps:
===========
1. Process collected data: python3 process_cluster_logs.py $TIMESTAMP
2. Generate AI training data: python3 prepare_cluster_data_for_ai.py $TIMESTAMP
3. Run anomaly detection: python3 cluster_anomaly_detection.py $TIMESTAMP
EOF

    log_message "Cluster summary created: $summary_file"
    
    # Convert to AI-readable format
    log_message "Converting cluster data to AI-readable format..."
    if python3 "$SCRIPT_DIR/convert_cluster_to_ai_format.py" "$TIMESTAMP"; then
        log_message "✅ Cluster data converted for AI analysis"
    else
        log_message "❌ Failed to convert cluster data for AI"
    fi
    
    echo ""
    echo "📊 CLUSTER COLLECTION SUMMARY:"
    echo "=============================="
    echo "✅ Successful: $success_count nodes"
    echo "❌ Failed: $failed_count nodes"
    echo "🔌 Unreachable: $unreachable_count nodes"
    echo "📈 Success Rate: $(( success_count * 100 / (success_count + failed_count + unreachable_count) ))%"
    echo ""
    echo "📁 Data stored in: $LOG_DIR/cluster_wide_logs/$TIMESTAMP"
    echo "🤖 AI-ready data: $LOG_DIR/system_logs_[timestamp]"
    echo "📋 Full summary: $summary_file"
}

# Main execution
main() {
    echo "🌐 LENGAU CLUSTER-WIDE LOG COLLECTION"
    echo "====================================="
    log_message "Starting cluster-wide log collection..."
    
    # Check prerequisites
    if ! command -v ssh &> /dev/null; then
        log_message "ERROR: SSH not available"
        exit 1
    fi
    
    if ! command -v scp &> /dev/null; then
        log_message "ERROR: SCP not available"
        exit 1
    fi
    
    # Generate node list
    generate_node_list
    
    # Verify node list before collection
    if [ ! -f "$LOG_DIR/active_nodes_$TIMESTAMP.txt" ]; then
        log_message "ERROR: Node list file not created"
        exit 1
    fi
    
    local node_count=$(wc -l < "$LOG_DIR/active_nodes_$TIMESTAMP.txt")
    log_message "📊 About to process $node_count nodes from node list"
    
    # Start parallel collection
    collect_parallel "$LOG_DIR/active_nodes_$TIMESTAMP.txt"
    
    # Create summary
    create_cluster_summary
    
    # Set proper ownership
    chown -R embele:embele "$LOG_DIR"
    
    log_message "=== Cluster-wide collection completed ==="
}

# Execute main function
main "$@"
