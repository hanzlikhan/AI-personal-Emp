'use strict';

const express = require('express');
const bodyParser = require('body-parser');
const nodemailer = require('nodemailer');
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.MCP_PORT || 3001;
const START_TIME = Date.now();

app.use(bodyParser.json());

// ─── configuration ────────────────────────────────────────────────────────────
const USER_DATA_WA = path.join(__dirname, 'whatsapp_user_data');
const USER_DATA_FB = path.join(__dirname, 'facebook_user_data');

// ─── Global State (Persistent Sessions) ──────────────────────────────────────
const SERVICES = {
    whatsapp: { context: null, page: null, type: 'whatsapp', userData: USER_DATA_WA, url: 'https://web.whatsapp.com/', userInteraction: false, launching: false },
    facebook: { context: null, page: null, type: 'facebook', userData: USER_DATA_FB, url: 'https://www.facebook.com/', userInteraction: false, launching: false }
};

// ─── Logger ──────────────────────────────────────────────────────────────────
function log(endpoint, status, detail = '') {
    const entry = {
        ts: new Date().toISOString(),
        endpoint,
        status,
        detail
    };
    console.log(JSON.stringify(entry));
    try {
        fs.appendFileSync(path.join(__dirname, 'mcp_server.log'), JSON.stringify(entry) + '\n');
    } catch (_) { }
}

