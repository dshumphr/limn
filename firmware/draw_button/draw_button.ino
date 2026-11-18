// limn draw button — M5Stack Atom VoiceS3R (SKU C126-ECHO)
//
// Hold the front button, speak, release. The recording is POSTed as a
// 16 kHz mono 16-bit WAV to the limn draw server.
//
// HARD RULES (all learned on hardware 2026-11-17, see ~/devices/draw-button.md):
// 1. ES8311 mic and speaker share I2S and cannot run at the same time.
//    Every tone is bracketed by mic-stop / speaker-start / speaker-stop /
//    mic-start, and every begin() return is checked.
// 2. Never wait on M5.Speaker.isPlaying() to sequence tones — it returns
//    false immediately after tone() (async audio task), so tones clobber
//    each other. Sequence with explicit M5.delay(ms + 40).
// 3. Tone tables are {freq, ms} pairs; a freq of 0 means "silent gap" and
//    is handled as M5.delay, never tone(0, ...) (unsafe on this stack).
// 4. The AP keeps stale per-MAC association state after a warm reset
//    (side button): re-auth fails with reason 203/202 for ~2 min. Fix:
//    rotate the STA MAC's low bytes every boot — new client, instant join.
//
// Tones:
//   boot          : three ascending notes (Wi-Fi up, ready) ~3-5 s after power/reset
//   record start  : short blip after pressing (recording begins right after)
//   record stop   : short blip after release
//   success       : ascending triad (server accepted the request)
//   failure       : three low buzzes (mic error, wifi down, server error)
//
// Board: M5AtomS3R (M5Stack board package >= 3.2.2), lib M5Unified >= 0.2.8
// Upload flags that work (mac, arduino-cli):
//   --fqbn "m5stack:esp32:m5stack_atoms3r:USBMode=default,CDCOnBoot=cdc,UploadMode=cdc"
// Runs standalone on 5V USB-C power. Has an internal battery: unplug/replug
// is NOT a reset — side-button quick-press resets, ~3 s hold = download mode.

#include <M5Unified.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <esp_wifi.h>
#include <esp_mac.h>

// ---- config: edit these or pass -DWIFI_SSID='"..."' etc. -------------------
#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "YOUR_WIFI_PASS"
#endif
#ifndef SERVER_URL
#define SERVER_URL "http://10.0.0.180:8000/upload"
#endif

static constexpr const int SAMPLE_RATE = 16000;
static constexpr const int CHUNK_SAMPLES = 200;              // per Mic.record call
static constexpr const int MAX_SECONDS = 30;                 // hard cap
static constexpr const size_t MAX_SAMPLES = SAMPLE_RATE * MAX_SECONDS;

static int16_t *rec_buf = nullptr;  // PSRAM
static size_t rec_len = 0;          // samples recorded

static bool wifiUp() {
  return WiFi.status() == WL_CONNECTED;
}

// --- exclusive audio helpers ------------------------------------------------

static void stopMic() {
  while (M5.Mic.isRecording()) M5.delay(1);
  M5.Mic.end();
}

static bool startMic() {
  M5.Speaker.end();
  auto cfg = M5.Mic.config();
  cfg.noise_filter_level = (cfg.noise_filter_level + 8) & 255;
  M5.Mic.config(cfg);
  if (!M5.Mic.begin()) return false;
  return M5.Mic.isEnabled();
}

// Play a {freq, ms} pair table; caller guarantees the mic is stopped.
// freq 0 = silent gap. Sequenced by delay, never isPlaying() (rule 2/3).
static void playTones(const int (*seq)[2], int n) {
  M5.Speaker.begin();
  M5.Speaker.setVolume(255);
  for (int i = 0; i < n; i++) {
    int freq = seq[i][0];
    int ms = seq[i][1];
    if (freq > 0) M5.Speaker.tone(freq, ms);
    M5.delay(ms + 40);
  }
  M5.Speaker.end();
}

static const int CHIME_BOOT[][2] = {{880, 280}, {0, 220}, {1175, 280}, {0, 220}, {1568, 450}};
static const int CHIME_OK[][2] = {{660, 100}, {880, 100}, {1320, 180}};
static const int CHIME_FAIL[][2] = {{220, 250}, {0, 300}, {220, 250}, {0, 300}, {220, 250}};
static const int BLIP_START[][2] = {{1200, 60}};
static const int BLIP_STOP[][2] = {{880, 60}};

// New MAC each boot: the AP rejects re-auth from a MAC it still associates
// with a dead session (~2 min). Low bytes randomized per boot (rule 4).
static void rotateStaMac() {
  uint8_t mac[6];
  esp_read_mac(mac, ESP_MAC_WIFI_STA);  // keep Espressif OUI in mac[0..2]
  uint32_t r = esp_random();
  mac[3] = (uint8_t)(r >> 8);
  mac[4] = (uint8_t)(r >> 16);
  mac[5] = (uint8_t)(r >> 24);
  esp_wifi_set_mac(WIFI_IF_STA, mac);
}

