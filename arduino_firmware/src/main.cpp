/**
 * ============================================================================
 *  Driver Drowsiness Detection System
 *  Arduino + ESP-01 (AT firmware) Firmware
 *
 *  Architecture
 *  ─────────────────────────────────────────────────────────────────────────
 *  Arduino Uno → main controller
 *    • reads  MPU6050 head-tilt sensor (I2C)
 *    • reads  push button
 *    • drives green LED, red LED, vibration motor (NPN transistor), buzzer
 *    • builds JSON payloads and hands them to the ESP module
 *
 *  ESP-01 module → Wi-Fi co-processor only
 *    • communicates with Arduino over SoftwareSerial using AT commands
 *    • no custom firmware required — stock AT firmware is assumed
 *
 *  Python server (laptop) → receives POST /sensor every second, returns JSON
 *
 *  MPU6050 library: jrowberg/I2Cdevlib-MPU6050  (see platformio.ini)
 *
 *  Pin map
 *  ─────────────────────────────────────────────────────────────────────────
 *  MPU6050  SDA  → A4
 *  MPU6050  SCL  → A5
 *  ESP-01   RX  ← Arduino D3  (TX)   ⚠ see voltage-divider warning below
 *  ESP-01   TX  → Arduino D2  (RX)
 *  Button        → D4   (INPUT_PULLUP, press = LOW)
 *  Vibration     → D5   (NPN transistor base via resistor)
 *  Buzzer        → D6   (passive, PWM or digital toggle)
 *  Red LED       → D7
 *  Green LED     → D8
 *
 *  ⚠  VOLTAGE WARNING
 *  ─────────────────────────────────────────────────────────────────────────
 *  The Arduino Uno operates at 5 V logic.
 *  The ESP-01 RX pin is rated for 3.3 V maximum.
 *  You MUST use a voltage divider or logic-level shifter on the wire that
 *  runs from Arduino D3 (TX) to ESP-01 RX.
 *  A simple 1 kΩ + 2 kΩ resistor divider works:
 *      Arduino D3 ──[1kΩ]──┬── ESP RX
 *                        [2kΩ]
 *                          │
 *                         GND
 *  The Arduino RX (D2) receiving from ESP TX (3.3 V) is fine — 3.3 V logic
 *  HIGH is recognised as HIGH by a 5 V AVR, no shifter needed on that side.
 * ============================================================================
 */

#include <Arduino.h>
#include <Wire.h>
#include <SoftwareSerial.h>
#include <MPU6050.h>           // jrowberg/I2Cdevlib-MPU6050


// ============================================================================
//  CONFIGURATION — change these constants to match your environment
// ============================================================================

// Wi-Fi credentials
const char* WIFI_SSID     = "ZTE_5G_ni2RJ9";
const char* WIFI_PASSWORD = "AHdgjiAg";

// Python server — laptop local IP, port 5000, path /sensor
const char* SERVER_HOST = "192.168.1.21";
const int   SERVER_PORT = 5000;
const char* SERVER_PATH = "/sensor";

// Device identification sent in every payload
const char* DEVICE_ID = "ARD_DROWSINESS_001";

// Timing intervals (milliseconds)
const unsigned long SEND_INTERVAL          = 1000;   // POST every 1 s
const unsigned long WIFI_RETRY_INTERVAL    = 10000;  // retry Wi-Fi every 10 s
const unsigned long MPU_READ_INTERVAL      = 100;    // sample MPU every 100 ms
const unsigned long AT_SHORT_TIMEOUT_MS    = 2000;   // short AT command timeout
const unsigned long AT_CWJAP_TIMEOUT_MS    = 15000;  // Wi-Fi join timeout
const unsigned long AT_TCP_TIMEOUT_MS      = 5000;   // TCP connect / send timeout

// Tilt thresholds
const float         TILT_THRESHOLD_DEG        = 30.0;   // degrees
const unsigned long TILT_DURATION_MS_ALERT    = 3000;   // 3 s → local alert candidate

