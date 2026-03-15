# main.py - v34.0 (OTA Auto-Update)
# - FEATURE: Checks GitHub for code updates before displaying images.
# - LOGIC: Compares local 'version.txt' vs GitHub 'version.txt'.

import time
import os
import machine
import network
import socket
import ssl
from machine import Pin, SPI, SoftSPI
import sdcard 
import neopixel

# --- CONFIGURATION ---
WIFI_SSID = "Nie ma nic za darmo - guest"
WIFI_PASS = "internet"

GH_USER = "Raging-Regret"
GH_REPO = "eink-images"
GH_BRANCH = "main"

# Current Internal Version (Update this manually when you flash via USB)
CURRENT_VERSION = 1 

# --- PINS ---
NEOPIXEL_PIN = 48 
SD_SCK=14; SD_MOSI=15; SD_MISO=16; SD_CS=5
EPD_SCK=18; EPD_MOSI=17; EPD_MISO=16
CS_M=10; CS_S=4; DC=9; RST=8; BUSY=7; PWR=13
TPL_DONE=6

# --- LED ---
class StatusLED:
    def __init__(self):
        self.np = neopixel.NeoPixel(Pin(NEOPIXEL_PIN), 1)
        self.b = 10
        self.set(0,0,self.b)

    def set(self, r, g, b):
        self.np[0] = (r, g, b); self.np.write()
    
    def off(self): self.set(0,0,0)
    def blue(self): self.set(0,0,self.b) # Boot
    def yellow(self): self.set(self.b, self.b, 0) # WiFi
    def cyan(self): self.set(0, self.b, self.b) # DL
    def magenta(self): self.set(self.b, 0, self.b) # UPDATE MODE
    def green(self): self.set(0, self.b, 0)
    def red(self): self.set(50, 0, 0)

led = StatusLED()

# --- WIFI ---
def connect_wifi():
    led.yellow()
    wlan = network.WLAN(network.STA_IF); wlan.active(True)
    try: wlan.config(pm=wlan.PM_NONE)
    except: pass
    
    print(f"Connecting to {WIFI_SSID}...")
    wlan.connect(WIFI_SSID, WIFI_PASS)
    
    for _ in range(40):
        if wlan.isconnected():
            print("Connected.")
            return True
        time.sleep(0.5)
    return False

# --- OTA UPDATER ---
def check_for_updates():
    print("Checking for updates...")
    
    # 1. Get Local Version
    local_ver = 0
    try:
        with open("version.txt", "r") as f:
            local_ver = int(f.read().strip())
    except:
        # If no file, assume version 1
        local_ver = CURRENT_VERSION
        with open("version.txt", "w") as f: f.write(str(local_ver))

    print(f"Current Version: {local_ver}")

    # 2. Get Remote Version
    try:
        ver_url = f"/{GH_USER}/{GH_REPO}/{GH_BRANCH}/version.txt"
        new_ver = int(http_get_content(ver_url).strip())
        print(f"Remote Version: {new_ver}")
        
        if new_ver > local_ver:
            perform_ota(new_ver)
            return True # We updated, should reboot
    except Exception as e:
        print(f"Update Check Error: {e}")
        
    return False # No update

def perform_ota(new_ver):
    led.magenta()
    print(f"⚡ UPDATE FOUND! Upgrading v{CURRENT_VERSION} -> v{new_ver}...")
    
    try:
        # 1. Download new main.py
        # Note: We save it as 'main_new.py' first to prevent bricking if download fails
        code_url = f"/{GH_USER}/{GH_REPO}/{GH_BRANCH}/main.py"
        code_content = http_get_content(code_url)
        
        if len(code_content) < 100:
            raise Exception("Downloaded code too short/invalid")

        # 2. Write to Flash
        with open("main_new.py", "w") as f:
            f.write(code_content)
            
        # 3. Swap Files
        # Delete old main (backup first if you want)
        try: os.remove("main.py")
        except: pass
        
        # Rename new to main
        os.rename("main_new.py", "main.py")
        
        # 4. Update Version File
        with open("version.txt", "w") as f:
            f.write(str(new_ver))
            
        print("Update Successful! Rebooting...")
        led.green()
        time.sleep(1)
        machine.reset() # Reboot to load new code
        
    except Exception as e:
        print(f"OTA FAILED: {e}")
        led.red()
        # If failed, we just continue running the old code

def http_get_content(path):
    # Simple Helper to get text content
    addr = socket.getaddrinfo("raw.githubusercontent.com", 443)[0][-1]
    s = socket.socket(); s.settimeout(10.0); s.connect(addr)
    ss = ssl.wrap_socket(s)
    ss.write(f"GET {path} HTTP/1.1\r\nHost: raw.githubusercontent.com\r\nUser-Agent: ESP32\r\nConnection: close\r\n\r\n".encode())
    
    # Read headers
    while True:
        line = ss.readline()
        if line == b"\r\n" or line == b"": break
            
    # Read Body
    content = ss.read().decode()
    ss.close(); s.close()
    return content

# --- STANDARD DOWNLOADER ---
def download_to_sd(filename, save_path):
    led.cyan()
    print(f"DL: {filename}")
    try:
        addr = socket.getaddrinfo("raw.githubusercontent.com", 443)[0][-1]
        s = socket.socket(); s.settimeout(15.0); s.connect(addr)
        ss = ssl.wrap_socket(s)
        ss.write(f"GET /{GH_USER}/{GH_REPO}/{GH_BRANCH}/{filename} HTTP/1.1\r\nHost: raw.githubusercontent.com\r\nUser-Agent: ESP32\r\nConnection: close\r\n\r\n".encode())
        
        status = ss.readline()
        if not status or b"200 OK" not in status:
            ss.close(); s.close(); return False
            
        while True:
            line = ss.readline()
            if line == b"\r\n" or line == b"": break
        
        with open(save_path, "wb") as f:
            total = 0
            while True:
                chunk = ss.read(1024)
                if not chunk: break
                f.write(chunk)
                total += len(chunk)
        
        ss.close(); s.close()
        if total < 950000: return False
        return True
    except: return False

