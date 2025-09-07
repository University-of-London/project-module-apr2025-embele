#!/usr/bin/env python3
"""
Live metrics viewer for Lengau monitoring
"""

import sqlite3
import time
import os
from pathlib import Path
from datetime import datetime, timedelta

class LiveMetricsViewer:
    def __init__(self, db_path="/opt/lengau-monitoring/scripts/lengau_metrics.db"):
        self.db_path = Path(db_path)
    
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def get_recent_metrics(self, minutes=5):
        """Get metrics from last N minutes"""
        if not self.db_path.exists():
            return []
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Get metrics from last N minutes
                cutoff_time = (datetime.now() - timedelta(minutes=minutes)).isoformat()
                
                cursor.execute("""
                    SELECT node_name, cpu_usage, memory_usage, load_average, 
                           timestamp, created_at
                    FROM metrics 
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                """, (cutoff_time,))
                
                return cursor.fetchall()
                
        except Exception as e:
            print(f"❌ Database error: {e}")
            return []
    
    def get_node_summary(self):
        """Get summary statistics by node type"""
        if not self.db_path.exists():
            return {}
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                
                # Get latest metrics per node
                cursor.execute("""
                    SELECT node_name, cpu_usage, memory_usage, load_average,
                           MAX(timestamp) as latest_time
                    FROM metrics 
                    GROUP BY node_name
                    HAVING latest_time > datetime('now', '-10 minutes')
                    ORDER BY node_name
                """)
                
                results = cursor.fetchall()
                
                # Categorize nodes
                summary = {
                    'compute': [],
                    'login': [],
                    'gpu': [],
                    'fat': [],
                    'other': []
                }
                
                for row in results:
                    node_name = row[0]
                    if node_name.startswith('cnode'):
                        summary['compute'].append(row)
                    elif node_name.startswith('login'):
                        summary['login'].append(row)
                    elif node_name.startswith('gpu'):
                        summary['gpu'].append(row)
                    elif node_name.startswith('fat'):
                        summary['fat'].append(row)
                    else:
                        summary['other'].append(row)
                
                return summary
                
        except Exception as e:
            print(f"❌ Database error: {e}")
            return {}
    
    def display_summary(self):
        """Display node summary"""
        summary = self.get_node_summary()
        
        print("🐆 LENGAU CLUSTER MONITORING DASHBOARD")
        print("=" * 60)
        print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        total_nodes = sum(len(nodes) for nodes in summary.values())
        print(f"📊 Active Nodes: {total_nodes}")
        
        for category, nodes in summary.items():
            if nodes:
                print(f"\n🔹 {category.upper()} NODES ({len(nodes)})")
                print(f"{'Node':<12} {'CPU%':<6} {'MEM%':<6} {'Load':<6} {'Status':<8}")
                print("-" * 45)
                
                for node in nodes[:10]:  # Show max 10 per category
                    node_name, cpu, mem, load, timestamp = node
                    
                    # Determine status
                    if cpu > 80 or mem > 90:
                        status = "🔴 HIGH"
                    elif cpu > 50 or mem > 70:
                        status = "🟡 MED"
                    elif cpu > 0 or mem > 0:
                        status = "🟢 OK"
                    else:
                        status = "⚪ IDLE"
                    
                    print(f"{node_name:<12} {cpu:<6.1f} {mem:<6.1f} {load:<6.2f} {status:<8}")
                
                if len(nodes) > 10:
                    print(f"... and {len(nodes) - 10} more nodes")
    
    def display_alerts(self):
        """Display any high-usage alerts"""
        recent_metrics = self.get_recent_metrics(minutes=5)
        
        alerts = []
        for metric in recent_metrics:
            node_name, cpu, mem, load, timestamp, created_at = metric
            
            if cpu > 90:
                alerts.append(f"🔴 {node_name}: High CPU {cpu:.1f}%")
            if mem > 95:
                alerts.append(f"🔴 {node_name}: High Memory {mem:.1f}%")
            if load > 20:
                alerts.append(f"🟡 {node_name}: High Load {load:.2f}")
        
        if alerts:
            print(f"\n🚨 ALERTS ({len(alerts)})")
            print("-" * 30)
            for alert in alerts[:5]:  # Show max 5 alerts
                print(f"  {alert}")
        else:
            print(f"\n✅ No alerts - all systems normal")
    
    def run_live_view(self, refresh_seconds=30):
        """Run live monitoring view"""
        try:
            while True:
                self.clear_screen()
                self.display_summary()
                self.display_alerts()
                
                print(f"\n🔄 Refreshing every {refresh_seconds}s... (Ctrl+C to exit)")
                time.sleep(refresh_seconds)
                
        except KeyboardInterrupt:
            print(f"\n👋 Monitoring stopped")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Live Lengau Metrics Viewer')
    parser.add_argument('--refresh', type=int, default=30,
                       help='Refresh interval in seconds')
    parser.add_argument('--once', action='store_true',
                       help='Show once and exit (no live refresh)')
    
    args = parser.parse_args()
    
    viewer = LiveMetricsViewer()
    
    if args.once:
        viewer.display_summary()
        viewer.display_alerts()
    else:
        viewer.run_live_view(refresh_seconds=args.refresh)

if __name__ == "__main__":
    main()

