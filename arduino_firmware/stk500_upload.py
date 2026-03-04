"""
Pure-Python STK500v1 flasher for ATmega328P.
Handles the entire upload in one serial session, avoiding the double-reset
timing issue that occurs when avrdude opens the port separately.

Usage:  python stk500_upload.py [COM_PORT] [HEX_FILE]

The standard Arduino auto-reset uses a 100nF cap between FTDI DTR and RESET.
Only a HIGH→LOW transition on DTR (pyserial: dtr going from False to True)
generates a negative pulse that resets the MCU. This script carefully controls
DTR to ensure a clean reset then immediately syncs with the bootloader.
"""
import serial
import time
import sys
import os

COM_PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HEX_FILE  = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    SCRIPT_DIR, ".pio", "build", "uno", "firmware.hex"
)

# STK500 constants
STK_GET_SYNC     = 0x30
STK_ENTER_PROGMODE = 0x50
STK_LEAVE_PROGMODE = 0x51
STK_LOAD_ADDRESS = 0x55
STK_PROG_PAGE    = 0x64
STK_READ_SIGN    = 0x75
CRC_EOP          = 0x20
STK_INSYNC       = 0x14
STK_OK           = 0x10

PAGE_SIZE = 128  # ATmega328P page size in bytes


def parse_ihex(path):
    """Parse Intel HEX file, return dict: address → byte_value."""
    data = {}
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line.startswith(':'):
                continue
            raw = bytes.fromhex(line[1:])
            byte_count = raw[0]
            addr = (raw[1] << 8) | raw[2]
            rec_type = raw[3]
            if rec_type == 0x00:  # data record
                for i in range(byte_count):
                    data[addr + i] = raw[4 + i]
            elif rec_type == 0x01:  # EOF
                break
    return data


