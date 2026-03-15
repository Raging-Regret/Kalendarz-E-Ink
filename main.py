import time
import os
import gc
import machine
import network
import socket
import ssl
import select
from machine import Pin, SPI
import sdcard 
import neopixel

# --- PINS ---
NEOPIXEL_PIN = 48 
BUTTON_PIN = 1 
SD_SCK=14; SD_MOSI=15; SD_MISO=16; SD_CS=5
EPD_SCK=18; EPD_MOSI=17; EPD_MISO=16
CS_M=10; CS_S=4; DC=9; RST=8; BUSY=7; PWR=13
TPL_DONE=6

# --- CONFIG ---
GH_USER = "Raging-Regret"
GH_REPO = "eink-images"
GH_BRANCH = "main"

def log(msg): print(msg)

# --- LED ---
class StatusLED:
    def __init__(self):
        self.np = neopixel.NeoPixel(Pin(NEOPIXEL_PIN), 1)
        self.b = 10 
    def set(self, r, g, b): self.np[0] = (r, g, b); self.np.write()
    def off(self): self.set(0,0,0)
    def purple(self): self.set(self.b, 0, self.b)
    def yellow(self): self.set(self.b, self.b, 0)
    def cyan(self): self.set(0, self.b, self.b)
    def white(self): self.set(5,5,5)
    def green(self): self.set(0, self.b, 0)
    def orange(self): self.set(self.b, 5, 0)
    def blue(self): self.set(0, 0, self.b) 
    def error(self, code):
        print(f"!! ERROR {code} !!")
        for _ in range(code):
            self.set(50, 0, 0); time.sleep(0.3)
            self.off(); time.sleep(0.3)
        time.sleep(1)

led = StatusLED()

# --- HELPER ---
def unquote(string):
    if not string: return ""
    res = string.split('%')
    for i in range(1, len(res)):
        item = res[i]
        try: res[i] = chr(int(item[:2], 16)) + item[2:]
        except: res[i] = '%' + item
    return "".join(res).replace("+", " ")

