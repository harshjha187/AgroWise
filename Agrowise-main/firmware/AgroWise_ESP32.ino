/*
 * ============================================================
 *  AgroWise — ESP32 Firmware
 *  IoT-Based Smart Soil Health Analysis, Barren Land Detection
 *  and Automated Recovery Recommendation System
 * ============================================================
 *
 *  Pipeline (matches the updated project pseudocode):
 *    Initialize ESP32 -> Initialize WiFi -> Initialize Bluetooth
 *    -> Initialize NPK / Moisture / pH / Temperature sensors -> LOOP:
 *    Read all six sensors -> Create data packet -> Send via WiFi
 *    (HTTP POST to the AgroWise backend) or Bluetooth -> Wait 30 s.
 *
 *  Validation, noise filtering, scoring, classification and the
 *  recommendation engine all run on the backend (server.py), so
 *  the firmware stays small and battery-friendly.
 *
 *  Libraries (Arduino IDE -> Library Manager):
 *    - OneWire               by Paul Stoffregen
 *    - DallasTemperature     by Miles Burton
 *  (WiFi, HTTPClient and BluetoothSerial ship with the ESP32 core.)
 *
 *  Wiring (default pins, change below if needed):
 *    NPK sensor (RS485)  : MAX485  RO->GPIO16(RX2)  DI->GPIO17(TX2)
 *                          DE+RE tied together -> GPIO4
 *    Moisture (analog)   : signal -> GPIO35 (ADC1, capacitive probe)
 *    pH sensor (analog)  : signal -> GPIO34 (ADC1)
 *    DS18B20 temperature : data   -> GPIO5 (with 4.7k pull-up to 3.3V)
 *    Status LED          : GPIO2 (onboard LED)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ------------------------------------------------------------------
// CONFIGURATION — edit this block only
// ------------------------------------------------------------------
#define SIMULATE_SENSORS  true       // true = demo without hardware
#define USE_BLUETOOTH     false      // also stream JSON over Bluetooth

const char* WIFI_SSID   = "YOUR_WIFI_NAME";
const char* WIFI_PASS   = "YOUR_WIFI_PASSWORD";

// PC/laptop running server.py — find its IP with `ipconfig` (Windows)
// or `ifconfig` (Linux/Mac). Keep the port and path as-is.
const char* SERVER_URL  = "http://192.168.1.10:5000/api/readings";

// server.py prints this on startup (or set AGROWISE_API_KEY on the
// backend) — every /api/* request is rejected with 401 without it.
const char* API_KEY     = "PASTE_THE_BACKEND_API_KEY_HERE";

// Only matters if you run more than one physical ESP32 against the same
// backend (e.g. separate fields) — give each unit a distinct ID so their
// readings don't get blended together. Leave as-is for a single-device
// setup; the backend defaults to the packet's "source" if omitted anyway.
const char* DEVICE_ID    = "ESP32-01";

const unsigned long READ_INTERVAL_MS = 30000UL;   // 30 s cycle

// Pins
#define RS485_RX_PIN   16
#define RS485_TX_PIN   17
#define RS485_DE_RE    4
#define PH_ADC_PIN     34
#define MOIST_ADC_PIN  35            // capacitive soil moisture sensor
#define DS18B20_PIN    5
#define STATUS_LED     2

// pH probe two-point calibration (measure with pH 4.0 & 7.0 buffers)
const float PH_NEUTRAL_VOLTAGE = 2.50;   // volts at pH 7.0  -> CALIBRATE
const float PH_VOLTS_PER_PH    = 0.18;   // slope            -> CALIBRATE

// Capacitive soil moisture calibration (measure ADC in air and in water)
const int MOIST_AIR_ADC   = 3200;        // dry / in air     -> CALIBRATE
const int MOIST_WATER_ADC = 1350;        // in a glass of water -> CALIBRATE

#if USE_BLUETOOTH
#include "BluetoothSerial.h"
BluetoothSerial SerialBT;
#endif

OneWire oneWire(DS18B20_PIN);
DallasTemperature tempSensor(&oneWire);

// JXCT-style NPK sensor Modbus inquiry frames (addr 0x01).
// Verify register addresses against YOUR sensor's datasheet.
const uint8_t FRAME_N[8] = {0x01, 0x03, 0x00, 0x1E, 0x00, 0x01, 0xE4, 0x0C};
const uint8_t FRAME_P[8] = {0x01, 0x03, 0x00, 0x1F, 0x00, 0x01, 0xB5, 0xCC};
const uint8_t FRAME_K[8] = {0x01, 0x03, 0x00, 0x20, 0x00, 0x01, 0x85, 0xC0};

unsigned long lastCycle = 0;

// ------------------------------------------------------------------
// Sensor reading
// ------------------------------------------------------------------
int readModbusRegister(const uint8_t* frame) {
  // Flush stale bytes
  while (Serial2.available()) Serial2.read();

  digitalWrite(RS485_DE_RE, HIGH);            // transmit mode
  Serial2.write(frame, 8);
  Serial2.flush();
  digitalWrite(RS485_DE_RE, LOW);             // receive mode

  uint8_t response[7];
  unsigned long start = millis();
  int index = 0;
  while (millis() - start < 400 && index < 7) {
    if (Serial2.available()) response[index++] = Serial2.read();
  }
  if (index < 7) return -1;                    // timeout
  return (response[3] << 8) | response[4];     // value = data hi/lo bytes
}

float readNitrogen()   { int v = readModbusRegister(FRAME_N); return v < 0 ? NAN : v; }
float readPhosphorus() { int v = readModbusRegister(FRAME_P); return v < 0 ? NAN : v; }
float readPotassium()  { int v = readModbusRegister(FRAME_K); return v < 0 ? NAN : v; }

float readPH() {
  // average 10 samples for a stable value
  long sum = 0;
  for (int i = 0; i < 10; i++) { sum += analogRead(PH_ADC_PIN); delay(8); }
  float voltage = (sum / 10.0f) * 3.3f / 4095.0f;
  return 7.0f + (PH_NEUTRAL_VOLTAGE - voltage) / PH_VOLTS_PER_PH;
}

float readMoisture() {
  // capacitive probes read LOW in wet soil, HIGH in dry — invert & map to %
  long sum = 0;
  for (int i = 0; i < 10; i++) { sum += analogRead(MOIST_ADC_PIN); delay(8); }
  int adc = sum / 10;
  float pct = 100.0f * (float)(MOIST_AIR_ADC - adc) / (float)(MOIST_AIR_ADC - MOIST_WATER_ADC);
  if (pct < 0) pct = 0;
  if (pct > 100) pct = 100;
  return pct;
}

float readTemperature() {
  tempSensor.requestTemperatures();
  float celsius = tempSensor.getTempCByIndex(0);
  return (celsius <= -100) ? NAN : celsius;    // -127 = sensor missing
}

// Gentle random-walk simulation of a moderate field (demo mode)
float simN = 55, simP = 13, simK = 92, simM = 22, simPH = 5.7, simT = 31;
float walk(float v, float step, float lo, float hi) {
  v += (random(-100, 101) / 100.0f) * step;
  return constrain(v, lo, hi);
}
void simulateSensors(float &n, float &p, float &k, float &m, float &ph, float &t) {
  simN  = walk(simN, 6,    8, 300);   simP = walk(simP, 1.8f, 2, 120);
  simK  = walk(simK, 8,   15, 450);   simM = walk(simM, 2.5f, 3, 80);
  simPH = walk(simPH, 0.12f, 4.2f, 9.2f);
  simT  = walk(simT, 0.9f, 12, 44);
  n = simN; p = simP; k = simK; m = simM; ph = simPH; t = simT;
}

// ------------------------------------------------------------------
// Networking
// ------------------------------------------------------------------
void connectWiFi() {
  Serial.printf("[WiFi] connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(400);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] connected, IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] FAILED — will retry next cycle");
  }
}

bool sendPacket(const String &json) {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  http.setTimeout(5000);
  int code = http.POST(json);
  if (code > 0) {
    Serial.printf("[HTTP] POST -> %d\n", code);
  } else {
    Serial.printf("[HTTP] POST failed: %s\n", http.errorToString(code).c_str());
  }
  http.end();
  return code == 201 || code == 200;
}

// ------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(STATUS_LED, OUTPUT);
  pinMode(RS485_DE_RE, OUTPUT);
  digitalWrite(RS485_DE_RE, LOW);

  Serial.println("\n=== AgroWise ESP32 ===");

  Serial2.begin(9600, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);  // NPK sensor
  tempSensor.begin();                                            // DS18B20
  analogSetPinAttenuation(PH_ADC_PIN,    ADC_11db);              // full 0-3.3 V
  analogSetPinAttenuation(MOIST_ADC_PIN, ADC_11db);              // full 0-3.3 V

#if USE_BLUETOOTH
  SerialBT.begin("AgroWise-ESP32");
  Serial.println("[BT] Bluetooth started as 'AgroWise-ESP32'");
#endif

  connectWiFi();
  randomSeed(esp_random());
  lastCycle = millis() - READ_INTERVAL_MS;   // fire the first cycle immediately
}

void loop() {
  if (millis() - lastCycle < READ_INTERVAL_MS) {
    delay(50);
    return;
  }
  lastCycle = millis();

  // -------- Read sensors --------
  float n, p, k, m, ph, t;
#if SIMULATE_SENSORS
  simulateSensors(n, p, k, m, ph, t);
#else
  n  = readNitrogen();
  p  = readPhosphorus();
  k  = readPotassium();
  m  = readMoisture();
  ph = readPH();
  t  = readTemperature();
#endif

  if (isnan(n) || isnan(p) || isnan(k) || isnan(m) || isnan(ph) || isnan(t)) {
    Serial.println("[SENSOR] invalid reading — skipping this cycle");
    return;
  }

  // -------- Create data packet --------
  String json = "{\"n\":"    + String(n, 1) +
                ",\"p\":"    + String(p, 1) +
                ",\"k\":"    + String(k, 1) +
                ",\"m\":"    + String(m, 1) +
                ",\"ph\":"   + String(ph, 2) +
                ",\"temp\":" + String(t, 1) +
                ",\"source\":\"ESP32\"" +
                ",\"device_id\":\"" + String(DEVICE_ID) + "\"}";
  Serial.println("[PACKET] " + json);

  // -------- Send via WiFi (and Bluetooth if enabled) --------
  bool sent = sendPacket(json);
#if USE_BLUETOOTH
  SerialBT.println(json);
#endif

  digitalWrite(STATUS_LED, HIGH);
  delay(sent ? 120 : 40);                    // long blink = delivered
  digitalWrite(STATUS_LED, LOW);
}