// ─── .env Loader ──────────────────────────────────────────────────────────────
function loadEnv() {
    const envPath = path.join(__dirname, '..', '.env');
    if (!fs.existsSync(envPath)) return {};
    const env = {};
    fs.readFileSync(envPath, 'utf-8').split('\n').forEach(line => {
        // Strip Windows \r
        line = line.replace(/\r$/, '');
        const m = line.match(/^\s*([^=#\s][^=]*)=(.*)$/);
        if (m) {
            const val = m[2].trim().replace(/^['"]/, '').replace(/['"]$/, '');
            process.env[m[1].trim()] = val;
            env[m[1].trim()] = val;
        }
    });
    return env;
}
loadEnv();

// Fresh env read for any operation that needs current credentials
function getEnv(key) {
    const envPath = path.join(__dirname, '..', '.env');
    if (fs.existsSync(envPath)) {
        const lines = fs.readFileSync(envPath, 'utf-8').split('\n');
        for (const line of lines) {
            const clean = line.replace(/\r$/, '').trim();
            if (clean.startsWith(`${key}=`)) {
                return clean.slice(key.length + 1).trim().replace(/^['"]/, '').replace(/['"]$/, '');
            }
        }
    }
    return process.env[key] || '';
}

// ─── Browser Management ──────────────────────────────────────────────────────

async function launchService(serviceName, headless = true) {
    const svc = SERVICES[serviceName];
    svc.launching = true;  // Set mutex — block check-* during launch
    log(`session:${serviceName}`, 'start', `Launching context (Headless: ${headless})`);

    try {
        // 1. Close existing if any
        if (svc.context) {
            try { await svc.context.close(); } catch (e) { }
            svc.context = null;
            svc.page = null;
        }

        // 2. Launch Persistent Context
        // Add args to help with reliability
        svc.context = await chromium.launchPersistentContext(svc.userData, {
            headless: headless,
            viewport: null, // Let browser decide for visible window
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            permissions: ['notifications', 'geolocation'],
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--start-maximized' // Better experience for user interaction
            ]
        });

        // 3. Get or Create Page
        // Wait a small bit for browser to stabilize
        await new Promise(r => setTimeout(r, 1000));

        const pages = svc.context.pages();
        if (pages.length > 0) {
            svc.page = pages[0];
            log(`session:${serviceName}`, 'info', `Reusing existing page (found ${pages.length})`);
        } else {
            svc.page = await svc.context.newPage();
            log(`session:${serviceName}`, 'info', 'Created new page');
        }

        // 4. Navigate
        log(`session:${serviceName}`, 'info', `Navigating to ${svc.url}`);

        // If visible, bring to front
        if (!headless) {
            try { await svc.page.bringToFront(); } catch (e) { }
        }

        try {
            await svc.page.goto(svc.url, { waitUntil: 'domcontentloaded', timeout: 60000 });
            // For WhatsApp, we might need to wait for the initial loader to finish
            if (serviceName === 'whatsapp') {
                try {
                    // Wait for either QR code, Chat List, or a "Retry" button
                    await Promise.race([
                        svc.page.waitForSelector('[data-testid="qrcode"]', { timeout: 15000 }),
                        svc.page.waitForSelector('[data-testid="chat-list"]', { timeout: 15000 }),
                        svc.page.waitForSelector('canvas', { timeout: 15000 })
                    ]);
                } catch (e) { console.log("WA load weak-wait: continued anyway"); }
            }
        } catch (e) {
            log(`session:${serviceName}`, 'warn', `Goto timeout/error: ${e.message}. Retrying...`);
            try {
                await svc.page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
            } catch (e2) {
                log(`session:${serviceName}`, 'error', `Retry failed: ${e2.message}`);
                // Don't abort, maybe it loaded partially?
            }
        }

        log(`session:${serviceName}`, 'ok', `Context active (Headless: ${headless})`);
        return true;
    } catch (e) {
        log(`session:${serviceName}`, 'error', `Launch failed: ${e.message}`);
        return false;
    } finally {
        svc.launching = false;  // Always release mutex
    }
}

async function getPage(serviceName) {
    const svc = SERVICES[serviceName];

    // If currently launching (user clicked connect), wait for it to finish
    if (svc.launching) {
        log(`session:${serviceName}`, 'info', 'Launch in progress, waiting...');
        for (let i = 0; i < 30 && svc.launching; i++) {
            await new Promise(r => setTimeout(r, 1000));
        }
        return svc.page;
    }

    // Case 1: Browser was closed manually by user or crashed
    if (svc.context && svc.page && (svc.page.isClosed() || !svc.context.pages().length)) {
        log(`session:${serviceName}`, 'warn', 'Page/Context closed unexpectedly. Relaunching Headless...');
        await launchService(serviceName, true);
    }

    // Case 2: Never started
    if (!svc.context) {
        log(`session:${serviceName}`, 'info', 'Context not running. Launching Headless...');
        await launchService(serviceName, true);
    }

    return svc.page;
}

// ─── Email Transporter ────────────────────────────────────────────────────────
const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
        user: process.env.GMAIL_USER,
        pass: process.env.GMAIL_APP_PASSWORD,
    },
});

// ─── WhatsApp ───

app.get('/connect-whatsapp', async (req, res) => {
    try {
        console.log("→ Launching WhatsApp for connection (Headless: FALSE)");
        SERVICES.whatsapp.userInteraction = true;

        // Auto-reset after 3 minutes
        setTimeout(() => {
            SERVICES.whatsapp.userInteraction = false;
            console.log("→ WhatsApp User Mode ended (timeout)");
        }, 180000);

        const success = await launchService('whatsapp', false);
        res.json({ success, message: success ? 'WhatsApp launched. Scan QR.' : 'Failed to launch.' });
    } catch (e) {
        log('/connect-whatsapp', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

app.get('/check-whatsapp', async (req, res) => {
    log('/check-whatsapp', 'start');
    try {
        const page = await getPage('whatsapp');
        if (!page) return res.json({ new_messages: [], status: 'offline' });

        // Ensure a large enough viewport so virtual-scroll renders chat items
        await page.setViewportSize({ width: 1280, height: 900 }).catch(() => { });

        // Navigate to WhatsApp Web if not already there
        const url = page.url();
        if (!url.includes('web.whatsapp.com')) {
            await page.goto('https://web.whatsapp.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });
            await page.waitForTimeout(4000);
        }

        // ── Check login state ──────────────────────────────────────────────
        const loginState = await page.evaluate(() => {
            const qrSelectors = ['canvas', '[data-testid="qrcode"]', '[data-testid="link-device-qrcode"]', 'div[data-ref]'];
            const chatSelectors = ['#pane-side', '[aria-label="Chat list"]', '[data-testid="chat-list"]'];

            const hasQR = qrSelectors.some(s => document.querySelector(s));
            const hasChat = chatSelectors.some(s => document.querySelector(s));
            return { hasQR, hasChat, url: location.href };
        });

        log('/check-whatsapp', 'info', `url=${loginState.url.slice(0, 50)} hasChat=${loginState.hasChat} hasQR=${loginState.hasQR}`);

        if (loginState.hasQR || !loginState.hasChat) {
            return res.json({ status: 'offline', detail: loginState.hasQR ? 'QR visible' : 'No chat panel', new_messages: [] });
        }

        // ── Wait & scroll so virtual-scroll renders chats ──────────────────
        try {
            await page.waitForSelector('#pane-side', { timeout: 8000 });
        } catch (e) { /* already checked above */ }

        // Scroll the chat list to force virtual-scroll to render items
        await page.evaluate(() => {
            const panel = document.querySelector('#pane-side div[tabindex="-1"][style]') ||
                document.querySelector('#pane-side > div') ||
                document.querySelector('#pane-side');
            if (panel) {
                panel.scrollTop = 0;
                panel.dispatchEvent(new Event('scroll'));
            }
        });
        await page.waitForTimeout(1500); // Let virtual scroll render

        // ── Scrape chat list ───────────────────────────────────────────────
        const chats = await page.evaluate(() => {
            const items = [];

            // Primary: span[title] inside #pane-side — most stable across WA versions
            // Each chat row contains a span with title= the contact name
            const nameSpans = document.querySelectorAll('#pane-side span[title]:not([title=""])');

            if (nameSpans.length > 0) {
                for (const span of Array.from(nameSpans).slice(0, 20)) {
                    const name = span.getAttribute('title') || span.innerText || '';
                    if (!name.trim()) continue;

                    // Walk up to find the row container
                    let row = span.parentElement;
                    for (let i = 0; i < 8 && row; i++) {
                        if (row.getAttribute('role') === 'row' ||
                            row.getAttribute('role') === 'listitem' ||
                            row.getAttribute('tabindex') === '-1') break;
                        row = row.parentElement;
                    }

                    // Get preview text from that row
                    const previewEl = row ? (
                        row.querySelector('[data-testid="last-msg"]') ||
                        row.querySelector('span.x1iyjqo2.q3l9s9k7') || // WA class (may change)
                        row.querySelector('span[dir="ltr"]')
                    ) : null;

                    // Unread badge
                    const badgeEl = row ? (
                        row.querySelector('span[aria-label*="unread"]') ||
                        row.querySelector('[data-testid="icon-unread-count"]') ||
                        Array.from(row.querySelectorAll('span')).find(
                            s => s.innerText && /^\d+$/.test(s.innerText.trim()) && parseInt(s.innerText) > 0
                        )
                    ) : null;

                    const preview = previewEl ? previewEl.innerText.trim() : '';
                    const countText = badgeEl ? badgeEl.innerText.trim() : '';
                    const count = countText && /^\d+$/.test(countText) ? parseInt(countText) : 0;

                    items.push({ sender: name.trim(), preview, count });
                }
                return { items, strategy: 'span[title]', found: nameSpans.length };
            }

            // Fallback: any row-like element with a title attribute
            const anyTitles = document.querySelectorAll('[role="row"] [title], [role="listitem"] [title]');
            for (const el of Array.from(anyTitles).slice(0, 20)) {
                const name = el.getAttribute('title') || el.innerText || '';
                if (name.trim()) items.push({ sender: name.trim(), preview: '', count: 0 });
            }

            // If still empty, return debug info
            if (items.length === 0) {
                return {
                    items: [],
                    _debug: true,
                    _pane_side: !!document.querySelector('#pane-side'),
                    _chat_list: !!document.querySelector('[aria-label="Chat list"]'),
                    _all_spans: document.querySelectorAll('span[title]').length,
                    _pane_spans: document.querySelectorAll('#pane-side span[title]').length,
                    _any_roles: document.querySelectorAll('[role="row"],[role="listitem"]').length,
                    strategy: 'fallback'
                };
            }

            return { items, strategy: 'fallback-titles' };
        });

        if (chats._debug || chats.items.length === 0) {
            log('/check-whatsapp', 'warn',
                `chats=0 | pane=${chats._pane_side} spans=${chats._pane_spans}/${chats._all_spans} roles=${chats._any_roles} strategy=${chats.strategy}`
            );
            // Take debug screenshot
            try {
                await page.screenshot({ path: 'whatsapp_debug.png' });
                log('/check-whatsapp', 'info', 'Debug screenshot saved');
            } catch (_) { }
        } else {
            log('/check-whatsapp', 'ok', `chats=${chats.items.length} strategy=${chats.strategy}`);
        }

        res.json({ status: 'online', new_messages: chats.items });

    } catch (e) {
        log('/check-whatsapp', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});


// ─── Facebook ───


app.get('/connect-facebook', async (req, res) => {
    try {
        console.log("→ Launching Facebook for connection (Headless: FALSE)");
        SERVICES.facebook.userInteraction = true;

        // Auto-reset after 3 minutes
        setTimeout(() => {
            SERVICES.facebook.userInteraction = false;
            console.log("→ Facebook User Mode ended (timeout)");
        }, 180000);

        const success = await launchService('facebook', false);
        res.json({ success, message: success ? 'Facebook launched. Please login.' : 'Failed to launch.' });
    } catch (e) {
        log('/connect-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

app.get('/check-facebook', async (req, res) => {
    log('/check-facebook', 'start');
    try {
        const page = await getPage('facebook');
        if (!page) return res.json({ status: 'offline' });

        const output = { friend_requests: [], messages: [], events: [], status: 'online' };

        // 0. If User is Interacting, DO NOT navigate. Just check current state.
        if (SERVICES.facebook.userInteraction) {
            const isLoggedIn = await page.evaluate(() => {
                return document.querySelectorAll('div[role="navigation"]').length > 0 || document.querySelector('input[name="email"]') === null;
            });
            if (isLoggedIn) return res.json({ ...output, status: 'online' });

            // If not logged in, just return offline (so user knows to log in)
            // But we don't want to disrupt them.
            return res.json({ status: 'offline', detail: 'User interacting/Logging in' });
        }

        // We will do a quick navigation check if not on a data page
        if (!page.url().includes('facebook.com')) await page.goto('https://www.facebook.com/');

        // Check Login (Standard)
        if (await page.locator('input[name="email"]').count() > 0) {
            return res.json({ ...output, status: 'offline' });
        }

        // 1. Gentle Scraping: Check Top Nav Badges (Aria-labels) instead of navigating
        const counts = await page.evaluate(() => {
            let friendReqsCount = 0;
            let msgsCount = 0;

            // Look for aria-labels on the top nav icons
            document.querySelectorAll('div[role="navigation"] div[aria-label]').forEach(el => {
                const label = el.getAttribute('aria-label') || '';
                // e.g. "Messenger, 3 unread messages"
                if (label.includes('unread messages') || label.includes('Messenger')) {
                    const match = label.match(/(\d+)/);
                    if (match) msgsCount = parseInt(match[1]);
                }
                // e.g. "Friends, 2 new requests"
                if (label.includes('Friends') && (label.includes('request') || label.includes('unread'))) {
                    const match = label.match(/(\d+)/);
                    if (match) friendReqsCount = parseInt(match[1]);
                }
            });
            return { friendReqsCount, msgsCount };
        });

        // Add placeholders if there are counts (since we can't get exact names without interrupting)
        if (counts.friendReqsCount > 0) {
            for (let i = 0; i < counts.friendReqsCount; i++) {
                output.friend_requests.push({ type: 'friend_request', name: 'Unknown', description: 'New Friend Request' });
            }
        }

        if (counts.msgsCount > 0) {
            for (let i = 0; i < counts.msgsCount; i++) {
                output.messages.push({ type: 'message', sender: 'Unknown', count: 1, preview: 'New Message' });
            }
        }

        log('/check-facebook', 'ok', `Found ${output.messages.length} msgs, ${output.friend_requests.length} requests`);
        res.json(output);

    } catch (e) {
        log('/check-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── Actions (Email, WhatsApp & Others) ───

// ─── Send WhatsApp ───
app.post('/send-whatsapp', async (req, res) => {
    const { contact, message } = req.body;
    log('/send-whatsapp', 'start', `contact=${contact}`);
    if (!contact || !message) return res.status(400).json({ success: false, error: 'Missing contact or message' });

    try {
        const page = await getPage('whatsapp');
        if (!page) return res.status(500).json({ success: false, error: 'WhatsApp not running' });

        // Ensure correct viewport
        await page.setViewportSize({ width: 1280, height: 900 }).catch(() => { });

        // ── STEP 1: Click contact using Playwright's click() — NOT DOM .click() ──
        // page.click() simulates real mouse events → triggers React handlers → navigates
        // DOM element.click() only fires basic event → React ignores it → no navigation
        let chatOpened = false;

        // Build selector for the row containing our contact name
        const exactSelector = `#pane-side span[title="${contact}"]`;
        const partialSelector = `#pane-side span[title*="${contact}"]`;

        // Try exact title first, then partial
        for (const selector of [exactSelector, partialSelector]) {
            try {
                const span = page.locator(selector).first();
                const count = await span.count();
                if (count === 0) continue;

                // Use Playwright's click — simulates real mouse event (React-compatible)
                await span.click({ timeout: 3000 });
                chatOpened = true;
                log('/send-whatsapp', 'info', `Clicked contact: ${selector}`);
                break;
            } catch (e) { /* try next */ }
        }

        // ── STEP 2: If contact not in visible chat list — use search keyboard shortcut ──
        if (!chatOpened) {
            log('/send-whatsapp', 'info', 'Not in chat list — trying Ctrl+k search');
            await page.keyboard.press('Escape');
            await page.waitForTimeout(400);
            await page.keyboard.press('Control+k');
            await page.waitForTimeout(800);
            await page.keyboard.type(contact, { delay: 80 });
            await page.waitForTimeout(2500);

            // Try clicking via Playwright on search results
            for (const sel of [`span[title="${contact}"]`, `span[title*="${contact}"]`]) {
                try {
                    const el = page.locator(sel).first();
                    if (await el.count() > 0) {
                        await el.click({ timeout: 3000 });
                        chatOpened = true;
                        break;
                    }
                } catch (e) { /* try next */ }
            }
        }

        if (!chatOpened) {
            return res.status(404).json({ success: false, error: `Contact "${contact}" not found in chat list. They must appear in your recent WhatsApp chats.` });
        }

        // ── STEP 3: Wait for chat to open — verify by checking compose box ──────
        await page.waitForTimeout(1500);

        // Try to find compose/message box — SPECIFIC to the chat panel (not search)
        // footer > div[contenteditable] is chat-only, never search box
        let msgBox = null;
        const msgSelectors = [
            'footer div[contenteditable="true"]',
            '[data-testid="conversation-compose-box-input"]',
            'div[aria-label="Type a message"]',
            'div[aria-placeholder="Type a message"]',
            '[contenteditable="true"][data-tab="10"]',
            '[contenteditable="true"][data-tab="6"]',
        ];
        for (const sel of msgSelectors) {
            try {
                const el = page.locator(sel).first();
                if (await el.count() > 0) { msgBox = el; break; }
            } catch (e) { /* try next */ }
        }

        if (!msgBox) {
            return res.status(500).json({
                success: false,
                error: `Chat for "${contact}" did not open properly. Try sending again, or ensure you have an existing conversation with this contact.`
            });
        }

        // ── STEP 4: Click, type, send ────────────────────────────────────────────
        await msgBox.click();
        await page.waitForTimeout(300);
        await msgBox.type(message, { delay: 40 });

        // Press Enter to send
        await page.keyboard.press('Enter');
        await page.waitForTimeout(800);

        // Verify message was sent by checking if compose box is now empty
        const isEmpty = await msgBox.evaluate(el => el.textContent.trim() === '');
        if (!isEmpty) {
            // Enter didn't clear — try clicking send button
            const sendBtn = page.locator('[data-testid="send"], [aria-label="Send"]').first();
            if (await sendBtn.count() > 0) await sendBtn.click();
            await page.waitForTimeout(500);
        }

        log('/send-whatsapp', 'ok', `Sent to ${contact}: "${message.slice(0, 40)}"`);
        res.json({ success: true, contact, message });

    } catch (e) {
        log('/send-whatsapp', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});




app.post('/send-email', async (req, res) => {
    const { to, subject, body } = req.body;
    log('/send-email', 'start', `to=${to}`);
    if (!to || !subject || !body) return res.status(400).json({ success: false, error: 'Missing fields' });

    // Always read fresh credentials from .env (handles post-startup credential changes)
    const gmailUser = getEnv('GMAIL_USER');
    const gmailPass = getEnv('GMAIL_APP_PASSWORD');

    if (!gmailUser || gmailUser.includes('your_email') || !gmailPass || gmailPass.includes('your_app')) {
        const err = `Gmail credentials not configured. Set GMAIL_USER and GMAIL_APP_PASSWORD in .env file.`;
        log('/send-email', 'error', err);
        return res.status(503).json({ success: false, error: err });
    }

    try {
        // Create fresh transporter with current credentials
        const freshTransporter = require('nodemailer').createTransport({
            service: 'gmail',
            auth: { user: gmailUser, pass: gmailPass },
        });
        const info = await freshTransporter.sendMail({
            from: gmailUser,
            to, subject, text: body,
            html: body.includes('<') ? body : undefined,
        });
        log('/send-email', 'ok', `messageId=${info.messageId}`);
        res.json({ success: true, messageId: info.messageId });
    } catch (e) {
        log('/send-email', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── Post to Facebook ───
app.post('/post-facebook', async (req, res) => {
    const { text, message } = req.body;
    const postContent = text || message;
    log('/post-facebook', 'start', `text=${(postContent || '').substring(0, 50)}`);
    if (!postContent) return res.status(400).json({ success: false, error: 'Missing text/message field' });

    try {
        const page = await getPage('facebook');
        if (!page) return res.status(500).json({ success: false, error: 'Facebook not running' });

        // Check if on Facebook
        if (!page.url().includes('facebook.com')) {
            await page.goto('https://www.facebook.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });
        }

        // Check login
        const loginForm = await page.$('input[name="email"]');
        if (loginForm) return res.status(503).json({ success: false, error: 'Facebook not logged in. Please connect first.' });

        // Click on "What\'s on your mind?" post composer
        const composerSelectors = [
            '[aria-label^="What\'s on your mind"]',
            '[placeholder^="What\'s on your mind"]',
            'div[role="button"][tabindex="0"]:has-text("What")',
            'span:has-text("What\'s on your mind")',
        ];
        let composerBtn = null;
        for (const sel of composerSelectors) {
            try {
                const el = page.locator(sel).first();
                if (await el.count() > 0) { composerBtn = el; break; }
            } catch (e) { /* next */ }
        }
        if (!composerBtn) {
            // Try going to home first
            await page.goto('https://www.facebook.com/', { waitUntil: 'domcontentloaded', timeout: 20000 });
            await page.waitForTimeout(2000);
            for (const sel of composerSelectors) {
                try {
                    const el = page.locator(sel).first();
                    if (await el.count() > 0) { composerBtn = el; break; }
                } catch (e) { /* next */ }
            }
        }
        if (!composerBtn) return res.status(500).json({ success: false, error: 'Could not find post composer' });

        await composerBtn.click({ timeout: 5000 });
        await page.waitForTimeout(2000);

        // Type in the expanded post box
        const textBoxSelectors = [
            '[aria-label^="What\'s on your mind"][contenteditable="true"]',
            'div[data-lexical-editor="true"]',
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
        ];
        let textBox = null;
        for (const sel of textBoxSelectors) {
            try {
                const el = page.locator(sel).first();
                if (await el.count() > 0) { textBox = el; break; }
            } catch (e) { /* next */ }
        }
        if (!textBox) return res.status(500).json({ success: false, error: 'Post textbox not found' });

        await textBox.click();
        await page.waitForTimeout(500);
        await textBox.type(postContent, { delay: 30 });
        await page.waitForTimeout(800);

        // Click Post button
        const postButton = await page.$('[aria-label="Post"]') || await page.$('button:has-text("Post")') || await page.$('div[aria-label="Post"]');
        if (!postButton) return res.status(500).json({ success: false, error: 'Post button not found' });

        await postButton.click();
        await page.waitForTimeout(2000);

        log('/post-facebook', 'ok', 'Posted successfully');
        res.json({ success: true, message: 'Posted to Facebook' });
    } catch (e) {
        log('/post-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── Post to Facebook with AI Image ───
// Downloads image from Pollinations.ai and posts with generated text
app.post('/post-facebook-ai', async (req, res) => {
    const { text, topic, generate_image } = req.body;
    const postContent = text;
    log('/post-facebook-ai', 'start', `topic=${topic}`);
    if (!postContent) return res.status(400).json({ success: false, error: 'Missing text field' });

    const fs = require('fs');
    const path = require('path');
    const https = require('https');
    const http = require('http');

    // Helper to download file
    const downloadFile = (url, dest) => new Promise((resolve, reject) => {
        const proto = url.startsWith('https') ? https : http;
        const file = fs.createWriteStream(dest);
        proto.get(url, (response) => {
            if (response.statusCode === 301 || response.statusCode === 302) {
                // Follow redirect
                downloadFile(response.headers.location, dest).then(resolve).catch(reject);
                return;
            }
            response.pipe(file);
            file.on('finish', () => { file.close(); resolve(dest); });
        }).on('error', (err) => { fs.unlink(dest, () => { }); reject(err); });
    });

    let imagePath = null;
    let imageStatus = 'not_added';

    // Step 1: Generate image via Pollinations.ai (free, no API key needed)
    if (generate_image && topic) {
        try {
            const imgPrompt = encodeURIComponent(`${topic} professional social media post illustration, vibrant, modern, no text`);
            const imgUrl = `https://image.pollinations.ai/prompt/${imgPrompt}?width=1200&height=630&seed=${Date.now() % 10000}&nologo=true`;
            imagePath = path.join(__dirname, `fb_post_img_${Date.now()}.jpg`);
            log('/post-facebook-ai', 'info', `Downloading image from Pollinations.ai...`);
            await downloadFile(imgUrl, imagePath);
            const stat = fs.statSync(imagePath);
            if (stat.size < 5000) throw new Error('Image too small — likely failed');
            log('/post-facebook-ai', 'info', `Image downloaded: ${stat.size} bytes`);
            imageStatus = 'generated';
        } catch (e) {
            log('/post-facebook-ai', 'warn', `Image generation failed: ${e.message}`);
            if (imagePath && fs.existsSync(imagePath)) fs.unlinkSync(imagePath);
            imagePath = null;
            imageStatus = 'generation_failed';
        }
    }

    try {
        const page = await getPage('facebook');
        if (!page) return res.status(500).json({ success: false, error: 'Facebook not running' });

        // Navigate to Facebook home
        if (!page.url().includes('facebook.com')) {
            await page.goto('https://www.facebook.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });
        }

        // Check login
        if (await page.$('input[name="email"]')) {
            return res.status(503).json({ success: false, error: 'Facebook not logged in. Please connect first.' });
        }

        // Go to home to ensure post composer is visible
        await page.goto('https://www.facebook.com/', { waitUntil: 'domcontentloaded', timeout: 20000 });
        await page.waitForTimeout(2000);

        // Click "What's on your mind?" button to open composer
        const composerTriggers = [
            '[aria-label^="What\'s on your mind"]',
            '[placeholder^="What\'s on your mind"]',
            'span[class*="x193iq5w"]:has-text("What")',
            'div[role="button"]:has-text("on your mind")',
        ];
        let opened = false;
        for (const sel of composerTriggers) {
            try {
                const el = page.locator(sel).first();
                if (await el.count() > 0) { await el.click({ timeout: 5000 }); opened = true; break; }
            } catch (e) { /* next */ }
        }
        if (!opened) {
            // Try clicking anywhere in the post creation area
            await page.evaluate(() => {
                const el = document.querySelector('[role="button"][tabindex="0"]');
                if (el) el.click();
            });
            await page.waitForTimeout(1000);
        }
        await page.waitForTimeout(1500);

        // If image: click photo/video button to attach image
        if (imagePath && fs.existsSync(imagePath)) {
            try {
                // Look for the photo button in composer
                const photoSelectors = [
                    '[aria-label="Photo/video"]',
                    'input[type="file"][accept*="image"]',
                    '[data-testid="media-attachment-button"]',
                    'div[aria-label*="Photo"]',
                ];
                let fileInput = null;

                for (const sel of photoSelectors) {
                    try {
                        const el = page.locator(sel).first();
                        if (await el.count() > 0) {
                            if (sel.includes('input[type="file"]')) {
                                fileInput = el;
                            } else {
                                await el.click({ timeout: 3000 });
                                await page.waitForTimeout(1000);
                            }
                            break;
                        }
                    } catch (e) { /* next */ }
                }

                // After clicking photo button, find file input
                if (!fileInput) {
                    fileInput = page.locator('input[type="file"]').first();
                }

                if (await fileInput.count() > 0) {
                    await fileInput.setInputFiles(imagePath);
                    await page.waitForTimeout(3000);
                    imageStatus = 'uploaded';
                    log('/post-facebook-ai', 'info', 'Image uploaded to composer');
                }
            } catch (e) {
                log('/post-facebook-ai', 'warn', `Image upload failed: ${e.message}`);
                imageStatus = 'upload_failed';
            }
        }

        // Type the post text
        const textBoxes = [
            '[aria-label^="What\'s on your mind"][contenteditable="true"]',
            'div[data-lexical-editor="true"]',
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
        ];
        let textBox = null;
        for (const sel of textBoxes) {
            try {
                const el = page.locator(sel).first();
                if (await el.count() > 0) { textBox = el; break; }
            } catch (e) { /* next */ }
        }

        if (!textBox) {
            return res.status(500).json({ success: false, error: 'Post textbox not found', image_status: imageStatus });
        }

        await textBox.click();
        await page.waitForTimeout(500);
        await textBox.type(postContent, { delay: 20 });
        await page.waitForTimeout(800);

        // Click Post button
        const postBtns = ['[aria-label="Post"]', 'button[type="submit"]', 'div[aria-label="Post"]'];
        let posted = false;
        for (const sel of postBtns) {
            try {
                const el = page.locator(sel).first();
                if (await el.count() > 0) { await el.click({ timeout: 3000 }); posted = true; break; }
            } catch (e) { /* next */ }
        }

        if (!posted) return res.status(500).json({ success: false, error: 'Post button not found', image_status: imageStatus });

        await page.waitForTimeout(3000);

        // Cleanup temp image
        if (imagePath && fs.existsSync(imagePath)) {
            try { fs.unlinkSync(imagePath); } catch (e) { }
        }

        log('/post-facebook-ai', 'ok', `Posted with image_status=${imageStatus}`);
        res.json({ success: true, message: 'Posted to Facebook', image_status: imageStatus });

    } catch (e) {
        // Cleanup temp image on error
        if (imagePath && fs.existsSync(imagePath)) { try { fs.unlinkSync(imagePath); } catch (_) { } }
        log('/post-facebook-ai', 'error', e.message);
        res.status(500).json({ success: false, error: e.message, image_status: imageStatus });
    }
});

// ─── Server Start ────────────────────────────────────────────────────────────

app.listen(PORT, async () => {
    log('server', 'ok', `Listening on port ${PORT}`);

    // Auto-Launch Headless on Start
    log('startup', 'info', 'Auto-launching background services...');
    launchService('whatsapp', true);
    launchService('facebook', true);
});

// Graceful Exit
process.on('SIGINT', async () => {
    log('shutdown', 'info', 'Closing contexts...');
    if (SERVICES.whatsapp.context) await SERVICES.whatsapp.context.close();
    if (SERVICES.facebook.context) await SERVICES.facebook.context.close();
    process.exit(0);
});
