#include <Wire.h>

#define SDA_PIN 6
#define SCL_PIN 7

void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);
  Serial.println("Đang quét I2C...");
}

void loop() {
  byte error, address;
  int nDevices = 0;

  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Thiết bị I2C tìm thấy ở địa chỉ 0x");
      Serial.println(address, HEX);
      nDevices++;
    }
  }

  if (nDevices == 0) Serial.println("Không tìm thấy thiết bị nào\n");
  else Serial.println("Hoàn tất quét\n");

  delay(2000);
}