// Alert output timing
const unsigned long BUZZER_TOGGLE_INTERVAL = 500;   // buzzer beep period
const unsigned long LED_BLINK_INTERVAL     = 250;   // red LED blink period

// ESP baud rate — must match the AT firmware baud rate on your module
const long ESP_BAUD = 115200;


// ============================================================================
//  PIN DEFINITIONS
// ============================================================================

// SoftwareSerial for ESP-01 AT communication
const uint8_t ESP_RX_PIN = 2;   // Arduino D2  ← ESP TX
const uint8_t ESP_TX_PIN = 3;   // Arduino D3  → ESP RX  (USE VOLTAGE DIVIDER!)

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

SoftwareSerial espSerial(ESP_RX_PIN, ESP_TX_PIN);
MPU6050        mpu;


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
bool          button_pressed     = false;
bool          button_last_state  = HIGH;
unsigned long button_debounce_ts = 0;
const unsigned long DEBOUNCE_DELAY = 50;

// Alert state (set by server response or local fallback)
bool   motor_on     = false;
bool   buzzer_on    = false;
bool   red_led_on   = false;
bool   green_led_on = true;
bool   ack_required = false;
int    alert_level  = 0;        // 0=OK  1=Level1  2=Level2/MAX

// Local fallback flag
bool local_alert_active = false;

// ESP / Wi-Fi state
bool esp_ready      = false;
bool wifi_connected = false;

// Output toggle state
bool          buzzer_state        = false;
bool          red_led_blink_state = false;
unsigned long last_buzzer_toggle  = 0;
unsigned long last_led_blink      = 0;

// Timing
unsigned long last_send_time     = 0;
unsigned long last_wifi_retry    = 0;
unsigned long last_mpu_read      = 0;


// ============================================================================
//  FUNCTION DECLARATIONS
// ============================================================================

// MPU6050
void  initMPU();
void  calibrateNeutralPosition();
float readTiltAngle();

// Button
void readButton();

// Alert logic
void updateLocalAlertState();
void applyOutputs();
void silenceAlerts();

// ESP / AT
bool   sendATCommand(const char* cmd, const char* expected,
                     unsigned long timeout_ms);
String waitForResponse(unsigned long timeout_ms);
bool   connectESP();
bool   connectWiFi();
void   buildJsonPayload(char* buf, size_t buf_size);
bool   sendHttpPost();
void   parseServerReply(const String& reply);


// ============================================================================
//  SETUP
// ============================================================================

void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.println(F("\n========================================"));
    Serial.println(F(" Drowsiness Detection — Arduino + ESP-01"));
    Serial.println(F("========================================\n"));

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

    Serial.println(F("[INIT] GPIO configured"));

    // I2C for MPU6050
    Wire.begin();
    Serial.println(F("[INIT] I2C started"));

    // MPU6050
    initMPU();

    // SoftwareSerial for ESP-01
    espSerial.begin(ESP_BAUD);
    delay(300);
    Serial.println(F("[INIT] SoftwareSerial started for ESP-01"));

    // Bring ESP up and connect to Wi-Fi
    esp_ready = connectESP();
    if (esp_ready) {
        wifi_connected = connectWiFi();
    }

    Serial.println(F("\n[READY] Entering main loop\n"));
}


// ============================================================================
//  MAIN LOOP
// ============================================================================

