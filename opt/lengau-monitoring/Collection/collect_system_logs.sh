#!/bin/bash

# HPC System Log Collection Script (Run as ROOT)
# Collects all system logs except PBS

# Configuration
LOG_DIR="/mnt/lustre/users/embele/hpc_logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"
chown embele:embele "$LOG_DIR"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/system_collection.log"
}

log_message "Starting HPC system log collection as ROOT..."

# 1. Collect System Resource Logs
collect_system_logs() {
    log_message "Collecting system resource logs..."
    
    SYSTEM_OUTPUT_DIR="$LOG_DIR/system_logs_$TIMESTAMP"
    mkdir -p "$SYSTEM_OUTPUT_DIR"
    
    # CPU and Load information
    cat /proc/loadavg > "$SYSTEM_OUTPUT_DIR/loadavg_$TIMESTAMP.txt"
    cat /proc/stat > "$SYSTEM_OUTPUT_DIR/stat_$TIMESTAMP.txt"
    cat /proc/cpuinfo > "$SYSTEM_OUTPUT_DIR/cpuinfo_$TIMESTAMP.txt"
    
    # Memory information
    cat /proc/meminfo > "$SYSTEM_OUTPUT_DIR/meminfo_$TIMESTAMP.txt"
    free -h > "$SYSTEM_OUTPUT_DIR/free_$TIMESTAMP.txt"
    
    # Disk information
    cat /proc/diskstats > "$SYSTEM_OUTPUT_DIR/diskstats_$TIMESTAMP.txt"
    df -h > "$SYSTEM_OUTPUT_DIR/df_$TIMESTAMP.txt"
    iostat -x 1 5 > "$SYSTEM_OUTPUT_DIR/iostat_$TIMESTAMP.txt" 2>/dev/null
    
    # Network information
    cat /proc/net/dev > "$SYSTEM_OUTPUT_DIR/net_dev_$TIMESTAMP.txt"
    ss -tuln > "$SYSTEM_OUTPUT_DIR/network_connections_$TIMESTAMP.txt"
    netstat -i > "$SYSTEM_OUTPUT_DIR/network_interfaces_$TIMESTAMP.txt" 2>/dev/null
    
    # System logs
    tail -n 2000 /var/log/messages > "$SYSTEM_OUTPUT_DIR/messages_$TIMESTAMP.txt" 2>/dev/null
    tail -n 2000 /var/log/syslog > "$SYSTEM_OUTPUT_DIR/syslog_$TIMESTAMP.txt" 2>/dev/null
    dmesg | tail -n 2000 > "$SYSTEM_OUTPUT_DIR/dmesg_$TIMESTAMP.txt"
    
    # System information
    uptime > "$SYSTEM_OUTPUT_DIR/uptime_$TIMESTAMP.txt"
    uname -a > "$SYSTEM_OUTPUT_DIR/uname_$TIMESTAMP.txt"
    lscpu > "$SYSTEM_OUTPUT_DIR/lscpu_$TIMESTAMP.txt"
    lsblk > "$SYSTEM_OUTPUT_DIR/lsblk_$TIMESTAMP.txt"
    
    # Process information
    ps aux > "$SYSTEM_OUTPUT_DIR/processes_$TIMESTAMP.txt"
    top -b -n 1 > "$SYSTEM_OUTPUT_DIR/top_$TIMESTAMP.txt"
    
    chown -R embele:embele "$SYSTEM_OUTPUT_DIR"
    log_message "System logs collected to $SYSTEM_OUTPUT_DIR"
}

# 2. Collect Lustre File System Logs
collect_lustre_logs() {
    log_message "Collecting Lustre file system logs..."
    
    LUSTRE_OUTPUT_DIR="$LOG_DIR/lustre_logs_$TIMESTAMP"
    mkdir -p "$LUSTRE_OUTPUT_DIR"
    
    # Check if Lustre is available
    if [ -d "/proc/fs/lustre" ]; then
        # Client statistics
        find /proc/fs/lustre/llite -name "stats" -exec cp {} "$LUSTRE_OUTPUT_DIR/client_stats_$(basename $(dirname {}))_$TIMESTAMP.txt" \; 2>/dev/null
        
        # OSC (Object Storage Client) statistics
        find /proc/fs/lustre/osc -name "stats" -exec cp {} "$LUSTRE_OUTPUT_DIR/osc_stats_$(basename $(dirname {}))_$TIMESTAMP.txt" \; 2>/dev/null
        
        # MDC (Metadata Client) statistics
        find /proc/fs/lustre/mdc -name "stats" -exec cp {} "$LUSTRE_OUTPUT_DIR/mdc_stats_$(basename $(dirname {}))_$TIMESTAMP.txt" \; 2>/dev/null
        
        # Lustre health status
        lctl get_param health_check > "$LUSTRE_OUTPUT_DIR/health_check_$TIMESTAMP.txt" 2>/dev/null
        lctl get_param version > "$LUSTRE_OUTPUT_DIR/version_$TIMESTAMP.txt" 2>/dev/null
        lctl get_param -R llite.*.stats > "$LUSTRE_OUTPUT_DIR/llite_detailed_stats_$TIMESTAMP.txt" 2>/dev/null
        
        # Lustre mount information
        mount | grep lustre > "$LUSTRE_OUTPUT_DIR/lustre_mounts_$TIMESTAMP.txt" 2>/dev/null
        
        chown -R embele:embele "$LUSTRE_OUTPUT_DIR"
        log_message "Lustre logs collected to $LUSTRE_OUTPUT_DIR"
    else
        rmdir "$LUSTRE_OUTPUT_DIR"
        log_message "Lustre not available on this node"
    fi
}

