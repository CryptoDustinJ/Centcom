/**
 * Dashboard Usage Tracker
 * Automatically tracks view duration, heartbeats, and interactions.
 *
 * Usage: <script src="/static/js/tracking.js"></script>
 *        <script>DashboardTracker.init({room: 'serverroom'});</script>
 */
const DashboardTracker = (function() {
    let room = null;
    let agent = null;
    let startTime = null;
    let heartbeatInterval = null;
    let sessionId = null;
    let interactions = 0;

    // Try to determine agent from page context or query param
    function detectAgent() {
        // Check URL param: ?agent=Rook
        const urlParams = new URLSearchParams(window.location.search);
        const paramAgent = urlParams.get('agent');
        if (paramAgent) return paramAgent;

        // Check for agent in localStorage (persists across visits)
        const stored = localStorage.getItem('office_agent');
        if (stored) return stored;

        // Default: could be set by server-side templating
        return null;
    }

    function sendEvent(type, extra = {}) {
        if (!room) return;

        const payload = {
            room: room,
            agent: agent || 'anonymous',
            timestamp: new Date().toISOString(),
            event_type: type,
            session_id: sessionId,
            ...extra
        };

        navigator.sendBeacon ? navigator.sendBeacon('/growth/track-view', JSON.stringify(payload)) :
            fetch('/growth/track-view', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
                keepalive: true
            }).catch(() => {}); // Ignore errors
    }

    function startSession() {
        sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        startTime = Date.now();
        sendEvent('session_start');
    }

    function endSession() {
        if (!startTime) return;
        const duration = Math.floor((Date.now() - startTime) / 1000);
        sendEvent('session_end', {duration_seconds: duration, interactions: interactions});
        if (heartbeatInterval) {
            clearInterval(heartbeatInterval);
            heartbeatInterval = null;
        }
        startTime = null;
    }

    function setupHeartbeat() {
        // Send heartbeat every 30 seconds to indicate active viewing
        heartbeatInterval = setInterval(() => {
            if (startTime) {
                sendEvent('heartbeat', {duration_seconds: Math.floor((Date.now() - startTime) / 1000)});
            }
        }, 30000);
    }

    function trackInteraction() {
        interactions++;
    }

    function init(options = {}) {
        room = options.room || room;
        agent = options.agent || detectAgent();

        if (!room) {
            console.warn('DashboardTracker: room not specified');
            return;
        }

        if (agent) {
            localStorage.setItem('office_agent', agent);
        }

        startSession();
        setupHeartbeat();

        // Track common interactions
        document.addEventListener('click', trackInteraction, {passive: true});
        document.addEventListener('keydown', trackInteraction, {passive: true});

        // End session on page unload
        window.addEventListener('beforeunload', endSession);
        window.addEventListener('unload', endSession);

        console.log(`DashboardTracker started for room: ${room}, agent: ${agent || 'anonymous'}`);
    }

    // Expose public API
    return {
        init: init,
        trackEvent: (eventName, data = {}) => sendEvent('custom_event', {event_name: eventName, ...data}),
        trackClick: (element) => { interactions++; },
    };
})();

// Auto-init if data-room attribute is present on <body>
document.addEventListener('DOMContentLoaded', function() {
    if (document.body.dataset && document.body.dataset.room) {
        DashboardTracker.init({
            room: document.body.dataset.room,
            agent: document.body.dataset.agent || null
        });
    }
});