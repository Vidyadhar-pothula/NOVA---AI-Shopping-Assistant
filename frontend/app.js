/**
 * NOVA — Personal AI Commerce Agent
 * Frontend Application Logic
 *
 * Payment flow:
 *   1. Agent calls create_order  →  order panel appears
 *   2. User clicks "Pay with Razorpay"
 *   3. We call GET /api/payment/config to get the key_id
 *   4. We call POST /api/payment/create-order to mint a Razorpay order
 *   5. We open the Razorpay Checkout modal (or simulate in demo mode)
 *   6. On payment success we call POST /api/payment/verify
 *   7. Show the success overlay
 */

// ── Session Setup ───────────────────────────────────────────────────────────
const SESSION_STORAGE_KEY = 'nova_authoritative_session_id';
const SHARED_NOVA_SESSION_ID = 'nova_authoritative_cart';
let sessionId = localStorage.getItem(SESSION_STORAGE_KEY) || SHARED_NOVA_SESSION_ID;
localStorage.setItem(SESSION_STORAGE_KEY, sessionId);

// ── DOM References ──────────────────────────────────────────────────────────
const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const voiceBtn = document.getElementById('voice-btn');
const voiceStatus = document.getElementById('voice-status');
const voiceModeBtn = document.getElementById('voice-mode-btn');
const voiceFab = document.getElementById('voice-fab');
const voiceOverlay = document.getElementById('voice-overlay');
const voiceCloseBtn = document.getElementById('voice-close-btn');
const voiceStartBtn = document.getElementById('voice-start-btn');
const voiceStopBtn = document.getElementById('voice-stop-btn');
const voiceModeStatus = document.getElementById('voice-mode-status');
const voiceTranscript = document.getElementById('voice-transcript');
const voiceOrb = document.getElementById('voice-orb');
const cartItemsContainer = document.getElementById('cart-items');
const cartTotalEl = document.getElementById('cart-total');
const cartCountBadge = document.getElementById('cart-count-badge');
const agentLogsContainer = document.getElementById('agent-logs');
const orderPanel = document.getElementById('order-panel');
const orderDetails = document.getElementById('order-details');
const orderStatusBadge = document.getElementById('order-status-badge');
const paymentBtn = document.getElementById('payment-btn');
const paymentDemoNote = document.getElementById('payment-demo-note');
const clearSessionBtn = document.getElementById('clear-session-btn');
const clearLogsBtn = document.getElementById('clear-logs-btn');
const statusPill = document.getElementById('status-pill');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const sessionIdVal = document.getElementById('session-id-val');
const suggestionChips = document.getElementById('suggestion-chips');
const paymentOverlay = document.getElementById('payment-overlay');
const paymentSuccessMsg = document.getElementById('payment-success-msg');
const paymentSuccessMeta = document.getElementById('payment-success-meta');
const paymentCloseBtn = document.getElementById('payment-close-btn');

// ── State & Market ──────────────────────────────────────────────────────────
let activeOrder = null;   // Our internal order object
let razorpayKeyId = null;   // Loaded from backend
let isThinking = false;
let currentMarket = { country_code: 'IN', currency_code: 'INR' };
let voiceEnabled = false;
let voiceCommandPending = false;
let recognition = null;
let restartingVoice = false;
let silenceTimer = null;
let isSpeakingTTS = false;
let lastSpokenTranscript = '';

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

// Warm up SpeechSynthesis voices
if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices();
    };
}

const marketSelect = document.getElementById('market-select');
const marketFlag = document.getElementById('market-flag');

const MARKET_FLAGS = {
    'IN': '🇮🇳',
    'US': '🇺🇸',
    'GB': '🇬🇧',
    'GLOBAL': '🌍'
};

// ── Initialise ──────────────────────────────────────────────────────────────
(async function init() {
    if (sessionIdVal) sessionIdVal.textContent = sessionId;

    // 1. Show welcome message immediately
    appendWelcomeMessage();

    // 2. Check backend connection immediately & set NOVA Online
    await checkBackendStatus();

    // 3. Detect market location & load cart asynchronously
    detectMarketLocation();
    fetchCart();
})();

// Market Dropdown Handler
if (marketSelect) {
    marketSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        currentMarket.country_code = val;
        currentMarket.currency_code = val === 'US' ? 'USD' : val === 'GB' ? 'GBP' : val === 'GLOBAL' ? 'USD' : 'INR';
        if (marketFlag) marketFlag.textContent = MARKET_FLAGS[val] || '🌍';
        console.log('🛍️ Market changed to:', currentMarket);
    });
}

// Market Detection Helper
async function detectMarketLocation() {
    try {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
        const res = await fetch(`/api/market/detect?timezone=${encodeURIComponent(tz)}`);
        if (res.ok) {
            const data = await res.json();
            currentMarket.country_code = data.country_code || 'IN';
            currentMarket.currency_code = data.currency_code || 'INR';
            if (marketSelect) marketSelect.value = currentMarket.country_code;
            if (marketFlag) marketFlag.textContent = MARKET_FLAGS[currentMarket.country_code] || '🇮🇳';
        }
    } catch (e) {
        console.warn('Market detection fallback to default:', e);
    }
}

// ── Backend Health Check ────────────────────────────────────────────────────
async function checkBackendStatus() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 4000);
        const res = await fetch('/api/payment/config', { signal: controller.signal });
        clearTimeout(timeoutId);
        if (res.ok) {
            const data = await res.json();
            razorpayKeyId = data.key_id;
            setStatus('online', 'NOVA Online');
        } else {
            setStatus('online', 'NOVA Online');
        }
    } catch (e) {
        console.warn('Health check fallback:', e);
        setStatus('online', 'NOVA Online');
    }
}

function setStatus(state, label) {
    if (statusText) statusText.textContent = label;
    if (statusPill) statusPill.className = `status-pill ${state}`;
}


// ── Welcome Message ─────────────────────────────────────────────────────────
function appendWelcomeMessage() {
    const el = document.createElement('div');
    el.className = 'message nova';
    el.innerHTML = `
        <div class="msg-meta">
            <span class="msg-avatar">N</span>
            <span>NOVA</span>
        </div>
        <div class="message-content">
             Hi! I'm <strong>NOVA</strong>, your Personal AI Commerce Agent.<br><br>
            I can help you <strong>search products</strong>, <strong>compare prices</strong> across stores,
            <strong>manage your cart</strong>, and <strong>place orders</strong> — all through natural language.<br><br>
            Tell me what you're shopping for, what matters to you, or where you're stuck choosing.
        </div>
    `;
    chatMessages.appendChild(el);
}

