/**
 * Camera Livestream Viewer
 *
 * WebRTC client for viewing camera streams.
 * Handles signaling, ICE candidates, and video playback.
 */

// Auto-detect server URLs based on current hostname
function getServerUrls() {
    const hostname = window.location.hostname;
    const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';

    if (isLocal) {
        return {
            apiUrl: 'http://localhost:8080',
            signalingUrl: 'ws://localhost:8765'
        };
    } else {
        // Remote access - use same hostname as current page
        return {
            apiUrl: `http://${hostname}:8080`,
            signalingUrl: `ws://${hostname}:8765`
        };
    }
}

// Configuration
const serverUrls = getServerUrls();
const CONFIG = {
    // Camera ID - update this to your camera ID or pass via URL param
    cameraId: new URLSearchParams(window.location.search).get('camera') || '56C1CADCF1FA4C6CAEBA3E2FD85EFEBF',

    // API server (auto-detected)
    apiUrl: serverUrls.apiUrl,

    // Signaling server (auto-detected)
    signalingUrl: serverUrls.signalingUrl,

    // STUN servers for ICE (enables remote viewing via NAT traversal)
    stunServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' }
    ],

    // ICE filtering
    // NOTE: Disabled for localhost connections - mDNS candidates are needed for Podman
    filterMdns: false  // Allow .local candidates for localhost Kurento
};

// Global state
let webSocket = null;
let peerConnection = null;
let videoElement = null;
let streamId = null;
let viewerId = null;

// UI elements
let startBtn, stopBtn, videoOverlay;
let cameraIdEl, connectionStatusEl, streamStateEl, iceStateEl;
let logsEl;

/**
 * Initialize viewer on page load
 */
window.addEventListener('DOMContentLoaded', () => {
    // Get UI elements
    videoElement = document.getElementById('video');
    videoOverlay = document.getElementById('videoOverlay');
    startBtn = document.getElementById('startBtn');
    stopBtn = document.getElementById('stopBtn');
    cameraIdEl = document.getElementById('cameraId');
    connectionStatusEl = document.getElementById('connectionStatus');
    streamStateEl = document.getElementById('streamState');
    iceStateEl = document.getElementById('iceState');
    logsEl = document.getElementById('logs');

    // Set camera ID
    cameraIdEl.textContent = CONFIG.cameraId.substring(0, 8) + '...';

    // Setup event listeners
    startBtn.addEventListener('click', startStream);
    stopBtn.addEventListener('click', stopStream);

    log('Viewer initialized', 'info');
    log(`Camera ID: ${CONFIG.cameraId}`, 'info');
});

/**
 * Start camera stream
 */
