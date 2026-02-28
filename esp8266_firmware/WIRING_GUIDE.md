# Wiring Guide — Driver Drowsiness Detection System
## Arduino Uno + ESP-01 (AT) + MPU6050

---

## Architecture Overview

```

                    Arduino Uno (5 V)                    
                   Main Controller                       
                                                         
  A4 (SDA)  MPU6050 (I2C head-tilt sensor)       
  A5 (SCL)  MPU6050                              
                                                         
  D2 (RX)   ESP-01 TX   (3.3 V safe, no shifter) 
  D3 (TX)  [] ESP-01 RX   ( NEEDS voltage divider)
                                                         
  D4        Push button  (INPUT_PULLUP)           
  D5        NPN base  Vibration motor          
  D6        Passive buzzer                        
  D7        Red LED (via 220 O)                   
  D8        Green LED (via 220 O)                 

                                     
    SoftwareSerial                  Wi-Fi
    AT commands                       
                                     
            
     ESP-01     ~~Wi-Fi~~  Python Server       
   (AT firmware)            (laptop, port 5000) 
            
```

---

## Power Distribution

| Rail | Source | Connects to |
|------|--------|-------------|
| 5 V | Arduino 5 V pin or USB | Arduino logic, LED resistors, optional motor supply |
| 3.3 V | Arduino 3.3 V pin | ESP-01 VCC, ESP-01 CH_PD, MPU6050 VCC |
| GND | Common ground rail | All components  every GND must be connected together |

>  **Never power the ESP-01 from the Arduino 5 V pin.** The ESP-01 is a 3.3 V device; 5 V will destroy it.

---

## Section 1  MPU6050 (I2C Head-Tilt Sensor)

Uses the GY-521 breakout board. Operates at 3.3 V.

```
Arduino A4 (SDA)  MPU6050 SDA
Arduino A5 (SCL)  MPU6050 SCL
Arduino 3.3 V     MPU6050 VCC
Arduino GND       MPU6050 GND
```

**Optional (if I2C is unstable):**
Add 4.7 kO pull-up resistors from SDA  3.3 V and SCL  3.3 V.
The GY-521 module includes these by default, so they are usually not needed.

| MPU6050 Pin | Connects to |
|-------------|-------------|
| VCC | Arduino 3.3 V |
| GND | Common GND |
| SDA | Arduino A4 |
| SCL | Arduino A5 |
| AD0 | Leave unconnected (I2C address 0x68) |
| INT | Leave unconnected |

---

## Section 2  ESP-01 Wi-Fi Module

The ESP-01 acts as a Wi-Fi co-processor only. The Arduino sends AT commands over SoftwareSerial at 115200 baud and reads the replies.

###  Critical Voltage Warning

The Arduino Uno is a **5 V** system. The ESP-01 RX pin tolerates **3.3 V maximum**.
Sending 5 V into ESP-01 RX will permanently damage the module.

- **Arduino D2 (RX)  ESP-01 TX**  safe without a shifter (3.3 V HIGH is read as HIGH by a 5 V AVR input)
- **Arduino D3 (TX)  ESP-01 RX**  **MUST use a voltage divider or logic-level shifter**

### Voltage Divider for D3  ESP-01 RX

```
Arduino D3 (TX, 5 V) [1 kO] ESP-01 RX
                                [2 kO]
                                 
                                GND
```

Output voltage = 5 V  2 kO / (1 kO + 2 kO) = **3.33 V** 

Standard resistor values (1 kO + 2 kO) produce 3.33 V, which is within the ESP-01's safe range.

### ESP-01 Full Connection Table

| ESP-01 Pin | Connects to | Notes |
|------------|-------------|-------|
| VCC | Arduino 3.3 V | Do NOT use 5 V |
| GND | Common GND | |
| CH_PD (EN) | Arduino 3.3 V | Must be HIGH for the module to run |
| TX | Arduino D2 (RX) | 3.3 V signal  no shifter needed |
| RX | Voltage divider output | See diagram above |
| RST | Leave unconnected | Or pull to 3.3 V for reliability |
| GPIO0 | Leave unconnected | Only used for flashing firmware |
| GPIO2 | Leave unconnected | |