// ── Chat Form Submission ────────────────────────────────────────────────────
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message || isThinking) return;

    // Hide suggestion chips once user starts chatting
    if (suggestionChips) suggestionChips.style.display = 'none';

    // Client-side quick action intent matching for immediate UI response
    const msgLower = message.toLowerCase().trim();
    if (/\b(?:move|switch|go|open|take me)\s+(?:to\s+)?discover\s*(?:mode)?\b/i.test(msgLower) || /\bdiscover\s+mode\b/i.test(msgLower)) {
        switchWorkspaceTab('view-discover');
    } else if (/\b(?:move|switch|go|open|take me)\s+(?:to\s+)?settings\s*(?:mode)?\b/i.test(msgLower) || /\bsettings\s+mode\b/i.test(msgLower)) {
        switchWorkspaceTab('view-settings');
    } else if (/\b(?:move|switch|go|open|take me)\s+(?:to\s+)?chat\s*(?:mode)?\b/i.test(msgLower) || /\bchat\s+mode\b/i.test(msgLower)) {
        switchWorkspaceTab('view-chat');
    }

    appendMessage('user', message);
    chatInput.value = '';
    setThinking(true);

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, message, market: currentMarket })
        });

        const data = await res.json();
        setThinking(false);

        if (data.response) {
            // Always prefer the structured response (may come alongside an error)
            renderNOVAResponse(data);
            if (voiceCommandPending) speakNOVAResponse(data.response);
        } else if (data.error) {
            // Internal technical error — show a friendly version, not the raw stack
            const friendly = data.error.includes('Ollama') || data.error.includes('model output')
                ? "⚠️ I'm having trouble connecting to my AI engine right now. Please try again in a moment."
                : `⚠️ ${data.error}`;
            appendMessage('nova', friendly);
            if (voiceCommandPending) speakNOVAResponse(friendly);
        }
        voiceCommandPending = false;

        await fetchCart();

    } catch (err) {
        setThinking(false);
        const errorText = ` Connection error: ${err.message}. Is the backend server running?`;
        appendMessage('nova', errorText);
        if (voiceCommandPending) speakNOVAResponse(errorText);
        voiceCommandPending = false;
        console.error(err);
    }
});

// ── Voice Mode ──────────────────────────────────────────────────────────────
if (voiceBtn) {
    voiceBtn.addEventListener('click', toggleVoiceMode);
}
if (voiceModeBtn) {
    voiceModeBtn.addEventListener('click', openVoiceAssistantMode);
}
if (voiceFab) {
    voiceFab.addEventListener('click', () => {
        openVoiceAssistantMode();
        startVoiceMode();
    });
}
if (voiceStartBtn) {
    voiceStartBtn.addEventListener('click', startVoiceMode);
}
if (voiceStopBtn) {
    voiceStopBtn.addEventListener('click', stopVoiceMode);
}
if (voiceCloseBtn) {
    voiceCloseBtn.addEventListener('click', closeVoiceAssistantMode);
}

function toggleVoiceMode() {
    if (!SpeechRecognition) {
        setVoiceStatus('Voice is not supported in this browser. Use Chrome desktop.', false);
        return;
    }
    if (voiceEnabled) {
        stopVoiceMode();
    } else {
        startVoiceMode();
    }
}

function startVoiceMode() {
    if (!SpeechRecognition) return;
    openVoiceAssistantMode();
    if (voiceEnabled && recognition) return;

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true; // Enable real-time speech feedback
    recognition.lang = 'en-IN';

    recognition.onstart = () => {
        voiceEnabled = true;
        if (voiceBtn) voiceBtn.classList.add('listening');
        if (voiceModeBtn) voiceModeBtn.classList.add('listening');
        if (voiceFab) voiceFab.classList.add('listening');
        if (voiceOrb) voiceOrb.classList.add('listening');
        if (voiceStartBtn) voiceStartBtn.textContent = 'Listening';
        setVoiceStatus('Listening... Speak your request clearly.', true);
    };

    recognition.onresult = (event) => {
        if (isThinking || isSpeakingTTS) return;

        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
            transcript += event.results[i][0].transcript;
        }
        transcript = transcript.trim();
        if (!transcript) return;

        setVoiceStatus(`Heard: ${transcript}`, true);
        setVoiceTranscript(transcript);
        lastSpokenTranscript = transcript;

        // Reset silence queue timer whenever user speaks a new word
        if (silenceTimer) clearTimeout(silenceTimer);

        // Auto-send query after 1.2 seconds of silence
        silenceTimer = setTimeout(() => {
            const finalMsg = lastSpokenTranscript.trim();
            if (!finalMsg || isThinking) return;

            let command = extractWakeCommand(finalMsg);
            if (!command) command = finalMsg;

            if (command && command.length >= 2) {
                setVoiceStatus(`Processing request...`, true);
                submitVoiceCommand(command);
            }
        }, 1200);
    };

    recognition.onerror = (event) => {
        if (event.error === 'no-speech') return; // Handled by silence queue timer
        if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
            stopVoiceMode();
            setVoiceStatus('Microphone permission was blocked. Allow mic access and try again.', false);
        } else {
            setVoiceStatus(`Voice paused: ${event.error}`, false);
        }
    };

    recognition.onend = () => {
        if (voiceEnabled && !restartingVoice && !isSpeakingTTS && !isThinking) {
            restartingVoice = true;
            setTimeout(() => {
                restartingVoice = false;
                try {
                    if (recognition && voiceEnabled) recognition.start();
                } catch (e) {
                    setVoiceStatus('Voice paused. Click the mic to start again.', false);
                }
            }, 400);
        }
    };

    try {
        recognition.start();
    } catch (e) {
        setVoiceStatus('Voice could not start. Try clicking the mic again.', false);
    }
}

function stopVoiceMode() {
    voiceEnabled = false;
    if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
    if (voiceBtn) voiceBtn.classList.remove('listening');
    if (voiceModeBtn) voiceModeBtn.classList.remove('listening');
    if (voiceFab) voiceFab.classList.remove('listening');
    if (voiceOrb) voiceOrb.classList.remove('listening');
    if (voiceStartBtn) voiceStartBtn.textContent = 'Start Voice';
    setVoiceStatus('Voice off. Click the mic, then speak.', false);
    if (recognition) {
        recognition.onend = null;
        recognition.stop();
        recognition = null;
    }
}

function extractWakeCommand(transcript) {
    const match = transcript.match(/\b(?:hey|hi|hello)\s+nova\b[:,\s-]*(.*)$/i);
    if (!match) return '';
    return match[1] && match[1].trim() ? match[1].trim() : 'How can you help me?';
}

function submitVoiceCommand(command) {
    if (!command || isThinking) return;
    if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
    voiceCommandPending = true;
    setVoiceTranscript(`Command: ${command}`);
    chatInput.value = command;
    chatForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}

function setVoiceStatus(label, active) {
    if (voiceStatus) {
        voiceStatus.textContent = label;
        voiceStatus.classList.toggle('active', active);
    }
    if (voiceModeStatus) voiceModeStatus.textContent = label;
    if (voiceBtn) voiceBtn.setAttribute('aria-pressed', active ? 'true' : 'false');
    if (voiceModeBtn) voiceModeBtn.setAttribute('aria-pressed', active ? 'true' : 'false');
}

function getFemaleVoice() {
    if (!window.speechSynthesis) return null;
    const voices = window.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) return null;

    const femalePatterns = [
        /Google UK English Female/i,
        /Google US English/i,
        /Samantha/i,
        /Victoria/i,
        /Veena/i,
        /Neerja/i,
        /Zira/i,
        /Karen/i,
        /Moira/i,
        /Fiona/i,
        /Tessa/i,
        /Serena/i,
        /Ava/i,
        /Allison/i,
        /Susan/i,
        /Female/i
    ];

    for (const pattern of femalePatterns) {
        const match = voices.find(v => pattern.test(v.name) || pattern.test(v.voiceURI));
        if (match) return match;
    }

    return voices.find(v => v.lang.startsWith('en') && (v.name.includes('Female') || v.name.includes('Natural') || v.name.includes('Google'))) || voices[0];
}

