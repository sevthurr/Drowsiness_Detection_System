/**
 * ============================================================================
 *  Driver Drowsiness Detection System — NodeMCU Wi-Fi Bridge
 *
 *  This firmware turns the NodeMCU into a transparent Wi-Fi bridge:
 *    1. Connects to Wi-Fi on boot
 *    2. Reads JSON lines from Serial (from Arduino on pins TX/RX)
 *    3. POSTs each line to the Python server via HTTP
 *    4. Sends the server's JSON response back over Serial to the Arduino
 *
 *  Serial protocol (line-based, 115200 baud):
 *    Arduino → NodeMCU:  {"device_id":"...","tilt_angle":12.3,...}\n
 *    NodeMCU → Arduino:  {"alert_level":0,"motor_on":false,...}\n
 *    NodeMCU → Arduino:  WIFI_OK\n       (on connect)
 *    NodeMCU → Arduino:  WIFI_FAIL\n     (on disconnect)
 *    NodeMCU → Arduino:  HTTP_FAIL\n     (on POST error)
 *
 *  Board: NodeMCU 1.0 (ESP-12E)   Framework: Arduino (PlatformIO)
 *
 *  Wiring to Arduino Uno:
 *    NodeMCU TX  → Arduino RX (pin 0)
 *    NodeMCU RX  ← Arduino TX (pin 1) via voltage divider (5V→3.3V)
 *    GND         ↔ GND (common ground)
 *    NodeMCU powered via its own USB or from Arduino 3.3V pin
 * ============================================================================
 */

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

// ======================== CONFIGURATION ========================

// Wi-Fi credentials
const char* WIFI_SSID     = "realme6";
const char* WIFI_PASSWORD = "GagoKaba?";

// Python server endpoint
const char* SERVER_HOST = "10.54.2.199";
const int   SERVER_PORT = 5000;
const char* SERVER_PATH = "/sensor";

// Timing
const unsigned long WIFI_RETRY_INTERVAL = 10000;  // ms between reconnect tries
const unsigned long HTTP_TIMEOUT        = 5000;    // ms HTTP response timeout

// ======================== GLOBALS ========================

bool     wifi_connected    = false;
unsigned long last_wifi_try = 0;
unsigned long last_command_poll = 0;
const unsigned long COMMAND_POLL_INTERVAL = 1000;  // poll /command every 1s
String   serial_buffer;

// ======================== FUNCTION DECLARATIONS ========================

void connectWiFi();
void handleSerialLine(const String& line);
String doHttpPost(const String& json_body);
String doHttpGet(const String& path);

// ======================== SETUP ========================

void setup() {
    // Increase UART RX buffer BEFORE Serial.begin so it takes effect.
    // Default is 64 bytes which overflows (~155-byte JSON) while HTTP POST blocks.
    Serial.setRxBufferSize(512);

    // Serial talks to the Arduino Uno (115200 baud, matching Arduino)
    Serial.begin(115200);
    serial_buffer.reserve(512);

    // Small delay for boot stability
    delay(500);

    // Connect to Wi-Fi
    connectWiFi();
}

// ======================== MAIN LOOP ========================

void loop() {
    // ── Check Wi-Fi ─────────────────────────────────────────────────
    if (WiFi.status() != WL_CONNECTED) {
        if (wifi_connected) {
            wifi_connected = false;
            Serial.println(F("WIFI_FAIL"));
        }
        unsigned long now = millis();
        if (now - last_wifi_try >= WIFI_RETRY_INTERVAL) {
            connectWiFi();
            last_wifi_try = now;
        }
    } else if (!wifi_connected) {
        wifi_connected = true;
        Serial.println(F("WIFI_OK"));
    }

    // ── Read serial lines from Arduino ──────────────────────────────
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n') {
            serial_buffer.trim();
            if (serial_buffer.length() > 0 && serial_buffer.charAt(0) == '{') {
                handleSerialLine(serial_buffer);
            }
            serial_buffer = "";
        } else if (c != '\r') {
            serial_buffer += c;
            if (serial_buffer.length() > 500) {
                serial_buffer = "";
            }
        }
    }

    // ── Poll /command for GUI-driven alerts ─────────────────────────
    if (wifi_connected) {
        unsigned long now2 = millis();
        if (now2 - last_command_poll >= COMMAND_POLL_INTERVAL) {
            last_command_poll = now2;
            String cmd = doHttpGet("/command");
            if (cmd.length() > 0) {
                Serial.println(cmd);
            }
        }
    }

    yield();
}

// ======================== WI-FI ========================

void connectWiFi() {
    WiFi.persistent(false);
    WiFi.mode(WIFI_OFF);
    delay(100);
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(200);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 40) {
        delay(500);
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        wifi_connected = true;
        Serial.println(F("WIFI_OK"));
    } else {
        wifi_connected = false;
        Serial.println(F("WIFI_FAIL"));
    }
}

// ======================== SERIAL LINE HANDLER ========================

void handleSerialLine(const String& line) {
    if (!wifi_connected) {
        Serial.println(F("WIFI_FAIL"));
        return;
    }

    String response = doHttpPost(line);
    if (response.length() > 0) {
        Serial.println(response);
    } else {
        Serial.println(F("HTTP_FAIL"));
    }
}

// ======================== HTTP POST ========================

String doHttpPost(const String& json_body) {
    WiFiClient client;
    HTTPClient http;

    String url = "http://";
    url += SERVER_HOST;
    url += ":";
    url += SERVER_PORT;
    url += SERVER_PATH;

    http.begin(client, url);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(HTTP_TIMEOUT);

    int httpCode = http.POST(json_body);

    String result = "";
    if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED) {
        result = http.getString();
        result.trim();
    }

    http.end();
    return result;
}

// ======================== HTTP GET ========================

String doHttpGet(const String& path) {
    WiFiClient client;
    HTTPClient http;

    String url = "http://";
    url += SERVER_HOST;
    url += ":";
    url += SERVER_PORT;
    url += path;

    http.begin(client, url);
    http.setTimeout(HTTP_TIMEOUT);

    int httpCode = http.GET();

    String result = "";
    if (httpCode == HTTP_CODE_OK) {
        result = http.getString();
        result.trim();
    }

    http.end();
    return result;
}

