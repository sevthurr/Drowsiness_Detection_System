# ESP8266 Quick Start Guide

## 🚀 5-Minute Setup

### Prerequisites
- [ ] VS Code with PlatformIO extension installed
- [ ] NodeMCU ESP8266 board with USB cable
- [ ] Components assembled (see WIRING_GUIDE.md)

### Step 1: Configure WiFi (1 min)

Edit `src/main.cpp` lines 31-33:

```cpp
const char* WIFI_SSID = "YourWiFiNetworkName";     // ← Change this
const char* WIFI_PASSWORD = "YourWiFiPassword";     // ← Change this
const char* SERVER_URL = "http://192.168.1.100:5000/sensor-data"; // ← Change IP
```

**To find your laptop's IP address:**

**Windows:**
```cmd
ipconfig
```
Look for "IPv4 Address" under your WiFi adapter

**Mac/Linux:**
```bash
ifconfig
```
Look for "inet" under en0 or wlan0

### Step 2: Upload Firmware (2 min)

1. Connect NodeMCU via USB
2. Click **PlatformIO: Upload** button (→ arrow)
3. Wait for "SUCCESS" message
4. Click **PlatformIO: Serial Monitor** button (🔌)

### Step 3: Start Python Server (1 min)

In a new terminal on your laptop:

```bash
cd esp8266_firmware
python server_example.py
```

You should see:
```
ESP8266 Drowsiness Detection - Test Server
Server starting on http://0.0.0.0:5000
Waiting for ESP8266 connections...
```

### Step 4: Test! (1 min)

1. **Check Serial Monitor** - Should show WiFi connected
2. **Tilt the MPU6050** - Angle should change
3. **Tilt > 30°** - Red LED blinks, motor vibrates, buzzer beeps
4. **Press button** - Alerts silence
5. **Check Python server** - Should show received data

## 🎯 Expected Behavior

### Normal Operation
✅ Green LED solid ON  
✅ Serial shows: `[SERVER] Alert: OK, Motor: 0, Buzzer: 0`  
✅ Python server receives data every 1 second

### Alert Triggered
✅ Red LED blinking  
✅ Vibration motor running  
✅ Buzzer beeping (500ms on/off)  
✅ Serial shows: `[ALERT] Local alert triggered!`  
✅ Python server shows: `→ Warning Alert (Level 1)`

### Button Pressed
✅ All alerts stop  
✅ Green LED turns ON  
✅ Serial shows: `[BUTTON] Pressed - Silencing alerts`

## 🐛 Common Issues

### Issue: WiFi won't connect

**Solution:**
- Verify SSID/password are correct (case-sensitive!)
- Ensure 2.4GHz WiFi (ESP8266 doesn't support 5GHz)
- Move ESP8266 closer to router
- Check router isn't blocking new devices

### Issue: MPU6050 initialization failed

**Solution:**
- Check wiring: SDA→D2, SCL→D1
- Verify MPU6050 gets 3.3V power
- Try disconnecting/reconnecting MPU6050
- Add 4.7kΩ pull-up resistors on SDA/SCL lines

### Issue: Server connection failed

**Solution:**
- Verify SERVER_URL uses correct IP address
- Check Python server is running (`python server_example.py`)
- Ensure laptop and ESP8266 on same network
- Disable laptop firewall temporarily to test
- Try accessing http://LAPTOP_IP:5000/status in browser

### Issue: Tilt angle always 0

**Solution:**
- MPU6050 needs calibration - keep it still during startup
- Check I2C connections are secure
- Verify MPU6050 module is authentic (cheap clones may fail)
- Try restarting ESP8266

### Issue: LEDs/motor/buzzer not working

**Solution:**
- Verify component wiring (see WIRING_GUIDE.md)
- Check LED polarity (long leg = +)
- Ensure transistor is NPN type (not PNP)
- Test components individually first
- Check for loose breadboard connections

## 📊 Serial Monitor Reference

### Good Output
```
[WIFI] Connecting to MyNetwork... Connected!
[WIFI] IP Address: 192.168.1.150
[MPU6050] Initializing sensor... Success!
[MPU6050] Calibrating neutral position.......... Done!
[READY] System initialized and ready!
[HTTP] Sending to server... Response: 200
[SERVER] Alert: OK, Motor: 0, Buzzer: 0
```

### Bad Output (WiFi)
```
[WIFI] Connecting to MyNetwork.......... Failed!
[WIFI] Will retry in 5 seconds...
```
→ Fix: Check SSID/password

### Bad Output (MPU6050)
```
[MPU6050] Initializing sensor... Failed!
[ERROR] MPU6050 not responding. Check wiring!
```
→ Fix: Check I2C connections

### Bad Output (Server)
```
[HTTP] Sending to server... Failed: connection refused
```
→ Fix: Start Python server

## 🔧 Testing Without Server

To test hardware without Python server, the ESP8266 will use **local fallback mode**:

1. Don't start Python server
2. Tilt sensor > 30° for 3+ seconds
3. Local alert triggers automatically
4. Motor/buzzer/LEDs activate
5. Serial shows: `[ALERT] Using local fallback (no server)`

This proves your hardware works independently!

## 📝 Integration with Main Project

Once firmware is working, integrate with your main Python application:

1. Replace `server_example.py` with your actual server
2. Update endpoint in `main.cpp` to match
3. Modify JSON response format if needed
4. Add authentication if required
5. Implement database logging

## 🎓 Next Steps

1. ✅ Basic upload and connection working
2. ⬜ Test all components (LEDs, motor, buzzer, button)
3. ⬜ Calibrate tilt thresholds for your use case
4. ⬜ Adjust timing intervals (send rate, beep rate)
5. ⬜ Integrate with your full Python application
6. ⬜ Build enclosure for wearable
7. ⬜ Add battery power (with power management)
8. ⬜ Test in real driving scenario (safely!)

## 💡 Tips

**Power Consumption:**
- WiFi uses ~80mA when transmitting
- Deep sleep mode can reduce to < 1mA
- For battery operation, implement sleep cycles
- Use 3.7V LiPo battery with charging circuit

**Calibration:**
- MPU6050 calibrates during startup - keep still!
- For car use, calibrate while sitting normally
- Adjust `TILT_THRESHOLD_DEG` for your head angle
- Test thresholds before real deployment

**Debugging:**
- Serial monitor is your friend - read messages!
- Add more `Serial.println()` for custom debugging
- Use oscilloscope/logic analyzer for I2C issues
- Test components with simple sketches first

## 📞 Support

If you're stuck:
1. Read error messages in Serial Monitor carefully
2. Check WIRING_GUIDE.md for correct connections
3. Test each component individually
4. Verify libraries are installed (`pio lib list`)
5. Try simple blink sketch to verify ESP8266 works

## ⚡️ One-Command Upload

After initial setup, you can rebuild and upload with one command:

```bash
pio run -t upload && pio device monitor
```

This builds, uploads, and opens serial monitor automatically!

---

**Ready to go? Let's detect some drowsiness! 😴➡️💪**