# --- CAPTIVE PORTAL ---
def run_config_portal():
    led.blue()
    log("Starting Hotspot...")
    
    ap = network.WLAN(network.AP_IF)
   
    ap.config(essid='Calendar_Setup', authmode=0)
    ap.active(True)
    
    while not ap.active(): time.sleep(0.1)
    my_ip = ap.ifconfig()[0]
    log(f"IP: {my_ip}")

    udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udps.setblocking(False); udps.bind(('', 53))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80)); s.listen(1); s.setblocking(False)

    poller = select.poll()
    poller.register(udps, select.POLLIN)
    poller.register(s, select.POLLIN)

    # --- YOUR NEW HTML (With Logic Injection) ---
    html_part1 = """<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E-ink Configurator</title>
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #efefef; --main-blue: #1a4371; --text-dark: #333; --teal: #1c8b82;
            --border-gray: #d1d1d1; --remove-gray: #888;
            --radius-main: 20px; --radius-small: 10px; --radius-pill: 40px;
            --indicator-width: 4px;
        }

        body {
            font-family: 'Quicksand', sans-serif; background-color: var(--bg-color);
            color: var(--text-dark); margin: 0; padding: 10px;
            display: flex; justify-content: center; align-items: flex-start; min-height: 100vh;
        }

        .config-card {
            background: white; width: 100%; max-width: 500px;
            border-radius: var(--radius-main); box-shadow: 0 10px 25px rgba(0,0,0,0.05);
            overflow: hidden; border: 1px solid var(--border-gray); margin-top: 20px;
        }

        .header-preview { padding: 30px 20px 15px 20px; border-bottom: 1px solid var(--border-gray); text-align: center; }
        .header-preview h1 { color: var(--main-blue); margin: 0; font-size: 24px; text-transform: uppercase; letter-spacing: 2px; }
        .header-preview span { font-weight: 800; }
        .settings-body { padding: 25px; }

        .section-title { font-size: 14px; font-weight: 700; margin-bottom: 15px; color: var(--main-blue); display: block; text-transform: uppercase; letter-spacing: 1px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; font-size: 13px; color: #555; }

        select, input[type="text"], input[type="password"] {
            width: 100%; padding: 14px; border: 1px solid var(--border-gray);
            border-radius: var(--radius-small); background: #fafafa; margin-bottom: 20px;
            box-sizing: border-box; font-family: inherit; font-size: 15px;
        }

        .options-grid { display: grid; grid-template-columns: 1fr; gap: 10px; margin-bottom: 25px; }
        .checkbox-item {
            display: flex; align-items: center; background: #f6f6f6; padding: 12px 20px;
            border-radius: var(--radius-pill); cursor: pointer; transition: 0.2s; border: 1px solid transparent; font-size: 14px;
        }
        .checkbox-item:hover { border-color: var(--border-gray); background: #f0f0f0; }
        .checkbox-item input { margin-right: 12px; width: 18px; height: 18px; accent-color: var(--main-blue); }

        .expandable-container { max-height: 0; overflow: hidden; opacity: 0; transition: all 0.4s ease-in-out; margin-bottom: 0; }
        .expandable-container.open { max-height: 600px; opacity: 1; margin-bottom: 25px; margin-top: -10px; }
        .inner-container { background: #f8f9fa; border: 1px solid #eee; padding: 20px; border-radius: var(--radius-main); box-sizing: border-box; width: 100%; }

        .birthday-input-row { display: flex; flex-direction: column; gap: 10px; margin-bottom: 15px; }
        .birthday-date-controls { display: flex; gap: 10px; }
        .birthday-date-controls select { margin-bottom: 0; flex: 1; height: 48px; }
        .btn-add-bday { background: var(--teal); color: white; border: none; border-radius: var(--radius-small); padding: 0 20px; cursor: pointer; font-size: 20px; font-weight: bold; }
        .birthday-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; }
        .birthday-tag { display: flex; align-items: center; background: white; border: 1px solid var(--border-gray); padding: 6px 15px; border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; }
        .birthday-tag span { margin-left: 10px; color: var(--remove-gray); cursor: pointer; font-weight: 800; }

        /* Photo Mode Styles */
        .converter-controls { background: #fdfdfd; border: 1px solid #eee; padding: 15px; border-radius: var(--radius-main); margin-bottom: 20px; }
        .slider-group { margin-bottom: 12px; }
        .slider-group label { display: flex; justify-content: space-between; font-size: 12px; color: #666; }
        .slider-group input { width: 100%; margin: 5px 0; accent-color: var(--main-blue); cursor: pointer; }
        .photo-upload-zone { border: 2px dashed var(--border-gray); border-radius: var(--radius-main); padding: 25px; text-align: center; cursor: pointer; color: #777; background: #fdfdfd; margin-bottom: 15px; }
        
        #progressWrapper { display: none; margin-bottom: 15px; background: #eee; border-radius: var(--radius-pill); height: 10px; width: 100%; overflow: hidden; }
        #progressFill { height: 100%; width: 0%; background: var(--teal); transition: width 0.2s; }

        .preview-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 12px; margin: 15px 0; position: relative; }
        .preview-item { position: relative; border: 1px solid var(--border-gray); border-radius: var(--radius-small); cursor: grab; background: white; transition: opacity 0.2s; overflow: hidden; }
        .preview-item.dragging { opacity: 0.2; }
        .preview-item canvas { width: 100%; display: block; pointer-events: none; transition: filter 0.3s; }
        .preview-item:hover canvas { filter: blur(4px); }
        .btn-remove { position: absolute; top: 5px; right: 5px; width: 22px; height: 22px; background: var(--remove-gray); color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; border: none; z-index: 10; cursor: pointer; opacity: 0; transition: 0.2s; }
        .preview-item:hover .btn-remove { opacity: 1; }

        .preview-item.drop-after::after, .preview-item.drop-before::before { content: ''; position: absolute; top: 0; width: var(--indicator-width); height: 100%; background: var(--main-blue); z-index: 100; }
        .preview-item.drop-before::before { left: -8px; }
        .preview-item.drop-after::after { right: -8px; }

        .radio-group { display: flex; justify-content: center; gap: 25px; margin: 15px 0 25px 0; padding: 10px; background: #f9f9f9; border-radius: var(--radius-main); }
        .radio-item { display: flex; align-items: center; font-size: 14px; font-weight: 600; cursor: pointer; }
        .radio-item input { margin-right: 8px; accent-color: var(--main-blue); }

        .wifi-box { background: #f4f4f4; padding: 20px; border-radius: var(--radius-main); margin-top: 20px; }
        .btn-group { display: flex; gap: 10px; }
        button { flex: 1; padding: 14px; border: none; border-radius: var(--radius-pill); font-weight: 700; cursor: pointer; text-transform: uppercase; font-size: 12px; font-family: inherit; }
        .btn-check { background-color: var(--teal); color: white; }
        .btn-save { background-color: var(--main-blue); color: white; }

        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); justify-content: center; align-items: center; }
        .modal-content-wrapper { position: relative; width: 90%; height: 90%; display: flex; justify-content: center; align-items: center; }
        .modal img { max-width: 100%; max-height: 100%; border-radius: var(--radius-main); border: 4px solid rgba(255,255,255,0.15); object-fit: contain; }
        .modal-close { position: absolute; top: -15px; right: -15px; width: 45px; height: 45px; background: white; color: black; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: bold; cursor: pointer; z-index: 1002; }

        .hidden { display: none; }
        @media (max-width: 480px) { .btn-group { flex-direction: column; } }
    </style>
</head>
<body>

<div class="config-card">
    <div class="header-preview">
        <h1>KONFIGURACJA2 <span>Urządzenia</span></h1>
    </div>

    <div class="settings-body">
        <label for="displayMode" style="text-align: center;">TRYB DZIAŁANIA2</label>
        <select id="displayMode" onchange="toggleMode()">
            <option value="calendar">📅 Kalendarz</option>
            <option value="photo">🖼️ Ramka na zdjęcia</option>
        </select>

        <!-- CALENDAR SECTION (ZACHOWANE Z PLIKU 1) -->
        <div id="calendar-settings">
            <span class="section-title">Opcje Kalendarza</span>
            <div class="options-grid">
                <label class="checkbox-item"><input type="checkbox" id="opt_trash"> Harmonogram śmieci</label>
                <label class="checkbox-item"><input type="checkbox" id="opt_names"> Imieniny</label>
                <label class="checkbox-item"><input type="checkbox" id="opt_sundays"> Niedziele handlowe</label>
                <label class="checkbox-item"><input type="checkbox" id="opt_weather"> Pogoda</label>
                <label class="checkbox-item"><input type="checkbox" id="opt_holidays"> Święta państwowe</label>
                <label class="checkbox-item"><input type="checkbox" id="checkBirthdays" onchange="toggleBirthdaySection()"> Urodziny</label>
            </div>

            <!-- BIRTHDAY SECTION (ZACHOWANE Z PLIKU 1) -->
            <div id="birthdayContainer" class="expandable-container">
                <div class="inner-container">
                    <span class="section-title" style="text-align: center;">Dodaj Urodziny</span>
                    <div class="birthday-input-row">
                        <input type="text" id="bdayName" placeholder="Imię osoby...">
                        <div class="birthday-date-controls">
                            <select id="bdayDay"><option value="" disabled selected>Dzień</option></select>
                            <select id="bdayMonth">
                                <option value="" disabled selected>Miesiąc</option>
                                <option value="1">Styczeń</option><option value="2">Luty</option><option value="3">Marzec</option><option value="4">Kwiecień</option><option value="5">Maj</option><option value="6">Czerwiec</option><option value="7">Lipiec</option><option value="8">Sierpień</option><option value="9">Wrzesień</option><option value="10">Październik</option><option value="11">Listopad</option><option value="12">Grudzień</option>
                            </select>
                            <button class="btn-add-bday" onclick="addBirthday()">+</button>
                        </div>
                    </div>
                    <div id="birthdayList" class="birthday-list"></div>
                </div>
            </div>
            
            <div class="wifi-box">
                <span class="section-title" style="text-align: center;">Połączenie Wi-Fi</span>
                <input type="text" id="wifi_ssid" placeholder="Nazwa sieci (SSID)" tabIndex="-1">
                <input type="password" id="wifi_pass" placeholder="Hasło" tabIndex="-1">
                <div class="btn-group">
                    <button class="btn-check">Sprawdź Połączenie</button>
                    <button class="btn-save" onclick="saveWifi()">Zapisz i uruchom</button>
                </div>
            </div>
        </div>

        <!-- PHOTO SECTION (ZACHOWANE I NAPRAWIONE) -->
        <div id="photo-settings" class="hidden">
            <span class="section-title">Korekta obrazu</span>
            <div class="converter-controls">
                <div class="slider-group"><label>Jasność: <span id="v-bright">0</span></label><input type="range" id="bright" min="-100" max="100" value="0" oninput="updateUI('bright'); debounceProcess();"></div>
                <div class="slider-group"><label>Kontrast: <span id="v-contrast">0</span></label><input type="range" id="contrast" min="-100" max="100" value="0" oninput="updateUI('contrast'); debounceProcess();"></div>
                <div class="slider-group"><label>Nasycenie: <span id="v-sat">1.0</span></label><input type="range" id="sat" min="0" max="2" step="0.1" value="1.0" oninput="updateUI('sat'); debounceProcess();"></div>
            </div>

            <span class="section-title">Twoje Zdjęcia (<span id="photoCount">0</span>/30)</span>
            <div id="loadingStatus" style="font-size: 11px; text-align: center; color: var(--teal); font-weight: 700; margin-bottom: 8px; display: none;">Przetwarzanie...</div>
            <div id="progressWrapper"><div id="progressFill"></div></div>

            <div class="photo-upload-zone" onclick="document.getElementById('photoInput').click()">
                <strong>Kliknij, aby dodać zdjęcia (maksymalnie 30)</strong>
            </div>
            <input type="file" id="photoInput" multiple accept="image/*" class="hidden" onchange="loadFiles(this)">
            <div id="previewContainer" class="preview-container"></div>

            <div class="radio-group">
                <label class="radio-item"><input type="radio" name="order" value="random" checked> Losowo</label>
                <label class="radio-item"><input type="radio" name="order" value="sequence"> Po kolei</label>
            </div>
            <button class="btn-save" id="btnUpload" style="width: 100%;" onclick="uploadPhoto()">Zapisz i wyślij zdjęcia</button>
            <p id="status" style="text-align:center; font-size:12px; margin-top:10px;"></p>
        </div>
    </div>
</div>

<div id="modal" class="modal">
    <div class="modal-content-wrapper">
        <div class="modal-close" onclick="closeModal()">✕</div>
        <img id="modalImg" src="">
    </div>
</div>

<script>
    const PALETTE = [[0,0,0],[255,255,255],[240,224,80],[160,32,32],[0,0,0],[80,128,184],[96,128,80]];
    let imagesData = [];
    let birthdaysData = [];
    let dragIdx = null;
    let timer;

    // Fill days
    for(let i=1; i<=31; i++) {
        let opt = document.createElement('option'); opt.value = i; opt.innerText = i;
        document.getElementById('bdayDay').appendChild(opt);
    }

    function toggleMode() {
        const mode = document.getElementById('displayMode').value;
        document.getElementById('calendar-settings').classList.toggle('hidden', mode !== 'calendar');
        document.getElementById('photo-settings').classList.toggle('hidden', mode !== 'photo');
    }

    function toggleBirthdaySection() {
        document.getElementById('birthdayContainer').classList.toggle('open', document.getElementById('checkBirthdays').checked);
    }

    function updateUI(id) { document.getElementById('v-'+id).innerText = document.getElementById(id).value; }
    function updateCounter() { document.getElementById('photoCount').innerText = imagesData.length; }

    function addBirthday() {
        const n = document.getElementById('bdayName'), d = document.getElementById('bdayDay'), m = document.getElementById('bdayMonth');
        if(!n.value || !d.value || !m.value) return;
        birthdaysData.push({ name: n.value, day: d.value, month: m.value });
        n.value = ''; renderBirthdays();
    }
    function renderBirthdays() {
        const list = document.getElementById('birthdayList'); list.innerHTML = '';
        birthdaysData.forEach((item, idx) => {
            const tag = document.createElement('div'); tag.className = 'birthday-tag';
            tag.innerHTML = `${item.name} (${item.day}.${item.month}) <span onclick="birthdaysData.splice(${idx},1);renderBirthdays()">✕</span>`;
            list.appendChild(tag);
        });
    }

    async function loadFiles(input) {
        const files = Array.from(input.files);
        for (const f of files) {
            if (imagesData.length >= 30) break;
            const img = await new Promise(res => {
                const r = new FileReader();
                r.onload = e => { const i = new Image(); i.onload = () => res(i); i.src = e.target.result; };
                r.readAsDataURL(f);
            });
            imagesData.push({ original: img, canvas: null, name: f.name });
        }
        processAll(); input.value = "";
    }

    function debounceProcess() { clearTimeout(timer); timer = setTimeout(processAll, 400); }

    async function processAll() {
        if (imagesData.length === 0) return;
        const p = { b: parseInt(document.getElementById('bright').value), c: parseInt(document.getElementById('contrast').value), s: parseFloat(document.getElementById('sat').value) };
        const bar = document.getElementById('progressWrapper'), fill = document.getElementById('progressFill'), status = document.getElementById('loadingStatus');
        bar.style.display = status.style.display = 'block';
        for (let i = 0; i < imagesData.length; i++) {
            status.innerText = `Przetwarzanie ${i + 1}/${imagesData.length}...`;
            fill.style.width = ((i + 1) / imagesData.length) * 100 + '%';
            await new Promise(res => setTimeout(res, 30));
            imagesData[i].canvas = convert(imagesData[i].original, p);
        }
        renderGallery(); updateCounter();
        setTimeout(() => { bar.style.display = 'none'; status.style.display = 'none'; }, 500);
    }

    function renderGallery() {
        const container = document.getElementById('previewContainer'); container.innerHTML = '';
        imagesData.forEach((obj, idx) => {
            const wrap = document.createElement('div'); wrap.className = 'preview-item'; wrap.draggable = true;
            wrap.ondragstart = () => { dragIdx = idx; setTimeout(() => wrap.classList.add('dragging'), 0); };
            wrap.ondragover = (e) => {
                e.preventDefault(); const rect = wrap.getBoundingClientRect();
                const isAfter = e.clientX > rect.left + rect.width / 2;
                wrap.classList.toggle('drop-after', isAfter); wrap.classList.toggle('drop-before', !isAfter);
            };
            wrap.ondragleave = () => wrap.classList.remove('drop-after', 'drop-before');
            wrap.ondrop = (e) => { e.preventDefault(); const rect = wrap.getBoundingClientRect(); move(dragIdx, e.clientX > rect.left + rect.width / 2 ? idx + 1 : idx); };
            wrap.ondragend = () => wrap.classList.remove('dragging');
            wrap.onclick = () => { document.getElementById('modal').style.display = 'flex'; document.getElementById('modalImg').src = obj.canvas.toDataURL(); };
            const del = document.createElement('div'); del.className = 'btn-remove'; del.innerText = '✕';
            del.onclick = (e) => { e.stopPropagation(); imagesData.splice(idx, 1); renderGallery(); updateCounter(); };
            const thumb = document.createElement('canvas'); thumb.width = 150; thumb.height = 200;
            thumb.getContext('2d').drawImage(obj.canvas, 0, 0, 150, 200);
            wrap.appendChild(del); wrap.appendChild(thumb); container.appendChild(wrap);
        });
    }

    function move(from, to) {
        if (from === to || from === to - 1) return;
        const item = imagesData.splice(from, 1)[0];
        if (to > from) to--;
        imagesData.splice(to, 0, item); renderGallery();
    }

    // NAPRAWIONY KONWERTER (Zapisuje indeksy kolorów)
    function convert(img, p) {
        const w = 1200, h = 1600;
        const cvs = document.createElement('canvas'); cvs.width = w; cvs.height = h;
        const ctx = cvs.getContext('2d');
        const scale = Math.max(w/img.width, h/img.height);
        const x = (w-img.width*scale)/2, y = (h-img.height*scale)/2;
        ctx.fillStyle = 'white'; ctx.fillRect(0,0,w,h);
        ctx.drawImage(img, x, y, img.width*scale, img.height*scale);

        const id = ctx.getImageData(0,0,w,h), d = id.data, cf = (259*(p.c+255))/(255*(259-p.c));
        cvs.indexes = new Uint8Array(w*h);

        for(let i=0; i<d.length; i+=4) {
            let r=d[i]+p.b, g=d[i+1]+p.b, b=d[i+2]+p.b;
            r=cf*(r-128)+128; g=cf*(g-128)+128; b=cf*(b-128)+128;
            const gray = 0.2989*r + 0.5870*g + 0.1140*b;
            r=gray+p.s*(r-gray); g=gray+p.s*(g-gray); b=gray+p.s*(b-gray);
            let best=0, min=Infinity;
            for(let j=0; j<7; j++) {
                if(j==4) continue;
                let dst = Math.pow(r-PALETTE[j][0],2) + Math.pow(g-PALETTE[j][1],2) + Math.pow(b-PALETTE[j][2],2);
                if(dst < min) { min=dst; best=j; }
            }
            cvs.indexes[i/4] = best;
            let fr=PALETTE[best][0], fg=PALETTE[best][1], fb=PALETTE[best][2];
            let er=r-fr, eg=g-fg, eb=b-fb;
            d[i]=fr; d[i+1]=fg; d[i+2]=fb;
            dist(d, i+4, er, eg, eb, 0.4375, w); dist(d, i+w*4-4, er, eg, eb, 0.1875, w); dist(d, i+w*4, er, eg, eb, 0.3125, w); dist(d, i+w*4+4, er, eg, eb, 0.0625, w);
        }
        ctx.putImageData(id, 0, 0); return cvs;
    }
    function dist(d, i, er, eg, eb, f, w) { if(i>=0 && i<d.length){ d[i]+=er*f; d[i+1]+=eg*f; d[i+2]+=eb*f; } }

    // WYSYŁANIE ZDJĘĆ (Logika binarna z Pliku 2)
    function uploadPhoto() {
        if(imagesData.length === 0) return alert("Brak zdjęcia!");
        const btn = document.getElementById('btnUpload');
        const st = document.getElementById('status');
        btn.innerText = "Przetwarzanie..."; btn.disabled = true;

        const indexes = imagesData[0].canvas.indexes;
        const w=1200, h=1600;
        const halfLen = (w/2 * h) / 2; 
        const masterBin = new Uint8Array(halfLen);
        const slaveBin = new Uint8Array(halfLen);
        let m=0, s=0;

        for(let y=0; y<h; y++) {
            for(let x=0; x<600; x+=2) {
                let p1 = indexes[y*w+x], p2 = indexes[y*w+x+1];
                masterBin[m++] = (p1<<4)|p2;
            }
            for(let x=600; x<1200; x+=2) {
                let p1 = indexes[y*w+x], p2 = indexes[y*w+x+1];
                slaveBin[s++] = (p1<<4)|p2;
            }
        }
        const finalBin = new Uint8Array(halfLen*2);
        finalBin.set(masterBin); finalBin.set(slaveBin, halfLen);

        st.innerText = "Wysyłanie...";
        fetch('/upload?mode=photo', {method:'POST', body:finalBin})
        .then(r => { st.innerText = "Wysłano!"; setTimeout(() => {btn.disabled=false; btn.innerText="Zapisz i wyślij zdjęcia"; st.innerText="";}, 3000); })
        .catch(e => { alert("Błąd połączenia"); btn.disabled=false; });
    }

    function saveWifi() {
        const ssid = document.getElementById('wifi_ssid').value;
        const pass = document.getElementById('wifi_pass').value;
        const mode = document.getElementById('displayMode').value;
        if(!ssid) return alert("Podaj nazwę sieci!");
        fetch(`/save?ssid=${encodeURIComponent(ssid)}&pass=${encodeURIComponent(pass)}&mode=${mode}`)
        .then(r => alert("Zapisano! Urządzenie się zrestartuje."));
    }
    
    function closeModal() { document.getElementById('modal').style.display = 'none'; }
</script>
</body>
</html>"""

    while True:
        responses = poller.poll(100)
        for sock, event in responses:
            if sock == udps:
                try:
                    data, addr = udps.recvfrom(1024)
                    if data:
                        ip_parts = [int(x) for x in my_ip.split('.')]
                        packet = data[:2] + b'\x81\x80' + data[4:6] + data[4:6] + b'\x00\x00\x00\x00' + data[12:]
                        packet += b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04' + bytes(ip_parts)
                        udps.sendto(packet, addr)
                except: pass
                
            elif sock == s:
                try:
                    conn, addr = s.accept()
                    req = conn.recv(1024)
                    req_str = req.decode()
                    
                    if "GET /save" in req_str:
                        try:
                            query = req_str.split(' ')[1].split('?')[1]
                            params = dict(x.split('=') for x in query.split('&'))
                            ssid = unquote(params.get('ssid', ''))
                            pwd = unquote(params.get('pass', ''))
                            mode = unquote(params.get('mode', 'calendar'))
                            
                            with open("/sd/settings.txt", "w") as f:
                                f.write(f"{ssid}\n{pwd}\n{mode}")
                            
                            conn.send("HTTP/1.1 200 OK\r\n\r\nOK")
                            conn.close()
                            time.sleep(1); machine.reset()
                        except: conn.send("HTTP/1.1 200 OK\r\n\r\nError")

                    elif "POST /upload" in req_str:
                        # PHOTO UPLOAD
                        log("Receiving Photo...")
                        led.cyan()
                        
                        cl = 0
                        for line in req_str.split('\r\n'):
                            if "Content-Length:" in line:
                                cl = int(line.split(':')[1])
                        
                        header_end = req.find(b'\r\n\r\n') + 4
                        data = req[header_end:]
                        total = len(data)
                        
                        with open("/sd/temp.bin", "wb") as f:
                            f.write(data)
                            while total < cl:
                                chunk = conn.recv(4096)
                                if not chunk: break
                                f.write(chunk)
                                total += len(chunk)
                        
                        # Also Force Mode to Photo in settings
                        try:
                            with open("/sd/settings.txt", "r") as f: l = f.readlines()
                            ssid = l[0].strip(); pwd = l[1].strip()
                        except: ssid=""; pwd=""
                        with open("/sd/settings.txt", "w") as f: f.write(f"{ssid}\n{pwd}\nphoto")

                        conn.send("HTTP/1.1 200 OK\r\n\r\nOK")
                        conn.close()
                        s.close(); udps.close(); ap.active(False)
                        return True # Trigger Display

                    else:
                        conn.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + html_part1)
                    conn.close()
                except: pass

