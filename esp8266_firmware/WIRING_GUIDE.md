# ESP8266 Hardware Wiring Guide

## Complete Circuit Connections

### Power Distribution
```
ESP8266 3.3V → MPU6050 VCC
ESP8266 GND → Common Ground Rail
```

### MPU6050 I2C Connections
```
MPU6050 VCC → ESP8266 3.3V
MPU6050 GND → ESP8266 GND
MPU6050 SDA → D2 (GPIO4)
MPU6050 SCL → D1 (GPIO5)
```

### LED Connections

#### Green LED (Ready/Normal)
```
D0 (GPIO16) → 220Ω Resistor → Green LED Anode (+, long leg)
Green LED Cathode (-, short leg) → GND
```

#### Red LED (Alert)
```
D7 (GPIO13) → 220Ω Resistor → Red LED Anode (+, long leg)
Red LED Cathode (-, short leg) → GND
```

### Push Button (Acknowledge)
```
D3 (GPIO0) → One side of button
Other side of button → GND
(Uses internal INPUT_PULLUP, no external resistor needed)
```

### Vibration Motor with NPN Transistor Driver

#### Using 2N2222 or similar NPN transistor
```
D5 (GPIO14) → 1kΩ Resistor → Transistor Base (middle pin)
Transistor Emitter (marked E) → GND
Transistor Collector (marked C) → Motor negative (-)
Motor positive (+) → 3.3V or 5V (depending on motor rating)
```

**Optional:** Add a 1N4007 diode across motor (cathode to +, anode to -) for back-EMF protection

### Passive Buzzer
```
D6 (GPIO12) → Buzzer Positive (+)
Buzzer Negative (-) → GND
```

**Alternative:** Use transistor driver like motor if buzzer draws > 12mA

## Component Specifications

| Component | Specification | Notes |
|-----------|---------------|-------|
| ESP8266 | NodeMCU v1.0 | ESP-12E module |
| MPU6050 | GY-521 module | 3.3V operation |
| Green LED | 3mm or 5mm, 2.0V forward voltage | Any green LED |
| Red LED | 3mm or 5mm, 2.0V forward voltage | Any red LED |
| Resistor (LED) | 220Ω, 1/4W | Calculate: (3.3V - 2.0V) / 20mA |
| Resistor (transistor base) | 1kΩ, 1/4W | For NPN base current limiting |
| Vibration Motor | 3-5V DC, coin or cylinder type | ~60-100mA typical |
| Transistor | 2N2222, BC547, or similar NPN | > 100mA collector current |
| Diode (optional) | 1N4007 or 1N4148 | Flyback protection for motor |
| Buzzer | Passive 3-5V | Not active/self-oscillating type |
| Button | Momentary push button | Normally open (NO) |
| Breadboard | Standard 830-point | Or equivalent |

## Pin Summary Table

| Function | ESP8266 Pin | GPIO | Connection |
|----------|-------------|------|------------|
| MPU SDA | D2 | 4 | MPU6050 SDA |
| MPU SCL | D1 | 5 | MPU6050 SCL |
| Motor | D5 | 14 | Transistor base via 1kΩ |
| Buzzer | D6 | 12 | Buzzer + |
| Red LED | D7 | 13 | Resistor → LED anode |
| Green LED | D0 | 16 | Resistor → LED anode |
| Button | D3 | 0 | Button terminal (other to GND) |

## Breadboard Layout Tips

1. **Power Rails:** 
   - Top rail: 3.3V from ESP8266
   - Bottom rail: GND (common ground)

2. **I2C Bus:**
   - Keep MPU6050 wires short (< 10cm)
   - Twist SDA/SCL wires together if longer
   - Add 4.7kΩ pull-up resistors if experiencing I2C issues

3. **LED Placement:**
   - Place LEDs in visible positions
   - Long leg (anode) toward resistor/GPIO
   - Short leg (cathode) toward ground

4. **Motor Circuit:**
   - Keep motor circuit separate from ESP8266
   - Use common ground only
   - Motor can use 5V if rated for it (via USB or external)

5. **Button:**
   - Place near user for easy access
   - No external resistor needed (using INPUT_PULLUP)