function speakNOVAResponse(text) {
    if (!window.speechSynthesis) return;
    const clean = sanitizeNOVAResponse(text).replace(/\s+/g, ' ').slice(0, 600);
    if (!clean) return;

    // Pause recognition while speaking so microphone doesn't pick up TTS audio
    isSpeakingTTS = true;
    if (recognition) {
        try { recognition.stop(); } catch (e) { }
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(clean);

    const femaleVoice = getFemaleVoice();
    if (femaleVoice) {
        utterance.voice = femaleVoice;
        utterance.lang = femaleVoice.lang;
    } else {
        utterance.lang = 'en-US';
    }

    // Warm, natural female voice pitch and conversational speed
    utterance.pitch = 1.15;
    utterance.rate = 1.04;

    utterance.onend = () => {
        isSpeakingTTS = false;
        // Resume listening automatically after speaking finishes
        if (voiceEnabled) {
            setTimeout(() => {
                try {
                    if (voiceEnabled && recognition) recognition.start();
                } catch (e) { }
            }, 400);
        }
    };

    utterance.onerror = () => {
        isSpeakingTTS = false;
    };

    window.speechSynthesis.speak(utterance);
}

function openVoiceAssistantMode() {
    if (voiceOverlay) voiceOverlay.style.display = 'flex';
    if (!SpeechRecognition) {
        setVoiceStatus('Voice is not supported in this browser. Use Chrome desktop.', false);
    }
}

function closeVoiceAssistantMode() {
    if (voiceOverlay) voiceOverlay.style.display = 'none';
}

function setVoiceTranscript(text) {
    if (voiceTranscript) voiceTranscript.textContent = text || 'Listening for "hey nova"...';
}

// ── Sanitize NOVA Response (safety net: strip raw tool-call JSON blobs) ──────
function sanitizeNOVAResponse(text) {
    if (!text) return text;
    let clean = text
        .replace(/```(?:json)?\s*\{[\s\S]*?\}\s*```/gi, '')
        .replace(/\{\s*["'](?:name|tool|function)["'][\s\S]*?(?:["']parameters["']|["']arguments["'])[\s\S]*?\}\s*/gi, '')
        .split('\n')
        .filter(line => {
            const lower = line.toLowerCase();
            return ![
                'ambiguous category noun',
                '"parameters"',
                '"arguments"',
                'search_products',
                'add_to_cart',
                'create_order',
                'compare_products',
                'compare_prices'
            ].some(marker => lower.includes(marker));
        })
        .join('\n')
        .trim();
    return clean || "I need one more detail to help with that properly. What matters most to you here: use, style, brand, size, or budget?";
}

// ── Render NOVA's Full Response ─────────────────────────────────────────────
function renderNOVAResponse(data) {
    const { response, executed_tools, payment_handoff } = data;

    // Show conversational response (sanitized to remove any leaked tool JSON)
    if (response) appendMessage('nova', sanitizeNOVAResponse(response));

    // Render tool-specific rich output
    if (executed_tools && executed_tools.length > 0) {
        appendAgentLogs(executed_tools);

        executed_tools.forEach(tool => {
            const result = tool.result;
            if (!result || result.error) return;

            // Render product search results as cards
            if (tool.name === 'search_products' && Array.isArray(result) && result.length > 0) {
                renderProductCards(result);
            }

            // Render price comparison results
            if (tool.name === 'compare_prices' && Array.isArray(result) && result.length > 0) {
                renderProductCards(result, true);
            }

            // Show order panel when an order is created — either directly via create_order
            // or via resolve_product_action single-product checkout staging pipeline.
            if (result && result.order && (tool.name === 'create_order' || tool.name === 'resolve_product_action')) {
                activeOrder = result.order;
                showOrderPanel(activeOrder);
                fetchCart();
            }

            // Handle Conversational Action Resolution, Navigation & Mode Switch
            if (tool.name === 'resolve_product_action' || tool.name === 'navigate_browser' || tool.name === 'switch_mode') {
                if (tool.name === 'switch_mode' || result.action_type === 'switch_mode') {
                    const modeName = (result.mode_name || '').toLowerCase();
                    const targetView = result.target_view
                        || (modeName.includes('discover') ? 'view-discover'
                            : modeName.includes('setting') ? 'view-settings'
                            : modeName.includes('catalog') ? 'view-catalogue'
                            : 'view-chat');
                    switchWorkspaceTab(targetView);
                } else if (result.action_type === 'open_url' && result.url) {
                    window.open(result.url, '_blank', 'noopener,noreferrer');
                } else if (result.action_type === 'checkout_confirmation_required' && !result.order) {
                    // Legacy external checkout path — only used when an order object is not present.
                    showCheckoutSafetyModal(result);
                } else if (result.action_type === 'add_to_cart') {
                    fetchCart();
                }
            }

            if (tool.name === 'inspect_catalog' && result.products) {
                renderCatalogueView(result);
                switchWorkspaceTab('view-catalogue');
            }

            // Handle Recommendation Tools
            if (tool.name === 'get_recommendations' && result.recommendations && result.recommendations.length > 0) {
                renderProductCards(result.recommendations);
            }

            // Handle Discovery Feed tool
            if (tool.name === 'get_discovery_feed') {
                if (result.feed) {
                    renderDiscoverFeedGrid(result.feed);
                    switchWorkspaceTab('view-discover');
                }
            }

            // Handle Calendar actions
            if (tool.name === 'calendar_action') {
                if (result.status === 'permission_required') {
                    switchWorkspaceTab('view-settings');
                }
            }

            // Handle Email actions
            if (tool.name === 'email_action') {
                if (result.status === 'permission_required') {
                    switchWorkspaceTab('view-settings');
                }
            }
        });
    }

    // ── Conversational Payment Handoff ─────────────────────────────────────────
    // When the agent called proceed_to_payment (after explicit "yes" confirmation),
    // the backend already created the real Razorpay order (or its deterministic
    // demo-mode equivalent) and attached the result as top-level `payment_handoff`.
    // Without this block, the conversational flow stalls after "yes" because the
    // frontend has no code path to open the Razorpay UI from the chat response.
    //
    // NOTE: We do NOT call /api/payment/create-order here. The Razorpay order was
    // already minted by proceed_to_payment on the backend — re-calling the REST
    // create-order endpoint would create a second, orphaned Razorpay order.
    if (payment_handoff && payment_handoff.razorpay_order_id && payment_handoff.success !== false) {
        // Ensure activeOrder is populated so verifyPayment() can submit internal_order_id
        if (!activeOrder || activeOrder.id !== payment_handoff.internal_order_id) {
            activeOrder = activeOrder || {};
            activeOrder.id = payment_handoff.internal_order_id;
            if (!activeOrder.items) {
                showOrderPanel({
                    id: payment_handoff.internal_order_id,
                    total_amount: payment_handoff.amount,
                    currency: payment_handoff.currency || 'INR',
                    items: []
                });
            }
        }

        const rzpPayload = {
            razorpay_order_id: payment_handoff.razorpay_order_id,
            amount: payment_handoff.amount_paise ?? Math.round((payment_handoff.amount || 0) * 100),
            currency: payment_handoff.currency || 'INR',
            demo_mode: payment_handoff.demo_mode === true
        };

        if (rzpPayload.demo_mode || !razorpayKeyId || razorpayKeyId === 'rzp_test_placeholder') {
            appendMessage('nova', 'Razorpay TEST is not configured, so the payment window cannot open. The cart is unchanged.');
        } else {
            openRazorpayCheckout(rzpPayload);
        }
    }
}

