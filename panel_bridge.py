"""
Arduino Mega -> vJoy bridge (52 кнопки + 6 энкодеров)
Автоматически находит порт, отправляет нажатия в vJoy.
Иконка в трее (красный/зелёный), меню: Перезапустить, Выход.
Иконка обновляется корректно с первого подключения.
"""

import serial
import serial.tools.list_ports
import json
import threading
import time
import os
import sys
import ctypes
from pystray import Icon, Menu, MenuItem
from PIL import Image

# ---------------------- ПУТЬ К ФАЙЛУ МАППИНГА ----------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPING_FILE = os.path.join(SCRIPT_DIR, "mapping.json")

# ---------------------- КОНФИГУРАЦИЯ (СОГЛАСОВАНО С ПРОШИВКОЙ) ----------------------
VJOY_DEVICE_ID = 1
NUM_VJOY_BUTTONS = 64
NUM_PHYSICAL_BUTTONS = 52
NUM_ENCODERS = 6
ENC_BUTTONS_PER = 2
TOTAL_PHYSICAL_INPUTS = NUM_PHYSICAL_BUTTONS + NUM_ENCODERS * ENC_BUTTONS_PER   # 52+12=64
MASK_BYTES = (TOTAL_PHYSICAL_INPUTS + 7) // 8   # 8 байт
BAUD_RATE = 115200
PACKET_HEADER = 0xAA

TARGET_VID = 0x2341
TARGET_PID = 0x0042

# ---------------------- ИНИЦИАЛИЗАЦИЯ VJOY ----------------------
vjoy_dll = None
vjoy_ready = False

def init_vjoy():
    global vjoy_dll, vjoy_ready
    possible_paths = [
        r"C:\Program Files\vJoy\x64\vJoyInterface.dll",
        r"C:\Program Files (x86)\vJoy\x64\vJoyInterface.dll",
        r"C:\Program Files\vJoy\x86\vJoyInterface.dll",
        r"C:\Program Files (x86)\vJoy\x86\vJoyInterface.dll",
        r"C:\Windows\System32\vJoyInterface.dll",
        r"C:\Windows\SysWOW64\vJoyInterface.dll",
    ]
    dll_path = None
    for p in possible_paths:
        if os.path.isfile(p):
            dll_path = p
            break
    if not dll_path:
        try:
            vjoy_dll = ctypes.WinDLL("vJoyInterface.dll")
        except OSError:
            raise RuntimeError("vJoyInterface.dll не найдена. Установите vJoy и перезагрузите ПК.")
    else:
        vjoy_dll = ctypes.WinDLL(dll_path)

    vjoy_dll.vJoyEnabled.restype = ctypes.c_bool
    if not vjoy_dll.vJoyEnabled():
        raise RuntimeError("vJoy не включён. Откройте vJoy Configuration и включите устройство.")

    vjoy_dll.AcquireVJD.argtypes = [ctypes.c_int]
    vjoy_dll.AcquireVJD.restype = ctypes.c_bool
    if not vjoy_dll.AcquireVJD(VJOY_DEVICE_ID):
        raise RuntimeError(f"Не удалось захватить vJoy устройство {VJOY_DEVICE_ID}.")

    vjoy_dll.SetBtn.argtypes = [ctypes.c_bool, ctypes.c_int, ctypes.c_ubyte]
    vjoy_dll.SetBtn.restype = ctypes.c_bool

    vjoy_ready = True

def set_vjoy_button(btn, state):
    if vjoy_ready:
        vjoy_dll.SetBtn(state, VJOY_DEVICE_ID, btn)

def release_vjoy():
    global vjoy_ready
    if vjoy_ready:
        vjoy_dll.RelinquishVJD.argtypes = [ctypes.c_int]
        vjoy_dll.RelinquishVJD(VJOY_DEVICE_ID)
        vjoy_ready = False

# ---------------------- ПОИСК COM-ПОРТА ----------------------
def find_arduino_port():
    for port in serial.tools.list_ports.comports():
        if port.vid == TARGET_VID and port.pid == TARGET_PID:
            return port.device
        if "Arduino Mega 2560" in port.description:
            return port.device
    return None

# ---------------------- МАППИНГ ----------------------
def get_default_mapping():
    m = {}
    for i in range(1, NUM_PHYSICAL_BUTTONS + 1):
        m[i] = i if i <= NUM_VJOY_BUTTONS else None
    for i in range(NUM_ENCODERS * ENC_BUTTONS_PER):
        phys = NUM_PHYSICAL_BUTTONS + i + 1
        virt = NUM_PHYSICAL_BUTTONS + 1 + i
        m[phys] = virt if virt <= NUM_VJOY_BUTTONS else None
    return m