# --- EPD DRIVER (Condensed) ---
class EPD:
    def __init__(self):
        self.spi = SoftSPI(baudrate=100000, sck=Pin(EPD_SCK), mosi=Pin(EPD_MOSI), miso=Pin(EPD_MISO))
        self.cs_m = Pin(CS_M, Pin.OUT, value=1); self.cs_s = Pin(CS_S, Pin.OUT, value=1)
        self.dc = Pin(DC, Pin.OUT, value=1); self.rst = Pin(RST, Pin.OUT, value=1)
        self.pwr = Pin(PWR, Pin.OUT, value=0); self.busy = Pin(BUSY, Pin.IN, Pin.PULL_UP)
        self.PON, self.DRF, self.POF = 0x04, 0x12, 0x02
        self.AN_TM_V = b'\xC0\x1C\x1C\xCC\xCC\xCC\x15\x15\x55'
        self.CMD66_V = b'\x49\x55\x13\x5D\x05\x10'
        self.PWR_V = b'\x0F\x00\x28\x2C\x28\x38'
        self.TRES_V = b'\x04\xb0\x06\x40'

    def _cmd_data(self, c, d):
        self.cs_m.value(0); self.cs_s.value(0) 
        self.dc.value(0); self.spi.write(bytearray([c])) 
        self.dc.value(1); self.spi.write(d) 
        self.cs_m.value(1); self.cs_s.value(1) 

    def _cmd(self, c):
        self.cs_m.value(0); self.cs_s.value(0)
        self.dc.value(0); self.spi.write(bytearray([c]))
        self.cs_m.value(1); self.cs_s.value(1)

    def init(self):
        self.pwr.value(1); time.sleep_ms(100)
        self.rst.value(0); time.sleep_ms(20); self.rst.value(1); time.sleep_ms(200)
        self._cmd_data(0x74, self.AN_TM_V); self._cmd_data(0xF0, self.CMD66_V)
        self._cmd_data(0x00, b'\xDF\x69'); self._cmd_data(0x50, b'\x37')
        self._cmd_data(0x60, b'\x03\x03'); self._cmd_data(0x61, self.TRES_V)
        self._cmd_data(0x01, self.PWR_V); self._cmd_data(0x06, b'\xE8\x28')
        self._cmd_data(0x05, b'\xE8\x28'); self._cmd_data(0xB0, b'\x01'); self._cmd_data(0xB1, b'\x02')

    def display_file(self, path):
        CHUNK = 4096; buf = bytearray(CHUNK); TOT = 480000
        with open(path, 'rb') as f:
            led.orange()
            self.cs_m.value(0); self._cmd(0x10); self.dc.value(1)
            sent = 0
            while sent < TOT:
                r = f.readinto(memoryview(buf)[:min(CHUNK, TOT-sent)])
                self.spi.write(memoryview(buf)[:r]); sent += r
            self.cs_m.value(1)
            led.cyan()
            self.cs_s.value(0); self._cmd(0x10); self.dc.value(1)
            sent = 0
            while sent < TOT:
                r = f.readinto(memoryview(buf)[:min(CHUNK, TOT-sent)])
                self.spi.write(memoryview(buf)[:r]); sent += r
            self.cs_s.value(1)
        led.white()
        self._cmd(self.PON); time.sleep(1); self._cmd(self.DRF); led.off(); time.sleep(40); self._cmd(self.POF)

    def shutdown_pins(self):
        self.cs_m.value(0); self.cs_s.value(0); self.dc.value(0); self.rst.value(0); self.pwr.value(0)

def kill_power():
    led.green(); time.sleep(0.5); led.off()
    done = Pin(TPL_DONE, Pin.OUT); done.value(1); time.sleep(0.5); done = Pin(TPL_DONE, Pin.IN, Pin.PULL_DOWN)
    while True: time.sleep(1)

# --- MAIN ---
if __name__ == '__main__':
    try:
        led.purple()
        spi = SPI(1, baudrate=4000000, sck=Pin(SD_SCK), mosi=Pin(SD_MOSI), miso=Pin(SD_MISO))
        os.mount(sdcard.SDCard(spi, Pin(SD_CS)), "/sd")
        
        try: 
            with open("/sd/idx.txt", "r") as f: idx = int(f.read().strip())
        except: idx = 0
        
        next_idx = idx + 1
        target = f"{next_idx}.bin"
        got_image = False
        
        if connect_wifi():
            # --- OTA CHECK START ---
            # If update found, it will reboot here and never reach display code
            check_for_updates()
            # --- OTA CHECK END ---
            
            if download_to_sd(target, "/sd/temp.bin"):
                got_image = True; idx = next_idx
            else:
                if download_to_sd("0.bin", "/sd/temp.bin"):
                    got_image = True; idx = 0
            
            network.WLAN(network.STA_IF).active(False); time.sleep(1)
            
        if got_image:
            epd = EPD(); epd.init(); epd.display_file("/sd/temp.bin")
            epd.shutdown_pins()
            with open("/sd/idx.txt", "w") as f: f.write(str(idx))
            
    except Exception as e:
        print(e)
    finally:
        try: os.umount("/sd")
        except: pass
        kill_power()
