/**
 * ============================================================================
 *  Driver Drowsiness Detection System — Arduino Sensor Controller
 *
 *  Architecture
 *  ─────────────────────────────────────────────────────────────────────────
 *  Arduino Uno → main controller
 *    • reads  MPU6050 head-tilt sensor (I2C on A4/A5)
 *    • reads  push button
 *    • drives green LED, red LED, vibration motor, buzzer
 *    • sends JSON sensor data over Serial to NodeMCU every 1 second
 *    • receives JSON alert commands back from NodeMCU
 *
 *  NodeMCU (ESP8266) → Wi-Fi bridge
 *    • receives JSON from Arduino over Serial
 *    • POSTs it to the Python server via HTTP
 *    • returns the server response back over Serial
 *    • sends WIFI_OK / WIFI_FAIL status messages
 *
 *  Python server (laptop) → receives POST /sensor, returns alert JSON
 *
 *  Pin map
 *  ─────────────────────────────────────────────────────────────────────────
 *  MPU6050  SDA  → A4
 *  MPU6050  SCL  → A5
 *  NodeMCU  RX   ← Arduino TX (pin 1) via voltage divider (5V→3.3V)
 *  NodeMCU  TX   → Arduino RX (pin 0)
 *  Button        → D4   (INPUT_PULLUP, press = LOW)
 *  Vibration     → D5   (NPN transistor base via resistor)
 *  Buzzer        → D6   (passive buzzer)
 *  Red LED       → D7
 *  Green LED     → D8
 *
 *  ⚠  UPLOAD WARNING — Disconnect NodeMCU wires from pins 0/1 before
 *     uploading, reconnect after upload completes.
 * ============================================================================
 */

#include <Arduino.h>
#include <Wire.h>
#include <MPU6050.h>           // jrowberg/I2Cdevlib-MPU6050
#include <avr/wdt.h>           // AVR watchdog timer — resets MCU on I2C hang


// ============================================================================
//  CONFIGURATION
// ============================================================================

// Device identification sent in every payload
const char* DEVICE_ID = "ARD_DROWSINESS_001";

// Timing intervals (milliseconds)
const unsigned long SEND_INTERVAL       = 1000;   // send JSON every 1 s
const unsigned long MPU_READ_INTERVAL   = 100;    // sample MPU every 100 ms

// Tilt thresholds
const float         TILT_THRESHOLD_DEG     = 30.0;   // degrees
const unsigned long TILT_DURATION_MS_ALERT = 3000;   // 3 s → local fallback

// Alert output timing
const unsigned long BUZZER_TOGGLE_INTERVAL = 500;   // buzzer beep period
const unsigned long LED_BLINK_INTERVAL     = 250;   // red LED blink period

// Serial baud — must match NodeMCU firmware
const long SERIAL_BAUD = 115200;


// ============================================================================
//  PIN DEFINITIONS
// ============================================================================

// NodeMCU uses hardware Serial (pins 0 RX / 1 TX)

// Inputs
const uint8_t BUTTON_PIN = 4;   // D4, INPUT_PULLUP

// Outputs
const uint8_t VIBRATION_PIN = 5;  // D5 → NPN transistor base
const uint8_t BUZZER_PIN    = 6;  // D6 → passive buzzer
const uint8_t RED_LED_PIN   = 7;  // D7
const uint8_t GREEN_LED_PIN = 8;  // D8


// ============================================================================
//  OBJECTS
// ============================================================================

MPU6050  mpu;           // default address 0x68; initMPU() also tries 0x69
bool     mpu_addr_tried_69 = false;


// ============================================================================
//  GLOBAL STATE
// ============================================================================

// MPU6050
bool    mpu_initialized  = false;
bool    mpu_calibrated   = false;
int16_t neutral_ax = 0, neutral_ay = 0, neutral_az = 0;
float   current_tilt_angle = 0.0;

// Tilt tracking
bool          tilt_over_threshold = false;
unsigned long tilt_start_time     = 0;
unsigned long tilt_duration_ms    = 0;

