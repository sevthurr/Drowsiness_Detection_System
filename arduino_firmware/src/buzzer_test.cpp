#include <Arduino.h>

static const uint8_t BUZZER_PIN = 6;

void setup() {
  pinMode(BUZZER_PIN, OUTPUT);
  Serial.begin(115200);
  delay(300);
  Serial.println("[TEST] Buzzer test started on D6");
}

void loop() {
  tone(BUZZER_PIN, 2000);
  delay(500);
  noTone(BUZZER_PIN);
  delay(500);
}