// ── Product Cards in Chat (Dual-Section Rendering) ──────────────────────────
function renderProductCards(products, isPriceComparison = false) {
    if (!products || products.length === 0) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'message nova';
    wrapper.innerHTML = `<div class="msg-meta"><span class="msg-avatar">N</span><span>NOVA</span></div>`;

    const container = document.createElement('div');
    container.className = 'message-content';

    const individualProducts = products.filter(p => p.result_type !== 'browse_list');
    const browseLists = products.filter(p => p.result_type === 'browse_list');

    // ── SECTION 1: RECOMMENDED PRODUCTS (Type A) ─────────────────────────────
    if (individualProducts.length > 0) {
        const sectionHeader = document.createElement('div');
        sectionHeader.className = 'results-section-header';
        sectionHeader.innerHTML = `<span> RECOMMENDED PRODUCTS</span><span class="section-subtitle">Verified individual listings</span>`;
        container.appendChild(sectionHeader);

        const grid = document.createElement('div');
        grid.className = 'product-grid';

        individualProducts.forEach((product, idx) => {
            const ratingStr = (product.rating !== null && product.rating !== undefined) ? `⭐ ${product.rating}` : 'Rating: N/A';
            const merchant = product.merchant_name || product.merchant || product.source_name || 'Verified Source';
            const prodUrl = product.product_url || product.product_link || '';
            const isVerified = product.is_verified !== false && !product.is_demo;

            const curr = product.currency || currentMarket.currency_code || 'INR';
            const currSym = curr === 'USD' ? '$' : curr === 'GBP' ? '£' : curr === 'EUR' ? '€' : '₹';

            // Filter favicons and merchant logos
            let imgUrl = product.image_url || (product.images && product.images.length > 0 ? product.images[0] : null);
            if (imgUrl && (imgUrl.includes('s2/favicons') || imgUrl.includes('favicon.ico') || imgUrl.includes('logo.'))) {
                imgUrl = null;
            }

            let imgHtml = '';
            if (imgUrl) {
                imgHtml = `
                    <div class="product-card-img-container">
                        <img src="${escHtml(imgUrl)}" alt="${escHtml(product.name || 'Product')}" class="product-card-img" onerror="this.parentElement.style.display='none';" />
                    </div>
                `;
            }

            const card = document.createElement('div');
            card.className = 'product-card';

            let actionBtnHtml = '';
            if (prodUrl) {
                actionBtnHtml = `
                    <a href="${escHtml(prodUrl)}" target="_blank" rel="noopener noreferrer" class="btn-view-product" onclick="event.stopPropagation();">
                        <span>View Product</span>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                    </a>
                `;
            }

            const badgeHtml = isVerified
                ? `<span class="verified-badge">✓ Verified Product</span>`
                : `<span class="product-card-source-badge">Live Source</span>`;

            card.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
                    <span class="product-card-badge">#${idx + 1}</span>
                    ${badgeHtml}
                </div>
                ${imgHtml}
                <div class="product-card-name" style="margin-top:6px;">${escHtml(product.name || product.title)}</div>
                <div class="product-card-brand">${escHtml(product.brand || '')}</div>
                <div class="product-card-price">${currSym}${Number(product.price).toLocaleString()}</div>
                <div class="product-card-meta">
                    <span class="product-card-rating">${ratingStr}</span>
                    <span class="product-card-merchant">${escHtml(merchant)}</span>
                </div>
                ${actionBtnHtml}
                <div class="product-card-index">ID: ${escHtml(product.id || '')}</div>
            `;

            if (prodUrl) {
                card.style.cursor = 'pointer';
                card.addEventListener('click', () => {
                    window.open(prodUrl, '_blank', 'noopener,noreferrer');
                });
            }

            grid.appendChild(card);
        });

        container.appendChild(grid);
    }

    // ── SECTION 2: BROWSE MORE / LISTING PAGES (Type B) ────────────────────────
    if (browseLists.length > 0) {
        const browseHeader = document.createElement('div');
        browseHeader.className = 'results-section-header';
        browseHeader.style.marginTop = individualProducts.length > 0 ? '16px' : '0';
        browseHeader.innerHTML = `<span> BROWSE MORE</span><span class="section-subtitle">Listing pages with multiple options</span>`;
        container.appendChild(browseHeader);

        const browseGrid = document.createElement('div');
        browseGrid.className = 'browse-grid';

        browseLists.forEach((listProduct) => {
            const merchant = listProduct.merchant_name || listProduct.merchant || 'Merchant Listing';
            const url = listProduct.product_url || '';

            const card = document.createElement('div');
            card.className = 'browse-card';
            card.innerHTML = `
                <div class="browse-card-header">
                    <span class="browse-badge">Product List</span>
                    <span class="browse-merchant">${escHtml(merchant)}</span>
                </div>
                <div class="browse-card-title">${escHtml(listProduct.name)}</div>
                <div class="browse-card-note">Opens verified category page with multiple options</div>
                ${url ? `
                    <a href="${escHtml(url)}" target="_blank" rel="noopener noreferrer" class="btn-browse-products" onclick="event.stopPropagation();">
                        <span>Browse Products →</span>
                    </a>
                ` : ''}
            `;

            if (url) {
                card.style.cursor = 'pointer';
                card.addEventListener('click', () => {
                    window.open(url, '_blank', 'noopener,noreferrer');
                });
            }

            browseGrid.appendChild(card);
        });

        container.appendChild(browseGrid);
    }

    wrapper.appendChild(container);
    chatMessages.appendChild(wrapper);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ── Append a Chat Message Bubble ────────────────────────────────────────────
function appendMessage(sender, text) {
    removeThinkingIndicator();
    const el = document.createElement('div');
    el.className = `message ${sender}`;

    const formattedText = formatText(text);
    const meta = sender === 'nova'
        ? `<div class="msg-meta"><span class="msg-avatar">N</span><span>NOVA</span></div>`
        : `<div class="msg-meta" style="justify-content:flex-end"><span>You</span></div>`;

    el.innerHTML = `${meta}<div class="message-content">${formattedText}</div>`;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function formatText(text) {
    return text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>')
        .replace(/^• |^- /gm, '• ');
}

function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Thinking Indicator ──────────────────────────────────────────────────────
function setThinking(state) {
    isThinking = state;
    sendBtn.disabled = state;
    chatInput.disabled = state;

    if (state) {
        const el = document.createElement('div');
        el.className = 'message nova thinking';
        el.id = 'thinking-indicator';
        el.innerHTML = `
            <div class="msg-meta"><span class="msg-avatar">N</span><span>NOVA</span></div>
            <div class="message-content">
                <div class="thinking-dots">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        chatMessages.appendChild(el);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    } else {
        removeThinkingIndicator();
    }
}

function removeThinkingIndicator() {
    const el = document.getElementById('thinking-indicator');
    if (el) el.remove();
}

// ── Cart ────────────────────────────────────────────────────────────────────
async function fetchCart() {
    try {
        const res = await fetch(`/api/cart?session_id=${sessionId}`);
        const cart = await res.json();
        renderCart(cart);
    } catch (err) {
        console.error('Cart fetch failed:', err);
    }
}

function renderCart(cart) {
    if (!cart || !cart.items || cart.items.length === 0) {
        cartItemsContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🛒</div>
                <p>Your cart is empty</p>
                <span>Ask NOVA to add products</span>
            </div>
        `;
        cartTotalEl.textContent = '₹0.00';
        updateCartBadge(0);
        return;
    }

    cartItemsContainer.innerHTML = '';
    let totalCount = 0;
    cart.items.forEach(item => {
        totalCount += item.quantity;
        const el = document.createElement('div');
        el.className = 'cart-item';
        el.innerHTML = `
            <div class="cart-item-info">
                <span class="cart-item-name">${escHtml(item.product.name)}</span>
                <span class="cart-item-merchant">${escHtml(item.product.merchant)}</span>
            </div>
            <div class="cart-item-right">
                <span class="cart-item-price">₹${Number(item.product.price).toLocaleString('en-IN')}</span>
                <span class="cart-item-qty">×${item.quantity}</span>
            </div>
        `;
        cartItemsContainer.appendChild(el);
    });

    cartTotalEl.textContent = `₹${Number(cart.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    updateCartBadge(totalCount);
}

function updateCartBadge(count) {
    cartCountBadge.textContent = count;
    cartCountBadge.classList.remove('bump');
    void cartCountBadge.offsetWidth; // force reflow
    cartCountBadge.classList.add('bump');
    setTimeout(() => cartCountBadge.classList.remove('bump'), 300);
}

// ── Order Panel ─────────────────────────────────────────────────────────────
function showOrderPanel(order) {
    orderPanel.style.display = 'block';
    orderStatusBadge.textContent = 'Pending';
    orderStatusBadge.className = 'order-status-badge';
    paymentBtn.disabled = false;
    paymentBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
            <line x1="1" y1="10" x2="23" y2="10"></line>
        </svg>
        Confirm and Pay with Razorpay
    `;

    const itemsHtml = order.items.map(item => `
        <div class="order-item-line">
            <span>${escHtml(item.name)} ×${item.quantity}</span>
            <span>₹${Number(item.subtotal).toLocaleString('en-IN')}</span>
        </div>
    `).join('');

    orderDetails.innerHTML = `
        <div class="order-id">Order: ${escHtml(order.id)}</div>
        ${itemsHtml}
        <div class="order-total-line">
            <span>Total Amount</span>
            <span>₹${Number(order.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
        </div>
    `;
}

// ── Payment Flow ─────────────────────────────────────────────────────────────
paymentBtn.addEventListener('click', async () => {
    if (!activeOrder) return;
    paymentBtn.disabled = true;
    paymentBtn.innerHTML = 'Creating order...';

    try {
        // Step 1: Create Razorpay order on backend
        const res = await fetch('/api/payment/create-order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ internal_order_id: activeOrder.id })
        });
        const rzpData = await res.json();

        if (!res.ok) throw new Error(rzpData.detail || 'Order creation failed');

        if (rzpData.demo_mode || !razorpayKeyId || razorpayKeyId === 'rzp_test_placeholder') {
            throw new Error(rzpData.detail || 'Razorpay TEST credentials are not configured. Cart is unchanged.');
        } else {
            openRazorpayCheckout(rzpData);
        }

    } catch (err) {
        paymentBtn.disabled = false;
        paymentBtn.textContent = 'Confirm and Pay with Razorpay';
        appendMessage('nova', `❌ Payment initiation failed: ${err.message}`);
        console.error(err);
    }
});

function openRazorpayCheckout(rzpData) {
    const options = {
        key: razorpayKeyId,
        amount: rzpData.amount,
        currency: rzpData.currency,
        name: 'NOVA Commerce',
        description: `Order ${activeOrder.id}`,
        order_id: rzpData.razorpay_order_id,
        theme: { color: '#6366f1' },
        modal: {
            ondismiss: () => {
                paymentBtn.disabled = false;
                paymentBtn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
                        <line x1="1" y1="10" x2="23" y2="10"></line>
                    </svg>
                    Confirm and Pay with Razorpay
                `;
                appendMessage('nova', 'Payment cancelled. Your order is still saved. Click "Confirm and Pay with Razorpay" again to retry.');
            }
        },
        handler: async (response) => {
            await verifyPayment(
                rzpData.razorpay_order_id,
                response.razorpay_payment_id,
                response.razorpay_signature
            );
        }
    };

    const rzp = new Razorpay(options);
    rzp.open();
}

async function simulateDemoPayment(rzpOrderId) {
    // Simulate a 2-second "processing" state
    paymentBtn.innerHTML = 'Processing demo payment...';
    await delay(2000);

    // Use placeholder IDs in demo mode
    const mockPaymentId = 'pay_DEMO_' + Math.random().toString(36).substring(2, 12).toUpperCase();
    const mockSignature = 'demo_signature_bypass';

    await verifyPayment(rzpOrderId, mockPaymentId, mockSignature);
}

async function verifyPayment(rzpOrderId, rzpPaymentId, rzpSignature) {
    try {
        const res = await fetch('/api/payment/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                internal_order_id: activeOrder.id,
                razorpay_order_id: rzpOrderId,
                razorpay_payment_id: rzpPaymentId,
                razorpay_signature: rzpSignature
            })
        });
        const data = await res.json();

        if (!res.ok) throw new Error(data.detail || 'Verification failed');

        // ✅ Payment confirmed
        showPaymentSuccess(data);

    } catch (err) {
        appendMessage('nova', `❌ Payment verification failed: ${err.message}`);
        paymentBtn.disabled = false;
        paymentBtn.innerHTML = 'Retry Payment';
        console.error(err);
    }
}

function showPaymentSuccess(data) {
    // Update order panel badge
    orderStatusBadge.textContent = 'Paid';
    orderStatusBadge.className = 'order-status-badge paid';
    paymentBtn.disabled = true;
    paymentBtn.innerHTML = '✅ Payment Complete';
    paymentDemoNote.textContent = '';

    // Show overlay
    paymentSuccessMsg.textContent = `Your order has been confirmed and paid.`;
    paymentSuccessMeta.innerHTML = `
        <strong>Order ID:</strong> ${escHtml(data.order_id)}<br>
        <strong>Payment ID:</strong> ${escHtml(data.payment_id)}<br>
        <strong>Mode:</strong> ${data.demo_mode ? 'Demo (Simulated)' : 'Live — Razorpay'}
    `;
    paymentOverlay.style.display = 'flex';

    // Chat confirmation
    appendMessage('nova',
        `🎉 **Payment Confirmed!** Thank you for your purchase.\n` +
            `**Order:** ${data.order_id}\n` +
            `**Payment:** ${data.payment_id}\n` +
            (data.demo_mode ? '_Demo mode payment (simulated)_' : '_Payment verified via Razorpay_')
    );

    // Clear active order state after a moment
    setTimeout(() => { activeOrder = null; }, 500);
    fetchCart();
}

// Close payment overlay
paymentCloseBtn.addEventListener('click', () => {
    paymentOverlay.style.display = 'none';
    orderPanel.style.display = 'none';
    activeOrder = null;
});

// ── Session Reset ────────────────────────────────────────────────────────────
clearSessionBtn.addEventListener('click', async () => {
    if (!confirm('Reset this session? This will clear your conversation, cart, and active order.')) return;

    try {
        await fetch('/api/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });

        // New session
        sessionId = SHARED_NOVA_SESSION_ID;
        localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
        sessionIdVal.textContent = sessionId;

        // Reset UI
        chatMessages.innerHTML = '';
        appendWelcomeMessage();
        if (suggestionChips) suggestionChips.style.display = 'flex';
        agentLogsContainer.innerHTML = '<p class="log-empty">No tools executed yet.</p>';
        orderPanel.style.display = 'none';
        paymentOverlay.style.display = 'none';
        activeOrder = null;

        await fetchCart();

    } catch (err) {
        alert('Failed to reset session. Please try again.');
    }
});

// ── Clear Logs ────────────────────────────────────────────────────────────────
clearLogsBtn.addEventListener('click', () => {
    agentLogsContainer.innerHTML = '<p class="log-empty">Logs cleared.</p>';
});

// ── Suggestion Chips ──────────────────────────────────────────────────────────
document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
        const msg = chip.dataset.msg;
        chatInput.value = msg;
        chatInput.focus();
        chatForm.dispatchEvent(new Event('submit'));
    });
});

