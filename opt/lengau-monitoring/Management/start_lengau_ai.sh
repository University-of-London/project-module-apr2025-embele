#!/bin/bash
echo "🚀 Starting Lengau AI System..."
sudo systemctl start lengau-detector
sudo systemctl start lengau-dashboard
echo "✅ System started!"
systemctl status lengau-detector lengau-dashboard
