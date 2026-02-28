# Setup Guide — Driver Drowsiness Detection System

---

## Part A — Python App (Camera Detection)

**1. Open the project in VS Code, then open the integrated terminal.**

**2. Create and activate a virtual environment** *(first time only)*
```
python -m venv .venv
.venv\Scripts\activate
```

**3. Install dependencies** *(first time only)*
```
pip install -r requirements.txt
```

**4. Run the app**
```
python app.py
```

Click **"Camera ON"** in the window to start detection.

---

## Part B — Arduino Firmware Upload

**1. Open `arduino_firmware/src/main.cpp` and set your Wi-Fi credentials** near the top of the file:
```cpp
#define WIFI_SSID     "your_network_name"
#define WIFI_PASSWORD "your_password"
#define SERVER_HOST   "192.168.x.x"   // laptop IP running app.py
```

To find your laptop's IP, run in the terminal:
```
ipconfig
```
Look for **IPv4 Address** under your Wi-Fi adapter.

**2. Plug in the Arduino Uno via USB.**

**3. In VS Code, open the PlatformIO terminal** (click the PlatformIO icon in the left sidebar → open a new terminal from there), then navigate to the firmware folder and upload:
```
cd arduino_firmware
pio run --target upload
```

**4. Verify it's working** by opening the serial monitor:
```
pio device monitor --baud 115200
```
You should see:
```
[MPU]  MPU6050 initialised
[AT]   << OK
[WIFI] Connected!
[SYS]  Ready.
```
Press `Ctrl + C` to exit.
