Import("env")
import time

def before_upload(source, target, env):
    port = env.get("UPLOAD_PORT", None)
    if not port: return
    try:
        import serial
        s = serial.Serial()
        s.port = port; s.baudrate = 115200; s.setDTR(False); s.open()
        time.sleep(0.1); s.setDTR(True); time.sleep(0.15); s.setDTR(False); s.close()
        time.sleep(0.8)
    except Exception as e:
        print(f"[reset] {e}")

env.AddPreAction("upload", before_upload)
