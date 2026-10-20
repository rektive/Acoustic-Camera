// frontend/app.js
const image2dCanvas = document.getElementById('image2dCanvas');
const imgCtx = image2dCanvas.getContext('2d');

const ascanCanvas = document.getElementById('ascanCanvas');
const ascanCtx = ascanCanvas.getContext('2d');

const connectBtn = document.getElementById('connectBtn');
const connStatus = document.getElementById('connStatus');
const fpsReadout = document.getElementById('fpsReadout');

let socket = null;
let lastFrameTime = performance.now();
let frameCount = 0;

// Thermal colormap (Black -> Blue -> Cyan -> Yellow -> Red -> White)
function getThermalColor(val) {
    val = Math.max(0, Math.min(1, val));
    let r, g, b;
    if (val < 0.2) {
        r = 0; g = 0; b = Math.floor(val * 5 * 180);
    } else if (val < 0.4) {
        r = 0; g = Math.floor((val - 0.2) * 5 * 255); b = 255;
    } else if (val < 0.7) {
        r = Math.floor((val - 0.4) * 3.33 * 255); g = 255; b = Math.floor(255 - (val - 0.4) * 3.33 * 255);
    } else if (val < 0.9) {
        r = 255; g = Math.floor(255 - (val - 0.7) * 5 * 200); b = 0;
    } else {
        r = 255; g = 255; b = Math.floor((val - 0.9) * 10 * 255);
    }
    return [r, g, b];
}

function drawGridOverlay() {
    const w = image2dCanvas.width;
    const h = image2dCanvas.height;

    imgCtx.strokeStyle = 'rgba(0, 240, 255, 0.15)';
    imgCtx.lineWidth = 1;
    imgCtx.fillStyle = '#4a779d';
    imgCtx.font = '10px monospace';

    // Depth markers (Y: 0.2m to 2.0m)
    for (let d = 0.5; d <= 2.0; d += 0.5) {
        const y = h - ((d - 0.2) / 1.8) * h;
        imgCtx.beginPath();
        imgCtx.moveTo(0, y);
        imgCtx.lineTo(w, y);
        imgCtx.stroke();
        imgCtx.fillText(`Y = ${d.toFixed(1)}m`, 10, y - 4);
    }

    // Horizontal markers (X: -0.8m to +0.8m)
    for (let x_m = -0.6; x_m <= 0.6; x_m += 0.3) {
        const x = ((x_m + 0.8) / 1.6) * w;
        imgCtx.beginPath();
        imgCtx.moveTo(x, 0);
        imgCtx.lineTo(x, h);
        imgCtx.stroke();
        imgCtx.fillText(`${x_m > 0 ? '+' : ''}${x_m.toFixed(1)}m`, x + 3, h - 8);
    }

    // Sensor baseline indicator
    imgCtx.strokeStyle = '#00ffaa';
    imgCtx.lineWidth = 3;
    const trackStart = ((-0.2 + 0.8) / 1.6) * w;
    const trackEnd = ((0.2 + 0.8) / 1.6) * w;
    imgCtx.beginPath();
    imgCtx.moveTo(trackStart, h - 2);
    imgCtx.lineTo(trackEnd, h - 2);
    imgCtx.stroke();
    imgCtx.fillStyle = '#00ffaa';
    imgCtx.fillText('BASELINE (40cm)', trackStart + 10, h - 10);
}

function renderLive2D(gridWidth, gridHeight, flatData) {
    const w = image2dCanvas.width;
    const h = image2dCanvas.height;

    const offscreen = document.createElement('canvas');
    offscreen.width = gridWidth;
    offscreen.height = gridHeight;
    const offCtx = offscreen.getContext('2d');
    const imgData = offCtx.createImageData(gridWidth, gridHeight);

    for (let y = 0; y < gridHeight; y++) {
        for (let x = 0; x < gridWidth; x++) {
            const srcIdx = (gridHeight - 1 - y) * gridWidth + x;
            const val = flatData[srcIdx];
            const [r, g, b] = getThermalColor(val);

            const dstIdx = (y * gridWidth + x) * 4;
            imgData.data[dstIdx + 0] = r;
            imgData.data[dstIdx + 1] = g;
            imgData.data[dstIdx + 2] = b;
            imgData.data[dstIdx + 3] = val > 0.05 ? 255 : 0;
        }
    }

    offCtx.putImageData(imgData, 0, 0);

    imgCtx.fillStyle = '#020406';
    imgCtx.fillRect(0, 0, w, h);
    imgCtx.imageSmoothingEnabled = true;
    imgCtx.drawImage(offscreen, 0, 0, w, h);

    drawGridOverlay();
}

function drawAScan(data) {
    const w = ascanCanvas.width;
    const h = ascanCanvas.height;

    ascanCtx.fillStyle = '#020406';
    ascanCtx.fillRect(0, 0, w, h);

    ascanCtx.strokeStyle = '#00f0ff';
    ascanCtx.lineWidth = 1.5;
    ascanCtx.beginPath();

    for (let i = 0; i < data.length; i++) {
        const val = data[i];
        const x = (i / (data.length - 1)) * w;
        const y = h - val * (h - 15) - 3;
        if (i === 0) ascanCtx.moveTo(x, y);
        else ascanCtx.lineTo(x, y);
    }
    ascanCtx.stroke();
}

function updateFPS() {
    frameCount++;
    const now = performance.now();
    if (now - lastFrameTime >= 1000) {
        fpsReadout.textContent = `${frameCount} FPS`;
        frameCount = 0;
        lastFrameTime = now;
    }
}

function connect() {
    socket = new WebSocket('ws://localhost:8000/ws/sonar');
    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
        connStatus.textContent = 'ONLINE (STREAMING)';
        connStatus.className = 'status-online';
        connectBtn.textContent = 'DISCONNECT';
        drawGridOverlay();
    };

    socket.onmessage = (event) => {
        const buffer = event.data;
        const meta = new Uint32Array(buffer, 0, 4);
        const gridW = meta[0];
        const gridH = meta[1];
        const ascanLen = meta[2];

        // Zero-copy Float32Array slicing aligned to 4 bytes
        const ascanData = new Float32Array(buffer, 16, ascanLen);
        const image2dData = new Float32Array(buffer, 16 + ascanLen * 4, gridW * gridH);

        drawAScan(ascanData);
        renderLive2D(gridW, gridH, image2dData);
        updateFPS();
    };

    socket.onclose = () => {
        connStatus.textContent = 'DISCONNECTED';
        connStatus.className = 'status-offline';
        connectBtn.textContent = 'CONNECT SENSORS';
    };
}

connectBtn.addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
    } else {
        connect();
    }
});

drawGridOverlay();