# --- WIFI CONNECT ---
def connect_wifi(ssid, password):
    led.yellow()
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try: wlan.config(pm=wlan.PM_NONE)
    except: pass
    
    log(f"Connecting to {ssid}...")
    wlan.connect(ssid, password)
    
    for _ in range(20):
        if wlan.isconnected(): return True
        time.sleep(1)
    return False

# --- OTA UPDATE ---
def check_for_update():
    log("Checking for updates...")

    local_hash = ""
    try:
        with open("/sd/version.txt", "r") as f:
            local_hash = f.read().strip()
    except:
        pass

    log(f"Local: {local_hash[:8] if local_hash else 'none'}")

    try:
        addr = socket.getaddrinfo("api.github.com", 443)[0][-1]
        s = socket.socket()
        s.settimeout(10.0)
        s.connect(addr)
        ss = ssl.wrap_socket(s)

        ss.write((f"GET /repos/Raging-Regret/Kalendarz-E-Ink/commits/main HTTP/1.1\r\n"
                   f"Host: api.github.com\r\n"
                   f"Accept: application/vnd.github.sha\r\n"
                   f"User-Agent: ESP32\r\n"
                   f"Connection: close\r\n\r\n").encode())

        status_line = ss.readline()
        if b"200" not in status_line:
            ss.close(); s.close()
            log("Update check: bad response")
            return

        while True:
            line = ss.readline()
            if line == b"\r\n" or line == b"": break

        remote_hash = ss.read().decode().strip()
        ss.close(); s.close()
        log(f"Remote: {remote_hash[:8]}")

        if remote_hash == local_hash:
            log("Up to date.")
            return

        log("Downloading new main.py...")
        led.orange()
        gc.collect()

        addr = socket.getaddrinfo("raw.githubusercontent.com", 443)[0][-1]
        s = socket.socket()
        s.settimeout(15.0)
        s.connect(addr)
        ss = ssl.wrap_socket(s)

        ss.write((f"GET /Raging-Regret/Kalendarz-E-Ink/main/main.py HTTP/1.1\r\n"
                   f"Host: raw.githubusercontent.com\r\n"
                   f"User-Agent: ESP32\r\n"
                   f"Connection: close\r\n\r\n").encode())

        while True:
            line = ss.readline()
            if line == b"\r\n" or line == b"": break

        with open("main_new.py", "wb") as f:
            while True:
                chunk = ss.read(1024)
                if not chunk: break
                f.write(chunk)

        ss.close(); s.close()

        if os.stat("main_new.py")[6] < 100:
            os.remove("main_new.py")
            log("Update file too small, skipping")
            return

        try: os.remove("main.py")
        except: pass
        os.rename("main_new.py", "main.py")

        with open("/sd/version.txt", "w") as f:
            f.write(remote_hash)

        log("Updated! Restarting...")
        led.green()
        time.sleep(1)
        machine.reset()

    except Exception as e:
        log(f"OTA Error: {e}")
        try: os.remove("main_new.py")
        except: pass

