/**
 * Vibration Motor Test — pin D5 via S8050 NPN transistor
 * Pulses ON 500ms / OFF 500ms repeatedly.
 * Upload with:  pio run -e vibration_test --target upload
 */
#include <Arduino.h>

static const uint8_t VIBRATION_PIN = 5;  // D5

void setup() {
    pinMode(VIBRATION_PIN, OUTPUT);
    digitalWrite(VIBRATION_PIN, LOW);
    Serial.begin(115200);
    delay(300);
    Serial.println("[TEST] Vibration motor test started on D5");
}

void loop() {
    Serial.println("[TEST] Motor ON");
    digitalWrite(VIBRATION_PIN, HIGH);
    delay(500);

    Serial.println("[TEST] Motor OFF");
    digitalWrite(VIBRATION_PIN, LOW);
    delay(500);
}