void loop() {
    unsigned long now = millis();

    // ── Read MPU6050 ────────────────────────────────────────────────────────
    if (mpu_initialized && (now - last_mpu_read >= MPU_READ_INTERVAL)) {
        current_tilt_angle = readTiltAngle();
        last_mpu_read = now;
    }

    // ── Read button ─────────────────────────────────────────────────────────
    readButton();

    // ── Update local alert candidate ────────────────────────────────────────
    updateLocalAlertState();

    // ── Periodic HTTP POST ──────────────────────────────────────────────────
    if (now - last_send_time >= SEND_INTERVAL) {
        last_send_time = now;

        if (!wifi_connected && esp_ready &&
            (now - last_wifi_retry >= WIFI_RETRY_INTERVAL)) {
            Serial.println(F("[WIFI] Attempting reconnect..."));
            wifi_connected = connectWiFi();
            last_wifi_retry = now;
        }

        if (wifi_connected) {
            bool ok = sendHttpPost();
            if (!ok) {
                Serial.println(F("[HTTP] POST failed — will retry next cycle"));
                wifi_connected = false;   // probe connection next interval
            }
        } else {
            Serial.println(F("[HTTP] Skipped — no Wi-Fi"));
        }
    }

    // ── Apply outputs (non-blocking PWM/blink/beep) ─────────────────────────
    applyOutputs();

    // Yield to keep the watchdog happy
    yield();
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
    Serial.print(F("[MPU] Initialising..."));
    mpu.initialize();

    if (!mpu.testConnection()) {
        Serial.println(F(" FAILED — check SDA/SCL wiring!"));
        mpu_initialized = false;
        return;
    }

    Serial.println(F(" OK"));
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

    Serial.print(F("[MPU] Calibrating neutral position"));

    long sum_ax = 0, sum_ay = 0, sum_az = 0;
    const int SAMPLES = 50;

    for (int i = 0; i < SAMPLES; i++) {
        int16_t ax, ay, az, gx, gy, gz;
        mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
        sum_ax += ax;
        sum_ay += ay;
        sum_az += az;
        delay(10);
        if (i % 10 == 0) Serial.print('.');
    }

    neutral_ax = (int16_t)(sum_ax / SAMPLES);
    neutral_ay = (int16_t)(sum_ay / SAMPLES);
    neutral_az = (int16_t)(sum_az / SAMPLES);
    mpu_calibrated = true;

    Serial.println(F(" done"));
    Serial.print(F("[MPU] Neutral — ax:"));
    Serial.print(neutral_ax);
    Serial.print(F("  ay:"));
    Serial.print(neutral_ay);
    Serial.print(F("  az:"));
    Serial.println(neutral_az);
}

/**
 * Compute the current head-tilt angle (degrees) relative to the calibrated
 * neutral position using accelerometer pitch.
 */
