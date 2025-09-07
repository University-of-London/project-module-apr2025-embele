#!/bin/bash
echo "📊 Lengau AI System Status"
echo "=========================="
echo ""
echo "🤖 Services:"
systemctl status lengau-detector --no-pager -l
echo ""
systemctl status lengau-dashboard --no-pager -l
echo ""
echo "📁 Recent logs:"
echo "Detector: $(tail -1 /opt/lengau-monitoring/logs/detector_service.log 2>/dev/null || echo 'No logs')"
echo "Dashboard: $(tail -1 /opt/lengau-monitoring/logs/dashboard_service.log 2>/dev/null || echo 'No logs')"
echo ""
echo "📊 Data status:"
echo "Detections today: $(find /opt/lengau-monitoring/data/detections -name "*$(date +%Y%m%d)*" -type f | wc -l)"
echo "Alerts today: $(find /opt/lengau-monitoring/data/alerts -name "*$(date +%Y%m%d)*" -type f | wc -l)"
