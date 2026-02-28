/**
 * Driver Drowsiness Detection System - ESP8266 Firmware
 * 
 * Hardware Controller for Wearable Alert System
 * - Reads MPU6050 head-tilt sensor
 * - Controls LEDs, vibration motor, and buzzer
 * - Communicates with Python server via WiFi/HTTP
 * - Implements local fallback alert logic
 * 
 * Board: NodeMCU 1.0 (ESP-12E Module)
 * Framework: Arduino (PlatformIO)
 */

#include <Arduino.h>
#include <Wire.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include <MPU6050.h>

// ======================== CONFIGURATION ========================

// WiFi credentials (CHANGE THESE!)
const char* WIFI_SSID = "YourWiFiSSID";
const char* WIFI_PASSWORD = "YourWiFiPassword";

// Python server endpoint (CHANGE THIS!)
const char* SERVER_URL = "http://192.168.1.100:5000/sensor-data";

// Device identification
const char* DEVICE_ID = "ESP8266_DROWSINESS_001";

// Timing intervals (milliseconds)
const unsigned long SEND_INTERVAL = 1000;       // Send data every 1 second
const unsigned long WIFI_RETRY_INTERVAL = 5000; // Retry WiFi every 5 seconds
const unsigned long MPU_READ_INTERVAL = 100;    // Read MPU every 100ms

// Tilt detection thresholds
const float TILT_THRESHOLD_DEG = 30.0;          // Degrees
const unsigned long TILT_DURATION_THRESHOLD = 3000; // 3 seconds

// Alert behavior
const unsigned long BUZZER_BEEP_INTERVAL = 500; // Beep every 500ms
const unsigned long LED_BLINK_INTERVAL = 250;   // Blink every 250ms

// ======================== PIN DEFINITIONS ========================

// MPU6050 I2C pins
const uint8_t MPU_SDA_PIN = D2;  // GPIO4
const uint8_t MPU_SCL_PIN = D1;  // GPIO5

// Output pins
const uint8_t VIBRATION_PIN = D5;  // GPIO14
const uint8_t BUZZER_PIN = D6;     // GPIO12
const uint8_t RED_LED_PIN = D7;    // GPIO13
const uint8_t GREEN_LED_PIN = D0;  // GPIO16

// Input pins
const uint8_t BUTTON_PIN = D3;     // GPIO0 (with INPUT_PULLUP)

// ======================== GLOBAL VARIABLES ========================

// MPU6050 sensor object
MPU6050 mpu;

// Calibration values
int16_t neutral_ax, neutral_ay, neutral_az;
bool mpu_initialized = false;
bool mpu_calibrated = false;

// Current sensor readings
float current_tilt_angle = 0.0;
bool tilt_over_threshold = false;
unsigned long tilt_start_time = 0;
unsigned long tilt_duration_ms = 0;

// Button state
bool button_pressed = false;
bool button_last_state = HIGH;
unsigned long button_debounce_time = 0;
const unsigned long DEBOUNCE_DELAY = 50;

// Alert state
bool local_alert_active = false;
bool motor_on = false;
bool buzzer_on = false;
bool red_led_on = false;
bool green_led_on = true;
bool ack_required = false;

// Server response state
String alert_level = "OK";
float visual_score = 0.0;

// Timing control
unsigned long last_send_time = 0;
unsigned long last_wifi_retry = 0;
unsigned long last_mpu_read = 0;
unsigned long last_buzzer_toggle = 0;
unsigned long last_led_blink = 0;

// Buzzer and LED toggle states
bool buzzer_state = false;
bool red_led_blink_state = false;

// WiFi status
bool wifi_connected = false;

// ======================== FUNCTION DECLARATIONS ========================

void connectWiFi();
void initMPU();
void calibrateNeutralPosition();
float readTiltAngle();
void readButton();
String buildPayload();
void sendToPython();
void parseServerResponse(String response);
void applyOutputs();
void silenceAlerts();
void updateLocalAlertState();
void setOutputs(bool motor, bool buzzer, bool red_led, bool green_led);

