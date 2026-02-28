# ESP8266 Driver Drowsiness Detection Firmware

Complete PlatformIO firmware for NodeMCU/ESP8266 hardware controller.

## 📋 Overview

This firmware runs on an ESP8266 (NodeMCU) and acts as the hardware controller for a wearable driver drowsiness detection system. It:

- Reads MPU6050 accelerometer for head-tilt detection
- Controls alert outputs (LEDs, vibration motor, buzzer)
- Communicates with Python server via WiFi/HTTP
- Implements local fallback alerts when server is unreachable

## 🔧 Hardware Requirements

### Components
- **NodeMCU 1.0 (ESP-12E Module)** or compatible ESP8266 board
- **MPU6050** 6-axis accelerometer/gyroscope module
- **Push button** (normally open)
- **Green LED** + 220Ω resistor
- **Red LED** + 220Ω resistor
- **Vibration motor** (3V DC)
- **NPN transistor** (e.g., 2N2222) for motor driver
- **Passive buzzer** (3-5V)
- **Breadboard** and jumper wires
- **USB cable** for programming

### Pin Connections

| Component | ESP8266 Pin | GPIO | Notes |
|-----------|-------------|------|-------|
| MPU6050 SDA | D2 | GPIO4 | I2C Data |
| MPU6050 SCL | D1 | GPIO5 | I2C Clock |
| Vibration Motor | D5 | GPIO14 | Via NPN transistor |
| Buzzer | D6 | GPIO12 | Direct or via transistor |
| Red LED | D7 | GPIO13 | + 220Ω resistor |
| Green LED | D0 | GPIO16 | + 220Ω resistor |
| Push Button | D3 | GPIO0 | INPUT_PULLUP (button to GND) |

**Important:** 
- MPU6050 VCC → 3.3V (not 5V!)
- All components share common GND
- Use NPN transistor for motor (base via 1kΩ resistor from D5)

## 📦 Required Libraries

The firmware uses the following Arduino libraries (auto-installed via PlatformIO):

1. **ElectronicCats MPU6050** (`electroniccats/mpu6050@^1.0.0`)
   - Used for MPU6050 sensor communication
   - Provides easy-to-use accelerometer and gyroscope access

2. **ArduinoJson** (`bblanchon/ArduinoJson@^6.21.3`)
   - JSON serialization/deserialization
   - Used for HTTP communication with Python server

3. **ESP8266WiFi** (built-in)
   - WiFi connectivity

4. **ESP8266HTTPClient** (built-in)
   - HTTP POST requests

5. **Wire** (built-in)
   - I2C communication

## 🚀 Getting Started

### 1. Install PlatformIO

Install the PlatformIO extension in VS Code or use PlatformIO CLI.

### 2. Clone/Download Project

Place the firmware files in your project directory:
```
your_project/
├── platformio.ini
└── src/
    └── main.cpp
```

### 3. Configure WiFi and Server

Edit `src/main.cpp` and update these constants:

```cpp
// WiFi credentials
const char* WIFI_SSID = "YourWiFiSSID";        // Your WiFi network name
const char* WIFI_PASSWORD = "YourWiFiPassword"; // Your WiFi password

// Python server endpoint
const char* SERVER_URL = "http://192.168.1.100:5000/sensor-data";

// Device ID (optional - for multiple devices)
const char* DEVICE_ID = "ESP8266_DROWSINESS_001";
```

### 4. Build and Upload

```bash
# Build the firmware
pio run

# Upload to ESP8266
pio run --target upload

# Open serial monitor
pio device monitor
```

Or use VS Code PlatformIO buttons:
- ✓ Build
- → Upload  
- 🔌 Serial Monitor

## 📡 Communication Protocol

### Request (ESP8266 → Python)

JSON payload sent every 1 second via HTTP POST:

```json
{
  "device_id": "ESP8266_DROWSINESS_001",
  "tilt_angle": 15.42,
  "tilt_over_threshold": false,
  "tilt_duration_ms": 0,
  "button_pressed": false,
  "local_alert_candidate": false,
  "wifi_rssi": -45,
  "uptime_ms": 12345
}
```

### Response (Python → ESP8266)

Expected JSON response:

```json
{
  "visual_score": 0.75,
  "alert_level": "Level 1",
  "motor_on": true,
  "buzzer_on": true,
  "red_led": true,
  "green_led": false,
  "ack_required": true
}
```

## ⚙️ Configuration

### Adjustable Constants (in `main.cpp`)

```cpp
// Timing intervals
const unsigned long SEND_INTERVAL = 1000;       // Send data every 1 second
const unsigned long MPU_READ_INTERVAL = 100;    // Read MPU every 100ms

// Tilt thresholds
const float TILT_THRESHOLD_DEG = 30.0;          // Tilt angle threshold (degrees)
const unsigned long TILT_DURATION_THRESHOLD = 3000; // Must exceed for 3 seconds

// Alert timing
const unsigned long BUZZER_BEEP_INTERVAL = 500; // Buzzer beep rate
const unsigned long LED_BLINK_INTERVAL = 250;   // LED blink rate
```

## 🎯 Operating Modes

### Normal Operation
- **Green LED:** ON (solid)
- **Red LED:** OFF
- **Motor:** OFF
- **Buzzer:** OFF

### Alert State (Level 1)
- **Green LED:** OFF
- **Red LED:** Blinking
- **Motor:** ON (vibrating)
- **Buzzer:** Beeping (500ms on/off)

### Critical Alert (Level 2/MAX)
- **Green LED:** OFF
- **Red LED:** Solid ON
- **Motor:** ON (continuous)
- **Buzzer:** Beeping (continuous)

### Local Fallback (No Server)
If Python server is unreachable and tilt exceeds threshold for 3+ seconds:
- Activates basic alert locally
- Uses tilt duration to trigger motor/buzzer/LEDs

## 🐛 Troubleshooting

### MPU6050 Not Detected
- Check I2C wiring (SDA to D2, SCL to D1)
- Ensure MPU6050 is powered by 3.3V (not 5V)
- Verify MPU6050 address (default 0x68)
- Try adding pull-up resistors (4.7kΩ) on SDA/SCL

### WiFi Connection Fails
- Verify SSID and password are correct
- Check 2.4GHz WiFi (ESP8266 doesn't support 5GHz)
- Ensure signal strength is adequate
- Check router MAC filtering

### HTTP Errors
- Verify Python server is running
- Check SERVER_URL matches Python server address/port
- Ensure both devices are on same network
- Check firewall settings

### Outputs Not Working
- Verify pin connections match configuration
- Check LED polarity (long leg = anode/+)
- Ensure transistor is correctly wired for motor
- Test components individually

## 📊 Serial Monitor Output

Example output at 115200 baud:

```
========================================
Driver Drowsiness Detection System
ESP8266 Firmware v1.0
========================================

[INIT] GPIO pins configured
[INIT] I2C initialized
[MPU6050] Initializing sensor... Success!
[MPU6050] Calibrating neutral position.......... Done!
[MPU6050] Neutral: ax=-1234, ay=567, az=16384
[WIFI] Connecting to MyWiFi... Connected!
[WIFI] IP Address: 192.168.1.150
[WIFI] Signal Strength: -45 dBm

[READY] System initialized and ready!

[HTTP] Sending to server... Response: 200
[HTTP] Response: {"alert_level":"OK","motor_on":false...}
[SERVER] Alert: OK, Motor: 0, Buzzer: 0
[TILT] Exceeded threshold: 35.2° > 30.0°
[ALERT] Local alert triggered! Tilt duration: 3000 ms
[BUTTON] Pressed - Silencing alerts
[ALERT] All alerts silenced
```

## 🔒 Safety Features

- **Watchdog Timer:** `yield()` calls prevent WDT resets
- **Debouncing:** Button inputs debounced (50ms)
- **Non-blocking:** All delays use `millis()` timing
- **Graceful Degradation:** Local fallback if server fails
- **Error Handling:** HTTP and JSON errors handled safely

## 📝 License

This firmware is part of the Driver Drowsiness Detection System project.

## 🤝 Support

For issues or questions:
1. Check serial monitor output for error messages
2. Verify hardware connections
3. Test with simple blink sketch first
4. Check PlatformIO library dependencies

---

**Note:** Always test the system in a safe environment before real-world use!
