'use strict';

const express = require('express');
const bodyParser = require('body-parser');
const nodemailer = require('nodemailer');
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.MCP_PORT || 3000;
const START_TIME = Date.now();

app.use(bodyParser.json());

// ─── configuration ────────────────────────────────────────────────────────────
const USER_DATA_WA = path.join(__dirname, 'whatsapp_user_data');
const USER_DATA_FB = path.join(__dirname, 'facebook_user_data');

// ─── Global State (Persistent Sessions) ──────────────────────────────────────
const SERVICES = {
    whatsapp: { context: null, page: null, type: 'whatsapp', userData: USER_DATA_WA, url: 'https://web.whatsapp.com/' },
    facebook: { context: null, page: null, type: 'facebook', userData: USER_DATA_FB, url: 'https://www.facebook.com/' }
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
    if (!fs.existsSync(envPath)) return;
    fs.readFileSync(envPath, 'utf-8').split('\n').forEach(line => {
        const m = line.match(/^\s*([^=#\s][^=]*)=(.*)$/);
        if (m) process.env[m[1].trim()] = m[2].trim().replace(/^['"]/, '').replace(/['"]$/, '');
    });
}
loadEnv();

// ─── Browser Management ──────────────────────────────────────────────────────

async function launchService(serviceName, headless = true) {
    const svc = SERVICES[serviceName];
    log(`session:${serviceName}`, 'start', `Launching context (Headless: ${headless})`);

    try {
        // 1. Close existing if any
        if (svc.context) {
            try { await svc.context.close(); } catch (e) { }
            svc.context = null;
            svc.page = null;
        }

        // 2. Launch Persistent Context
        svc.context = await chromium.launchPersistentContext(svc.userData, {
            headless: headless,
            viewport: { width: 1280, height: 800 },
            args: ['--no-sandbox', '--disable-setuid-sandbox']
        });

        // 3. Get or Create Page
        const pages = svc.context.pages();
        if (pages.length > 0) {
            svc.page = pages[0];
        } else {
            svc.page = await svc.context.newPage();
        }

        // 4. Navigate (Don't wait strictly for networkidle to avoid hanging)
        await svc.page.goto(svc.url, { waitUntil: 'domcontentloaded', timeout: 30000 });

        log(`session:${serviceName}`, 'ok', `Context active (Headless: ${headless})`);
        return true;
    } catch (e) {
        log(`session:${serviceName}`, 'error', `Launch failed: ${e.message}`);
        return false;
    }
}

async function getPage(serviceName) {
    const svc = SERVICES[serviceName];

    // Case 1: Browser was closed manually by user or crashed
    if (svc.context && (svc.page.isClosed() || !svc.context.pages().length)) {
        log(`session:${serviceName}`, 'warn', 'Page/Context closed unexpectedly. Relauching Headless...');
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

// ─── Endpoints ───────────────────────────────────────────────────────────────

app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        services: {
            whatsapp: !!SERVICES.whatsapp.context,
            facebook: !!SERVICES.facebook.context
        },
        uptime: Math.round((Date.now() - START_TIME) / 1000)
    });
});

// ─── WhatsApp ───

app.get('/connect-whatsapp', async (req, res) => {
    // Switch to VISIBLE mode for user interaction
    const success = await launchService('whatsapp', false);
    res.json({ success, message: success ? 'WhatsApp launched. Scan QR.' : 'Failed to launch.' });
});

app.get('/check-whatsapp', async (req, res) => {
    log('/check-whatsapp', 'start');
    try {
        const page = await getPage('whatsapp');
        if (!page) return res.json({ new_messages: [], status: 'offline' });

        // Evaluate page state
        const result = await page.evaluate(async () => {
            // Check Login
            const loginSelectors = ['#pane-side', '[data-testid="chat-list"]'];
            const qrSelectors = ['canvas', '[data-testid="qrcode"]'];

            const isLoggedIn = loginSelectors.some(s => document.querySelector(s));
            const isQrVisible = qrSelectors.some(s => document.querySelector(s));

            if (isQrVisible || !isLoggedIn) return { status: 'offline', new_messages: [] };

            // Wait for chat list (critical fix)
            const chatSelector = '[data-testid="cell-frame-container"]';
            // Simple waiter pattern inside evaluate (since we can't use page.waitForSelector easily inside evaluate, handling it via DOM check loop)
            // Actually, we can just return what we have. If 0, maybe it's still loading.
            // Better: use page.waitForSelector BEFORE calling evaluate for this.

            return { status: 'online', new_messages: [] }; // Placeholder, scraping happens outside now
        });

        if (result.status === 'offline') return res.json(result);

        // Scrape Chats (Wait up to 5s for list)
        try {
            await page.waitForSelector('[data-testid="cell-frame-container"]', { timeout: 5000 });
        } catch (e) { /* Ignore timeout, might really have 0 chats or network slow */ }

        const chats = await page.evaluate(() => {
            const rows = document.querySelectorAll('[data-testid="cell-frame-container"]');
            const items = [];
            for (const row of Array.from(rows).slice(0, 15)) {
                const titleEl = row.querySelector('[data-testid="cell-frame-title"]');
                const lastMsgEl = row.querySelector('[data-testid="last-msg"]');
                const badgeEl = row.querySelector('span[aria-label*="unread"]');

                items.push({
                    sender: titleEl ? titleEl.innerText : 'Unknown',
                    preview: lastMsgEl ? lastMsgEl.innerText : '',
                    count: badgeEl ? parseInt(badgeEl.innerText) || 1 : 0
                });
            }
            return items;
        });

        log('/check-whatsapp', 'ok', `status=online chats=${chats.length}`);
        res.json({ status: 'online', new_messages: chats });

    } catch (e) {
        log('/check-whatsapp', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── Facebook ───

app.get('/connect-facebook', async (req, res) => {
    const success = await launchService('facebook', false);
    res.json({ success, message: success ? 'Facebook launched. Please login.' : 'Failed to launch.' });
});

app.get('/check-facebook', async (req, res) => {
    log('/check-facebook', 'start');
    try {
        const page = await getPage('facebook');
        if (!page) return res.json({ status: 'offline' });

        // Simple scraper for FB (assuming already on a useful page or navigating)
        // For background monitoring, we assume we are just checking what's visible or quick-checking

        // We will do a quick navigation check if not on a data page
        if (!page.url().includes('facebook.com')) await page.goto('https://www.facebook.com/');

        const output = { friend_requests: [], messages: [], events: [], status: 'online' };

        // Check Login
        if (await page.locator('input[name="email"]').count() > 0) {
            return res.json({ ...output, status: 'offline' });
        }

        // 1. Friend Requests (Scrape if on page, or go there?)
        // To be less intrusive, we only scrape if we are there, OR every 5 mins?
        // For now, let's keep it simple: Go there.
        await page.goto('https://www.facebook.com/friends/requests', { waitUntil: 'domcontentloaded' });

        const rawReqs = await page.evaluate(() => {
            const items = [];
            document.querySelectorAll('div[data-pagelet="FriendingCometFriendRequestsRoot"] div[role="article"]').forEach(card => {
                const name = card.querySelector('span')?.innerText;
                if (name) items.push({ name, mutual: 0 });
            });
            return items;
        });
        if (rawReqs) rawReqs.forEach(r => output.friend_requests.push({ type: 'friend_request', name: r.name, description: 'Friend Request' }));

        // 2. Messages
        await page.goto('https://www.facebook.com/messages/', { waitUntil: 'domcontentloaded' });
        const msgs = await page.evaluate(() => {
            const items = [];
            document.querySelectorAll('div[role="row"] span[style*="font-weight: bold"]').forEach(el => {
                items.push({ sender: el.innerText, count: 1 });
            });
            return items;
        });
        if (msgs) msgs.forEach(m => output.messages.push({ type: 'message', sender: m.sender, count: m.count, preview: 'New Message' }));

        log('/check-facebook', 'ok', `Found ${output.messages.length} msgs`);
        res.json(output);

    } catch (e) {
        log('/check-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── Actions (Email & Others) ───

app.post('/send-email', async (req, res) => {
    const { to, subject, body } = req.body;
    log('/send-email', 'start', `to=${to}`);
    if (!to || !subject || !body) return res.status(400).json({ success: false, error: 'Missing fields' });

    try {
        const info = await transporter.sendMail({
            from: process.env.GMAIL_USER,
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