// ======================== SETUP ========================

void setup() {
  Serial.begin(115200);
  delay(500);
  
  Serial.println("\n\n========================================");
  Serial.println("Driver Drowsiness Detection System");
  Serial.println("ESP8266 Firmware v1.0");
  Serial.println("========================================\n");

  // Initialize pins
  pinMode(VIBRATION_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Initial output states - all off except green LED
  digitalWrite(VIBRATION_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, HIGH);

  Serial.println("[INIT] GPIO pins configured");

  // Initialize I2C for MPU6050
  Wire.begin(MPU_SDA_PIN, MPU_SCL_PIN);
  Serial.println("[INIT] I2C initialized");

  // Initialize MPU6050
  initMPU();

  // Connect to WiFi
  connectWiFi();

  Serial.println("\n[READY] System initialized and ready!\n");
}

// ======================== MAIN LOOP ========================

void loop() {
  unsigned long current_millis = millis();

  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    wifi_connected = false;
    if (current_millis - last_wifi_retry >= WIFI_RETRY_INTERVAL) {
      connectWiFi();
      last_wifi_retry = current_millis;
    }
  } else {
    wifi_connected = true;
  }

  // Read MPU6050 sensor periodically
  if (mpu_initialized && current_millis - last_mpu_read >= MPU_READ_INTERVAL) {
    current_tilt_angle = readTiltAngle();
    last_mpu_read = current_millis;
  }

  // Read button (with debouncing)
  readButton();

  // Update local alert state based on tilt duration
  updateLocalAlertState();

  // Send data to Python server periodically
  if (wifi_connected && current_millis - last_send_time >= SEND_INTERVAL) {
    sendToPython();
    last_send_time = current_millis;
  }

  // Apply output states (handles buzzer beeping and LED blinking)
  applyOutputs();

  // Small delay to prevent WDT issues
  yield();
}

// ======================== FUNCTION IMPLEMENTATIONS ========================

/**
 * Connect to WiFi network with retry logic
 */
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.print("[WIFI] Connecting to ");
  Serial.print(WIFI_SSID);
  Serial.print("...");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(" Connected!");
    Serial.print("[WIFI] IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("[WIFI] Signal Strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    wifi_connected = true;
  } else {
    Serial.println(" Failed!");
    Serial.println("[WIFI] Will retry in 5 seconds...");
    wifi_connected = false;
  }
}

/**
 * Initialize MPU6050 sensor
 */
void initMPU() {
  Serial.print("[MPU6050] Initializing sensor...");
  
  mpu.initialize();
  
  if (mpu.testConnection()) {
    Serial.println(" Success!");
    mpu_initialized = true;
    
    // Configure MPU6050 settings
    mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_2);
    mpu.setFullScaleGyroRange(MPU6050_GYRO_FS_250);
    
    // Calibrate neutral position
    delay(500);
    calibrateNeutralPosition();
  } else {
    Serial.println(" Failed!");
    Serial.println("[ERROR] MPU6050 not responding. Check wiring!");
    mpu_initialized = false;
  }
}

/**
 * Calibrate neutral head position (average of readings)
 */
void calibrateNeutralPosition() {
  if (!mpu_initialized) {
    return;
  }

  Serial.print("[MPU6050] Calibrating neutral position");
  
  long sum_ax = 0, sum_ay = 0, sum_az = 0;
  const int samples = 50;
  
  for (int i = 0; i < samples; i++) {
    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    
    sum_ax += ax;
    sum_ay += ay;
    sum_az += az;
    
    delay(10);
    if (i % 10 == 0) Serial.print(".");
  }
  
  neutral_ax = sum_ax / samples;
  neutral_ay = sum_ay / samples;
  neutral_az = sum_az / samples;
  
  mpu_calibrated = true;
  
  Serial.println(" Done!");
  Serial.printf("[MPU6050] Neutral: ax=%d, ay=%d, az=%d\n", 
                neutral_ax, neutral_ay, neutral_az);
}

