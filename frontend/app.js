/**
 * Acoustic Camera Instrumentation UI Engine
 * Author: Nikita Zhuravlov
 */
const image2dCanvas = document.getElementById('image2dCanvas');
const imgCtx = image2dCanvas.getContext('2d');

const ascanCanvas = document.getElementById('ascanCanvas');
const ascanCtx = ascanCanvas.getContext('2d');

const connectBtn = document.getElementById('connectBtn');
const statusPip = document.getElementById('statusPip');
const fpsReadout = document.getElementById('fpsReadout');

const btnModeStereo = document.getElementById('btnModeStereo');
const btnModeMono = document.getElementById('btnModeMono');
const modeDescription = document.getElementById('modeDescription');
const infoText = document.getElementById('infoText');
const baselineStat = document.getElementById('baselineStat');

let socket = null;
let currentMode = "stereo";
let frameCounter = 0;
let lastFpsStamp = performance.now();

// High-Dynamic Range Acoustic Palette
// Smooth progression: Deep Navy -> Electric Azure -> Teal -> Bright Amber -> Pure White
function getAcousticSpectrum(val) {
    val = Math.max(0, Math.min(1, val));
    let r = 0, g = 0, b = 0;
    
    if (val < 0.25) {
        let t = val / 0.25;
        r = Math.floor(4 * (1 - t) + 0 * t);
        g = Math.floor(8 * (1 - t) + 110 * t);
        b = Math.floor(20 * (1 - t) + 240 * t);
    } else if (val < 0.6) {
        let t = (val - 0.25) / 0.35;
        r = 0;
        g = Math.floor(110 * (1 - t) + 230 * t);
        b = Math.floor(240 * (1 - t) + 180 * t);
    } else if (val < 0.85) {
        let t = (val - 0.6) / 0.25;
        r = Math.floor(255 * t);
        g = Math.floor(230 * (1 - t) + 220 * t);
        b = Math.floor(180 * (1 - t) + 60 * t);
    } else {
        let t = (val - 0.85) / 0.15;
        r = 255;
        g = Math.floor(220 + 35 * t);
        b = Math.floor(60 + 195 * t);
    }
    return [r, g, b];
}

function drawGridOverlay(mode) {
    const w = image2dCanvas.width;
    const h = image2dCanvas.height;

    imgCtx.strokeStyle = "rgba(255, 255, 255, 0.06)";
    imgCtx.lineWidth = 1;
    imgCtx.fillStyle = "#5d6a7d";
    imgCtx.font = "10px JetBrains Mono, monospace";

    if (mode === "stereo") {
        // Polar Azimuth & Range arcs for stereo beamforming
        const originX = w / 2;
        const originY = h;

        for (let r_m = 0.5; r_m <= 2.0; r_m += 0.5) {
            const radius = (r_m / 2.2) * h;
            imgCtx.beginPath();
            imgCtx.arc(originX, originY, radius, Math.PI, 2 * Math.PI);
            imgCtx.stroke();
            imgCtx.fillText(`${r_m.toFixed(1)}m`, originX + 6, originY - radius + 12);
        }

        // Azimuth angles (-45°, -22.5°, 0°, +22.5°, +45°)
        const angles = [-45, -22.5, 0, 22.5, 45];
        angles.forEach(deg => {
            const rad = (deg - 90) * (Math.PI / 180);
            imgCtx.beginPath();
            imgCtx.moveTo(originX, originY);
            imgCtx.lineTo(originX + Math.cos(rad) * h, originY + Math.sin(rad) * h);
            imgCtx.stroke();
        });
    } else {
        // Cartesian metric grid for Mono SAS
        for (let d = 0.5; d <= 2.0; d += 0.5) {
            const y = h - ((d - 0.2) / 2.0) * h;
            imgCtx.beginPath();
            imgCtx.moveTo(0, y);
            imgCtx.lineTo(w, y);
            imgCtx.stroke();
            imgCtx.fillText(`Y ${d.toFixed(1)}m`, 10, y - 4);
        }
        for (let x_m = -0.6; x_m <= 0.6; x_m += 0.3) {
            const x = ((x_m + 0.9) / 1.8) * w;
            imgCtx.beginPath();
            imgCtx.moveTo(x, 0);
            imgCtx.lineTo(x, h);
            imgCtx.stroke();
            imgCtx.fillText(`${x_m > 0 ? '+' : ''}${x_m.toFixed(1)}m`, x + 4, h - 8);
        }
    }
}

