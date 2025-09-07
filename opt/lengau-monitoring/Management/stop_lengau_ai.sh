#!/bin/bash
echo "🛑 Stopping Lengau AI System..."
sudo systemctl stop lengau-detector
sudo systemctl stop lengau-dashboard
echo "✅ System stopped!"