// ── Agent Log Rendering ────────────────────────────────────────────────────────
function appendAgentLogs(tools) {
    if (!tools || tools.length === 0) return;

    const emptyEl = agentLogsContainer.querySelector('.log-empty');
    if (emptyEl) emptyEl.remove();

    tools.forEach(tool => {
        const entry = document.createElement('div');
        const hasError = tool.result && tool.result.error;
        entry.className = `log-entry${hasError ? ' error' : ''}`;

        let resultStr = '';
        if (tool.result) {
            if (hasError) {
                resultStr = `Error: ${tool.result.error}`;
            } else if (tool.name === 'search_products' && Array.isArray(tool.result)) {
                resultStr = `✓ Found ${tool.result.length} product(s)`;
            } else if (tool.name === 'compare_prices' && Array.isArray(tool.result)) {
                resultStr = `✓ Found ${tool.result.length} price comparison(s)`;
            } else if (['add_to_cart', 'get_cart'].includes(tool.name)) {
                fetchCart();
                const cartObj = tool.result.cart || tool.result;
                const items = cartObj.items || [];
                const total = cartObj.total_amount ?? '—';
                const failed = tool.result.error || tool.result.success === false;
                resultStr = failed
                    ? `FAILED: ${tool.result.error || 'cart operation failed'}`
                    : `${items.length} item(s), total ${total}`;
            } else if (tool.name === 'create_order') {
                resultStr = tool.result.success
                    ? `PREPARED ${tool.result.order?.id || ''} — confirmation required, cart unchanged`
                    : `FAILED: ${tool.result.error || 'order not prepared'}`;
            } else if (tool.name === 'proceed_to_payment') {
                resultStr = tool.result.success
                    ? `RAZORPAY ORDER ${tool.result.razorpay_order_id} — payment not verified yet`
                    : `FAILED: ${tool.result.error || 'payment handoff not created'}`;
            } else if (tool.name === 'inspect_catalog') {
                const s = tool.result.summary || {};
                resultStr = `Catalogue: ${s.total_valid || 0} valid / ${s.total_detected || 0} detected`;
            } else {
                const snippet = JSON.stringify(tool.result).substring(0, 100);
                resultStr = snippet + (snippet.length >= 100 ? '…' : '');
            }
        }

        const argsStr = JSON.stringify(tool.arguments || {}).substring(0, 80);

        entry.innerHTML = `
            <div class="log-tool">${escHtml(tool.name)}()</div>
            <div class="log-args">${escHtml(argsStr)}</div>
            <div class="log-result${hasError ? ' err' : ''}">${escHtml(resultStr)}</div>
        `;
        agentLogsContainer.appendChild(entry);
    });

    agentLogsContainer.scrollTop = agentLogsContainer.scrollHeight;
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function delay(ms) { return new Promise(res => setTimeout(res, ms)); }

// ── Workspace Tab Navigation ──────────────────────────────────────────────────
const tabChat = document.getElementById('tab-chat');
const tabDiscover = document.getElementById('tab-discover');
const tabSettings = document.getElementById('tab-settings');

function switchWorkspaceTab(targetViewId) {
    document.querySelectorAll('.workspace-view').forEach(view => view.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));

    const targetView = document.getElementById(targetViewId);
    if (targetView) targetView.classList.add('active');

    if (targetViewId === 'view-chat' && tabChat) tabChat.classList.add('active');
    if (targetViewId === 'view-discover') {
        if (tabDiscover) tabDiscover.classList.add('active');
        fetchDiscoverFeed('all');
    }
    if (targetViewId === 'view-catalogue') {
        const tabInspectorEl = document.getElementById('tab-inspector');
        if (tabInspectorEl) tabInspectorEl.classList.add('active');
        loadCatalogueMode();
    }
    if (targetViewId === 'view-settings') {
        if (tabSettings) tabSettings.classList.add('active');
        loadIntegrationsSettings();
    }
}

