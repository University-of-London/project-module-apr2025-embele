#!/usr/bin/env python3
"""
Lengau Optimized Network Prometheus Exporter
High-performance network metrics for HPC InfiniBand and Ethernet
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
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LengauNetworkExporter:
    def __init__(self, port=8086, collection_interval=30, timeout=15):
        self.port = port
        self.collection_interval = collection_interval
        self.timeout = timeout
        self.running = True
        
        # InfiniBand Metrics
        self.ib_port_state = Gauge('ib_port_state', 'InfiniBand port state (1=Active)', ['hca', 'port'])
        self.ib_port_physical_state = Gauge('ib_port_physical_state', 'InfiniBand port physical state', ['hca', 'port', 'state'])
        self.ib_port_rate_gbps = Gauge('ib_port_rate_gbps', 'InfiniBand port rate in Gbps', ['hca', 'port'])
        self.ib_port_width = Gauge('ib_port_width', 'InfiniBand port width', ['hca', 'port'])
        
        # InfiniBand Performance Counters
        self.ib_xmit_data_bytes = Counter('ib_xmit_data_bytes_total', 'InfiniBand transmitted data bytes', ['hca', 'port'])
        self.ib_rcv_data_bytes = Counter('ib_rcv_data_bytes_total', 'InfiniBand received data bytes', ['hca', 'port'])
        self.ib_xmit_packets = Counter('ib_xmit_packets_total', 'InfiniBand transmitted packets', ['hca', 'port'])
        self.ib_rcv_packets = Counter('ib_rcv_packets_total', 'InfiniBand received packets', ['hca', 'port'])
        
        # InfiniBand Error Counters
        self.ib_symbol_errors = Counter('ib_symbol_errors_total', 'InfiniBand symbol errors', ['hca', 'port'])
        self.ib_link_error_recovery = Counter('ib_link_error_recovery_total', 'InfiniBand link error recovery', ['hca', 'port'])
        self.ib_link_downed = Counter('ib_link_downed_total', 'InfiniBand link downed', ['hca', 'port'])
        self.ib_rcv_errors = Counter('ib_rcv_errors_total', 'InfiniBand receive errors', ['hca', 'port'])
        self.ib_xmit_discards = Counter('ib_xmit_discards_total', 'InfiniBand transmit discards', ['hca', 'port'])
        self.ib_rcv_constraint_errors = Counter('ib_rcv_constraint_errors_total', 'InfiniBand receive constraint errors', ['hca', 'port'])
        
        # Ethernet Interface Metrics
        self.net_receive_bytes = Counter('net_receive_bytes_total', 'Network received bytes', ['interface'])
        self.net_transmit_bytes = Counter('net_transmit_bytes_total', 'Network transmitted bytes', ['interface'])
        self.net_receive_packets = Counter('net_receive_packets_total', 'Network received packets', ['interface'])
        self.net_transmit_packets = Counter('net_transmit_packets_total', 'Network transmitted packets', ['interface'])
        self.net_receive_errors = Counter('net_receive_errors_total', 'Network receive errors', ['interface'])
        self.net_transmit_errors = Counter('net_transmit_errors_total', 'Network transmit errors', ['interface'])
        self.net_receive_dropped = Counter('net_receive_dropped_total', 'Network receive dropped', ['interface'])
        self.net_transmit_dropped = Counter('net_transmit_dropped_total', 'Network transmit dropped', ['interface'])
        
        # Interface Status
        self.net_interface_up = Gauge('net_interface_up', 'Network interface up status', ['interface'])
        self.net_interface_speed_mbps = Gauge('net_interface_speed_mbps', 'Network interface speed in Mbps', ['interface'])
        self.net_interface_mtu = Gauge('net_interface_mtu_bytes', 'Network interface MTU', ['interface'])
        
        # Network Connection Metrics
        self.net_tcp_connections = Gauge('net_tcp_connections', 'TCP connections by state', ['state'])
        self.net_udp_connections = Gauge('net_udp_connections', 'UDP connections')
        
        # Performance Metrics
        self.network_collection_duration = Histogram('network_collection_duration_seconds', 'Time spent collecting network metrics', ['component'])
        self.network_collection_success = Gauge('network_collection_success', 'Network collection success flag')
        self.network_last_update = Gauge('network_last_update_timestamp', 'Last successful update timestamp')
        
        # System Info
        self.network_info = Info('network_system', 'Network system information')
        
        # Cache
        self._cache = {}
        self._cache_time = {}
        self._cache_ttl = 20
        
        # Tool availability
        self.has_ibstat = self._check_command_available('ibstat')
        self.has_perfquery = self._check_command_available('perfquery')
        
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
    
    def _check_command_available(self, command):
        """Check if command is available"""
        try:
            result = subprocess.run([command, '--help'], capture_output=True, timeout=2)
            return result.returncode in [0, 1, 2]  # Many commands return 1 or 2 for --help
        except:
            return False
    
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
    
    def collect_infiniband_metrics(self):
        """Collect InfiniBand metrics"""
        start_time = time.time()
        
        if not self.has_ibstat:
            logger.debug("📡 InfiniBand tools not available")
            return
        
        try:
            # Get HCA list
            returncode, stdout, stderr = self.run_command(['ibstat', '-l'])
            if returncode != 0:
                logger.warning(f"⚠️ ibstat -l failed: {stderr}")
                return
            
            hcas = [hca.strip() for hca in stdout.strip().split('\n') if hca.strip()]
            
            for hca in hcas:
                self._collect_hca_metrics(hca)
            
            self.network_collection_duration.labels(component='infiniband').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting InfiniBand metrics: {e}")
    
    def _collect_hca_metrics(self, hca):
        """Collect metrics for a specific HCA"""
        try:
            # Get HCA info
            returncode, stdout, stderr = self.run_command(['ibstat', hca])
            if returncode != 0:
                return
            
            content = stdout
            
            # Parse port information
            port_blocks = re.split(r'Port (\d+):', content)
            for i in range(1, len(port_blocks), 2):
                if i + 1 < len(port_blocks):
                    port_num = port_blocks[i]
                    port_block = port_blocks[i + 1]
                    
                    self._parse_port_info(hca, port_num, port_block)
            
            # Get performance counters if available
            if self.has_perfquery:
                self._collect_performance_counters(hca)
                
        except Exception as e:
            logger.error(f"❌ Error processing HCA {hca}: {e}")
    
    def _parse_port_info(self, hca, port_num, port_block):
        """Parse port information from ibstat output"""
        try:
            # Extract port state
            state_match = re.search(r'State:\s*(\w+)', port_block)
            if state_match:
                state = state_match.group(1)
                state_value = 1 if state == 'Active' else 0
                self.ib_port_state.labels(hca=hca, port=port_num).set(state_value)
            
            # Extract physical state
            phys_state_match = re.search(r'Physical state:\s*(\w+)', port_block)
            if phys_state_match:
                phys_state = phys_state_match.group(1)
                self.ib_port_physical_state.labels(hca=hca, port=port_num, state=phys_state).set(1)
            
            # Extract port rate
            rate_match = re.search(r'Rate:\s*(\d+)', port_block)
            if rate_match:
                rate = int(rate_match.group(1))
                self.ib_port_rate_gbps.labels(hca=hca, port=port_num).set(rate)
            
            # Extract port width
            width_match = re.search(r'Width:\s*(\d+)X', port_block)
            if width_match:
                width = int(width_match.group(1))
                self.ib_port_width.labels(hca=hca, port=port_num).set(width)
                
        except Exception as e:
            logger.debug(f"Error parsing port info for {hca}:{port_num}: {e}")
    
    def _collect_performance_counters(self, hca):
        """Collect InfiniBand performance counters"""
        try:
            # Get port count first
            returncode, stdout, stderr = self.run_command(['ibstat', hca, '1'])
            if returncode != 0:
                return
            
            # Collect performance data for each port
            for port in ['1', '2']:  # Most HCAs have 1-2 ports
                returncode, stdout, stderr = self.run_command(['perfquery', '-C', hca, port])
                if returncode == 0:
                    self._parse_performance_counters(hca, port, stdout)
                    
        except Exception as e:
            logger.debug(f"Error collecting performance counters for {hca}: {e}")
    
    def _parse_performance_counters(self, hca, port, perf_content):
        """Parse performance counter output"""
        try:
            # Performance counters mapping
            counter_patterns = {
                'XmitData': (self.ib_xmit_data_bytes, r'XmitData:\.*(\d+)'),
                'RcvData': (self.ib_rcv_data_bytes, r'RcvData:\.*(\d+)'),
                'XmitPkts': (self.ib_xmit_packets, r'XmitPkts:\.*(\d+)'),
                'RcvPkts': (self.ib_rcv_packets, r'RcvPkts:\.*(\d+)'),
                'SymbolErrorCounter': (self.ib_symbol_errors, r'SymbolErrorCounter:\.*(\d+)'),
                'LinkErrorRecoveryCounter': (self.ib_link_error_recovery, r'LinkErrorRecoveryCounter:\.*(\d+)'),
                'LinkDownedCounter': (self.ib_link_downed, r'LinkDownedCounter:\.*(\d+)'),
                'PortRcvErrors': (self.ib_rcv_errors, r'PortRcvErrors:\.*(\d+)'),
                'PortXmitDiscards': (self.ib_xmit_discards, r'PortXmitDiscards:\.*(\d+)'),
                'PortRcvConstraintErrors': (self.ib_rcv_constraint_errors, r'PortRcvConstraintErrors:\.*(\d+)')
            }
            
            for counter_name, (metric, pattern) in counter_patterns.items():
                match = re.search(pattern, perf_content)
                if match:
                    value = int(match.group(1))
                    
                    # For data counters, convert to bytes (values are in 4-byte words)
                    if 'Data' in counter_name:
                        value = value * 4
                    
                    # Set counter value directly
                    metric.labels(hca=hca, port=port)._value._value = value
                    
        except Exception as e:
            logger.debug(f"Error parsing performance counters: {e}")
    
    def collect_ethernet_metrics(self):
        """Collect Ethernet interface metrics"""
        start_time = time.time()
        
        try:
            # Collect interface statistics
            with open('/proc/net/dev', 'r') as f:
                lines = f.readlines()
            
            for line in lines[2:]:  # Skip headers
                parts = line.split()
                if len(parts) >= 16:
                    interface = parts[0].rstrip(':')
                    
                    # Skip loopback and virtual interfaces for performance
                    if interface in ['lo'] or interface.startswith('docker') or interface.startswith('veth'):
                        continue
                    
                    # Receive metrics
                    rx_bytes = int(parts[1])
                    rx_packets = int(parts[2])
                    rx_errors = int(parts[3])
                    rx_dropped = int(parts[4])
                    
                    # Transmit metrics
                    tx_bytes = int(parts[9])
                    tx_packets = int(parts[10])
                    tx_errors = int(parts[11])
                    tx_dropped = int(parts[12])
                    
                    # Update metrics
                    self.net_receive_bytes.labels(interface=interface)._value._value = rx_bytes
                    self.net_transmit_bytes.labels(interface=interface)._value._value = tx_bytes
                    self.net_receive_packets.labels(interface=interface)._value._value = rx_packets
                    self.net_transmit_packets.labels(interface=interface)._value._value = tx_packets
                    self.net_receive_errors.labels(interface=interface)._value._value = rx_errors
                    self.net_transmit_errors.labels(interface=interface)._value._value = tx_errors
                    self.net_receive_dropped.labels(interface=interface)._value._value = rx_dropped
                    self.net_transmit_dropped.labels(interface=interface)._value._value = tx_dropped
                    
                    # Collect interface details
                    self._collect_interface_details(interface)
            
            self.network_collection_duration.labels(component='ethernet').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting Ethernet metrics: {e}")
    
    def _collect_interface_details(self, interface):
        """Collect detailed interface information"""
        try:
            # Check if interface is up
            operstate_file = f'/sys/class/net/{interface}/operstate'
            if os.path.exists(operstate_file):
                with open(operstate_file, 'r') as f:
                    operstate = f.read().strip()
                    self.net_interface_up.labels(interface=interface).set(1 if operstate == 'up' else 0)
            
            # Get interface speed
            speed_file = f'/sys/class/net/{interface}/speed'
            if os.path.exists(speed_file):
                try:
                    with open(speed_file, 'r') as f:
                        speed = int(f.read().strip())
                        self.net_interface_speed_mbps.labels(interface=interface).set(speed)
                except:
                    pass
            
            # Get MTU
            mtu_file = f'/sys/class/net/{interface}/mtu'
            if os.path.exists(mtu_file):
                try:
                    with open(mtu_file, 'r') as f:
                        mtu = int(f.read().strip())
                        self.net_interface_mtu.labels(interface=interface).set(mtu)
                except:
                    pass
                    
        except Exception as e:
            logger.debug(f"Error collecting details for {interface}: {e}")
    
    def collect_connection_metrics(self):
        """Collect network connection metrics"""
        start_time = time.time()
        
        try:
            # TCP connections
            with open('/proc/net/tcp', 'r') as f:
                tcp_lines = f.readlines()
            
            tcp_states = defaultdict(int)
            for line in tcp_lines[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 4:
                    state_hex = parts[3]
                    state_mapping = {
                        '01': 'ESTABLISHED',
                        '02': 'SYN_SENT',
                        '03': 'SYN_RECV',
                        '04': 'FIN_WAIT1',
                        '05': 'FIN_WAIT2',
                        '06': 'TIME_WAIT',
                        '07': 'CLOSE',
                        '08': 'CLOSE_WAIT',
                        '09': 'LAST_ACK',
                        '0A': 'LISTEN',
                        '0B': 'CLOSING'
                    }
                    
                    state_name = state_mapping.get(state_hex, 'UNKNOWN')
                    tcp_states[state_name] += 1
            
            for state, count in tcp_states.items():
                self.net_tcp_connections.labels(state=state).set(count)
            
            # UDP connections
            with open('/proc/net/udp', 'r') as f:
                udp_lines = f.readlines()
            
            udp_count = len(udp_lines) - 1  # Subtract header
            self.net_udp_connections.set(udp_count)
            
            self.network_collection_duration.labels(component='connections').observe(time.time() - start_time)
            
        except Exception as e:
            logger.error(f"❌ Error collecting connection metrics: {e}")
    
    def collect_metrics(self):
        """Main metrics collection function"""
        start_time = time.time()
        
        try:
            # Collect InfiniBand metrics
            if self.has_ibstat:
                self.get_cached_data('infiniband', self.collect_infiniband_metrics)
            
            # Collect Ethernet metrics
            self.collect_ethernet_metrics()
            
            # Collect connection metrics
            self.collect_connection_metrics()
            
            # Update system info
            self.network_info.info({
                'collection_time': datetime.now().isoformat(),
                'infiniband_available': str(self.has_ibstat),
                'perfquery_available': str(self.has_perfquery)
            })
            
            # Update success metrics
            self.network_collection_success.set(1)
            self.network_last_update.set(time.time())
            
            collection_time = time.time() - start_time
            logger.info(f"✅ Network metrics collected in {collection_time:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Failed to collect network metrics: {e}")
            self.network_collection_success.set(0)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("🛑 Received shutdown signal")
        self.running = False
    
    def run(self):
        """Main run loop"""
        logger.info(f"🚀 Starting Lengau Network Exporter on port {self.port}")
        logger.info(f"📡 InfiniBand support: {'✅' if self.has_ibstat else '❌'}")
        logger.info(f"📊 Performance counters: {'✅' if self.has_perfquery else '❌'}")
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # Start HTTP server
        start_http_server(self.port)
        logger.info(f"📊 Network metrics available at http://localhost:{self.port}/metrics")
        
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
        
        logger.info("👋 Network Exporter stopped")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Lengau Network Prometheus Exporter')
    parser.add_argument('--port', type=int, default=8086, help='Port to serve metrics on')
    parser.add_argument('--interval', type=int, default=30, help='Collection interval in seconds')
    parser.add_argument('--timeout', type=int, default=15, help='Command timeout in seconds')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    exporter = LengauNetworkExporter(
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
