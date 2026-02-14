#include <Arduino.h>
#include "driver/i2s.h"
#include <math.h>
#include "pins_arduino.h"

constexpr int I2S_MCLK_PIN = I2S0_MCLK;
constexpr int I2S_BCLK_PIN = I2S0_SCLK;
constexpr int I2S_LRCK_PIN = I2S0_LRCK;
constexpr int I2S_DATA_OUT_PIN = I2S0_DSDIN;
constexpr int AMP_ENABLE_PIN = PA_CTRL;

constexpr uint32_t SAMPLE_RATE = 16000;
constexpr size_t BUFFER_SAMPLES = 256;
constexpr float TWO_PI = 2.0f * 3.14159265f;
constexpr float AMPLITUDE = 0.25f;

struct Note {
  float frequency;
  uint16_t duration_ms;
};

constexpr Note kMelody[] = {
  {261.63f, 450}, // Do (C4)
  {293.66f, 450}, // Re (D4)
  {329.63f, 450}, // Mi (E4)
  {0.0f,    200}  // Rest
};

constexpr size_t kMelodyCount = sizeof(kMelody) / sizeof(kMelody[0]);

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    delay(10);
  }
  Serial.println("CYOBot audio test: Do-Re-Mi");

  pinMode(AMP_ENABLE_PIN, OUTPUT);
  digitalWrite(AMP_ENABLE_PIN, HIGH);

  i2s_config_t i2s_config = {
    .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = BUFFER_SAMPLES,
    .use_apll = false,
    .tx_desc_auto_clear = true,
    .fixed_mclk = SAMPLE_RATE * 256
  };

  i2s_pin_config_t pin_config = {
    .mck_io_num = I2S_MCLK_PIN,
    .bck_io_num = I2S_BCLK_PIN,
    .ws_io_num = I2S_LRCK_PIN,
    .data_out_num = I2S_DATA_OUT_PIN,
    .data_in_num = I2S_PIN_NO_CHANGE
  };

  esp_err_t err = i2s_driver_install(I2S_NUM_0, &i2s_config, 0, nullptr);
  if (err != ESP_OK) {
    Serial.printf("Failed to install I2S driver: %d\n", err);
    while (true) {
      delay(1000);
    }
  }

  err = i2s_set_pin(I2S_NUM_0, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("Failed to set I2S pins: %d\n", err);
    while (true) {
      delay(1000);
    }
  }

  err = i2s_set_clk(I2S_NUM_0, SAMPLE_RATE, I2S_BITS_PER_SAMPLE_16BIT, I2S_CHANNEL_MONO);
  if (err != ESP_OK) {
    Serial.printf("Failed to set I2S clock: %d\n", err);
    while (true) {
      delay(1000);
    }
  }
}

void loop() {
  static size_t note_index = 0;
  static size_t samples_remaining = 0;
  static float current_frequency = 0.0f;
  static float phase = 0.0f;

  auto load_note = [&]() {
    const Note& note = kMelody[note_index];
    current_frequency = note.frequency;
    samples_remaining = static_cast<size_t>((note.duration_ms * SAMPLE_RATE) / 1000);
    if (samples_remaining == 0) {
      samples_remaining = 1;
    }
    phase = 0.0f;
  };

  if (samples_remaining == 0) {
    load_note();
  }

  int16_t buffer[BUFFER_SAMPLES];
  for (size_t i = 0; i < BUFFER_SAMPLES; ++i) {
    if (samples_remaining == 0) {
      note_index = (note_index + 1) % kMelodyCount;
      load_note();
    }

    float sample = 0.0f;
    if (current_frequency > 0.0f) {
      sample = sinf(phase) * AMPLITUDE;
      phase += (TWO_PI * current_frequency) / SAMPLE_RATE;
      if (phase > TWO_PI) {
        phase -= TWO_PI;
      }
    }

    buffer[i] = static_cast<int16_t>(sample * 32767.0f);
    samples_remaining--;
  }

  size_t bytes_written = 0;
  i2s_write(I2S_NUM_0, reinterpret_cast<const char*>(buffer), sizeof(buffer), &bytes_written, portMAX_DELAY);
}