if (tabChat) tabChat.addEventListener('click', () => switchWorkspaceTab('view-chat'));
if (tabDiscover) tabDiscover.addEventListener('click', () => switchWorkspaceTab('view-discover'));
if (tabSettings) tabSettings.addEventListener('click', () => switchWorkspaceTab('view-settings'));

const tabInspector = document.getElementById('tab-inspector');
const catalogueRefreshBtn = document.getElementById('catalogue-refresh-btn');

async function loadCatalogueMode() {
    try {
        const res = await fetch(`/api/catalog/inspect?session_id=${encodeURIComponent(sessionId)}`);
        const data = await res.json();
        renderCatalogueView(data);
    } catch (e) {
        console.error("Error fetching catalogue:", e);
        const grid = document.getElementById('catalogue-product-grid');
        if (grid) grid.innerHTML = `<p class="empty-state">Could not load catalogue from the backend.</p>`;
    }
}

function renderCatalogueView(data) {
    if (!data) return;
    const summary = data.summary || {};
    const source = data.source || {};
    const prods = data.products || [];
    const meta = document.getElementById('catalogue-meta');
    const grid = document.getElementById('catalogue-product-grid');
    if (meta) {
        const cards = [];
        if (source.merchant_name) cards.push(`<div class="catalogue-meta-card"><span>Source</span><strong>${escHtml(source.merchant_name)}</strong></div>`);
        if (source.page_url) cards.push(`<div class="catalogue-meta-card"><span>Page</span><strong style="font-size:0.78rem;word-break:break-all;">${escHtml(source.page_url)}</strong></div>`);
        cards.push(`<div class="catalogue-meta-card"><span>Products detected</span><strong>${summary.total_detected || 0}</strong></div>`);
        cards.push(`<div class="catalogue-meta-card"><span>Valid products</span><strong>${summary.total_valid || 0}</strong></div>`);
        meta.innerHTML = cards.join('');
    }
    if (!grid) return;
    if (!prods.length) {
        grid.innerHTML = `<p class="empty-state">${escHtml(data.message || 'No valid products on the current page. Open a supported ecommerce listing or product page with the NOVA extension.')}</p>`;
        return;
    }
    grid.innerHTML = '';
    prods.forEach((p) => {
        const card = document.createElement('div');
        card.className = 'catalogue-product-card';
        const fields = [];
        fields.push(`<strong>${escHtml(p.name || 'Product')}</strong>`);
        if (p.brand) fields.push(`Brand: ${escHtml(String(p.brand))}`);
        if (p.category) fields.push(`Category: ${escHtml(String(p.category))}`);
        if (p.price != null) fields.push(`Price: ${escHtml(String(p.currency || ''))} ${escHtml(String(p.price))}`);
        if (p.availability != null) fields.push(`Availability: ${p.availability ? 'in stock' : 'unavailable'}`);
        if (p.rating != null) fields.push(`Rating: ${escHtml(String(p.rating))}`);
        if (p.image_url) fields.push(`<img src="${escHtml(p.image_url)}" alt="" style="max-width:120px;border-radius:8px;margin-top:8px;">`);
        if (p.product_url) fields.push(`URL: <a href="${escHtml(p.product_url)}" target="_blank" rel="noopener noreferrer">${escHtml(p.product_url)}</a>`);
        if (p.id) fields.push(`Product ID: <code>${escHtml(p.id)}</code>`);
        card.innerHTML = fields.map((f, i) => i === 0 ? f : `<div style="font-size:0.8rem;color:var(--text-secondary);margin-top:4px;">${f}</div>`).join('');
        grid.appendChild(card);
    });
}

