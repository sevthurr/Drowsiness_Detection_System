"""
Pre-upload script for PlatformIO.
Toggles DTR on the upload port to reset the Arduino into bootloader mode
before avrdude tries to connect.  Fixes boards where the auto-reset via
the USB-serial chip doesn't trigger reliably.
"""
import time

Import("env")   # PlatformIO SCons env

def reset_via_dtr(source, target, env):
    port = env.get("UPLOAD_PORT", "COM3")
    print(f"[reset] Toggling DTR on {port} to enter bootloader...")
    try:
        import serial
        s = serial.Serial(port, 115200, timeout=1)
        s.dtr = False
        time.sleep(0.1)
        s.dtr = True
        time.sleep(0.05)
        s.dtr = False
        time.sleep(0.2)   # give the bootloader time to start
        s.close()
        print("[reset] DTR toggled — bootloader should be active")
    except Exception as e:
        print(f"[reset] DTR toggle failed ({e}) — you may need to press Reset manually")

env.AddPreAction("upload", reset_via_dtr)