/**
 * Read current tilt angle from MPU6050
 * Returns angle in degrees from neutral position
 */
float readTiltAngle() {
  if (!mpu_initialized || !mpu_calibrated) {
    return 0.0;
  }

  int16_t ax, ay, az, gx, gy, gz;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

  // Calculate tilt angle using accelerometer
  // Using pitch calculation: atan2(ax, sqrt(ay^2 + az^2))
  float pitch_current = atan2(ax, sqrt(ay * ay + az * az)) * 180.0 / PI;
  float pitch_neutral = atan2(neutral_ax, sqrt(neutral_ay * neutral_ay + neutral_az * neutral_az)) * 180.0 / PI;
  
  float tilt = abs(pitch_current - pitch_neutral);
  
  return tilt;
}

/**
 * Read button state with debouncing
 */
void readButton() {
  bool current_state = digitalRead(BUTTON_PIN);
  unsigned long current_time = millis();

  // Check for state change
  if (current_state != button_last_state) {
    button_debounce_time = current_time;
  }

  // If stable for debounce delay
  if ((current_time - button_debounce_time) > DEBOUNCE_DELAY) {
    // Button pressed (LOW because of INPUT_PULLUP)
    if (current_state == LOW && button_last_state == HIGH) {
      button_pressed = true;
      Serial.println("[BUTTON] Pressed - Silencing alerts");
      silenceAlerts();
    }
  }

  button_last_state = current_state;
}

/**
 * Build JSON payload for Python server
 */
String buildPayload() {
  StaticJsonDocument<512> doc;
  
  doc["device_id"] = DEVICE_ID;
  doc["tilt_angle"] = round(current_tilt_angle * 100) / 100.0;
  doc["tilt_over_threshold"] = tilt_over_threshold;
  doc["tilt_duration_ms"] = tilt_duration_ms;
  doc["button_pressed"] = button_pressed;
  doc["local_alert_candidate"] = local_alert_active;
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["uptime_ms"] = millis();
  
  String payload;
  serializeJson(doc, payload);
  
  return payload;
}

/**
 * Send data to Python server via HTTP POST
 */
void sendToPython() {
  if (!wifi_connected) {
    Serial.println("[HTTP] WiFi not connected, skipping send");
    return;
  }

  WiFiClient client;
  HTTPClient http;

  String payload = buildPayload();
  
  Serial.print("[HTTP] Sending to server... ");
  
  http.begin(client, SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  
  int httpCode = http.POST(payload);
  
  if (httpCode > 0) {
    Serial.printf("Response: %d\n", httpCode);
    
    if (httpCode == HTTP_CODE_OK) {
      String response = http.getString();
      Serial.print("[HTTP] Response: ");
      Serial.println(response);
      parseServerResponse(response);
    }
  } else {
    Serial.printf("Failed: %s\n", http.errorToString(httpCode).c_str());
    // Use local fallback if server unreachable
    Serial.println("[ALERT] Server unreachable, using local fallback");
  }
  
  http.end();
  
  // Reset button pressed flag after sending
  button_pressed = false;
}

/**
 * Parse JSON response from Python server
 */
void parseServerResponse(String response) {
  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, response);
  
  if (error) {
    Serial.print("[JSON] Parse error: ");
    Serial.println(error.c_str());
    return;
  }

  // Extract fields (with defaults if missing)
  visual_score = doc["visual_score"] | 0.0;
  alert_level = doc["alert_level"] | "OK";
  motor_on = doc["motor_on"] | false;
  buzzer_on = doc["buzzer_on"] | false;
  red_led_on = doc["red_led"] | false;
  green_led_on = doc["green_led"] | true;
  ack_required = doc["ack_required"] | false;

  Serial.printf("[SERVER] Alert: %s, Motor: %d, Buzzer: %d\n", 
                alert_level.c_str(), motor_on, buzzer_on);
}

/**
 * Apply output states with buzzer beeping and LED blinking
 */