if (tabInspector) tabInspector.addEventListener('click', () => switchWorkspaceTab('view-catalogue'));
if (catalogueRefreshBtn) catalogueRefreshBtn.addEventListener('click', loadCatalogueMode);

// ── Discover Feed Logic ───────────────────────────────────────────────────────
const discoverFeedGrid = document.getElementById('discover-feed-grid');
const discoverFilterPills = document.querySelectorAll('#discover-filters .filter-pill');

if (discoverFilterPills) {
    discoverFilterPills.forEach(pill => {
        pill.addEventListener('click', () => {
            discoverFilterPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            const cat = pill.dataset.category || 'all';
            fetchDiscoverFeed(cat);
        });
    });
}

async function fetchDiscoverFeed(category = 'all', query = null) {
    if (!discoverFeedGrid) return;
    discoverFeedGrid.innerHTML = `
        <div class="discover-loading">
            <span class="spinner"></span>
            <p>Retrieving live verified discovery updates...</p>
        </div>
    `;

    try {
        let url = `/api/discover?category=${encodeURIComponent(category)}&country=${encodeURIComponent(currentMarket.country_code || 'IN')}`;
        if (query) url += `&query=${encodeURIComponent(query)}`;

        const res = await fetch(url);
        const data = await res.json();
        if (data && data.feed) {
            renderDiscoverFeedGrid(data.feed);
        } else {
            discoverFeedGrid.innerHTML = `<p class="empty-state">No live discovery updates found.</p>`;
        }
    } catch (e) {
        console.error('Fetch discover feed failed:', e);
        discoverFeedGrid.innerHTML = `<p class="empty-state">Unable to load discovery updates right now.</p>`;
    }
}

function renderDiscoverFeedGrid(feed) {
    if (!discoverFeedGrid) return;
    if (!feed || feed.length === 0) {
        discoverFeedGrid.innerHTML = `<p class="empty-state">No discovery updates matching your selection.</p>`;
        return;
    }

    discoverFeedGrid.innerHTML = '';
    feed.forEach(item => {
        const card = document.createElement('div');
        card.className = 'discover-card';

        const categoryTag = item.category || 'Update';
        const imgUrl = item.image_url || 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=600&auto=format&fit=crop&q=80';
        const sourceName = item.merchant || item.source || 'Verified Source';
        const discountHtml = item.discount_label ? `<span class="discount-tag">${escHtml(item.discount_label)}</span>` : '';

        card.innerHTML = `
            <div class="discover-card-img-wrap">
                <img src="${escHtml(imgUrl)}" alt="${escHtml(item.title)}" onerror="this.src='https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=600&auto=format&fit=crop&q=80';" />
                <span class="discover-badge">${escHtml(categoryTag)}</span>
            </div>
            <div class="discover-card-body">
                <span class="discover-card-source">${escHtml(sourceName)}</span>
                <div class="discover-card-title">${escHtml(item.title)}</div>
                <div class="discover-card-desc">${escHtml(item.description || '')}</div>
                <div class="discover-card-footer">
                    ${discountHtml}
                    ${item.url ? `
                        <a href="${escHtml(item.url)}" target="_blank" rel="noopener noreferrer" class="btn-discover-action">
                            <span>Explore Source →</span>
                        </a>
                    ` : ''}
                </div>
            </div>
        `;

        if (item.url) {
            card.style.cursor = 'pointer';
            card.addEventListener('click', () => {
                window.open(item.url, '_blank', 'noopener,noreferrer');
            });
        }

        discoverFeedGrid.appendChild(card);
    });
}

// ── Settings API Logic ────────────────────────────────────────────────────────
const settingCalendarToggle = document.getElementById('setting-calendar-toggle');
const settingEmailToggle = document.getElementById('setting-email-toggle');
const settingEmailInput = document.getElementById('setting-email-input');
const settingSpendingLimit = document.getElementById('setting-spending-limit');
const saveSettingsBtn = document.getElementById('save-settings-btn');
const settingsStatusMsg = document.getElementById('settings-status-msg');

async function loadIntegrationsSettings() {
    try {
        const res = await fetch('/api/settings/integrations');
        const data = await res.json();
        if (settingCalendarToggle) settingCalendarToggle.checked = !!data.calendar?.is_connected;
        if (settingEmailToggle) settingEmailToggle.checked = !!data.email?.is_configured;
        if (settingEmailInput && data.email?.user_email) settingEmailInput.value = data.email.user_email;
        if (settingSpendingLimit) settingSpendingLimit.value = data.spending_limit != null ? data.spending_limit : '';
    } catch (e) {
        console.warn('Failed to load settings:', e);
    }
}

if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', async () => {
        const calendarConnected = settingCalendarToggle ? settingCalendarToggle.checked : false;
        const emailEnabled = settingEmailToggle ? settingEmailToggle.checked : false;
        const emailVal = settingEmailInput ? settingEmailInput.value.trim() : '';
        const limitRaw = settingSpendingLimit ? settingSpendingLimit.value.trim() : '';
        const payload = {
            calendar_connected: calendarConnected,
            email_enabled: emailEnabled,
            user_email: emailVal
        };
        if (!limitRaw) {
            payload.clear_spending_limit = true;
        } else {
            payload.spending_limit = Number(limitRaw);
        }
        try {
            const res = await fetch('/api/settings/integrations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                if (settingsStatusMsg) {
                    settingsStatusMsg.textContent = '✓ Settings saved successfully!';
                    setTimeout(() => { settingsStatusMsg.textContent = ''; }, 3000);
                }
            }
        } catch (e) {
            alert('Failed to save settings.');
        }
    });
}