# --- DOWNLOADER ---
def download_to_sd(filename, save_path):
    led.cyan()
    log(f"Downloading {filename}...")
    gc.collect()
    
    buf = bytearray(32768)
    mv = memoryview(buf)
    
    try:
        addr = socket.getaddrinfo("raw.githubusercontent.com", 443)[0][-1]
        s = socket.socket()
        s.settimeout(15.0) 
        s.connect(addr)
        ss = ssl.wrap_socket(s)
        
        request = (f"GET /api/render?format=bin HTTP/1.1\r\n"
                   f"Host: calendar-kds.vercel.app\r\n"
                   f"User-Agent: ESP32\r\n"
                   f"Connection: close\r\n\r\n")
        ss.write(request.encode())
        
        while True:
            line = ss.readline()
            if line == b"\r\n" or line == b"": break
        
        with open(save_path, "wb") as f:
            while True:
                n = ss.readinto(mv)
                if not n: break
                f.write(mv[:n])
        
        ss.close(); s.close()
        return True
    except Exception as e:
        log(f"DL Error: {e}")
        return False

# --- DISPLAY DRIVER ---
class EPD_Definitive:
    WIDTH, HEIGHT, DTM = 1200, 1600, 0x10

    def __init__(self):
        print("Init Display...")
        self.spi = SPI(2, baudrate=10_000_000, 
                       sck=Pin(EPD_SCK), mosi=Pin(EPD_MOSI), miso=None)
        
        self.cs_m = Pin(CS_M, Pin.OUT, value=1)
        self.cs_s = Pin(CS_S, Pin.OUT, value=1)
        self.dc = Pin(DC, Pin.OUT, value=1)
        self.rst = Pin(RST, Pin.OUT, value=1)
        self.pwr = Pin(PWR, Pin.OUT, value=0)
        self.busy = Pin(BUSY, Pin.IN, Pin.PULL_UP)
        
        self.PSR, self.PWR_epd, self.POF, self.PON = 0x00, 0x01, 0x02, 0x04
        self.BTST_N, self.BTST_P, self.DRF, self.CDI = 0x05, 0x06, 0x12, 0x50
        self.TCON, self.TRES, self.AN_TM, self.AGID = 0x60, 0x61, 0x74, 0x86
        self.BUCK_BOOST_VDDN, self.TFT_VCOM_POWER = 0xB0, 0xB1
        self.EN_BUF, self.BOOST_VDDP_EN, self.CCSET, self.PWS, self.CMD66 = 0xB6, 0xB7, 0xE0, 0xE3, 0xF0

        self.AN_TM_V = b'\xC0\x1C\x1C\xCC\xCC\xCC\x15\x15\x55'
        self.CMD66_V = b'\x49\x55\x13\x5D\x05\x10'
        self.PSR_V   = b'\xDF\x69'
        self.PWR_V   = b'\x0F\x00\x28\x2C\x28\x38'
        self.POF_V, self.DRF_V, self.CDI_V = b'\x00', b'\x00', b'\xF7'
        self.TCON_V, self.AGID_V = b'\x03\x03', b'\x10'
        self.PWS_V, self.CCSET_V, self.EN_BUF_V = b'\x22', b'\x01', b'\x07'
        self.BTST_P_V, self.BOOST_VDDP_EN_V = b'\xE8\x28', b'\x01'
        self.BTST_N_V, self.BUCK_BOOST_VDDN_V = b'\xE8\x28', b'\x01'
        self.TFT_VCOM_POWER_V = b'\x02'
        self.TRES_V = b'\x04\xb0\x06\x40'

    def _cs_all(self, value):
        self.cs_m.value(value)
        self.cs_s.value(value)

    def _send_cmd_and_data(self, cmd, data_buffer, cs_pin):
        cs_pin.value(0)
        self.dc.value(0)
        self.spi.write(bytearray([cmd]))
        self.dc.value(1)
        self.spi.write(data_buffer)
        cs_pin.value(1)

    def _wait_until_idle(self):
        time.sleep_ms(50)
        while self.busy.value() == 0:
            time.sleep_ms(50)

    def reset(self):
        self.rst.value(1); time.sleep_ms(30)
        self.rst.value(0); time.sleep_ms(30)
        self.rst.value(1); time.sleep_ms(30)
        self.rst.value(0); time.sleep_ms(30)
        self.rst.value(1); time.sleep_ms(30)

    def _turn_on_display(self):
        log("Refreshing Screen...")
        self._cs_all(0); self.dc.value(0); self.spi.write(bytearray([self.PON])); self._cs_all(1)
        self._wait_until_idle()
        time.sleep_ms(20)
        self._cs_all(0); self._send_cmd_and_data(self.DRF, self.DRF_V, self.cs_m); self._cs_all(1)
        self._wait_until_idle()
        self._cs_all(0); self._send_cmd_and_data(self.POF, self.POF_V, self.cs_m); self._cs_all(1)
        log("Refresh complete.")
    
    def init(self):
        log("Initializing...")
        self.pwr.value(1)
        time.sleep_ms(100)
        self.reset()
        
        self._send_cmd_and_data(self.AN_TM, self.AN_TM_V, self.cs_m)
        self._cs_all(0); self._send_cmd_and_data(self.CMD66, self.CMD66_V, self.cs_m); self._cs_all(1)
        self._cs_all(0); self._send_cmd_and_data(self.PSR, self.PSR_V, self.cs_m); self._cs_all(1)
        self._cs_all(0); self._send_cmd_and_data(self.CDI, self.CDI_V, self.cs_m); self._cs_all(1)
        self._cs_all(0); self._send_cmd_and_data(self.TCON, self.TCON_V, self.cs_m); self._cs_all(1)
        self._cs_all(0); self._send_cmd_and_data(self.AGID, self.AGID_V, self.cs_m); self._cs_all(1)
        self._cs_all(0); self._send_cmd_and_data(self.PWS, self.PWS_V, self.cs_m); self._cs_all(1)
        self._cs_all(0); self._send_cmd_and_data(self.CCSET, self.CCSET_V, self.cs_m); self._cs_all(1)
        self._cs_all(0); self._send_cmd_and_data(self.TRES, self.TRES_V, self.cs_m); self._cs_all(1) 
        self._send_cmd_and_data(self.PWR_epd, self.PWR_V, self.cs_m)
        self._send_cmd_and_data(self.EN_BUF, self.EN_BUF_V, self.cs_m)
        self._send_cmd_and_data(self.BTST_P, self.BTST_P_V, self.cs_m)
        self._send_cmd_and_data(self.BOOST_VDDP_EN, self.BOOST_VDDP_EN_V, self.cs_m)
        self._send_cmd_and_data(self.BTST_N, self.BTST_N_V, self.cs_m)
        self._send_cmd_and_data(self.BUCK_BOOST_VDDN, self.BUCK_BOOST_VDDN_V, self.cs_m)
        self._send_cmd_and_data(self.TFT_VCOM_POWER, self.TFT_VCOM_POWER_V, self.cs_m)

    def sleep(self):
        self._cs_all(0); self.dc.value(0); self.spi.write(b'\x07'); self.dc.value(1); self.spi.write(b'\xA5'); self._cs_all(1)
        time.sleep_ms(2000)
        self.pwr.value(0)

    def display_from_sd_card(self, filepath):
        log(f"Loading {filepath} into RAM...")
        gc.collect()
        
        try:
            with open(filepath, 'rb') as f:
                f.seek(0, 2); size = f.tell(); f.seek(0)
                img_data = bytearray(size)
                f.readinto(img_data)
            
            led.white()
            half_size = len(img_data) // 2
            
            # Master Chunk
            led.orange()
            self.cs_m.value(0); self.dc.value(0); self.spi.write(bytearray([self.DTM])); self.dc.value(1)
            self.spi.write(img_data[:half_size])
            self.cs_m.value(1)
            
            # Slave Chunk
            led.cyan()
            self.cs_s.value(0); self.dc.value(0); self.spi.write(bytearray([self.DTM])); self.dc.value(1)
            self.spi.write(img_data[half_size:])
            self.cs_s.value(1)

        except Exception as e:
            log(f"Display Error: {e}")
            self._cs_all(1)
            return
        
        led.white()
        self._turn_on_display()

