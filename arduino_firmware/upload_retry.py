"""
Upload wrapper — retries avrdude every 0.5s for up to 30 seconds.
Press the Arduino RESET button at any time during the countdown.
"""
import subprocess, time, sys, os

PORT     = "COM3"
FIRMWARE = r".pio\build\uno\firmware.hex"
AVRDUDE  = r"C:\Users\John Benedic Dutaro\.platformio\packages\tool-avrdude\avrdude.exe"
CONF     = r"C:\Users\John Benedic Dutaro\.platformio\packages\tool-avrdude\avrdude.conf"

MAX_TRIES   = 40
RETRY_DELAY = 0.5  # seconds between attempts

print("=" * 60)
print("UPLOAD WRAPPER — Arduino Uno")
print("=" * 60)
print(f"Press the RESET button on the Arduino at any time.")
print(f"Will try {MAX_TRIES} times (up to {MAX_TRIES * RETRY_DELAY:.0f} seconds).")
print("=" * 60)
time.sleep(1)

for i in range(1, MAX_TRIES + 1):
    remaining = (MAX_TRIES - i) * RETRY_DELAY
    print(f"\r[{i}/{MAX_TRIES}] Trying... ({remaining:.0f}s remaining)", end="", flush=True)

    cmd = [
        AVRDUDE,
        "-p", "atmega328p",
        "-C", CONF,
        "-c", "arduino",
        "-b", "115200",
        "-P", PORT,
        "-D",
        "-U", f"flash:w:{FIRMWARE}:i"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"\n\n✓ SUCCESS on attempt {i}!")
        print(result.stderr[-500:])
        sys.exit(0)
    
    time.sleep(RETRY_DELAY)

print(f"\n\nAll {MAX_TRIES} attempts failed.")
print("Check that the Arduino is powered and connected to COM3.")
sys.exit(1)