## Troubleshooting Hardware

### MPU6050 Not Working
- [ ] Check MPU6050 is getting 3.3V (measure with multimeter)
- [ ] Verify SDA/SCL connections are correct
- [ ] Try swapping SDA/SCL (some boards have different labels)
- [ ] Add 4.7kΩ pull-up resistors on SDA and SCL lines
- [ ] Check for loose connections

### LEDs Not Lighting
- [ ] Verify polarity (long leg = anode)
- [ ] Check resistor value (should be 220Ω)
- [ ] Test LED with battery (3V coin cell)
- [ ] Measure voltage at GPIO pins

### Motor Not Vibrating
- [ ] Check transistor orientation (E-B-C)
- [ ] Verify base resistor (1kΩ)
- [ ] Test motor directly with 3.3V
- [ ] Check transistor type (NPN, not PNP)
- [ ] Measure voltage across motor

### Button Not Responding
- [ ] Check button is normally open (NO) type
- [ ] Verify connection to GPIO0 (D3)
- [ ] Test button with multimeter (continuity mode)
- [ ] Ensure other terminal connects to GND

### Buzzer Silent
- [ ] Confirm it's a PASSIVE buzzer (needs PWM)
- [ ] Check polarity (+ to GPIO, - to GND)
- [ ] Test with simple tone() function
- [ ] Try different buzzer if available

## Safety Notes

⚠️ **Important Safety Guidelines:**

1. **Never connect 5V to ESP8266 GPIO pins** - They are 3.3V only!
2. **MPU6050 must use 3.3V** - Not 5V (check module datasheet)
3. **Motor current must go through transistor** - Not directly from GPIO
4. **Observe LED polarity** - Reversed connection may damage LED
5. **Use appropriate resistors** - Too low may damage ESP8266
6. **Common ground is essential** - All components must share GND
7. **Test components individually** - Before assembling full circuit

## Testing Procedure

### Step 1: Test ESP8266 Alone
- Upload blink sketch
- Verify D0 (built-in LED) blinks

### Step 2: Test LEDs
- Upload LED test sketch
- Verify both LEDs light up

### Step 3: Test MPU6050
- Upload I2C scanner sketch
- Verify MPU6050 detected at 0x68

### Step 4: Test Button
- Upload button test sketch
- Verify serial output when pressed

### Step 5: Test Motor
- Upload motor test sketch
- Verify vibration occurs

### Step 6: Test Buzzer
- Upload tone test sketch
- Verify beeping sound

### Step 7: Upload Full Firmware
- Upload main.cpp from this project
- Monitor serial output for all functions

## Circuit Variations

### Using 5V Motor
If your vibration motor is rated for 5V:
```
5V (from USB) → Motor positive
Motor negative → Transistor collector
(Rest of circuit same)
```

### Using Active Buzzer
If you have an active (self-oscillating) buzzer:
```
D6 (GPIO12) → Buzzer + (direct, no PWM needed)
Buzzer - → GND
```

### External Power Supply
For higher current motors:
```
External 3.3V/5V supply → Motor power
Supply GND → ESP8266 GND (common ground!)
Transistor controls motor as before
```

## Example Shopping List

For building this project, you'll need:

- [ ] 1× NodeMCU ESP8266 development board
- [ ] 1× MPU6050 gyroscope/accelerometer module (GY-521)
- [ ] 1× Green 5mm LED
- [ ] 1× Red 5mm LED
- [ ] 2× 220Ω resistors (for LEDs)
- [ ] 1× 1kΩ resistor (for transistor base)
- [ ] 1× Vibration motor (coin or cylinder type, 3-5V)
- [ ] 1× 2N2222 or BC547 NPN transistor
- [ ] 1× 1N4007 diode (optional, for motor protection)
- [ ] 1× Passive buzzer (3-5V)
- [ ] 1× Momentary push button (normally open)
- [ ] 1× Breadboard (830 points)
- [ ] 1× Set of male-to-male jumper wires
- [ ] 1× USB cable (for programming and power)

Total cost: ~$10-15 USD (depending on source)

---

📌 **Pro Tip:** Build and test each section of the circuit incrementally rather than all at once. This makes troubleshooting much easier!
