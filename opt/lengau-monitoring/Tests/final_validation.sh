#!/bin/bash

echo "🐆 LENGAU HPC MONITORING SYSTEM - FINAL VALIDATION"
echo "=================================================="
echo "Validation Time: $(date)"
echo ""

# Function to test endpoint with timeout
test_endpoint_with_timeout() {
    local name=$1
    local port=$2
    local timeout=${3:-5}
    
    echo -n "Testing $name (port $port)... "
    
    if timeout $timeout curl -s http://localhost:$port/metrics >/dev/null 2>&1; then
        local count=$(timeout $timeout curl -s http://localhost:$port/metrics 2>/dev/null | grep -c "^[a-zA-Z]" 2>/dev/null)
        echo "✅ OK ($count metrics)"
        return 0
    else
        echo "❌ FAILED"
        return 1
    fi
}

# Test all collectors
echo "📊 COLLECTOR ENDPOINT TESTS:"
echo "============================"

passed=0
total=0

# Test each collector
collectors=(
    "Lengau Simplified Metrics:8084"
    "HPC Log Exporter:8081"
    "PBS Metrics Exporter:8085"
    "Network Metrics:8086"
    "Storage Metrics:8087"
    "User Activity:8088"
    "Security Events:8089"
)

for collector in "${collectors[@]}"; do
    name=$(echo "$collector" | cut -d: -f1)
    port=$(echo "$collector" | cut -d: -f2)
    
    if test_endpoint_with_timeout "$name" "$port"; then
        ((passed++))
    fi
    ((total++))
done

echo ""
echo "📈 COLLECTOR TEST RESULTS:"
echo "========================="
echo "Passed: $passed/$total collectors"

if [ $passed -eq $total ]; then
    echo "🎉 ALL COLLECTORS WORKING!"
    collector_status="✅ PASS"
else
    echo "⚠️  Some collectors need attention"
    collector_status="⚠️  PARTIAL"
fi

# Test core services
echo ""
echo "🔧 CORE SERVICES TEST:"
echo "====================="

core_passed=0
core_total=0

# Test Prometheus
echo -n "Testing Prometheus... "
if timeout 10 curl -s http://localhost:9090/-/healthy >/dev/null 2>&1; then
    echo "✅ OK"
    ((core_passed++))
else
    echo "❌ FAILED"
fi
((core_total++))

# Test Grafana
echo -n "Testing Grafana... "
if timeout 10 curl -s http://localhost:3000/api/health >/dev/null 2>&1; then
    echo "✅ OK"
    ((core_passed++))
else
    echo "❌ FAILED"
fi
((core_total++))

echo ""
echo "📈 CORE SERVICES RESULTS:"
echo "========================"
echo "Passed: $core_passed/$core_total services"

if [ $core_passed -eq $core_total ]; then
    echo "🎉 ALL CORE SERVICES WORKING!"
    core_status="✅ PASS"
else
    echo "⚠️  Some core services need attention"
    core_status="⚠️  PARTIAL"
fi

# Test Prometheus targets
echo ""
echo "🎯 PROMETHEUS TARGETS TEST:"
echo "=========================="

if timeout 10 curl -s http://localhost:9090/api/v1/targets >/dev/null 2>&1; then
    echo "✅ Prometheus API accessible"
    
    # Count healthy targets
    targets_response=$(timeout 10 curl -s http://localhost:9090/api/v1/targets 2>/dev/null)
    if [ -n "$targets_response" ]; then
        healthy_count=$(echo "$targets_response" | grep -o '"health":"up"' | wc -l)
        total_targets=$(echo "$targets_response" | grep -o '"health":"[^"]*"' | wc -l)
        echo "📊 Healthy targets: $healthy_count/$total_targets"
        
        if [ $healthy_count -gt 0 ]; then
            targets_status="✅ PASS"
        else
            targets_status="❌ FAIL"
        fi
    else
        echo "⚠️  Unable to parse targets"
        targets_status="⚠️  UNKNOWN"
    fi
else
    echo "❌ Prometheus API not accessible"
    targets_status="❌ FAIL"
fi

# Generate final report
echo ""
echo "🏆 FINAL VALIDATION REPORT:"
echo "=========================="
echo "Collectors:        $collector_status"
echo "Core Services:     $core_status"
echo "Prometheus Targets: $targets_status"
echo ""

# Overall status
if [ "$collector_status" = "✅ PASS" ] && [ "$core_status" = "✅ PASS" ] && [ "$targets_status" = "✅ PASS" ]; then
    echo "🎉 SYSTEM STATUS: FULLY OPERATIONAL"
    echo "🚀 Lengau HPC Monitoring System is ready for production!"
    overall_status=0
elif [ $passed -gt $((total/2)) ] && [ $core_passed -gt 0 ]; then
    echo "⚠️  SYSTEM STATUS: PARTIALLY OPERATIONAL"
    echo "�� Most components working, minor issues to resolve"
    overall_status=1
else
    echo "❌ SYSTEM STATUS: NEEDS ATTENTION"
    echo "🛠️  Multiple components need troubleshooting"
    overall_status=2
fi

echo ""
echo "🌐 ACCESS INFORMATION:"
echo "====================="
echo "• Prometheus Dashboard: http://172.18.0.128:9090"
echo "• Grafana Dashboard:    http://172.18.0.128:3000"
echo "• Metrics Endpoints:    http://172.18.0.128:808X/metrics"
echo ""
echo "📋 QUICK COMMANDS:"
echo "=================="
echo "• View all metrics:     ./view_all_metrics.sh"
echo "• Check service logs:   ./manage_all_collectors_enhanced.sh logs-new"
echo "• Restart collectors:   ./manage_all_collectors_enhanced.sh restart-new"
echo "• Full system status:   ./manage_all_collectors_enhanced.sh full-status"

exit $overall_status
