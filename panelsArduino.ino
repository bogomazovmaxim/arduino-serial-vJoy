/*
 * ПАНЕЛЬ НА MEGA 2560 -> Serial -> vJoy
 * Отправляет пакет: [0xAA] [8 байт масок] [12 байт энкодеров] [CRC]
 * Каждые 10 мс.
 * Кнопки: 52 шт, энкодеры: 6 шт.
 */

#include <Bounce2.h>

// -------------------- НАСТРОЙКИ --------------------
const uint8_t NUM_BUTTONS = 52;          // обычных кнопок (ровно по числу пинов в массиве)
const uint8_t NUM_ENCODERS = 6;          // число энкодеров
const uint8_t ENC_BUTTONS_PER = 2;       // CW и CCW

// Всего входов: кнопки + направления энкодеров
const uint8_t TOTAL_INPUTS = NUM_BUTTONS + NUM_ENCODERS * ENC_BUTTONS_PER; // 52+12=64
const uint8_t MASK_BYTES = (TOTAL_INPUTS + 7) / 8;   // (64+7)/8 = 8 байт маски

// Пины обычных кнопок (52 пина – ваша распиновка)
const uint8_t btnPins[NUM_BUTTONS] = {
  2,3,4,5,6,7,8,9,10,11,12,13,16,17,18,19,20,21,22,23,24,25,26,27,28,29,
  30,31,32,33,34,35,36,37,38,39,41,43,46,47,48,49,50,51,52,53,
  A0,A5,A10,A11,A12,A13
};

// Пины энкодеров (6 энкодеров, пары {A, B})
const uint8_t encPins[NUM_ENCODERS][2] = {
  {A1, A2},   // Энкодер 0
  {A8, A9},   // Энкодер 1
  {44, 45},   // Энкодер 2
  {14, 15},   // Энкодер 3
  {A3, A4},   // Энкодер 4
  {40, 42}    // Энкодер 5
};

// --------------------------------------------------------------------------

Bounce *buttons[NUM_BUTTONS];
uint8_t encLastState[NUM_ENCODERS];   // предыдущее состояние (2 бита)

void setup() {
  Serial.begin(115200);
  // Инициализация кнопок с антидребезгом
  for (int i = 0; i < NUM_BUTTONS; i++) {
    pinMode(btnPins[i], INPUT_PULLUP);
    buttons[i] = new Bounce();
    buttons[i]->attach(btnPins[i]);
    buttons[i]->interval(5);   // дребезг 5 мс
  }
  // Инициализация энкодеров
  for (int i = 0; i < NUM_ENCODERS; i++) {
    pinMode(encPins[i][0], INPUT_PULLUP);
    pinMode(encPins[i][1], INPUT_PULLUP);
    encLastState[i] = (digitalRead(encPins[i][0]) << 1) | digitalRead(encPins[i][1]);
  }
}

void loop() {
  static uint32_t lastSend = 0;
  uint32_t now = millis();
  
  // Обновляем все кнопки
  for (int i = 0; i < NUM_BUTTONS; i++) {
    buttons[i]->update();
  }

  // Читаем энкодеры и формируем мгновенные нажатия
  uint8_t encPresses[NUM_ENCODERS * ENC_BUTTONS_PER] = {0};
  for (int i = 0; i < NUM_ENCODERS; i++) {
    uint8_t a = digitalRead(encPins[i][0]);
    uint8_t b = digitalRead(encPins[i][1]);
    uint8_t current = (a << 1) | b;
    if (current != encLastState[i]) {
      uint8_t diff = (encLastState[i] << 2) | current;
      // CW
      if (diff == 0b0001 || diff == 0b0111 || diff == 0b1110 || diff == 0b1000) {
        encPresses[i * 2] = 1;
      }
      // CCW
      else if (diff == 0b0010 || diff == 0b1011 || diff == 0b1101 || diff == 0b0100) {
        encPresses[i * 2 + 1] = 1;
      }
      encLastState[i] = current;
    }
  }

  // Отправка пакета каждые 10 мс
  if (now - lastSend >= 10) {
    lastSend = now;
    sendPacket(encPresses);
  }
}

void sendPacket(uint8_t *encPresses) {
  uint8_t packet[1 + MASK_BYTES + NUM_ENCODERS*ENC_BUTTONS_PER + 1];
  packet[0] = 0xAA;
  
  // Заполняем байты масок кнопок
  memset(&packet[1], 0, MASK_BYTES);
  for (int i = 0; i < NUM_BUTTONS; i++) {
    if (buttons[i]->read() == LOW) {   // нажата
      uint8_t byteIndex = i / 8;
      uint8_t bitIndex = i % 8;
      packet[1 + byteIndex] |= (1 << bitIndex);
    }
  }
  
  // Добавляем биты энкодеров (временные кнопки)
  for (int i = 0; i < NUM_ENCODERS * ENC_BUTTONS_PER; i++) {
    if (encPresses[i]) {
      uint16_t idx = NUM_BUTTONS + i;
      uint8_t byteIndex = idx / 8;
      uint8_t bitIndex = idx % 8;
      packet[1 + byteIndex] |= (1 << bitIndex);
    }
  }
  
  // CRC (XOR всех байт, кроме последнего)
  uint8_t crc = 0;
  for (int i = 0; i < 1 + MASK_BYTES + NUM_ENCODERS*ENC_BUTTONS_PER; i++) {
    crc ^= packet[i];
  }
  packet[1 + MASK_BYTES + NUM_ENCODERS*ENC_BUTTONS_PER] = crc;
  
  Serial.write(packet, sizeof(packet));
}