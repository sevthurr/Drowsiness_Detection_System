# Setup Guide — Driver Drowsiness Detection System

This guide has two parts:

- **Part A** — Running the Python app on your laptop (camera-based drowsiness detection)
- **Part B** — Uploading the Arduino firmware to the wearable device (required for head-tilt + vibration alerts)

If you only have the laptop and webcam, Part A is enough to get started.

---

## What You Need

| Requirement | Details |
|-------------|---------|
| **Operating System** | Windows 10 / 11 |
| **Python** | Version **3.10 or newer** ([download here](https://www.python.org/downloads/)) |
| **Webcam** | Built-in or USB — must be connected before starting |
| **Project folder** | The `wearable_IoT` folder shared with you |
| **Arduino (Part B only)** | Arduino Uno connected via USB |
| **PlatformIO CLI (Part B only)** | Installed via pip — instructions in Part B |

> **During Python installation:** On the first screen, make sure to tick **"Add Python to PATH"** before clicking Install.

---

## Step 1 — Open a Terminal in the Project Folder

1. Open the `wearable_IoT` folder in **File Explorer**
2. Click the address bar at the top, type `cmd`, and press **Enter**

A black terminal window will open, already inside the project folder.

---

## Step 2 — Create a Virtual Environment

A virtual environment keeps the project's dependencies isolated from the rest of your system.

```
python -m venv .venv
```

This creates a hidden `.venv` folder. You only need to do this **once**.

---

## Step 3 — Activate the Virtual Environment

```
.venv\Scripts\activate
```

You'll know it worked when your terminal prompt starts with **`(.venv)`**.

> You need to do this **every time** you open a new terminal to run the project.

---

## Step 4 — Install Dependencies

```
pip install -r requirements.txt
```

This installs the four packages the project needs:

| Package | Purpose |
|---------|---------|
| `PySide6` | The graphical user interface (GUI) |
| `opencv-python` | Camera access and face/eye/mouth detection |
| `numpy` | Image data processing |
| `qtawesome` | Icons used in the UI |

This may take a minute or two. You only need to do this **once**.

---

## Step 5 — Run the Program

```
python app.py
```

The application window will open. Make sure your webcam is connected and click **"Camera ON"** to start detection.

---

## What the Application Does

The program monitors the driver through the webcam and tracks:

- **Eye closure** — detects when eyes stay closed for too long
- **Yawning** — detects open-mouth yawns by analysing the mouth region
- **Head tilt** — (requires the Arduino hardware, optional for laptop-only use)

On screen you will see:
- A live camera feed with coloured bounding boxes around the face and eyes
- **EAR** (Eye Aspect Ratio) — goes green/red based on eye state
- **MAR** (Mouth Aspect Ratio) — rises when the mouth opens
- An orange box around the detected mouth cavity during a yawn
- A **"YAWN DETECTED!"** message after the mouth stays open for 2.5 seconds

---

## Configuration (Optional)

Open `config.json` with any text editor to adjust detection behaviour:

| Setting | Default | What it controls |
|---------|---------|-----------------|
| `eyes_closed_threshold_s` | `2.0` | Seconds before an eye-closure alert triggers |
| `eyes_critical_s` | `4.0` | Seconds before a critical alert triggers |
| `yawns_per_min_threshold` | `2.0` | Yawns per minute before a drowsiness warning |
| `tilt_threshold_deg` | `15.0` | Head tilt angle (degrees) before alert |
| `tilt_duration_s` | `3.0` | Seconds of tilt before alert triggers |
| `theme` | `"dark"` | UI theme — `"dark"` or `"light"` |

Save the file and restart the program for changes to take effect.

---

## Quick-Start Summary (Part A)

Open a terminal in the project folder, then run these **three commands**:

```
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

> If you have already installed the packages before, skip the `pip install` line.

---

---

# Part B — Arduino Firmware Setup

This part covers uploading the wearable device firmware to the Arduino Uno. Skip this if you are only testing the camera detection on your laptop.

---

## B-1 — Install PlatformIO CLI

PlatformIO is the build tool used to compile and upload the Arduino firmware. It installs as a Python package.

Make sure your virtual environment is active first (you should see `(.venv)` in your terminal), then run:

```
pip install platformio
```

This only needs to be done **once**. Verify it worked:

```
pio --version
```

You should see something like `PlatformIO Core, version 6.x.x`.

---

## B-2 — Edit Wi-Fi Credentials

Before uploading, open `arduino_firmware/src/main.cpp` in any text editor and find these three lines near the top:

```cpp
#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define SERVER_HOST   "192.168.x.x"   // IP address of the laptop running app.py
```

Replace the values with:
- The **name** of your Wi-Fi network (exactly as it appears, case-sensitive)
- Your **Wi-Fi password**
- The **local IP address** of the laptop that will be running the Python app

> **How to find your laptop's IP:** Open a terminal and run `ipconfig`. Look for the **IPv4 Address** under your active Wi-Fi adapter (e.g. `192.168.1.5`).

Save the file when done.

---

## B-3 — Navigate to the Firmware Folder

```
cd arduino_firmware
```

---

## B-4 — Connect the Arduino

1. Plug the Arduino Uno into your laptop with a **USB-A to USB-B cable**
2. Windows should automatically install drivers. If it does not, install the [Arduino IDE](https://www.arduino.cc/en/software) which bundles the drivers
3. You can verify the Arduino is detected by opening **Device Manager** and checking under **Ports (COM & LPT)** — you should see something like `USB-SERIAL CH340 (COM3)`

---

## B-5 — Build and Upload the Firmware

```
pio run --target upload
```

PlatformIO will automatically:
1. Download the required `atmelavr` toolchain (first time only, takes ~1–2 minutes)
2. Download the `jrowberg/I2Cdevlib-MPU6050` library
3. Compile the firmware
4. Upload it to the Arduino over USB

A successful upload ends with output like:

```
Uploading .pio\build\uno\firmware.hex
avrdude: 26240 bytes of flash verified
========== [SUCCESS] ==========
```

---

## B-6 — Verify the Arduino is Working

After uploading, open the Serial Monitor to check the startup log:

```
pio device monitor --baud 115200
```

You should see output similar to:

```
[SYS]  Drowsiness Detection System starting...
[MPU]  MPU6050 initialised
[AT]   >> AT
[AT]   << OK
[WIFI] Connecting to MyNetwork...
[WIFI] Connected!
[SYS]  Ready.
```

If you see `[AT] No response` — check the ESP-01 wiring and voltage divider on D3.

Press `Ctrl + C` to exit the monitor.

---

## Quick-Start Summary (Part B)

From inside the `arduino_firmware` folder, with the virtual environment active:

```
pio run --target upload
```

> Run `pip install platformio` first if you haven't already.

---

## Troubleshooting

**"python is not recognized..."**
→ Python is not on PATH. Reinstall Python and tick **"Add Python to PATH"** on the first screen.

**"No module named 'PySide6'"**
→ The virtual environment is not activated. Run `.venv\Scripts\activate` first.

**Camera shows a black screen or "Error"**
→ Close any other app using the webcam (Teams, Zoom, etc.) and try again. Make sure the webcam is plugged in before starting.

**Face / eyes not detected**
→ Ensure good lighting — avoid sitting with a bright window directly behind you. Face the light source if possible.

**Application window immediately closes**
→ Run the program from the terminal (not by double-clicking `app.py`) so you can see any error messages.