# 3. Collect InfiniBand Network Logs
collect_infiniband_logs() {
    log_message "Collecting InfiniBand network logs..."
    
    IB_OUTPUT_DIR="$LOG_DIR/infiniband_logs_$TIMESTAMP"
    mkdir -p "$IB_OUTPUT_DIR"
    
    # Check if InfiniBand tools are available
    if command -v ibstat &> /dev/null; then
        # HCA information
        ibstat > "$IB_OUTPUT_DIR/ibstat_$TIMESTAMP.txt" 2>/dev/null
        ibstat -l > "$IB_OUTPUT_DIR/ibstat_list_$TIMESTAMP.txt" 2>/dev/null
        
        # Performance counters
        perfquery -a > "$IB_OUTPUT_DIR/perfquery_all_$TIMESTAMP.txt" 2>/dev/null
        
        # Network topology
        ibnetdiscover > "$IB_OUTPUT_DIR/topology_$TIMESTAMP.txt" 2>/dev/null
        
        # Port information for each HCA
        for hca in $(ibstat -l 2>/dev/null); do
            if [ -n "$hca" ]; then
                ibstat "$hca" > "$IB_OUTPUT_DIR/hca_${hca}_$TIMESTAMP.txt" 2>/dev/null
                perfquery -C "$hca" > "$IB_OUTPUT_DIR/perfquery_${hca}_$TIMESTAMP.txt" 2>/dev/null
            fi
        done
        
        # IB subnet manager info
        sminfo > "$IB_OUTPUT_DIR/sminfo_$TIMESTAMP.txt" 2>/dev/null
        
        chown -R embele:embele "$IB_OUTPUT_DIR"
        log_message "InfiniBand logs collected to $IB_OUTPUT_DIR"
    else
        rmdir "$IB_OUTPUT_DIR"
        log_message "InfiniBand tools not available on this node"
    fi
}

# 4. Collect Hardware Monitoring Logs
collect_hardware_logs() {
    log_message "Collecting hardware monitoring logs..."
    
    HW_OUTPUT_DIR="$LOG_DIR/hardware_logs_$TIMESTAMP"
    mkdir -p "$HW_OUTPUT_DIR"
    
    # IPMI information (if available)
    if command -v ipmitool &> /dev/null; then
        ipmitool sel list > "$HW_OUTPUT_DIR/ipmi_sel_$TIMESTAMP.txt" 2>/dev/null
        ipmitool sdr list > "$HW_OUTPUT_DIR/ipmi_sdr_$TIMESTAMP.txt" 2>/dev/null
        ipmitool sensor list > "$HW_OUTPUT_DIR/ipmi_sensors_$TIMESTAMP.txt" 2>/dev/null
        ipmitool fru list > "$HW_OUTPUT_DIR/ipmi_fru_$TIMESTAMP.txt" 2>/dev/null
    fi
    
    # Temperature and power information
    if [ -d "/sys/class/hwmon" ]; then
        find /sys/class/hwmon -name "temp*_input" -exec cat {} \; > "$HW_OUTPUT_DIR/temperatures_$TIMESTAMP.txt" 2>/dev/null
        find /sys/class/hwmon -name "fan*_input" -exec cat {} \; > "$HW_OUTPUT_DIR/fan_speeds_$TIMESTAMP.txt" 2>/dev/null
    fi
    
    # GPU information (if available)
    if command -v nvidia-smi &> /dev/null; then
        nvidia-smi -q > "$HW_OUTPUT_DIR/nvidia_smi_$TIMESTAMP.txt" 2>/dev/null
        nvidia-smi -q -d TEMPERATURE,POWER,CLOCK > "$HW_OUTPUT_DIR/nvidia_detailed_$TIMESTAMP.txt" 2>/dev/null
        nvidia-smi --query-gpu=timestamp,name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv > "$HW_OUTPUT_DIR/nvidia_metrics_$TIMESTAMP.csv" 2>/dev/null
    fi
    
    # PCI devices
    lspci -v > "$HW_OUTPUT_DIR/lspci_$TIMESTAMP.txt" 2>/dev/null
    
    # USB devices
    lsusb > "$HW_OUTPUT_DIR/lsusb_$TIMESTAMP.txt" 2>/dev/null
    
    chown -R embele:embele "$HW_OUTPUT_DIR"
    log_message "Hardware logs collected to $HW_OUTPUT_DIR"
}

