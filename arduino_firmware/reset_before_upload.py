"""
Upload helper for Arduino Uno clone with FTDI.
Prompts user to press RESET, then runs avrdude with stk500v1 programmer.

Usage:  python reset_before_upload.py [COM_PORT]
"""
import time
import subprocess
import sys
import os

COM_PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FIRMWARE_HEX = os.path.join(SCRIPT_DIR, ".pio", "build", "uno", "firmware.hex")

PLATFORMIO_HOME = os.path.join(os.path.expanduser("~"), ".platformio")
AVRDUDE = os.path.join(PLATFORMIO_HOME, "packages", "tool-avrdude", "avrdude.exe")
AVRDUDE_CONF = os.path.join(PLATFORMIO_HOME, "packages", "tool-avrdude", "avrdude.conf")

if not os.path.exists(FIRMWARE_HEX):
    print(f"ERROR: {FIRMWARE_HEX} not found.")
    sys.exit(1)

MAX_RETRIES = 5
for attempt in range(1, MAX_RETRIES + 1):
    print(f"\n=== Attempt {attempt}/{MAX_RETRIES} ===")
    print("Press and RELEASE the Arduino RESET button, then IMMEDIATELY press ENTER here")
    input(">>> ")

    cmd = [
        AVRDUDE, "-C", AVRDUDE_CONF,
        "-p", "atmega328p",
        "-c", "stk500v1",       # no DTR toggle
        "-P", COM_PORT,
        "-b", "115200",
        "-U", f"flash:w:{FIRMWARE_HEX}:i",
    ]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\n[OK] Upload succeeded!")
        sys.exit(0)
    print(f"Failed. Try pressing RESET and ENTER faster next time.")

print("All attempts failed.")
sys.exit(1)
