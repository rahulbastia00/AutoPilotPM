#!/bin/bash

echo "🚀 Starting Product Management Task Splitter Services..."

# Kill any existing processes on the ports
echo "🧹 Cleaning up existing processes..."
lsof -ti:5000 | xargs kill -9 2>/dev/null || true
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# Also kill any existing python/node processes that might be running our services
pkill -f "uvicorn.*react_split" 2>/dev/null || true
pkill -f "npm start" 2>/dev/null || true
pkill -f "node.*server" 2>/dev/null || true

echo "⏳ Waiting for ports to be freed..."
sleep 2

# Start FastAPI Python service on port 5000
echo "🐍 Starting FastAPI service on port 5000..."
python -m uvicorn agents.react_split:app --host 0.0.0.0 --port 5000 --reload &
FASTAPI_PID=$!

# Wait a moment for FastAPI to start
echo "⏳ Waiting for FastAPI to initialize..."
sleep 5

# Check if FastAPI started successfully
if ! kill -0 $FASTAPI_PID 2>/dev/null; then
    echo "❌ FastAPI failed to start"
    exit 1
fi

# Start Node.js service on port 8000
echo "🟢 Starting Node.js service on port 8000..."
PORT=8000 npm start &
NODEJS_PID=$!

# Wait for Node.js to start
echo "⏳ Waiting for Node.js to initialize..."
sleep 3

# Check if Node.js started successfully
if ! kill -0 $NODEJS_PID 2>/dev/null; then
    echo "❌ Node.js failed to start"
    kill $FASTAPI_PID 2>/dev/null || true
    exit 1
fi

echo ""
echo "✅ Both services are running successfully!"
echo "   - FastAPI (Python): http://localhost:5000"
echo "   - Node.js API: http://localhost:8000"
echo ""
echo "📊 Service Status:"
echo "   - FastAPI PID: $FASTAPI_PID"
echo "   - Node.js PID: $NODEJS_PID"
echo ""
echo "🧪 Test with:"
echo "curl -X POST http://localhost:8000/plan -H 'Content-Type: application/json' -d '{\"goal\":\"Build a mobile e-commerce app for small businesses\"}'"
echo ""
echo "📝 Live reloading is enabled for both services"
echo "   - FastAPI will auto-reload on Python file changes"
echo "   - Node.js will auto-reload if you have nodemon configured"
echo ""
echo "Press Ctrl+C to stop both services"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    
    # Kill FastAPI
    if kill -0 $FASTAPI_PID 2>/dev/null; then
        echo "   Stopping FastAPI (PID: $FASTAPI_PID)..."
        kill $FASTAPI_PID 2>/dev/null || true
    fi
    
    # Kill Node.js
    if kill -0 $NODEJS_PID 2>/dev/null; then
        echo "   Stopping Node.js (PID: $NODEJS_PID)..."
        kill $NODEJS_PID 2>/dev/null || true
    fi
    
    # Final cleanup - kill any remaining processes on our ports
    lsof -ti:5000 | xargs kill -9 2>/dev/null || true
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    
    echo "✅ All services stopped"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup INT TERM EXIT

# Monitor services and restart if they crash
monitor_services() {
    while true do
        sleep 10
        
        # Check FastAPI
        if ! kill -0 $FASTAPI_PID 2>/dev/null; then
            echo "⚠️  FastAPI service crashed, restarting..."
            python -m uvicorn agents.react_split:app --host 0.0.0.0 --port 5000 --reload &
            FASTAPI_PID=$!
        fi
        
        # Check Node.js
        if ! kill -0 $NODEJS_PID 2>/dev/null; then
            echo "⚠️  Node.js service crashed, restarting..."
            PORT=8000 npm start &
            NODEJS_PID=$!
        fi
    done
}

# Start monitoring in background
monitor_services &
MONITOR_PID=$!

# Wait for processes
wait