static bool wifiConnect(uint32_t timeout_ms) {
  WiFi.disconnect();
  rotateStaMac();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (!wifiUp() && millis() - t0 < timeout_ms) M5.delay(50);
  if (wifiUp()) {
    Serial.printf("[wifi] joined, rssi=%d mac=%s\n", WiFi.RSSI(), WiFi.macAddress().c_str());
  } else {
    Serial.println("[wifi] join failed");
  }
  return wifiUp();
}

// WAV header for 16 kHz mono 16-bit PCM, |samples| samples.
static void fillWavHeader(uint8_t *h, uint32_t samples) {
  uint32_t dataSize = samples * 2;
  uint32_t fileSize = 36 + dataSize;
  uint32_t byteRate = SAMPLE_RATE * 2;
  memcpy(h, "RIFF", 4);          memcpy(h + 4, &fileSize, 4);
  memcpy(h + 8, "WAVE", 4);      memcpy(h + 12, "fmt ", 4);
  uint32_t fmtSize = 16;         memcpy(h + 16, &fmtSize, 4);
  uint16_t fmtPcm = 1;           memcpy(h + 20, &fmtPcm, 2);
  uint16_t channels = 1;         memcpy(h + 22, &channels, 2);
  memcpy(h + 24, &SAMPLE_RATE, 4);
  memcpy(h + 28, &byteRate, 4);
  uint16_t blockAlign = 2;       memcpy(h + 32, &blockAlign, 2);
  uint16_t bits = 16;            memcpy(h + 34, &bits, 2);
  memcpy(h + 36, "data", 4);     memcpy(h + 40, &dataSize, 4);
}

static bool postRecording() {
  HTTPClient http;
  if (!http.begin(SERVER_URL)) return false;
  http.setTimeout(15000);
  http.addHeader("Content-Type", "application/octet-stream");
  uint8_t header[44];
  fillWavHeader(header, rec_len);

  static uint8_t *payload = nullptr;  // header + samples, contiguous, in PSRAM
  if (!payload) payload = (uint8_t *)heap_caps_malloc(44 + MAX_SAMPLES * 2, MALLOC_CAP_SPIRAM);
  if (!payload) return false;
  memcpy(payload, header, 44);
  memcpy(payload + 44, rec_buf, rec_len * 2);

  int code = http.POST(payload, 44 + rec_len * 2);
  http.end();
  Serial.printf("[http] POST -> %d (%u samples)\n", code, (unsigned)rec_len);
  return code == 200;
}

void setup() {
  M5.begin();
  M5.Speaker.setVolume(255);
  Serial.begin(115200);

  rec_buf = (int16_t *)heap_caps_malloc(MAX_SAMPLES * 2, MALLOC_CAP_SPIRAM);
  memset(rec_buf, 0, MAX_SAMPLES * 2);

  WiFi.mode(WIFI_STA);
  wifiConnect(20000);

  if (wifiUp() && rec_buf) {
    playTones(CHIME_BOOT, 5);
  } else {
    playTones(CHIME_FAIL, 5);
  }
  if (!startMic()) {  // retry once before giving up this cycle
    M5.delay(200);
    startMic();
  }
}

void loop() {
  M5.update();

  if (!rec_buf || !wifiUp()) {  // degraded: recover wifi forever
    M5.delay(5000);
    if (!wifiConnect(10000) && rec_buf) return;
    playTones(CHIME_BOOT, 5);
    return;
  }

  if (!M5.BtnA.isPressed()) return;

  rec_len = 0;

  // Mic down -> start blip -> mic up -> record. Never tone() while mic runs.
  stopMic();
  playTones(BLIP_START, 1);
  bool micOk = startMic();
  if (micOk) {
    int fail_streak = 0;
    while (M5.BtnA.isPressed() && rec_len < MAX_SAMPLES) {
      M5.update();
      if (M5.Mic.record(&rec_buf[rec_len], CHUNK_SAMPLES, SAMPLE_RATE)) {
        rec_len += CHUNK_SAMPLES;
        fail_streak = 0;
      } else if (++fail_streak > 50) {  // ~1 s of dead mic: abort
        micOk = false;
        break;
      }
    }
  }
  stopMic();

  playTones(BLIP_STOP, 1);
  bool ok = micOk && rec_len > SAMPLE_RATE / 2 && postRecording();  // ignore <0.5s
  if (!startMic()) {
    M5.delay(200);
    startMic();
  }
  playTones(ok ? CHIME_OK : CHIME_FAIL, ok ? 3 : 5);
}
