#!/usr/bin/env python3
"""
Lengau Optimized Security Events Prometheus Exporter
Enhanced security monitoring for HPC environments
"""

import subprocess
import time
import re
import os
from collections import defaultdict
from prometheus_client import start_http_server, Gauge, Counter, Histogram, Info
import logging
import signal
import sys
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LengauSecurityExporter:
    def __init__(self, port=8089, collection_interval=60, timeout=15):
        self.port = port
        self.collection_interval = collection_interval
        self.timeout = timeout
        self.running = True
        
        # Authentication Metrics
        self.auth_attempts_total = Counter('auth_attempts_total', 'Authentication attempts', ['type', 'result'])
        self.ssh_login_attempts = Counter('ssh_login_attempts_total', 'SSH login attempts', ['user', 'source_ip', 'result'])
        self.failed_login_attempts = Counter('failed_login_attempts_total', 'Failed login attempts', ['service', 'user'])
        self.successful_logins = Counter('successful_logins_total', 'Successful logins', ['service', 'user'])
        
        # User Activity Metrics
        self.active_users = Gauge('active_users_count', 'Currently active users')
        self.user_sessions = Gauge('user_sessions_count', 'User sessions by type', ['session_type'])
        self.sudo_usage = Counter('sudo_usage_total', 'Sudo command usage', ['user', 'command'])
        self.privilege_escalations = Counter('privilege_escalations_total', 'Privilege escalation attempts', ['user', 'method'])
        
        # System Security Metrics
        self.security_alerts = Counter('security_alerts_total', 'Security alerts', ['severity', 'type'])
        self.firewall_blocks = Counter('firewall_blocks_total', 'Firewall blocked connections', ['source_ip', 'port'])
        self.intrusion_attempts = Counter('intrusion_attempts_total', 'Intrusion attempts', ['type', 'source'])
        self.malware_detections = Counter('malware_detections_total', 'Malware detections', ['scanner', 'type'])
        
        # File System Security
        self.file_permission_changes = Counter('file_permission_changes_total', 'File permission changes', ['path', 'user'])
        self.suspicious_file_access = Counter('suspicious_file_access_total', 'Suspicious file access', ['path', 'user', 'action'])
        self.setuid_executions = Counter('setuid_executions_total', 'SETUID/SETGID executions', ['binary', 'user'])
        
        # Network Security
        self.network_anomalies = Counter('network_anomalies_total', 'Network anomalies', ['type', 'source'])
        self.port_scan_attempts = Counter('port_scan_attempts_total', 'Port scan attempts', ['source_ip', 'target_port'])
        self.suspicious_connections = Counter('suspicious_connections_total', 'Suspicious network connections', ['protocol', 'source', 'destination'])
        
        # System Integrity
        self.system_file_changes = Counter('system_file_changes_total', 'System file modifications', ['file', 'type'])
        self.configuration_changes = Counter('configuration_changes_total', 'Configuration changes', ['service', 'user'])
        self.package_changes = Counter('package_changes_total', 'Package installations/removals', ['action', 'package', 'user'])
        
        # Resource Abuse Detection
        self.resource_abuse = Counter('resource_abuse_total', 'Resource abuse attempts', ['type', 'user'])
        self.unusual_processes = Counter('unusual_processes_total', 'Unusual process executions', ['process', 'user'])
        self.high_resource_usage = Gauge('high_resource_usage_alerts', 'High resource usage alerts', ['resource', 'user'])
        
        # Performance Metrics
        self.security_collection_duration = Histogram('security_collection_duration_seconds', 'Time spent collecting security metrics', ['component'])
        self.security_collection_success = Gauge('security_collection_success', 'Security collection success flag')
        self.security_last_update = Gauge('security_last_update_timestamp', 'Last successful update timestamp')
        
        # System Info
        self.security_info = Info('security_system', 'Security monitoring system information')
        
        # Cache and state
        self._last_auth_check = 0
        self._last_syslog_position = 0
        self._known_users = set()
        self._suspicious_ips = set()
        
        # Security patterns
        self.security_patterns = {
            'failed_ssh': re.compile(r'Failed password for (\w+) from ([\d\.]+) port \d+'),
            'successful_ssh': re.compile(r'Accepted password for (\w+) from ([\d\.]+) port \d+'),
            'sudo_usage': re.compile(r'(\w+) : TTY=\w+ ; PWD=.+ ; USER=root ; COMMAND=(.+)'),
            'su_usage': re.compile(r'su: \(to (\w+)\) (\w+) on'),
            'invalid_user': re.compile(r'Invalid user (\w+) from ([\d\.]+)'),
            'root_login': re.compile(r'ROOT LOGIN.*from ([\d\.]+)'),
            'permission_denied': re.compile(r'Permission denied.*user (\w+)'),
            'file_permission': re.compile(r'chmod.*?(\S+).*?by user (\w+)'),
            'suspicious_process': re.compile(r'Process: (.+?) PID: \d+ User: (\w+)')
        }
    
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
    
    def collect_authentication_metrics(self):
        """Collect authentication and login metrics"""
        start_time = time.time()
        
        try:
            # Check auth.log for recent entries
            auth_logs = ['/var/log/auth.log', '/var/log/secure']
            
            for log_file in auth_logs:
                if os.path.exists(log_file):
                    self._parse_auth_log(log_file)
                    break
            
            # Check who is currently logged in
            self._collect_active_sessions()
            
            self.security_collection_duration.labels(component='authentication').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting authentication metrics: {e}")
    
    def _parse_auth_log(self, log_file):
        """Parse authentication log file"""
        try:
            # Read recent entries (last 1000 lines for performance)
            returncode, stdout, stderr = self.run_command(['tail', '-n', '1000', log_file])
            
            if returncode != 0:
                return
            
            current_time = time.time()
            for line in stdout.split('\n'):
                if not line.strip():
                    continue
                
                # SSH authentication attempts
                match = self.security_patterns['failed_ssh'].search(line)
                if match:
                    user, source_ip = match.groups()
                    self.ssh_login_attempts.labels(user=user, source_ip=source_ip, result='failed').inc()
                    self.failed_login_attempts.labels(service='ssh', user=user).inc()
                    self._suspicious_ips.add(source_ip)
                    continue
                
                match = self.security_patterns['successful_ssh'].search(line)
                if match:
                    user, source_ip = match.groups()
                    self.ssh_login_attempts.labels(user=user, source_ip=source_ip, result='success').inc()
                    self.successful_logins.labels(service='ssh', user=user).inc()
                    self._known_users.add(user)
                    continue
                
                # Sudo usage
                match = self.security_patterns['sudo_usage'].search(line)
                if match:
                    user, command = match.groups()
                    # Truncate long commands
                    command = command[:50] + "..." if len(command) > 50 else command
                    self.sudo_usage.labels(user=user, command=command).inc()
                    continue
                
                # Invalid users
                match = self.security_patterns['invalid_user'].search(line)
                if match:
                    user, source_ip = match.groups()
                    self.intrusion_attempts.labels(type='invalid_user', source=source_ip).inc()
                    self.security_alerts.labels(severity='medium', type='invalid_user').inc()
                    continue
                
                # Root login attempts
                if self.security_patterns['root_login'].search(line):
                    match = self.security_patterns['root_login'].search(line)
                    source_ip = match.group(1) if match else 'unknown'
                    self.privilege_escalations.labels(user='root', method='direct_login').inc()
                    self.security_alerts.labels(severity='high', type='root_login').inc()
                    continue
                    
        except Exception as e:
            logger.debug(f"Error parsing auth log: {e}")
    
    def _collect_active_sessions(self):
        """Collect information about active user sessions"""
        try:
            # Count active users
            returncode, stdout, stderr = self.run_command(['who'])
            if returncode == 0:
                active_users = len([line for line in stdout.strip().split('\n') if line.strip()])
                self.active_users.set(active_users)
            
            # Count session types
            returncode, stdout, stderr = self.run_command(['w', '-h'])
            if returncode == 0:
                session_types = defaultdict(int)
                for line in stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            tty = parts[1]
                            if tty.startswith('pts'):
                                session_types['ssh'] += 1
                            elif tty.startswith('tty'):
                                session_types['console'] += 1
                            else:
                                session_types['other'] += 1
                
                for session_type, count in session_types.items():
                    self.user_sessions.labels(session_type=session_type).set(count)
                    
        except Exception as e:
            logger.debug(f"Error collecting session info: {e}")
    
    def collect_system_security_metrics(self):
        """Collect system security metrics"""
        start_time = time.time()
        
        try:
            # Check for suspicious processes
            self._check_suspicious_processes()
            
            # Check system logs for security events
            self._check_system_logs()
            
            # Check for unusual network activity
            self._check_network_security()
            
            # Check file system integrity
            self._check_file_integrity()
            
            self.security_collection_duration.labels(component='system').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting system security metrics: {e}")
    
    def _check_suspicious_processes(self):
        """Check for suspicious running processes"""
        try:
            returncode, stdout, stderr = self.run_command(['ps', 'aux'])
            if returncode != 0:
                return
            
            suspicious_commands = ['nc', 'netcat', 'ncat', 'socat', 'telnet', 'wget', 'curl']
            unusual_locations = ['/tmp/', '/var/tmp/', '/dev/shm/']
            
            for line in stdout.split('\n')[1:]:  # Skip header
                if not line.strip():
                    continue
                
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    user = parts[0]
                    command = parts[10]
                    
                    # Check for suspicious commands
                    for sus_cmd in suspicious_commands:
                        if sus_cmd in command.lower():
                            self.unusual_processes.labels(process=sus_cmd, user=user).inc()
                            break
                    
                    # Check for processes running from unusual locations
                    for location in unusual_locations:
                        if location in command:
                            self.suspicious_file_access.labels(path=location, user=user, action='execute').inc()
                            break
                            
        except Exception as e:
            logger.debug(f"Error checking processes: {e}")
    
    def _check_system_logs(self):
        """Check system logs for security events"""
        try:
            # Check syslog for security events
            syslog_files = ['/var/log/syslog', '/var/log/messages']
            
            for log_file in syslog_files:
                if os.path.exists(log_file):
                    returncode, stdout, stderr = self.run_command(['tail', '-n', '500', log_file])
                    
                    if returncode == 0:
                        for line in stdout.split('\n'):
                            line_lower = line.lower()
                            
                            # Check for various security events
                            if 'denied' in line_lower or 'blocked' in line_lower:
                                self.security_alerts.labels(severity='low', type='access_denied').inc()
                            elif 'attack' in line_lower or 'intrusion' in line_lower:
                                self.security_alerts.labels(severity='high', type='attack').inc()
                            elif 'malware' in line_lower or 'virus' in line_lower:
                                self.malware_detections.labels(scanner='system', type='detected').inc()
                            elif 'firewall' in line_lower and 'drop' in line_lower:
                                self.firewall_blocks.labels(source_ip='unknown', port='unknown').inc()
                    break
                    
        except Exception as e:
            logger.debug(f"Error checking system logs: {e}")
    
    def _check_network_security(self):
        """Check for network security issues"""
        try:
            # Check for unusual network connections
            returncode, stdout, stderr = self.run_command(['netstat', '-tuln'])
            if returncode == 0:
                listening_ports = []
                for line in stdout.split('\n'):
                    if 'LISTEN' in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            addr_port = parts[3]
                            if ':' in addr_port:
                                port = addr_port.split(':')[-1]
                                listening_ports.append(port)
                
                # Check for unusual high ports
                for port in listening_ports:
                    try:
                        port_num = int(port)
                        if port_num > 49152:  # Dynamic/private ports
                            self.network_anomalies.labels(type='high_port', source='localhost').inc()
                    except:
                        pass
            
            # Check established connections
            returncode, stdout, stderr = self.run_command(['netstat', '-tn'])
            if returncode == 0:
                external_connections = 0
                for line in stdout.split('\n'):
                    if 'ESTABLISHED' in line:
                        external_connections += 1
                
                # If too many external connections, it might be suspicious
                if external_connections > 100:
                    self.network_anomalies.labels(type='many_connections', source='localhost').inc()
                    
        except Exception as e:
            logger.debug(f"Error checking network security: {e}")
    
    def _check_file_integrity(self):
        """Check file system integrity"""
        try:
            # Check for world-writable files in sensitive locations
            sensitive_dirs = ['/etc', '/usr/bin', '/usr/sbin', '/bin', '/sbin']
            
            for directory in sensitive_dirs:
                if os.path.exists(directory):
                    returncode, stdout, stderr = self.run_command(['find', directory, '-type', 'f', '-perm', '-002', '-ls'], timeout=10)
                    
                    if returncode == 0 and stdout.strip():
                        # Found world-writable files
                        file_count = len(stdout.strip().split('\n'))
                        for i in range(min(file_count, 5)):  # Limit to avoid too many metrics
                            self.system_file_changes.labels(file=f'{directory}_file_{i}', type='world_writable').inc()
            
            # Check for SUID/SGID files
            returncode, stdout, stderr = self.run_command(['find', '/', '-type', 'f', '(', '-perm', '-4000', '-o', '-perm', '-2000', ')', '-ls'], timeout=10)
            
            if returncode == 0:
                suid_count = len([line for line in stdout.split('\n') if line.strip()])
                if suid_count > 50:  # Unusual number of SUID files
                    self.security_alerts.labels(severity='medium', type='many_suid_files').inc()
                    
        except Exception as e:
            logger.debug(f"Error checking file integrity: {e}")
    
    def collect_resource_abuse_metrics(self):
        """Collect resource abuse detection metrics"""
        start_time = time.time()
        
        try:
            # Check for processes using excessive resources
            returncode, stdout, stderr = self.run_command(['ps', 'aux', '--sort=-%cpu'])
            if returncode == 0:
                lines = stdout.split('\n')[1:11]  # Top 10 processes
                for line in lines:
                    if not line.strip():
                        continue
                    
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        user = parts[0]
                        cpu_percent = float(parts[2])
                        mem_percent = float(parts[3])
                        
                        # Flag high resource usage
                        if cpu_percent > 90:
                            self.high_resource_usage_alerts.labels(resource='cpu', user=user).set(cpu_percent)
                            self.resource_abuse.labels(type='cpu_abuse', user=user).inc()
                        
                        if mem_percent > 80:
                            self.high_resource_usage_alerts.labels(resource='memory', user=user).set(mem_percent)
                            self.resource_abuse.labels(type='memory_abuse', user=user).inc()
            
            self.security_collection_duration.labels(component='resource_abuse').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting resource abuse metrics: {e}")
    
    def collect_metrics(self):
        """Main metrics collection function"""
        start_time = time.time()
        
        try:
            # Collect authentication metrics
            self.collect_authentication_metrics()
            
            # Collect system security metrics
            self.collect_system_security_metrics()
            
            # Collect resource abuse metrics
            self.collect_resource_abuse_metrics()
            
            # Update system info
            self.security_info.info({
                'collection_time': datetime.now().isoformat(),
                'known_users_count': str(len(self._known_users)),
                'suspicious_ips_count': str(len(self._suspicious_ips)),
                'monitoring_status': 'active'
            })
            
            # Update success metrics
            self.security_collection_success.set(1)
            self.security_last_update.set(time.time())
            
            collection_time = time.time() - start_time
            logger.info(f"🔒 Security metrics collected in {collection_time:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Failed to collect security metrics: {e}")
            self.security_collection_success.set(0)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("🛑 Received shutdown signal")
        self.running = False
    
    def run(self):
        """Main run loop"""
        logger.info(f"🚀 Starting Lengau Security Exporter on port {self.port}")
        logger.info(f"🔒 Security monitoring active (interval: {self.collection_interval}s)")
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # Start HTTP server
        start_http_server(self.port)
        logger.info(f"📊 Security metrics available at http://localhost:{self.port}/metrics")
        
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
        
        logger.info("👋 Security Exporter stopped")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Lengau Security Prometheus Exporter')
    parser.add_argument('--port', type=int, default=8089, help='Port to serve metrics on')
    parser.add_argument('--interval', type=int, default=60, help='Collection interval in seconds')
    parser.add_argument('--timeout', type=int, default=15, help='Command timeout in seconds')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    exporter = LengauSecurityExporter(
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