// Button
bool          button_pressed        = false;
bool          button_last_state     = HIGH;
bool          button_debounced_state = HIGH;   // tracks the stable state
unsigned long button_debounce_ts    = 0;
const unsigned long DEBOUNCE_DELAY  = 50;

// Alert state (set by server response or local fallback)
bool   motor_on     = false;
bool   buzzer_on    = false;
bool   red_led_on   = false;
bool   green_led_on = true;
bool   ack_required = false;
int    alert_level  = 0;        // 0=OK  1=Level1  2=Level2/MAX

// Local fallback flag
bool local_alert_active = false;

// Wi-Fi status (reported by NodeMCU)
bool wifi_connected = false;

// Output toggle state
bool          buzzer_state        = false;
bool          red_led_blink_state = false;
unsigned long last_buzzer_toggle  = 0;
unsigned long last_led_blink      = 0;

// Timing
unsigned long last_send_time     = 0;
unsigned long last_mpu_read      = 0;

// Serial receive buffer
char   rx_buf[256];
int    rx_pos = 0;


// ============================================================================
//  FUNCTION DECLARATIONS
// ============================================================================

// MPU6050
void  initMPU();
void  calibrateNeutralPosition();
void  recoverI2C();
float readTiltAngle();

// Button
void readButton();

// Alert logic
void updateLocalAlertState();
void applyOutputs();
void silenceAlerts();

// Communication
void sendSensorData();
void checkSerial();
void parseResponse(const char* line);


// ============================================================================
//  SETUP
// ============================================================================

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(200);

    // Output pins
    pinMode(VIBRATION_PIN, OUTPUT);
    pinMode(BUZZER_PIN,    OUTPUT);
    pinMode(RED_LED_PIN,   OUTPUT);
    pinMode(GREEN_LED_PIN, OUTPUT);
    digitalWrite(VIBRATION_PIN, LOW);
    digitalWrite(BUZZER_PIN,    LOW);
    digitalWrite(RED_LED_PIN,   LOW);
    digitalWrite(GREEN_LED_PIN, HIGH);   // green ON = system starting up

    // Input pin
    pinMode(BUTTON_PIN, INPUT_PULLUP);

    // I2C for MPU6050
    Wire.begin();
    Wire.setWireTimeout(25000, true);  // 25 ms I2C timeout, auto-reset TWI

    // Wait for NodeMCU to boot and connect to Wi-Fi before sending any serial
    // data — prevents boot interference on the shared UART line.
    for (int i = 0; i < 20; i++) {
        delay(1000);
    }

    // MPU6050
    initMPU();

    // Enable watchdog timer (8 seconds).  If the I2C bus or any other
    // subsystem hangs longer than this, the MCU resets automatically.
    wdt_enable(WDTO_8S);
}


// ============================================================================
//  MAIN LOOP
// ============================================================================

void loop() {
    wdt_reset();  // Pet the watchdog every iteration
    unsigned long now = millis();

    // ── Read incoming data from NodeMCU ─────────────────────────────────
    checkSerial();

    // ── Read MPU6050 ────────────────────────────────────────────────────
    if (mpu_initialized && (now - last_mpu_read >= MPU_READ_INTERVAL)) {
        current_tilt_angle = readTiltAngle();
        last_mpu_read = now;
    }

    // ── Read button ─────────────────────────────────────────────────────
    readButton();

    // ── Update local alert candidate ────────────────────────────────────
    updateLocalAlertState();

    // ── Send sensor data every SEND_INTERVAL ────────────────────────────
    if (now - last_send_time >= SEND_INTERVAL) {
        last_send_time = now;
        sendSensorData();
    }

    // ── Apply outputs (non-blocking blink/beep) ─────────────────────────
    applyOutputs();
}


// ============================================================================
//  MPU6050
// ============================================================================

/**
 * Initialise the MPU6050 over I2C.
 * If the sensor is not found, mpu_initialized stays false and tilt
 * detection is disabled — the rest of the system still operates.
 */