# 5. Collect Kernel and Module Logs
collect_kernel_logs() {
    log_message "Collecting kernel and module logs..."
    
    KERNEL_OUTPUT_DIR="$LOG_DIR/kernel_logs_$TIMESTAMP"
    mkdir -p "$KERNEL_OUTPUT_DIR"
    
    # Kernel modules
    lsmod > "$KERNEL_OUTPUT_DIR/lsmod_$TIMESTAMP.txt"
    
    # Kernel parameters
    sysctl -a > "$KERNEL_OUTPUT_DIR/sysctl_$TIMESTAMP.txt" 2>/dev/null
    
    # Kernel ring buffer
    dmesg > "$KERNEL_OUTPUT_DIR/dmesg_full_$TIMESTAMP.txt"
    
    # Boot logs
    journalctl -b > "$KERNEL_OUTPUT_DIR/boot_log_$TIMESTAMP.txt" 2>/dev/null
    
    # System services
    systemctl list-units --failed > "$KERNEL_OUTPUT_DIR/failed_services_$TIMESTAMP.txt" 2>/dev/null
    systemctl status > "$KERNEL_OUTPUT_DIR/systemctl_status_$TIMESTAMP.txt" 2>/dev/null
    
    chown -R embele:embele "$KERNEL_OUTPUT_DIR"
    log_message "Kernel logs collected to $KERNEL_OUTPUT_DIR"
}

# 6. Create system summary report
create_system_summary() {
    log_message "Creating system summary report..."
    
    SUMMARY_FILE="$LOG_DIR/system_summary_$TIMESTAMP.txt"
    
    cat > "$SUMMARY_FILE" << EOF
HPC System Log Collection Summary
=================================
Collection Time: $(date)
Hostname: $(hostname)
Collected by: ROOT
Target Directory: $LOG_DIR

System Information:
- Hostname: $(hostname)
- Kernel: $(uname -r)
- OS: $(cat /etc/redhat-release 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME)
- Uptime: $(uptime)
- Load Average: $(cat /proc/loadavg)
- Memory: $(free -h | grep Mem)
- CPU: $(lscpu | grep "Model name" | cut -d: -f2 | xargs)

Directories Created:
$(find "$LOG_DIR" -maxdepth 1 -type d -name "*_$TIMESTAMP" | sort)

File Counts:
$(find "$LOG_DIR" -name "*_$TIMESTAMP*" -type f | wc -l) total files collected

Disk Usage:
$(du -sh "$LOG_DIR"/*_$TIMESTAMP 2>/dev/null)

Storage Information:
$(df -h "$LOG_DIR")

Collection Log:
$(tail -20 "$LOG_DIR/system_collection.log")
EOF

    chown embele:embele "$SUMMARY_FILE"
    log_message "System summary report created: $SUMMARY_FILE"
}

# Main execution
main() {
    log_message "=== HPC System Log Collection Started ==="
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: This script must be run as root"
        echo "Usage: sudo $0"
        exit 1
    fi
    
    # Collect all system logs
    collect_system_logs
    collect_lustre_logs
    collect_infiniband_logs
    collect_hardware_logs
    collect_kernel_logs
    
    # Create summary
    create_system_summary
    
    # Set proper ownership
    chown -R embele:embele "$LOG_DIR"
    
    log_message "=== HPC System Log Collection Completed ==="
    
    # Display summary
    echo
    echo "System Collection Summary:"
    echo "========================="
    echo "Total files collected: $(find "$LOG_DIR" -name "*_$TIMESTAMP*" -type f | wc -l)"
    echo "Total size: $(du -sh "$LOG_DIR"/*_$TIMESTAMP 2>/dev/null | awk '{print $1}' | paste -sd+ | bc 2>/dev/null || echo "Unknown")"
    echo "Summary report: $SUMMARY_FILE"
    echo "All logs stored in: $LOG_DIR"
}

# Execute main function
main "$@"

