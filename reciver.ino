#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

void showLine(int row, String text) {
  // Pad/trim to exactly 16 characters to wipe out old text artifacts
  while (text.length() < 16) text += " ";
  text = text.substring(0, 16);
  lcd.setCursor(0, row);
  lcd.print(text);
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(100);
  lcd.init();
  lcd.backlight();
  showLine(0, "Ready for Lyrics");
  showLine(1, "");
}

void loop() {
  if (Serial.available() > 0) {
    String incoming = Serial.readStringUntil('\n');
    incoming.trim();

    int separator = incoming.indexOf('|');
    if (separator != -1) {
      showLine(0, incoming.substring(0, separator));
      showLine(1, incoming.substring(separator + 1));
    }
  }
}
