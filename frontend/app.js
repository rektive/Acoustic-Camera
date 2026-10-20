const ascanCanvas = document.getElementById('ascanCanvas');
const ascanCtx = ascanCanvas.getContext('2d');

const waterfallCanvas = document.getElementById('waterfallCanvas');
const wfCtx = waterfallCanvas.getContext('2d');

const toggleBtn = document.getElementById('toggleBtn');
const connStatus = document.getElementById('connStatus');
const peakReadout = document.getElementById('peakReadout');

let socket = null;
const MAX_RANGE_M = 2.5;

// Turbo/Inferno Thermal Look-Up Table
function getThermalColor(val) {
    val = Math.max(0, Math.min(1, val));
    let r, g, b;
    if (val < 0.25) {
        // Black to Blue
        r = 0;
        g = Math.floor(val * 4 * 80);
        b = Math.floor(val * 4 * 255);
    } else if (val < 0.5) {
        // Blue to Cyan/Green
        r = 0;
        g = Math.floor(80 + (val - 0.25) * 4 * 175);
        b = Math.floor(255 - (val - 0.25) * 4 * 100);
    } else if (val < 0.75) {
        // Green to Orange/Yellow
        r = Math.floor((val - 0.5) * 4 * 255);
        g = 255;
        b = 0;
    } else {
        // Yellow to White Hot
        r = 255;
        g = Math.floor(255 - (val - 0.75) * 4 * 155);
        b = Math.floor((val - 0.75) * 4 * 255);
    }
    return [r, g, b];
}

function drawAScan(data) {
    const w = ascanCanvas.width;
    const h = ascanCanvas.height;

    ascanCtx.fillStyle = '#030609';
    ascanCtx.fillRect(0, 0, w, h);

    // Grid lines for distance markers (every 0.5 meters)
    ascanCtx.strokeStyle = '#0e2233';
    ascanCtx.lineWidth = 1;
    ascanCtx.fillStyle = '#3a6688';
    ascanCtx.font = '10px monospace';

    for (let d = 0.5; d <= MAX_RANGE_M; d += 0.5) {
        const x = (d / MAX_RANGE_M) * w;
        ascanCtx.beginPath();
        ascanCtx.moveTo(x, 0);
        ascanCtx.lineTo(x, h);
        ascanCtx.stroke();
        ascanCtx.fillText(`${d.toFixed(1)}m`, x + 4, 14);
    }

    // Plot A-Scan line
    ascanCtx.strokeStyle = '#00f0ff';
    ascanCtx.lineWidth = 2;
    ascanCtx.beginPath();

    let maxVal = 0;
    let maxIdx = 0;

    for (let i = 0; i < data.length; i++) {
        const val = data[i];
        const x = (i / (data.length - 1)) * w;
        const y = h - val * (h - 25) - 5;

        if (i === 0) ascanCtx.moveTo(x, y);
        else ascanCtx.lineTo(x, y);

        if (val > maxVal) {
            maxVal = val;
            maxIdx = i;
        }
    }
    ascanCtx.stroke();

    // Peak distance calculation
    if (maxVal > 0.15) {
        const peakDist = (maxIdx / (data.length - 1)) * MAX_RANGE_M;
        peakReadout.textContent = `PEAK: ${peakDist.toFixed(2)}m (${Math.round(maxVal * 100)}%)`;
        peakReadout.style.color = '#00ffaa';
    } else {
        peakReadout.textContent = `NO TARGET`;
        peakReadout.style.color = '#4a779d';
    }
}

function updateWaterfall(data) {
    const w = waterfallCanvas.width;
    const h = waterfallCanvas.height;

    // Shift existing waterfall canvas down by 2 pixels
    wfCtx.drawImage(waterfallCanvas, 0, 0, w, h - 2, 0, 2, w, h - 2);

    // Draw the latest scan line at the top
    const imgData = wfCtx.createImageData(w, 2);
    for (let x = 0; x < w; x++) {
        const dataIdx = Math.floor((x / w) * data.length);
        const val = data[dataIdx];
        const [r, g, b] = getThermalColor(val);

        // 2-pixel row
        for (let row = 0; row < 2; row++) {
            const pixelIdx = (row * w + x) * 4;
            imgData.data[pixelIdx + 0] = r;
            imgData.data[pixelIdx + 1] = g;
            imgData.data[pixelIdx + 2] = b;
            imgData.data[pixelIdx + 3] = 255;
        }
    }
    wfCtx.putImageData(imgData, 0, 0);
}

function connect() {
    socket = new WebSocket('ws://localhost:8000/ws/sonar');
    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
        connStatus.textContent = 'ONLINE (STREAMING)';
        connStatus.className = 'status-online';
        toggleBtn.textContent = 'DISCONNECT';
    };

    socket.onmessage = (event) => {
        // Parse raw Float32 array from WebSocket binary buffer
        const floatData = new Float32Array(event.data);
        drawAScan(floatData);
        updateWaterfall(floatData);
    };

    socket.onclose = () => {
        connStatus.textContent = 'DISCONNECTED';
        connStatus.className = 'status-offline';
        toggleBtn.textContent = 'RECONNECT';
    };
}

toggleBtn.addEventListener('click', () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
    } else {
        connect();
    }
});