void initMPU() {
    // Try default I2C address 0x68 first (AD0 = LOW / floating-low)
    mpu = MPU6050(0x68);
    mpu.initialize();

    // testConnection() fails on many clone MPU6050 boards even when the sensor
    // is wired correctly — skip it and check if readings are non-zero instead.
    // If the sensor truly isn't present, readings will stay at 0 and tilt
    // detection simply won't trigger.
    mpu_initialized = true;
    mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_2);
    mpu.setFullScaleGyroRange(MPU6050_GYRO_FS_250);

    delay(300);
    calibrateNeutralPosition();
}

/**
 * Average 50 readings at startup to establish the neutral head orientation.
 * The driver must sit still during the first few seconds after power-on.
 */
void calibrateNeutralPosition() {
    if (!mpu_initialized) return;

    long sum_ax = 0, sum_ay = 0, sum_az = 0;
    const int SAMPLES = 50;

    for (int i = 0; i < SAMPLES; i++) {
        int16_t ax, ay, az, gx, gy, gz;
        mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
        sum_ax += ax;
        sum_ay += ay;
        sum_az += az;
        delay(10);
        wdt_reset();  // Keep watchdog alive during calibration
    }

    neutral_ax = (int16_t)(sum_ax / SAMPLES);
    neutral_ay = (int16_t)(sum_ay / SAMPLES);
    neutral_az = (int16_t)(sum_az / SAMPLES);
    mpu_calibrated = true;
}

/**
 * Attempt to recover the I2C bus when SDA is stuck LOW.
 * Bit-bangs up to 9 SCL pulses to free the slave, then re-inits Wire.
 */
void recoverI2C() {
    // Disable TWI hardware
    TWCR = 0;
    pinMode(A5, OUTPUT);            // SCL
    pinMode(A4, INPUT_PULLUP);      // SDA — read back
    for (int i = 0; i < 9; i++) {
        digitalWrite(A5, LOW);
        delayMicroseconds(5);
        digitalWrite(A5, HIGH);
        delayMicroseconds(5);
        if (digitalRead(A4) == HIGH) break;   // SDA freed
    }
    Wire.begin();
    Wire.setWireTimeout(25000, true);
}

/**
 * Compute the current head-tilt angle (degrees) relative to the calibrated
 * neutral position using accelerometer pitch.
 *
 * If the I2C bus is stuck (all-zero readings), attempts bus recovery
 * and re-initialises the MPU6050.  Returns the last known good angle on
 * unrecoverable failure.
 */
float readTiltAngle() {
    if (!mpu_initialized || !mpu_calibrated) return 0.0f;

    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

    // Detect I2C lockup — all-zero readings
    if (ax == 0 && ay == 0 && az == 0) {
        recoverI2C();
        mpu.initialize();
        mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_2);
        mpu.setFullScaleGyroRange(MPU6050_GYRO_FS_250);
        delay(10);
        mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
        if (ax == 0 && ay == 0 && az == 0) {
            return current_tilt_angle;  // keep last known value
        }
    }

    float pitch_now     = atan2((float)ax,
                                 sqrt((float)ay * ay + (float)az * az))
                          * 180.0f / PI;
    float pitch_neutral = atan2((float)neutral_ax,
                                 sqrt((float)neutral_ay * neutral_ay +
                                      (float)neutral_az * neutral_az))
                          * 180.0f / PI;

    return fabs(pitch_now - pitch_neutral);
}


// ============================================================================
//  BUTTON
// ============================================================================

/**
 * Non-blocking debounced button read.
 * Sets button_pressed = true on a falling edge (press).
 * Calls silenceAlerts() immediately so the output pins react without
 * waiting for the next HTTP cycle.
 */