>  **Tip:** The ESP-01 draws up to 250 mA during Wi-Fi transmissions.
> The Arduino's onboard 3.3 V regulator is typically limited to 50150 mA.
> If the module resets unexpectedly, power it from a dedicated AMS1117-3.3 LDO
> regulator fed from the Arduino's 5 V or USB rail, and add a 100 �F capacitor
> between ESP-01 VCC and GND to absorb current spikes.

---

## Section 3  Green LED (Ready / Normal)

```
Arduino D8 [220 O] Green LED anode (+, long leg)
                          Green LED cathode (, short leg)  GND
```

- LED forward voltage: ~2.0 V
- Resistor calculation: (5 V  2.0 V) / 20 mA = 150 O minimum  use **220 O** for safety

---

## Section 4  Red LED (Alert)

```
Arduino D7 [220 O] Red LED anode (+, long leg)
                          Red LED cathode (, short leg)  GND
```

Same resistor sizing as green LED above.

---

## Section 5  Vibration Motor (NPN Transistor Driver)

GPIO pins cannot supply enough current to drive a motor directly. Use an NPN transistor as a switch.

### Circuit

```
Arduino D5 [1 kO] Transistor Base (B)

Transistor Emitter (E)  GND
Transistor Collector (C)  Motor negative ()
Motor positive (+)  3.3 V  (or 5 V if motor is 5 V rated)

Flyback diode (recommended):
  Cathode (band)  Motor positive (+) rail
  Anode           Motor negative () / Collector
```

### Transistor Pin Orientation  2N2222 TO-92 (flat side facing you)

```
  Flat side
  
   E B C 
  
```

- **E** (Emitter)  GND
- **B** (Base)     1 kO resistor  Arduino D5
- **C** (Collector)  Motor negative ()

Compatible transistors: 2N2222, BC547, BC548, 2N3904 (NPN, Ic > 100 mA)

---

## Section 6  Passive Buzzer

```
Arduino D6  Buzzer positive (+)
                Buzzer negative ()  GND
```

>  Use a **passive** buzzer (no internal oscillator). An active buzzer sounds
> at a fixed frequency when powered; a passive buzzer requires a square wave
> from the pin to produce sound. The firmware generates the toggling signal.

If the buzzer draws more than ~40 mA, drive it through a transistor circuit
identical to the motor driver above.

---

## Section 7  Push Button (Acknowledge / Silence)

```
Arduino D4  Button terminal 1
                Button terminal 2  GND
```

The firmware configures D4 as `INPUT_PULLUP`  no external resistor is needed.
Pressing the button pulls D4 LOW, which the firmware detects as a press event.

Use a **normally open (NO) momentary** push button.

---

## Complete Pin Summary

| Arduino Pin | Direction | Connects to | Notes |
|-------------|-----------|-------------|-------|
| A4 | I/O | MPU6050 SDA | I2C data |
| A5 | I/O | MPU6050 SCL | I2C clock |
| D2 | INPUT | ESP-01 TX | 3.3 V logic  no shifter needed |
| D3 | OUTPUT | 1 kO  node  2 kO  GND; node  ESP-01 RX |  Step-down required |
| D4 | INPUT | Push button terminal 1 (terminal 2  GND) | INPUT_PULLUP |
| D5 | OUTPUT | 1 kO  NPN transistor base | Vibration motor driver |
| D6 | OUTPUT | Passive buzzer + | PWM-capable |
| D7 | OUTPUT | 220 O  Red LED anode | Alert indicator |
| D8 | OUTPUT | 220 O  Green LED anode | Ready indicator |
| 3.3 V | Power | ESP-01 VCC, ESP-01 CH_PD, MPU6050 VCC | |
| 5 V | Power | LED resistors; optional motor/buzzer supply | |
| GND | Power | All component grounds (common rail) | |

---

## Component List