float readTiltAngle() {
    if (!mpu_initialized || !mpu_calibrated) return 0.0f;

    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

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
        if (cur == LOW && button_last_state == HIGH) {
            // Falling edge — button just pressed
            button_pressed = true;
            Serial.println(F("[BTN] Pressed — silencing alerts"));
            silenceAlerts();
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
            Serial.print(F("[TILT] Exceeded threshold: "));
            Serial.print(current_tilt_angle, 1);
            Serial.print(F("° > "));
            Serial.print(TILT_THRESHOLD_DEG, 1);
            Serial.println('°');
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
            Serial.println(F("[ALERT] Local fallback triggered!"));
        }
    } else {
        if (tilt_over_threshold) {
            Serial.print(F("[TILT] Returned to normal: "));
            Serial.print(current_tilt_angle, 1);
            Serial.println('°');
        }
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

    // Vibration motor
    digitalWrite(VIBRATION_PIN, motor_on ? HIGH : LOW);

    // Green LED
    digitalWrite(GREEN_LED_PIN, green_led_on ? HIGH : LOW);

    // Buzzer (beeping)
    if (buzzer_on) {
        if (now - last_buzzer_toggle >= BUZZER_TOGGLE_INTERVAL) {
            buzzer_state = !buzzer_state;
            digitalWrite(BUZZER_PIN, buzzer_state ? HIGH : LOW);
            last_buzzer_toggle = now;
        }
    } else {
        digitalWrite(BUZZER_PIN, LOW);
        buzzer_state = false;
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

    Serial.println(F("[ALERT] Silenced"));
}


// ============================================================================
//  ESP-01 AT HELPERS
// ============================================================================

/**
 * Send an AT command string to the ESP module and wait for an expected
 * response keyword (e.g. "OK", "CONNECT", "SEND OK").
 *
 * @param cmd       null-terminated command string  (e.g. "AT+CWMODE=1")
 * @param expected  substring to look for in the reply (e.g. "OK")
 * @param timeout_ms  how long to wait in milliseconds
 * @return true if the expected substring was found before timeout
 *
 * A trailing '\r\n' is appended automatically.
 */
bool sendATCommand(const char* cmd, const char* expected,
                   unsigned long timeout_ms) {
    // Flush any pending data
    while (espSerial.available()) espSerial.read();

    Serial.print(F("[AT] >> "));
    Serial.println(cmd);

    espSerial.print(cmd);
    espSerial.print(F("\r\n"));

    String response = waitForResponse(timeout_ms);

    Serial.print(F("[AT] << "));
    Serial.println(response);

    return response.indexOf(expected) != -1;
}

/**
 * Read all bytes from espSerial until timeout_ms elapses with no new data,
 * or the buffer overflows.  Returns the accumulated string.
 */
String waitForResponse(unsigned long timeout_ms) {
    String resp;
    resp.reserve(256);
    unsigned long start   = millis();
    unsigned long last_rx = millis();

    while (true) {
        while (espSerial.available()) {
            char c = (char)espSerial.read();
            resp += c;
            last_rx = millis();
            if (resp.length() > 512) break;   // safety cap
        }
        // Done when we haven't received anything for 200 ms OR hard timeout
        if ((millis() - last_rx > 200) && resp.length() > 0) break;
        if (millis() - start > timeout_ms) break;
    }

    return resp;
}

/**
 * Wake the ESP module and put it into station mode.
 * Returns true if the module responds to AT and accepts CWMODE=1.
 */
bool connectESP() {
    Serial.println(F("[ESP] Initialising AT interface..."));

    // Some modules need a moment after power-on
    delay(1000);

    // Clear garbage
    while (espSerial.available()) espSerial.read();

    // Test basic communication — try up to 3 times
    for (int attempt = 1; attempt <= 3; attempt++) {
        Serial.print(F("[ESP] AT test attempt "));
        Serial.println(attempt);
        if (sendATCommand("AT", "OK", AT_SHORT_TIMEOUT_MS)) {
            Serial.println(F("[ESP] AT OK"));
            break;
        }
        if (attempt == 3) {
            Serial.println(F("[ESP] No response from ESP module! Check wiring."));
            return false;
        }
        delay(500);
    }

    // Disable echo so responses are easier to parse
    sendATCommand("ATE0", "OK", AT_SHORT_TIMEOUT_MS);

    // Station mode (client)
    if (!sendATCommand("AT+CWMODE=1", "OK", AT_SHORT_TIMEOUT_MS)) {
        Serial.println(F("[ESP] Failed to set station mode"));
        return false;
    }

    Serial.println(F("[ESP] Ready — station mode set"));
    return true;
}

/**
 * Join the Wi-Fi network.
 * Returns true if CWJAP reports "WIFI GOT IP" within the timeout.
 */
bool connectWiFi() {
    Serial.print(F("[WIFI] Connecting to "));
    Serial.println(WIFI_SSID);

    // Build the AT+CWJAP command string dynamically
    char cmd[128];
    snprintf(cmd, sizeof(cmd), "AT+CWJAP=\"%s\",\"%s\"",
             WIFI_SSID, WIFI_PASSWORD);

    if (!sendATCommand(cmd, "WIFI GOT IP", AT_CWJAP_TIMEOUT_MS)) {
        Serial.println(F("[WIFI] Connection failed"));
        return false;
    }

    Serial.println(F("[WIFI] Connected!"));
    return true;
}


// ============================================================================
//  HTTP POST VIA AT COMMANDS
// ============================================================================

/**
 * Build the JSON payload into the caller-supplied buffer.
 * Manual string construction — no heap allocation, safe on Uno.
 */
void buildJsonPayload(char* buf, size_t buf_size) {
    // tilt_duration_ms as integer, tilt_angle with 2 decimal places
    snprintf(buf, buf_size,
        "{"
        "\"device_id\":\"%s\","
        "\"tilt_angle\":%.2f,"
        "\"tilt_over_threshold\":%s,"
        "\"tilt_duration_ms\":%lu,"
        "\"button_pressed\":%s,"
        "\"local_alert_candidate\":%s"
        "}",
        DEVICE_ID,
        current_tilt_angle,
        tilt_over_threshold  ? "true" : "false",
        tilt_duration_ms,
        button_pressed       ? "true" : "false",
        local_alert_active   ? "true" : "false"
    );
}

/**
 * Open a TCP connection to the Python server, send an HTTP POST request
 * containing the JSON payload, read the response, then close the connection.
 *
 * Returns true if the response was received (even partial); false on error.
 *
 * AT command sequence used:
 *   1. AT+CIPSTART="TCP","<host>",<port>   — open TCP socket
 *   2. AT+CIPSEND=<byte_count>             — tell ESP how many bytes follow
 *   3. <raw HTTP request>                  — send the actual data
 *   4. AT+CIPCLOSE                         — close socket
 */
bool sendHttpPost() {
    // ── 1. Build JSON payload ────────────────────────────────────────────
    char json_body[256];
    buildJsonPayload(json_body, sizeof(json_body));
    int body_len = strlen(json_body);

    // ── 2. Build the full HTTP request ───────────────────────────────────
    //    We need the exact byte length before sending AT+CIPSEND.
    char http_req[384];
    int req_len = snprintf(http_req, sizeof(http_req),
        "POST %s HTTP/1.1\r\n"
        "Host: %s:%d\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n"
        "\r\n"
        "%s",
        SERVER_PATH,
        SERVER_HOST, SERVER_PORT,
        body_len,
        json_body
    );

    if (req_len <= 0 || (size_t)req_len >= sizeof(http_req)) {
        Serial.println(F("[HTTP] Request buffer too small!"));
        return false;
    }

    // ── 3. AT+CIPSTART — open TCP socket ─────────────────────────────────
    char cipstart_cmd[80];
    snprintf(cipstart_cmd, sizeof(cipstart_cmd),
             "AT+CIPSTART=\"TCP\",\"%s\",%d", SERVER_HOST, SERVER_PORT);

    Serial.println(F("[HTTP] Opening TCP connection..."));
    if (!sendATCommand(cipstart_cmd, "CONNECT", AT_TCP_TIMEOUT_MS)) {
        Serial.println(F("[HTTP] TCP CIPSTART failed"));
        // Module may already have an open connection — close it and return
        sendATCommand("AT+CIPCLOSE", "OK", AT_SHORT_TIMEOUT_MS);
        return false;
    }

    // ── 4. AT+CIPSEND — declare byte count ───────────────────────────────
    char cipsend_cmd[32];
    snprintf(cipsend_cmd, sizeof(cipsend_cmd), "AT+CIPSEND=%d", req_len);

    if (!sendATCommand(cipsend_cmd, ">", AT_TCP_TIMEOUT_MS)) {
        Serial.println(F("[HTTP] CIPSEND prompt not received"));
        sendATCommand("AT+CIPCLOSE", "OK", AT_SHORT_TIMEOUT_MS);
        return false;
    }

    // ── 5. Write raw HTTP request bytes ──────────────────────────────────
    Serial.println(F("[HTTP] Sending request body..."));
    espSerial.print(http_req);

    // Wait for ESP to confirm the data was delivered
    String send_response = waitForResponse(AT_TCP_TIMEOUT_MS);
    Serial.print(F("[HTTP] SEND response: "));
    Serial.println(send_response);

    if (send_response.indexOf("SEND OK") == -1) {
        Serial.println(F("[HTTP] Data send failed"));
        sendATCommand("AT+CIPCLOSE", "OK", AT_SHORT_TIMEOUT_MS);
        return false;
    }

    // ── 6. Read the HTTP response ─────────────────────────────────────────
    //    The server will send the response and then close the connection
    //    (Connection: close).  We collect data for up to AT_TCP_TIMEOUT_MS.
    Serial.println(F("[HTTP] Waiting for server response..."));
    String server_reply = waitForResponse(AT_TCP_TIMEOUT_MS);
    Serial.print(F("[HTTP] Reply: "));
    Serial.println(server_reply);

    // ── 7. Parse reply ────────────────────────────────────────────────────
    if (server_reply.length() > 0) {
        parseServerReply(server_reply);
    }

    // ── 8. AT+CIPCLOSE ────────────────────────────────────────────────────
    sendATCommand("AT+CIPCLOSE", "OK", AT_SHORT_TIMEOUT_MS);

    // Reset button flag after a successful send
    button_pressed = false;

    return true;
}


// ============================================================================
//  RESPONSE PARSING
// ============================================================================

/**
 * Scan the raw HTTP response text for known JSON keywords and update the
 * alert output variables accordingly.
 *
 * This avoids a full JSON parser (too heavy for Uno's 2 KB SRAM).
 * It looks for exact substrings expected from the Python server, e.g.:
 *   "alert_level":1  "motor_on":true  "buzzer_on":false  etc.
 *
 * The approach is robust enough for a controlled private protocol where the
 * key names are known in advance.
 */
void parseServerReply(const String& reply) {
    // ── alert_level ──────────────────────────────────────────────────────
    if (reply.indexOf(F("\"alert_level\":2")) != -1 ||
        reply.indexOf(F("\"alert_level\": 2")) != -1 ||
        reply.indexOf(F("\"alert_level\":\"MAX\"")) != -1 ||
        reply.indexOf(F("\"alert_level\": \"MAX\"")) != -1) {
        alert_level = 2;
    } else if (reply.indexOf(F("\"alert_level\":1")) != -1 ||
               reply.indexOf(F("\"alert_level\": 1")) != -1) {
        alert_level = 1;
    } else {
        alert_level = 0;
    }

    // ── motor_on ─────────────────────────────────────────────────────────
    if (reply.indexOf(F("\"motor_on\":true")) != -1 ||
        reply.indexOf(F("\"motor_on\": true")) != -1) {
        motor_on = true;
    } else if (reply.indexOf(F("\"motor_on\":false")) != -1 ||
               reply.indexOf(F("\"motor_on\": false")) != -1) {
        motor_on = false;
    }

    // ── buzzer_on ─────────────────────────────────────────────────────────
    if (reply.indexOf(F("\"buzzer_on\":true")) != -1 ||
        reply.indexOf(F("\"buzzer_on\": true")) != -1) {
        buzzer_on = true;
    } else if (reply.indexOf(F("\"buzzer_on\":false")) != -1 ||
               reply.indexOf(F("\"buzzer_on\": false")) != -1) {
        buzzer_on = false;
    }

    // ── red_led ───────────────────────────────────────────────────────────
    if (reply.indexOf(F("\"red_led\":true")) != -1 ||
        reply.indexOf(F("\"red_led\": true")) != -1) {
        red_led_on = true;
    } else if (reply.indexOf(F("\"red_led\":false")) != -1 ||
               reply.indexOf(F("\"red_led\": false")) != -1) {
        red_led_on = false;
    }

    // ── green_led ─────────────────────────────────────────────────────────
    if (reply.indexOf(F("\"green_led\":false")) != -1 ||
        reply.indexOf(F("\"green_led\": false")) != -1) {
        green_led_on = false;
    } else if (reply.indexOf(F("\"green_led\":true")) != -1 ||
               reply.indexOf(F("\"green_led\": true")) != -1) {
        green_led_on = true;
    }

    // ── ack_required ──────────────────────────────────────────────────────
    ack_required = (reply.indexOf(F("\"ack_required\":true")) != -1 ||
                    reply.indexOf(F("\"ack_required\": true")) != -1);

    Serial.print(F("[PARSE] alert_level="));
    Serial.print(alert_level);
    Serial.print(F("  motor="));
    Serial.print(motor_on);
    Serial.print(F("  buzzer="));
    Serial.print(buzzer_on);
    Serial.print(F("  red_led="));
    Serial.println(red_led_on);
}