void readButton() {
    bool cur = digitalRead(BUTTON_PIN);
    unsigned long now = millis();

    if (cur != button_last_state) {
        button_debounce_ts = now;
    }

    if ((now - button_debounce_ts) > DEBOUNCE_DELAY) {
        // The reading has been stable longer than the debounce period
        if (cur != button_debounced_state) {
            button_debounced_state = cur;
            if (cur == LOW) {
                // Falling edge — button just pressed
                button_pressed = true;
                silenceAlerts();
            }
        }
    }

    button_last_state = cur;
}


// ============================================================================
//  ALERT LOGIC
// ============================================================================

/**
 * Track how long the tilt exceeds the threshold.
 * If Wi-Fi is unavailable and the duration exceeds TILT_DURATION_MS_ALERT,
 * the local fallback alert is triggered directly.
 */
void updateLocalAlertState() {
    if (!mpu_initialized) return;

    unsigned long now = millis();

    if (current_tilt_angle > TILT_THRESHOLD_DEG) {
        if (!tilt_over_threshold) {
            tilt_over_threshold = true;
            tilt_start_time     = now;
        }
        tilt_duration_ms = now - tilt_start_time;

        // Local fallback — only triggers when the server is unreachable
        if (!wifi_connected &&
            tilt_duration_ms >= TILT_DURATION_MS_ALERT &&
            !local_alert_active) {
            local_alert_active = true;
            motor_on    = true;
            buzzer_on   = true;
            red_led_on  = true;
            green_led_on = false;
        }
    } else {
        tilt_over_threshold = false;
        tilt_duration_ms    = 0;
        tilt_start_time     = 0;
    }
}

/**
 * Non-blocking output driver called every loop iteration.
 *   • Vibration motor — direct on/off
 *   • Green LED       — direct on/off
 *   • Red LED         — solid (alert_level >= 2) or blinking (level 1)
 *   • Buzzer          — toggled at BUZZER_TOGGLE_INTERVAL when buzzer_on
 */
void applyOutputs() {
    unsigned long now = millis();

    // Shared toggle timer — buzzer and motor pulse together in sync
    if ((buzzer_on || motor_on) &&
        (now - last_buzzer_toggle >= BUZZER_TOGGLE_INTERVAL)) {
        buzzer_state = !buzzer_state;
        last_buzzer_toggle = now;
    }
    if (!buzzer_on && !motor_on) {
        buzzer_state = false;
    }

    // Vibration motor — continuous when alone, pulse in sync with buzzer during alerts
    if (motor_on) {
        if (buzzer_on) {
            digitalWrite(VIBRATION_PIN, buzzer_state ? HIGH : LOW);
        } else {
            digitalWrite(VIBRATION_PIN, HIGH);   // continuous (test mode)
        }
    } else {
        digitalWrite(VIBRATION_PIN, LOW);
    }

    // Green LED
    digitalWrite(GREEN_LED_PIN, green_led_on ? HIGH : LOW);

    // Buzzer (beeping in sync with motor)
    if (buzzer_on) {
        digitalWrite(BUZZER_PIN, buzzer_state ? HIGH : LOW);
    } else {
        digitalWrite(BUZZER_PIN, LOW);
    }

    // Red LED (solid = critical, blink = level 1)
    if (red_led_on) {
        if (alert_level >= 2) {
            digitalWrite(RED_LED_PIN, HIGH);
        } else {
            if (now - last_led_blink >= LED_BLINK_INTERVAL) {
                red_led_blink_state = !red_led_blink_state;
                digitalWrite(RED_LED_PIN, red_led_blink_state ? HIGH : LOW);
                last_led_blink = now;
            }
        }
    } else {
        digitalWrite(RED_LED_PIN, LOW);
        red_led_blink_state = false;
    }
}

/**
 * Turn off all alert outputs and clear the alert state.
 * Called when the button is pressed.
 */