def tpl5110_done():
    log("Shutting down...")
    led.green(); time.sleep(0.5); led.off()
    done_pin = Pin(TPL_DONE, Pin.OUT)
    done_pin.value(0); time.sleep_ms(100)
    done_pin.value(1); time.sleep_ms(100)
    done_pin.value(0)
    while True: time.sleep(1)

# --- MAIN ---
if __name__ == '__main__':
    try:
        led.purple()
        spi_sd = SPI(1, baudrate=20_000_000, sck=Pin(SD_SCK), mosi=Pin(SD_MOSI), miso=Pin(SD_MISO))
        cs_sd = Pin(SD_CS, Pin.OUT)
        sd = sdcard.SDCard(spi_sd, cs_sd)
        os.mount(os.VfsFat(sd), "/sd")
        
        # READ SETTINGS
        ssid, password, mode = "", "", "calendar"
        try:
            with open("/sd/settings.txt", "r") as f:
                l = f.readlines()
                ssid = l[0].strip()
                password = l[1].strip()
                if len(l) > 2: mode = l[2].strip()
        except: pass
        
        # BUTTON CHECK
        btn = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        run_setup = False
        if btn.value() == 0 or not ssid: run_setup = True
        
        local_path = "/sd/temp.bin"
        uploaded_now = False
        
        # 1. SETUP / HOTSPOT
        if run_setup:
            if run_config_portal():
                uploaded_now = True
            # Read Mode again after setup
            try:
                with open("/sd/settings.txt", "r") as f:
                    l = f.readlines()
                    ssid = l[0].strip(); password = l[1].strip()
                    if len(l) > 2: mode = l[2].strip()
            except: pass

        # 2. OPERATION
        if uploaded_now:
            # User uploaded photo -> Show it
            try:
                epd = EPD_Definitive()
                epd.init()
                epd.display_from_sd_card(local_path)
                epd.sleep()
            except: led.error(5)

        elif mode == "calendar":
            # Calendar Mode: Download from GitHub
            try: 
                with open("/sd/idx.txt", "r") as f: idx = int(f.read().strip())
            except: idx = 0
            
            next_idx = idx + 1
            filename = f"{next_idx}.bin"
            
            if connect_wifi(ssid, password):
                check_for_update()
                if download_to_sd(filename, local_path):
                    with open("/sd/idx.txt", "w") as f: f.write(str(next_idx))
                    try:
                        epd = EPD_Definitive()
                        epd.init()
                        epd.display_from_sd_card(local_path)
                        epd.sleep()
                    except: led.error(5)
                elif download_to_sd("0.bin", local_path):
                    # Fallback to 0.bin if next day fails
                    with open("/sd/idx.txt", "w") as f: f.write("0")
                    try:
                        epd = EPD_Definitive()
                        epd.init()
                        epd.display_from_sd_card(local_path)
                        epd.sleep()
                    except: led.error(5)
                else: led.error(4)
                
            else: led.error(3)
        
        elif mode == "photo":
            # Photo Mode (Saved): Do nothing, just sleep
            # (Assuming image is already static on screen from previous upload)
            # If you want it to re-draw the last uploaded image on every boot:
            try:
                epd = EPD_Definitive()
                epd.init()
                epd.display_from_sd_card(local_path)
                epd.sleep()
            except: pass

    except Exception as e:
        log(f"Err: {e}")
        led.error(2)
    finally:
        try: os.umount("/sd")
        except: pass
        tpl5110_done()
