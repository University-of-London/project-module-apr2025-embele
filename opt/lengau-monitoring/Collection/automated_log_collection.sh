#!/bin/bash

# Automated HPC Log Collection Script
# Runs periodically to collect fresh logs
# Enhanced with cluster-wide monitoring for AI anomaly detection

LOG_DIR="/mnt/lustre/users/embele/hpc_logs"
SCRIPT_DIR="/opt/lengau-monitoring/scripts"
LOCK_FILE="/tmp/hpc_log_collection.lock"
MAX_LOG_AGE_HOURS=6
CLUSTER_LOG_AGE_HOURS=12  # Cluster-wide collection less frequent due to scale

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/automated_collection.log"
}

# Check if collection is needed
needs_collection() {
    local log_type=$1
    local latest_dir=$(find "$LOG_DIR" -maxdepth 1 -type d -name "${log_type}_logs_*" | sort | tail -1)
    
    if [ -z "$latest_dir" ]; then
        return 0  # No logs exist, need collection
    fi
    
    local dir_timestamp=$(basename "$latest_dir" | sed "s/${log_type}_logs_//")
    local dir_epoch=$(date -d "${dir_timestamp:0:8} ${dir_timestamp:9:2}:${dir_timestamp:11:2}:${dir_timestamp:13:2}" +%s 2>/dev/null)
    local current_epoch=$(date +%s)
    local age_hours=$(( (current_epoch - dir_epoch) / 3600 ))
    
    # Use different age thresholds for cluster-wide vs regular collections
    local threshold_hours=$MAX_LOG_AGE_HOURS
    if [ "$log_type" = "cluster_wide" ]; then
        threshold_hours=$CLUSTER_LOG_AGE_HOURS
    fi
    
    if [ $age_hours -gt $threshold_hours ]; then
        return 0  # Logs are old, need collection
    fi
    
    return 1  # Logs are fresh
}

# Main execution
main() {
    # Check for lock file
    if [ -f "$LOCK_FILE" ]; then
        local lock_pid=$(cat "$LOCK_FILE")
        if kill -0 "$lock_pid" 2>/dev/null; then
            log_message "Collection already running (PID: $lock_pid)"
            exit 1
        else
            log_message "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi
    
    # Create lock file
    echo $$ > "$LOCK_FILE"
    trap "rm -f $LOCK_FILE" EXIT
    

    log_message "=== Starting Automated HPC Log Collection ==="
    log_message "🎯 Enhanced with AI anomaly detection capabilities"
    
    # Check if system logs need updating
    if needs_collection "system"; then
        log_message "System logs need updating, running collection..."
        if sudo "$SCRIPT_DIR/collect_system_logs.sh"; then
            log_message "✓ System log collection completed"
        else
            log_message "✗ System log collection failed"
        fi
    else
        log_message "System logs are current, skipping"
    fi
    
    # Check if PBS logs need updating
    if needs_collection "pbs"; then
        log_message "PBS logs need updating, running collection..."
        if sudo -u embele "$SCRIPT_DIR/collect_pbs_logs.sh"; then
            log_message "✓ PBS log collection completed"
        else
            log_message "✗ PBS log collection failed"
        fi
    else
        log_message "PBS logs are current, skipping"
    fi
    
    # Check if cluster-wide logs need updating (for AI anomaly detection)
    if needs_collection "cluster_wide"; then
        log_message "Cluster-wide logs need updating, running collection..."
        log_message "🔍 Collecting node failure patterns, load imbalance, network partitions"
        log_message "⚡ Using aggressive timeouts to avoid hanging on unreachable nodes"
        
        # Set timeout for entire cluster collection (30 minutes max)
        if timeout 1800 sudo "$SCRIPT_DIR/collect_cluster_wide_logs.sh"; then
            log_message "✓ Cluster-wide log collection completed"
            log_message "📊 Node status patterns collected for AI analysis"
        else
            log_message "✗ Cluster-wide log collection failed or timed out"
            log_message "⚠️  Some nodes may be unreachable - check logs for details"
        fi
    else
        log_message "Cluster-wide logs are current, skipping"
    fi
    
    # Note: Log cleanup disabled to preserve historical data for monitoring
    log_message "Log cleanup disabled - preserving all collections for monitoring"
    
    # Update ownership
    chown -R embele:embele "$LOG_DIR"
    
    log_message "=== Automated HPC Log Collection Completed ==="
    log_message "📈 AI-ready data collected: system metrics, PBS scheduler, cluster topology"
}

# Execute main function
main "$@"