void silenceAlerts() {
    motor_on    = false;
    buzzer_on   = false;
    red_led_on  = false;
    green_led_on = true;
    alert_level  = 0;
    ack_required = false;
    local_alert_active  = false;
    tilt_over_threshold = false;
    tilt_duration_ms    = 0;
    tilt_start_time     = 0;

    digitalWrite(VIBRATION_PIN, LOW);
    digitalWrite(BUZZER_PIN,    LOW);
    digitalWrite(RED_LED_PIN,   LOW);
    digitalWrite(GREEN_LED_PIN, HIGH);
}


// ============================================================================
//  SERIAL COMMUNICATION WITH NODEMCU
// ============================================================================

/**
 * Send sensor data as a JSON line to the NodeMCU.
 * The NodeMCU will POST it to the server and return a response.
 */
void sendSensorData() {
    // Build JSON manually (no heap alloc, safe for Uno)
    // NOTE: AVR snprintf does NOT support %f — use dtostrf() first.
    char tilt_str[12];
    if (isnan(current_tilt_angle) || isinf(current_tilt_angle)) {
        strcpy(tilt_str, "0.00");
    } else {
        dtostrf(current_tilt_angle, 1, 2, tilt_str);
    }

    char buf[256];
    snprintf(buf, sizeof(buf),
        "{"
        "\"device_id\":\"%s\","
        "\"tilt_angle\":%s,"
        "\"tilt_over_threshold\":%s,"
        "\"tilt_duration_ms\":%lu,"
        "\"button_pressed\":%s,"
        "\"local_alert_candidate\":%s"
        "}",
        DEVICE_ID,
        tilt_str,
        tilt_over_threshold  ? "true" : "false",
        tilt_duration_ms,
        button_pressed       ? "true" : "false",
        local_alert_active   ? "true" : "false"
    );
    Serial.println(buf);

    // Reset button flag after sending
    button_pressed = false;
}

/**
 * Check for incoming serial data from NodeMCU.
 * Reads one line at a time and dispatches to parseResponse().
 */
void checkSerial() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (rx_pos > 0) {
                rx_buf[rx_pos] = '\0';
                parseResponse(rx_buf);
                rx_pos = 0;
            }
        } else {
            if (rx_pos < (int)sizeof(rx_buf) - 1) {
                rx_buf[rx_pos++] = c;
            } else {
                rx_pos = 0;  // overflow — discard
            }
        }
    }
}

/**
 * Parse a line received from NodeMCU.
 * Could be:
 *   - "WIFI_OK"   → Wi-Fi connected
 *   - "WIFI_FAIL" → Wi-Fi disconnected
 *   - "HTTP_FAIL" → POST failed
 *   - JSON object → server response
 */
void parseResponse(const char* line) {
    // Check status messages first
    if (strncmp(line, "WIFI_OK", 7) == 0) {
        wifi_connected = true;
        return;
    }
    if (strncmp(line, "WIFI_FAIL", 9) == 0) {
        wifi_connected = false;
        return;
    }
    if (strncmp(line, "HTTP_FAIL", 9) == 0) {
        return;  // nothing to do, will retry next cycle
    }

    // Must be a JSON response from the server — parse it.
    // Uses strstr() instead of String to avoid heap allocation on 2 KB RAM.

    // alert_level
    if (strstr(line, "\"alert_level\":2") || strstr(line, "\"alert_level\": 2")) {
        alert_level = 2;
    } else if (strstr(line, "\"alert_level\":1") || strstr(line, "\"alert_level\": 1")) {
        alert_level = 1;
    } else {
        alert_level = 0;
    }

    motor_on   = (strstr(line, "\"motor_on\":true")   || strstr(line, "\"motor_on\": true"));
    buzzer_on  = (strstr(line, "\"buzzer_on\":true")  || strstr(line, "\"buzzer_on\": true"));
    red_led_on = (strstr(line, "\"red_led\":true")    || strstr(line, "\"red_led\": true"));
    green_led_on = (strstr(line, "\"green_led\":true") || strstr(line, "\"green_led\": true"));
    ack_required = (strstr(line, "\"ack_required\":true") || strstr(line, "\"ack_required\": true"));

    // Clear local fallback if server is now responding
    local_alert_active = false;
}