async function startStream() {
    try {
        log('Starting stream...', 'info');
        updateStatus('connecting', 'Starting...');
        startBtn.disabled = true;

        // Step 1: Check if stream already exists
        log('Checking stream status...', 'info');
        const statusResponse = await fetch(`${CONFIG.apiUrl}/streams/${CONFIG.cameraId}`);

        if (statusResponse.ok) {
            // Stream already active - use existing stream
            const existingStream = await statusResponse.json();
            streamId = existingStream.stream.stream_id;
            log(`Stream already active (${existingStream.stream.session_id}), connecting to existing stream...`, 'info');
            streamStateEl.textContent = existingStream.stream.state;
        } else {
            // Stream not active - start new stream
            log('Requesting stream start from API server...', 'info');
            const response = await fetch(`${CONFIG.apiUrl}/streams/${CONFIG.cameraId}/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to start stream');
            }

            const streamInfo = await response.json();
            streamId = streamInfo.stream_id;

            log(`✅ Stream started: ${streamInfo.session_id}`, 'success');
            streamStateEl.textContent = streamInfo.state;
        }

        // Step 2: Connect to signaling server
        log('Connecting to signaling server...', 'info');
        await connectSignaling();

        // Step 3: Setup WebRTC
        log('Setting up WebRTC...', 'info');
        await setupWebRTC();

        stopBtn.disabled = false;

    } catch (error) {
        log(`❌ Error starting stream: ${error.message}`, 'error');
        updateStatus('disconnected', 'Error');
        startBtn.disabled = false;
        cleanup();
    }
}

/**
 * Stop camera stream
 *
 * This stops the camera from streaming and stops all keepalive messages.
 * The camera will receive a stop command via MQTT.
 */
async function stopStream() {
    try {
        log('Stopping stream...', 'info');
        stopBtn.disabled = true;

        // Step 1: Close viewer's WebSocket connection (stop receiving from Kurento)
        if (webSocket && webSocket.readyState === WebSocket.OPEN) {
            log('Closing signaling connection...', 'info');
            webSocket.send(JSON.stringify({ type: 'stop' }));
        }

        // Step 2: Stop the camera stream on API server
        // This will:
        // - Stop keepalive messages to camera
        // - Send stop command to camera via MQTT
        // - Release Kurento resources (pipeline, endpoints)
        log('Sending stop command to API server...', 'info');
        const response = await fetch(`${CONFIG.apiUrl}/streams/${CONFIG.cameraId}/stop`, {
            method: 'POST'
        });

        if (response.ok) {
            const result = await response.json();
            log(`✅ Stream stopped successfully`, 'success');
            log(`Duration: ${result.duration_seconds}s, Keepalives sent: ${result.keepalive_stats?.keepalive_count || 0}`, 'info');
        } else {
            const error = await response.json();
            log(`⚠️ Error stopping stream: ${error.error}`, 'warning');
        }

    } catch (error) {
        log(`⚠️ Error stopping stream: ${error.message}`, 'warning');
    } finally {
        // Clean up viewer resources
        cleanup();
        updateStatus('disconnected', 'Stopped');
        streamStateEl.textContent = 'stopped';
        startBtn.disabled = false;
        stopBtn.disabled = true;
    }
}

/**
 * Connect to signaling server via WebSocket
 */
function connectSignaling() {
    return new Promise((resolve, reject) => {
        webSocket = new WebSocket(CONFIG.signalingUrl);

        webSocket.onopen = () => {
            log('✅ Connected to signaling server', 'success');
            updateStatus('connected', 'Connected');
            resolve();
        };

        webSocket.onerror = (error) => {
            log(`❌ WebSocket error: ${error.message || 'Connection failed'}`, 'error');
            reject(new Error('WebSocket connection failed'));
        };

        webSocket.onclose = () => {
            log('WebSocket closed', 'info');
            updateStatus('disconnected', 'Disconnected');
        };

        webSocket.onmessage = handleSignalingMessage;
    });
}

/**
 * Setup WebRTC peer connection
 */
async function setupWebRTC() {
    try {
        // Create peer connection
        peerConnection = new RTCPeerConnection({
            iceServers: CONFIG.stunServers
        });

        log('WebRTC peer connection created', 'info');

        // Setup event handlers
        peerConnection.ontrack = (event) => {
            log('📺 Received media track', 'success');
            videoElement.srcObject = event.streams[0];
            videoOverlay.classList.add('hidden');
        };

        peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                const candidate = event.candidate;

                // Filter mDNS candidates if enabled
                if (CONFIG.filterMdns && candidate.address && candidate.address.endsWith('.local')) {
                    log('🔍 Filtered mDNS candidate (.local)', 'info');
                    return;
                }

                log('🧊 Sending ICE candidate', 'info');

                // Send to signaling server
                webSocket.send(JSON.stringify({
                    type: 'onIceCandidate',
                    candidate: {
                        candidate: candidate.candidate,
                        sdpMid: candidate.sdpMid,
                        sdpMLineIndex: candidate.sdpMLineIndex
                    }
                }));
            } else {
                log('🧊 ICE gathering complete', 'info');
            }
        };

        peerConnection.oniceconnectionstatechange = () => {
            const state = peerConnection.iceConnectionState;
            log(`🧊 ICE connection state: ${state}`, 'info');
            iceStateEl.textContent = state;

            if (state === 'failed' || state === 'disconnected') {
                log('❌ ICE connection failed', 'error');
                updateStatus('disconnected', 'Connection Failed');
            }
        };

        peerConnection.onconnectionstatechange = () => {
            const state = peerConnection.connectionState;
            log(`🔗 Connection state: ${state}`, 'info');

            if (state === 'connected') {
                log('✅ WebRTC connection established', 'success');
                updateStatus('connected', 'Streaming');
            } else if (state === 'failed') {
                log('❌ WebRTC connection failed', 'error');
                updateStatus('disconnected', 'Connection Failed');
            }
        };

        // Create SDP offer
        log('Creating SDP offer...', 'info');
        const offer = await peerConnection.createOffer({
            offerToReceiveAudio: true,
            offerToReceiveVideo: true
        });

        await peerConnection.setLocalDescription(offer);
        log('✅ Local description set', 'success');

        // Send viewer request with SDP offer
        log('Sending viewer request...', 'info');
        webSocket.send(JSON.stringify({
            type: 'viewer',
            cameraId: CONFIG.cameraId,
            streamId: streamId,
            sdpOffer: offer.sdp
        }));

    } catch (error) {
        log(`❌ WebRTC setup error: ${error.message}`, 'error');
        throw error;
    }
}

/**
 * Handle signaling messages from server
 */
async function handleSignalingMessage(event) {
    try {
        const message = JSON.parse(event.data);

        switch (message.type) {
            case 'viewerResponse':
                await handleViewerResponse(message);
                break;

            case 'iceCandidate':
                await handleIceCandidate(message);
                break;

            case 'error':
                log(`❌ Server error: ${message.message}`, 'error');
                updateStatus('disconnected', 'Error');
                break;

            default:
                log(`⚠️ Unknown message type: ${message.type}`, 'warning');
        }

    } catch (error) {
        log(`❌ Error handling message: ${error.message}`, 'error');
    }
}

/**
 * Handle viewer response with SDP answer
 */
async function handleViewerResponse(message) {
    try {
        viewerId = message.viewerId;
        log(`✅ Viewer response received (ID: ${viewerId.substring(0, 8)}...)`, 'success');

        // Set remote description (SDP answer)
        const answer = new RTCSessionDescription({
            type: 'answer',
            sdp: message.sdpAnswer
        });

        await peerConnection.setRemoteDescription(answer);
        log('✅ Remote description set', 'success');

    } catch (error) {
        log(`❌ Error handling viewer response: ${error.message}`, 'error');
        throw error;
    }
}

/**
 * Handle ICE candidate from server
 */
async function handleIceCandidate(message) {
    try {
        const candidate = new RTCIceCandidate(message.candidate);

        // Filter mDNS candidates if enabled
        if (CONFIG.filterMdns && candidate.address && candidate.address.endsWith('.local')) {
            log('🔍 Filtered mDNS candidate from server (.local)', 'info');
            return;
        }

        await peerConnection.addIceCandidate(candidate);
        log('🧊 Added ICE candidate from server', 'info');

    } catch (error) {
        log(`⚠️ Error adding ICE candidate: ${error.message}`, 'warning');
    }
}

/**
 * Cleanup resources
 */
function cleanup() {
    log('Cleaning up resources...', 'info');

    // Close peer connection
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }

    // Close WebSocket
    if (webSocket) {
        webSocket.close();
        webSocket = null;
    }

    // Clear video
    if (videoElement) {
        videoElement.srcObject = null;
    }

    // Show overlay
    videoOverlay.classList.remove('hidden');
    videoOverlay.textContent = 'Waiting to connect...';

    // Reset state
    streamId = null;
    viewerId = null;
    iceStateEl.textContent = '-';
}

/**
 * Update connection status display
 */
function updateStatus(status, text) {
    connectionStatusEl.textContent = text;
    connectionStatusEl.className = 'status-value';

    switch (status) {
        case 'connected':
            connectionStatusEl.classList.add('status-connected');
            break;
        case 'connecting':
            connectionStatusEl.classList.add('status-connecting');
            break;
        case 'disconnected':
            connectionStatusEl.classList.add('status-disconnected');
            break;
    }
}

/**
 * Log message to console and UI
 */
function log(message, level = 'info') {
    // Console log
    console[level === 'error' ? 'error' : level === 'warning' ? 'warn' : 'log'](message);

    // UI log
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry log-${level}`;
    entry.innerHTML = `<span class="log-time">${time}</span>${message}`;

    logsEl.insertBefore(entry, logsEl.firstChild);

    // Limit log entries
    while (logsEl.children.length > 100) {
        logsEl.removeChild(logsEl.lastChild);
    }
}

/**
 * Handle errors
 */
window.addEventListener('error', (event) => {
    log(`❌ Uncaught error: ${event.message}`, 'error');
});

window.addEventListener('unhandledrejection', (event) => {
    log(`❌ Unhandled promise rejection: ${event.reason}`, 'error');
});