def load_mapping():
    try:
        with open(MAPPING_FILE, "r") as f:
            mapping = json.load(f)
        mapping = {int(k): v for k, v in mapping.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        mapping = get_default_mapping()
        save_mapping(mapping)
    default = get_default_mapping()
    for k, v in default.items():
        if k not in mapping:
            mapping[k] = v
    for k in list(mapping.keys()):
        if k < 1 or k > TOTAL_PHYSICAL_INPUTS:
            del mapping[k]
    return mapping

def save_mapping(mapping):
    with open(MAPPING_FILE, "w") as f:
        json.dump(mapping, f, indent=2)

# ---------------------- ПОТОК ЧТЕНИЯ ----------------------
class SerialToVJoy(threading.Thread):
    def __init__(self, update_icon_callback):
        super().__init__(daemon=False)
        self.update_icon = update_icon_callback
        self.mapping = load_mapping()
        self.ser = None
        self.running = True
        self.connected = False
        self.encoder_buttons = {}
        self.lock = threading.Lock()

    def run(self):
        while self.running:
            if not self.connected:
                port = find_arduino_port()
                if port:
                    try:
                        self.ser = serial.Serial(port, BAUD_RATE, timeout=1)
                        self.connected = True
                        self.update_icon("green")   # ← вызовет set_icon_color
                    except serial.SerialException:
                        self.ser = None
                else:
                    time.sleep(2)
            else:
                try:
                    if not self.ser or not self.ser.is_open:
                        self.connected = False
                        self.update_icon("red")
                        time.sleep(1)
                        continue
                    header = self.ser.read(1)
                    if header and header[0] == PACKET_HEADER:
                        enc_len = NUM_ENCODERS * ENC_BUTTONS_PER
                        total_len = MASK_BYTES + enc_len + 1
                        payload = self.ser.read(total_len)
                        if len(payload) == total_len:
                            mask = payload[:MASK_BYTES]
                            enc_data = payload[MASK_BYTES:MASK_BYTES+enc_len]
                            crc_byte = payload[-1]
                            calc = header[0]
                            for b in mask + enc_data:
                                calc ^= b
                            if calc == crc_byte:
                                self.process(mask, enc_data)
                except (serial.SerialException, OSError, TypeError):
                    if self.ser and self.ser.is_open:
                        try:
                            self.ser.close()
                        except:
                            pass
                    self.ser = None
                    self.connected = False
                    self.update_icon("red")
                    time.sleep(1)

    def process(self, mask, enc_data):
        now = time.time()
        for phys in range(1, NUM_PHYSICAL_BUTTONS + 1):
            byte = (phys - 1) // 8
            bit = (phys - 1) % 8
            state = (mask[byte] >> bit) & 1 if byte < len(mask) else 0
            vbtn = self.mapping.get(phys)
            if vbtn is not None:
                set_vjoy_button(vbtn, state)

        for enc_idx in range(NUM_ENCODERS * ENC_BUTTONS_PER):
            phys = NUM_PHYSICAL_BUTTONS + enc_idx + 1
            byte = (phys - 1) // 8
            bit = (phys - 1) % 8
            state = (mask[byte] >> bit) & 1 if byte < len(mask) else 0
            if state:
                vbtn = self.mapping.get(phys)
                if vbtn is not None:
                    self.encoder_buttons[vbtn] = now + 0.05
                    set_vjoy_button(vbtn, 1)
        to_del = [v for v, t in self.encoder_buttons.items() if now >= t]
        for v in to_del:
            set_vjoy_button(v, 0)
            del self.encoder_buttons[v]

    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

# ---------------------- ИКОНКА В ТРЕЕ ----------------------
class TrayApp:
    def __init__(self):
        self.current_color = "red"
        self.pending_color = "red"          # цвет, который ждёт применения после создания иконки
        self.bridge = SerialToVJoy(self.set_icon_color)
        self.icon = None
        self.create_image(self.current_color)

    def create_image(self, color):
        self.icon_image = Image.new("RGB", (16, 16), color)

    def set_icon_color(self, color):
        """Вызывается из потока SerialToVJoy при изменении статуса подключения."""
        self.current_color = color
        self.create_image(color)
        if self.icon:
            self.icon.icon = self.icon_image   # обновить иконку сразу
        else:
            self.pending_color = color          # запомнить, чтобы применить после создания иконки

    def restart_program(self):
        self.bridge.stop()
        release_vjoy()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def quit(self):
        self.bridge.stop()
        release_vjoy()
        if self.icon:
            self.icon.stop()

    def run(self):
        menu = Menu(
            MenuItem("Перезапустить", self.restart_program),
            MenuItem("Выход", self.quit)
        )
        self.icon = Icon("Arduino Joystick", self.icon_image, "Arduino -> vJoy", menu)
        # Применяем отложенный цвет, если он был изменён до создания иконки
        if self.pending_color != self.current_color or self.pending_color != "red":
            self.create_image(self.pending_color)
            self.icon.icon = self.icon_image
        self.icon.run()

if __name__ == "__main__":
    init_vjoy()
    app = TrayApp()
    app.bridge.start()
    app.run()