import serial, time

print("Opening COM3...")
s = serial.Serial("COM3", 115200, timeout=0.5)
print("Watching BEFORE DTR toggle (3 seconds)...")
t0 = time.time()
while time.time() - t0 < 3:
    line = s.readline()
    if line:
        print(f"  [{time.time()-t0:.1f}s] {line.decode(errors='replace').strip()}")

print("--- Toggling DTR NOW ---")
s.dtr = False
time.sleep(0.05)
s.dtr = True
time.sleep(0.05)
s.dtr = False

print("Watching AFTER DTR toggle (25 seconds)...")
print("If Arduino reset: expect SILENCE for ~20 seconds, then JSON resumes")
print("If DTR not connected: JSON continues uninterrupted")
t0 = time.time()
while time.time() - t0 < 25:
    line = s.readline()
    if line:
        print(f"  [{time.time()-t0:.1f}s] {line.decode(errors='replace').strip()}")

s.close()
print("Done.")
