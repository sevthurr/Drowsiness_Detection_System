"""
Simple Python Server for ESP8266 Drowsiness Detection System
This is a minimal example server for testing the ESP8266 firmware.
Run this on your laptop/PC on the same network as the ESP8266.

Usage:
    python server_example.py

The server will:
- Listen on port 5000
- Receive POST requests from ESP8266
- Send back alert commands based on tilt angle
- Log all interactions
"""

from flask import Flask, request, jsonify
import json
from datetime import datetime

app = Flask(__name__)

# Simple threshold for demonstration
TILT_ALERT_THRESHOLD = 30.0
TILT_CRITICAL_THRESHOLD = 45.0

@app.route('/sensor-data', methods=['POST'])
def receive_sensor_data():
    """
    Endpoint to receive sensor data from ESP8266
    """
    try:
        # Get JSON data from ESP8266
        data = request.get_json()
        
        # Log received data
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] Received from {data.get('device_id', 'Unknown')}:")
        print(f"  Tilt Angle: {data.get('tilt_angle', 0):.1f}°")
        print(f"  Over Threshold: {data.get('tilt_over_threshold', False)}")
        print(f"  Duration: {data.get('tilt_duration_ms', 0)} ms")
        print(f"  Button Pressed: {data.get('button_pressed', False)}")
        print(f"  WiFi RSSI: {data.get('wifi_rssi', 0)} dBm")
        
        # Determine alert level based on tilt angle
        tilt = data.get('tilt_angle', 0)
        button = data.get('button_pressed', False)
        
        # Build response
        response = {
            "visual_score": 0.0,
            "alert_level": "OK",
            "motor_on": False,
            "buzzer_on": False,
            "red_led": False,
            "green_led": True,
            "ack_required": False
        }
        
        # If button pressed, clear alerts
        if button:
            print("  → Button pressed, clearing alerts")
            return jsonify(response)
        
        # Check tilt thresholds
        if tilt >= TILT_CRITICAL_THRESHOLD:
            response.update({
                "alert_level": "Level 2",
                "motor_on": True,
                "buzzer_on": True,
                "red_led": True,
                "green_led": False,
                "ack_required": True,
                "visual_score": 0.9
            })
            print("  → CRITICAL ALERT (Level 2)")
            
        elif tilt >= TILT_ALERT_THRESHOLD:
            response.update({
                "alert_level": "Level 1",
                "motor_on": True,
                "buzzer_on": True,
                "red_led": True,
                "green_led": False,
                "ack_required": True,
                "visual_score": 0.6
            })
            print("  → Warning Alert (Level 1)")
            
        else:
            print("  → Normal (OK)")
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error processing request: {e}")
        # Return safe default response
        return jsonify({
            "alert_level": "OK",
            "motor_on": False,
            "buzzer_on": False,
            "red_led": False,
            "green_led": True
        })

@app.route('/status', methods=['GET'])
def status():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "server": "ESP8266 Drowsiness Detection",
        "version": "1.0"
    })

if __name__ == '__main__':
    print("=" * 50)
    print("ESP8266 Drowsiness Detection - Test Server")
    print("=" * 50)
    print("\nServer starting on http://0.0.0.0:5000")
    print(f"Tilt Alert Threshold: {TILT_ALERT_THRESHOLD}°")
    print(f"Tilt Critical Threshold: {TILT_CRITICAL_THRESHOLD}°")
    print("\nWaiting for ESP8266 connections...\n")
    
    # Run Flask server
    # Use host='0.0.0.0' to accept connections from ESP8266 on network
    app.run(host='0.0.0.0', port=5000, debug=False)