def ihex_to_pages(data, page_size=PAGE_SIZE):
    """Convert address→byte dict to list of (page_addr, page_bytes) tuples."""
    if not data:
        return []
    min_addr = min(data.keys())
    max_addr = max(data.keys())
    pages = []
    addr = (min_addr // page_size) * page_size
    while addr <= max_addr:
        page = bytearray(page_size)
        has_data = False
        for i in range(page_size):
            if (addr + i) in data:
                page[i] = data[addr + i]
                has_data = True
            else:
                page[i] = 0xFF
        if has_data:
            pages.append((addr, bytes(page)))
        addr += page_size
    return pages


def open_port_no_reset(port, baud=115200):
    """Open serial port WITHOUT triggering DTR auto-reset."""
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = 0.1   # Short timeouts for fast retries
    ser.write_timeout = 1
    ser.dtr = False      # Keep DTR HIGH (inactive) on open → no reset
    ser.rts = False
    ser.open()
    return ser


def pulse_reset(ser):
    """Pulse DTR LOW to trigger auto-reset via the 100nF cap.
    Returns the time.time() when the pulse was sent."""
    # Ensure DTR is HIGH (inactive) first
    ser.dtr = False
    time.sleep(0.1)

    # DTR HIGH → LOW transition → 100nF cap pulses RESET low → MCU resets
    ser.dtr = True
    time.sleep(0.050)    # Hold LOW for 50ms (cap needs brief pulse)
    ser.dtr = False      # Release — cap blocks DC, RESET pulled HIGH by pull-up
    reset_time = time.time()

    # Bootloader takes ~65ms to initialize after reset
    time.sleep(0.065)
    ser.reset_input_buffer()
    return reset_time


def try_sync(ser, max_attempts=60, interval=0.008):
    """Blast STK_GET_SYNC repeatedly. Returns True on success."""
    sync_cmd = bytes([STK_GET_SYNC, CRC_EOP])
    for i in range(max_attempts):
        ser.reset_input_buffer()
        ser.write(sync_cmd)
        ser.flush()
        time.sleep(interval)
        r = ser.read(2)
        if len(r) >= 2 and r[0] == STK_INSYNC and r[1] == STK_OK:
            # Double-check with a second sync
            ser.reset_input_buffer()
            ser.write(sync_cmd)
            ser.flush()
            time.sleep(0.050)
            r2 = ser.read(2)
            if len(r2) >= 2 and r2[0] == STK_INSYNC and r2[1] == STK_OK:
                return True
        elif len(r) > 0:
            # Print what we got for debugging
            hex_str = ' '.join(f'{b:02X}' for b in r)
            elapsed = (i + 1) * interval
            print(f"\r    [{elapsed:.2f}s] got: {hex_str}     ", end="", flush=True)
    return False


def stk_command(ser, *cmd_bytes, response_len=2, retries=3):
    """Send an STK500 command and expect INSYNC...OK response."""
    cmd = bytes(cmd_bytes)
    for _ in range(retries):
        ser.reset_input_buffer()
        ser.write(cmd)
        ser.flush()
        time.sleep(0.010)
        r = ser.read(response_len)
        if len(r) >= 2 and r[0] == STK_INSYNC:
            if r[-1] == STK_OK:
                return r
    return None


def flash_pages(ser, pages):
    """Program all pages. Returns True on success."""
    for i, (addr, page_data) in enumerate(pages):
        word_addr = addr // 2
        lo = word_addr & 0xFF
        hi = (word_addr >> 8) & 0xFF

        # LOAD_ADDRESS
        r = stk_command(ser, STK_LOAD_ADDRESS, lo, hi, CRC_EOP)
        if r is None:
            print(f"\n[!] Failed to set address 0x{addr:04X}")
            return False

        # PROG_PAGE
        size = len(page_data)
        cmd = bytes([STK_PROG_PAGE, (size >> 8) & 0xFF, size & 0xFF, ord('F')])
        cmd += page_data + bytes([CRC_EOP])
        ser.reset_input_buffer()
        ser.write(cmd)
        ser.flush()
        time.sleep(0.015)  # Page write time
        r = ser.read(2)
        if len(r) < 2 or r[0] != STK_INSYNC or r[1] != STK_OK:
            print(f"\n[!] Failed to write page at 0x{addr:04X}")
            return False

        # Progress
        pct = (i + 1) * 100 // len(pages)
        bar = '#' * (pct // 2) + '-' * (50 - pct // 2)
        print(f"\r    [{bar}] {pct:3d}%", end="", flush=True)

    print()
    return True


def main():
    if not os.path.exists(HEX_FILE):
        print(f"ERROR: {HEX_FILE} not found")
        sys.exit(1)

    # Parse hex file
    print(f"[*] Parsing {os.path.basename(HEX_FILE)}...")
    raw_data = parse_ihex(HEX_FILE)
    pages = ihex_to_pages(raw_data)
    total_bytes = sum(len(p[1]) for p in pages)
    print(f"    {total_bytes} bytes in {len(pages)} pages")

    MAX_RETRIES = 5
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n{'='*50}")
        print(f"  ATTEMPT {attempt}/{MAX_RETRIES}")
        print(f"{'='*50}")

        # Strategy 1 (attempts 1-3): DTR auto-reset
        # Strategy 2 (attempts 4-5): manual reset
        use_manual = attempt > 3

        if use_manual:
            input("\n[!] Hold RESET button, then press ENTER... ")
            ser = open_port_no_reset(COM_PORT)
            time.sleep(0.5)
            input("[!] Release RESET button NOW, then press ENTER... ")
            time.sleep(0.010)
            ser.reset_input_buffer()
        else:
            print("[*] Opening port (DTR inactive, no reset)...")
            ser = open_port_no_reset(COM_PORT)
            time.sleep(0.3)  # Let port stabilize

            print("[*] Pulsing DTR to reset Arduino...")
            pulse_reset(ser)

        # Sync
        print("[*] Syncing with bootloader...", flush=True)
        if try_sync(ser, max_attempts=60, interval=0.008):
            print("\r[OK] Synced with bootloader!                    ")
        else:
            print("\n[!] Could not sync.")
            ser.close()
            time.sleep(1)
            continue

        # Read signature
        r = stk_command(ser, STK_READ_SIGN, CRC_EOP, response_len=5)
        if r and len(r) >= 4:
            sig = r[1:4]
            print(f"[*] Signature: 0x{sig[0]:02X} 0x{sig[1]:02X} 0x{sig[2]:02X}", end="")
            if sig == b'\x1e\x95\x0f':
                print(" (ATmega328P)")
            else:
                print(" (unknown — continuing)")
        else:
            print("[*] Could not read signature (continuing)")

        # Enter programming mode
        if stk_command(ser, STK_ENTER_PROGMODE, CRC_EOP) is None:
            print("[!] Failed to enter programming mode")
            ser.close()
            continue

        # Flash
        print("[*] Programming flash...")
        if not flash_pages(ser, pages):
            stk_command(ser, STK_LEAVE_PROGMODE, CRC_EOP)
            ser.close()
            continue

        # Leave programming mode (resets to app)
        stk_command(ser, STK_LEAVE_PROGMODE, CRC_EOP)
        ser.close()

        print(f"\n[OK] Upload complete! {total_bytes} bytes written.")
        sys.exit(0)

    print(f"\nAll {MAX_RETRIES} attempts failed.")
    print("TIP: Try uploading with Arduino IDE directly.")
    sys.exit(1)


if __name__ == "__main__":
    main()