function renderSpatialField(width, height, data, mode) {
    const w = image2dCanvas.width;
    const h = image2dCanvas.height;

    const offscreen = document.createElement('canvas');
    offscreen.width = width;
    offscreen.height = height;
    const offCtx = offscreen.getContext('2d');
    const imgData = offCtx.createImageData(width, height);

    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const srcIdx = (height - 1 - y) * width + x;
            const val = data[srcIdx];
            const [r, g, b] = getAcousticSpectrum(val);

            const dstIdx = (y * width + x) * 4;
            imgData.data[dstIdx + 0] = r;
            imgData.data[dstIdx + 1] = g;
            imgData.data[dstIdx + 2] = b;
            imgData.data[dstIdx + 3] = val > 0.03 ? Math.floor(val * 255) : 0;
        }
    }

    offCtx.putImageData(imgData, 0, 0);

    imgCtx.fillStyle = '#040507';
    imgCtx.fillRect(0, 0, w, h);
    imgCtx.imageSmoothingEnabled = true;
    imgCtx.drawImage(offscreen, 0, 0, w, h);

    drawGridOverlay(mode);
}

function drawAScan(data) {
    const w = ascanCanvas.width;
    const h = ascanCanvas.height;

    ascanCtx.fillStyle = '#040507';
    ascanCtx.fillRect(0, 0, w, h);

    // Subtle background guidelines
    ascanCtx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
    ascanCtx.lineWidth = 1;
    ascanCtx.beginPath();
    for (let x = 0.25; x < 1.0; x += 0.25) {
        ascanCtx.moveTo(x * w, 0);
        ascanCtx.lineTo(x * w, h);
    }
    ascanCtx.stroke();

    // Signal waveform
    ascanCtx.strokeStyle = '#00e6b4';
    ascanCtx.lineWidth = 1.5;
    ascanCtx.beginPath();

    for (let i = 0; i < data.length; i++) {
        const val = data[i];
        const x = (i / (data.length - 1)) * w;
        const y = h - val * (h - 16) - 4;
        if (i === 0) ascanCtx.moveTo(x, y);
        else ascanCtx.lineTo(x, y);
    }
    ascanCtx.stroke();
}

function updateFPS() {
    frameCounter++;
    const now = performance.now();
    if (now - lastFpsStamp >= 1000) {
        fpsReadout.textContent = `${frameCounter} FPS`;
        frameCounter = 0;
        lastFpsStamp = now;
    }
}

function setOperatingMode(mode) {
    currentMode = mode;
    if (mode === "stereo") {
        btnModeStereo.classList.add("active");
        btnModeMono.classList.remove("active");
        modeDescription.textContent = "Stationary 2-Channel TDOA Beamforming";
        baselineStat.textContent = "15.0 cm";
        infoText.innerHTML = `
            <p><strong>Stereo Mode Active:</strong> Real-time beamforming utilizes dual capsules with inter-aural time difference (ITD) filtering. Instantaneous spatial mapping without moving the sensor.</p>
            <div class="metric-row"><span>APERTURE BASELINE</span><span class="mono-stat">15.0 cm</span></div>
            <div class="metric-row"><span>GRID RESOLUTION</span><span class="mono-stat">80 × 80 px (6,400 bins)</span></div>
        `;
    } else {
        btnModeMono.classList.add("active");
        btnModeStereo.classList.remove("active");
        modeDescription.textContent = "Synthetic Aperture Sonar (Rolling Backprojection)";
        baselineStat.textContent = "35.0 cm (virtual)";
        infoText.innerHTML = `
            <p><strong>Mono SAS Active:</strong> Slide your single microphone along your desk to synthesize a wide aperture baseline. Backprojection accumulates dynamic returns into a spatial profile.</p>
            <div class="metric-row"><span>SYNTHETIC BASELINE</span><span class="mono-stat">35.0 cm (slide mic)</span></div>
            <div class="metric-row"><span>ROLLING BUFFER</span><span class="mono-stat">20 aperture bins</span></div>
        `;
    }

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: "SET_MODE", mode: currentMode }));
    }
    drawGridOverlay(currentMode);
}

btnModeStereo.addEventListener('click', () => setOperatingMode("stereo"));
btnModeMono.addEventListener('click', () => setOperatingMode("mono"));

function connect() {
    socket = new WebSocket('ws://localhost:8000/ws/sonar');
    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
        statusPip.classList.add('online');
        connectBtn.textContent = 'DISCONNECT';
        socket.send(JSON.stringify({ action: "SET_MODE", mode: currentMode }));
        drawGridOverlay(currentMode);
    };

    socket.onmessage = (event) => {
        const buffer = event.data;
        const meta = new Uint32Array(buffer, 0, 4);
        const gridW = meta[0];
        const gridH = meta[1];
        const ascanLen = meta[2];
        const activeModeCode = meta[3];
        const activeMode = activeModeCode === 2 ? "stereo" : "mono";

        const ascanData = new Float32Array(buffer, 16, ascanLen);
        const image2dData = new Float32Array(buffer, 16 + ascanLen * 4, gridW * gridH);

        drawAScan(ascanData);
        renderSpatialField(gridW, gridH, image2dData, activeMode);
        updateFPS();
    };

    socket.onclose = () => {
        statusPip.classList.remove('online');
        connectBtn.textContent = 'CONNECT';
    };
}

connectBtn.addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
    } else {
        connect();
    }
});

drawGridOverlay(currentMode);