| Component | Specification | Qty |
|-----------|---------------|-----|
| Arduino Uno | Rev 3 or compatible | 1 |
| ESP-01 | With AT firmware pre-loaded | 1 |
| MPU6050 | GY-521 breakout, 3.3 V | 1 |
| Green LED | 5 mm, ~2.0 V Vf | 1 |
| Red LED | 5 mm, ~2.0 V Vf | 1 |
| Resistor 220 O | 1/4 W | 2 |
| Resistor 1 kO | 1/4 W | 2 (transistor base + voltage divider) |
| Resistor 2 kO | 1/4 W | 1 (voltage divider) |
| NPN transistor | 2N2222 / BC547 / 2N3904, Ic > 100 mA | 1 |
| Flyback diode | 1N4007 or 1N4148 | 1 (optional, motor protection) |
| Vibration motor | 35 V DC, coin or cylinder type | 1 |
| Passive buzzer | 35 V | 1 |
| Momentary push button | Normally open (NO) | 1 |
| AMS1117-3.3 LDO | Optional  if ESP resets under load | 1 |
| Capacitor 100 �F | Optional  ESP power filtering | 1 |
| Breadboard | 830-point | 1 |
| Jumper wires | Male-to-male | 1 set |
| USB cable | USB-A to USB-B | 1 |

Estimated cost: ~$1218 USD

---

## Breadboard Layout Tips

1. **Label power rails**  use one rail for 3.3 V and another for 5 V to avoid accidentally connecting components to the wrong voltage.
2. **Voltage divider placement**  assemble the two resistors close to the ESP-01 RX pin, not near the Arduino, to keep the 5 V trace short.
3. **Motor / buzzer area**  place the transistor on the side of the breadboard opposite the MPU6050 to minimise I2C noise.
4. **Short I2C wires**  SDA and SCL wires to the MPU6050 should be under 10 cm.
5. **ESP-01 decoupling**  a 100 �F capacitor between ESP-01 VCC and GND prevents voltage droop during Wi-Fi transmissions.

---

## Troubleshooting Checklist

### ESP-01 Not Responding to AT Commands
- [ ] ESP-01 VCC and CH_PD both connected to 3.3 V (not 5 V)
- [ ] Voltage divider assembled correctly: D3  1 kO  node  2 kO  GND; node  ESP-01 RX
- [ ] Baud rate in firmware matches AT firmware on module (default 115200; some ship at 9600)
- [ ] Open Serial Monitor at 115200 and look for `[AT] >> AT` / `[AT] << OK`
- [ ] Try a serial passthrough sketch to send `AT` manually if no response

### MPU6050 Not Detected
- [ ] Confirm VCC is 3.3 V (not 5 V)
- [ ] Try swapping SDA / SCL if I2C scanner finds nothing
- [ ] Run I2C scanner  should find address `0x68`
- [ ] Add 4.7 kO pull-ups on SDA and SCL if scanner finds nothing

### LEDs Not Lighting
- [ ] Verify polarity (long leg = anode toward resistor, short leg to GND)
- [ ] Measure voltage at D7 / D8 with a multimeter  should be ~5 V when ON
- [ ] Test LED separately with a 3 V coin cell

### Motor Not Vibrating
- [ ] Check transistor orientation: flat side facing you  E B C left to right
- [ ] Measure ~5 V at D5 when commanded ON
- [ ] Test motor directly across 3.3 V / GND to confirm it works

### Buzzer Silent
- [ ] Confirm it is a **passive** buzzer, not an active (self-oscillating) type
- [ ] Check polarity: + to D6,  to GND

### Button Not Registering
- [ ] Confirm button is normally open (NO) momentary type
- [ ] One terminal to D4, other terminal to GND  no resistor needed

### Wi-Fi Not Connecting
- [ ] SSID and PASSWORD in `main.cpp` match exactly (case-sensitive)
- [ ] ESP-01 powered with sufficient current  add AMS1117-3.3 if module resets
- [ ] Watch Serial Monitor for `[WIFI] Connected!` or the specific AT error message

---

## Safety Notes

1. **Never feed 5 V into ESP-01**  the voltage divider on D3  ESP RX is mandatory.
2. **Never drive the motor directly from a GPIO pin**  always use the NPN transistor circuit.
3. **Common ground is mandatory**  Arduino GND, ESP-01 GND, MPU6050 GND, motor GND, and buzzer GND must all connect to the same rail.
4. **MPU6050 runs at 3.3 V**  most GY-521 breakout boards include an onboard regulator and accept 35 V on VCC; check your specific module's datasheet.
5. **ESP-01 current spike**  during Wi-Fi association the module can briefly draw 250 mA; add a 100 �F capacitor between ESP-01 VCC and GND to absorb the spike.

---

 **Pro Tip:** Build and test each section independently before connecting everything together. Use the `Serial Monitor` at 115200 baud  the firmware prints a labelled debug log for every subsystem during startup.