void applyOutputs() {
  unsigned long current_time = millis();

  // Vibration motor - direct control
  digitalWrite(VIBRATION_PIN, motor_on ? HIGH : LOW);

  // Green LED - direct control
  digitalWrite(GREEN_LED_PIN, green_led_on ? HIGH : LOW);

  // Buzzer - beep on/off if buzzer_on is true
  if (buzzer_on) {
    if (current_time - last_buzzer_toggle >= BUZZER_BEEP_INTERVAL) {
      buzzer_state = !buzzer_state;
      digitalWrite(BUZZER_PIN, buzzer_state ? HIGH : LOW);
      last_buzzer_toggle = current_time;
    }
  } else {
    digitalWrite(BUZZER_PIN, LOW);
    buzzer_state = false;
  }

  // Red LED - blink if alert active, solid if critical
  if (red_led_on) {
    if (alert_level == "MAX" || alert_level == "Level 2") {
      // Solid red for critical alerts
      digitalWrite(RED_LED_PIN, HIGH);
    } else {
      // Blink for Level 1
      if (current_time - last_led_blink >= LED_BLINK_INTERVAL) {
        red_led_blink_state = !red_led_blink_state;
        digitalWrite(RED_LED_PIN, red_led_blink_state ? HIGH : LOW);
        last_led_blink = current_time;
      }
    }
  } else {
    digitalWrite(RED_LED_PIN, LOW);
    red_led_blink_state = false;
  }
}

/**
 * Silence all alerts when button is pressed
 */
void silenceAlerts() {
  motor_on = false;
  buzzer_on = false;
  red_led_on = false;
  green_led_on = true;
  local_alert_active = false;
  ack_required = false;
  
  // Reset tilt tracking
  tilt_over_threshold = false;
  tilt_duration_ms = 0;
  tilt_start_time = 0;
  
  setOutputs(false, false, false, true);
  
  Serial.println("[ALERT] All alerts silenced");
}

/**
 * Update local alert state based on tilt sensor
 * (Fallback if Python server is unreachable)
 */
void updateLocalAlertState() {
  if (!mpu_initialized) {
    return;
  }

  unsigned long current_time = millis();

  // Check if tilt exceeds threshold
  if (current_tilt_angle > TILT_THRESHOLD_DEG) {
    if (!tilt_over_threshold) {
      // Tilt just exceeded threshold
      tilt_over_threshold = true;
      tilt_start_time = current_time;
      Serial.printf("[TILT] Exceeded threshold: %.1f° > %.1f°\n", 
                    current_tilt_angle, TILT_THRESHOLD_DEG);
    }
    
    // Calculate duration
    tilt_duration_ms = current_time - tilt_start_time;
    
    // Trigger local alert if duration exceeds threshold
    if (tilt_duration_ms >= TILT_DURATION_THRESHOLD && !local_alert_active) {
      local_alert_active = true;
      Serial.printf("[ALERT] Local alert triggered! Tilt duration: %lu ms\n", 
                    tilt_duration_ms);
      
      // Activate local fallback alerts
      if (!wifi_connected) {
        motor_on = true;
        buzzer_on = true;
        red_led_on = true;
        green_led_on = false;
        Serial.println("[ALERT] Using local fallback (no server)");
      }
    }
  } else {
    // Tilt back to normal
    if (tilt_over_threshold) {
      Serial.printf("[TILT] Returned to normal: %.1f°\n", current_tilt_angle);
    }
    tilt_over_threshold = false;
    tilt_duration_ms = 0;
    tilt_start_time = 0;
  }
}

/**
 * Directly set output states (helper function)
 */
void setOutputs(bool motor, bool buzzer, bool red_led, bool green_led) {
  digitalWrite(VIBRATION_PIN, motor ? HIGH : LOW);
  digitalWrite(BUZZER_PIN, buzzer ? HIGH : LOW);
  digitalWrite(RED_LED_PIN, red_led ? HIGH : LOW);
  digitalWrite(GREEN_LED_PIN, green_led ? HIGH : LOW);
}