// ── Checkout Safety Confirmation Modal Logic ──────────────────────────────────
const checkoutSafetyOverlay = document.getElementById('checkout-safety-overlay');
const checkoutSafetyMsg = document.getElementById('checkout-safety-msg');
const checkoutProductPreview = document.getElementById('checkout-product-preview');
const checkoutConfirmBtn = document.getElementById('checkout-confirm-btn');
const checkoutCancelBtn = document.getElementById('checkout-cancel-btn');
let pendingCheckoutResult = null;

function showCheckoutSafetyModal(actionResult) {
    pendingCheckoutResult = actionResult;
    if (checkoutSafetyOverlay) checkoutSafetyOverlay.style.display = 'grid';
    if (checkoutSafetyMsg) checkoutSafetyMsg.textContent = actionResult.message || 'You are about to proceed to checkout. Do you want to place the order?';
    if (checkoutProductPreview && actionResult.product) {
        checkoutProductPreview.textContent = `Product: ${actionResult.product.name} | Price: ₹${actionResult.product.price} | Store: ${actionResult.product.merchant_name}`;
    }
}

if (checkoutCancelBtn) {
    checkoutCancelBtn.addEventListener('click', () => {
        if (checkoutSafetyOverlay) checkoutSafetyOverlay.style.display = 'none';
        pendingCheckoutResult = null;
    });
}

if (checkoutConfirmBtn) {
    checkoutConfirmBtn.addEventListener('click', () => {
        if (checkoutSafetyOverlay) checkoutSafetyOverlay.style.display = 'none';
        if (pendingCheckoutResult && pendingCheckoutResult.checkout_url) {
            window.open(pendingCheckoutResult.checkout_url, '_blank', 'noopener,noreferrer');
        }
        pendingCheckoutResult = null;
    });
}

// ═══════════════════════════════════════════════════════════════════════════
// NOVA — First-Open / Splash Screen Controller (Phase 1 UI, self-contained)
//
// This block is a pure presentation layer. It does NOT call init(), does NOT
// touch sessionId, market detection, cart, backend health checks, agent
// logic, or any existing behaviour above. It only fades an overlay in/out
// while the real app (already initialising via init() above) loads behind
// it, then gets out of the way. Safe to remove entirely with no effect on
// app functionality.
// ═══════════════════════════════════════════════════════════════════════════
(function novaSplashController() {
    const splash = document.getElementById('nova-splash');
    if (!splash) return; // splash markup not present — no-op

    const loaderFill = document.getElementById('nova-splash-loader-fill');
    const musicEl = document.getElementById('nova-splash-music');

    // Slowed so the loader only finishes once the voice line and the
    // opening bars of the music have had room to play out.
    const SPLASH_DURATION_MS = 7200;

    const MUSIC_VOLUME_OPEN = 0.55; // clearly audible on open
    const MUSIC_VOLUME_FEEBLE = 0.18; // ducked, but still audible once the voice starts

    // Kick off the loading-bar fill (CSS transition handles the smoothness)
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            if (loaderFill) loaderFill.style.width = '100%';
        });
    });

    // Smoothly ramp the music element's volume from one level to another
    // over `durationMs`. We never touch the audio file itself — this only
    // adjusts playback volume in the browser, so the original track you
    // uploaded stays exactly as-is.
    function rampVolume(el, from, to, durationMs) {
        if (!el) return;
        const steps = 24;
        const stepTime = durationMs / steps;
        let i = 0;
        el.volume = from;
        const timer = setInterval(() => {
            i++;
            const t = i / steps;
            el.volume = from + (to - from) * t;
            if (i >= steps) clearInterval(timer);
        }, stepTime);
    }

    // Background music: plays your uploaded track from its own beginning,
    // unedited. It opens at a normal level, then is ducked down to a
    // feeble/background level once the voice line starts speaking.
    try {
        if (musicEl && musicEl.querySelector('source[src]')) {
            musicEl.volume = MUSIC_VOLUME_OPEN;
            musicEl.play().catch(() => { /* autoplay may be blocked; ignore */ });
        }
    } catch (e) { /* non-critical */ }

    // Welcome line via the browser's built-in speech synthesis — no
    // external audio source, nothing copyrighted. Tuned to sound soft and
    // warm rather than bold/robotic, with a nicer, slightly higher-pitched
    // voice preferred when the browser offers one.
    function speakWelcome() {
        if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) return;

        // Duck the music down to a feeble level right as the voice begins.
        rampVolume(musicEl, MUSIC_VOLUME_OPEN, MUSIC_VOLUME_FEEBLE, 700);

        const line = 'Welcome to NOVA. Your intelligent shopping experience is starting now.';
        const utter = new SpeechSynthesisUtterance(line);
        utter.rate = 0.85;  // slower, gentle delivery — not clipped or bold
        utter.pitch = 1.15;  // a touch higher, softer/warmer than a flat default
        utter.volume = 1.0;   // kept clearly audible over the low background music

        // Preferred voices in order: a "nicer", slightly higher-pitched
        // female voice first, then any other clearly-female voice, then
        // any English voice as a last resort. Names vary by OS/browser, so
        // this is best-effort matching rather than a guarantee.
        const NICE_HIGHER_VOICE_NAMES = /(samantha|serena|ava|allison|moira|tessa|fiona|kathy|karen|joanna|kendra|salli|aria|jenny)/i;
        const OTHER_FEMALE_VOICE_NAMES = /(female|zira|victoria|susan|hazel|zoe|emma)/i;

        const pickVoice = () => {
            const voices = window.speechSynthesis.getVoices() || [];
            const nicer = voices.find(v => NICE_HIGHER_VOICE_NAMES.test(v.name));
            const female = voices.find(v => OTHER_FEMALE_VOICE_NAMES.test(v.name));
            const englishFallback = voices.find(v => v.lang && v.lang.startsWith('en'));
            const chosen = nicer || female || englishFallback;
            if (chosen) utter.voice = chosen;
            window.speechSynthesis.speak(utter);
        };

        const existingVoices = window.speechSynthesis.getVoices();
        if (existingVoices && existingVoices.length) {
            pickVoice();
        } else {
            // Voices load async in some browsers
            window.speechSynthesis.onvoiceschanged = pickVoice;
        }
    }

    // Speak shortly after the NOVA name has faded in, so it doesn't collide
    // with the very first icon fade-in beat.
    setTimeout(speakWelcome, 1600);

    // End the sequence and hand off to the existing app UI underneath.
    setTimeout(() => {
        splash.classList.add('nova-splash-hidden'); // triggers the 0.9s splash fade → main page reveal
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        if (musicEl && !musicEl.paused) {
            // Fade out over the same span as the splash's own fade-out, so
            // the music finishes disappearing right as the main page opens.
            rampVolume(musicEl, musicEl.volume, 0, 900);
            setTimeout(() => musicEl.pause(), 950);
        }
        // Fully remove after the fade-out transition so it can never
        // intercept clicks or be reachable by screen readers.
        setTimeout(() => {
            if (splash && splash.parentNode) splash.remove();
        }, 950);
    }, SPLASH_DURATION_MS);
})();
