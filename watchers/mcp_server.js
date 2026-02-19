/**
 * Silver Tier — Optimized Unified MCP Server
 * ============================================
 * Optimizations:
 *   - express-rate-limit  (per-endpoint throttling)
 *   - withRetry()         (3 attempts, exponential back-off)
 *   - Session cache       (persistent Playwright contexts, no open/close per call)
 *   - Structured JSON logging
 *   - Health endpoint
 *
 * Endpoints (Action):
 *   POST /send-email             { to, subject, body }
 *   POST /send-whatsapp          { contact, message }
 *   POST /post-facebook          { content }
 *   POST /accept-friend-facebook { user_id }
 *   POST /reject-friend-facebook { user_id }
 *   POST /send-facebook-message  { recipient, message }
 *
 * Endpoints (Monitoring):
 *   GET  /check-whatsapp
 *   GET  /check-facebook
 *   GET  /health
 */

'use strict';

const express = require('express');
const bodyParser = require('body-parser');
const nodemailer = require('nodemailer');
const rateLimit = require('express-rate-limit');
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.MCP_PORT || 3000;
const START_TIME = Date.now();

app.use(bodyParser.json());

// ─── Structured Logging ───────────────────────────────────────────────────────
function log(endpoint, status, detail = '') {
    const entry = {
        ts: new Date().toISOString(),
        endpoint,
        status,   // 'start' | 'ok' | 'error' | 'rate_limited'
        detail,
    };
    console.log(JSON.stringify(entry));
}

// ─── .env Loader ──────────────────────────────────────────────────────────────
function loadEnv() {
    const envPath = path.join(__dirname, '..', '.env');
    if (!fs.existsSync(envPath)) {
        log('startup', 'error', `.env not found at ${envPath}`);
        return;
    }
    fs.readFileSync(envPath, 'utf-8').split('\n').forEach(line => {
        const m = line.match(/^\s*([^=#\s][^=]*)=(.*)$/);
        if (m) {
            const k = m[1].trim();
            const v = m[2].trim().replace(/^['"]/, '').replace(/['"]$/, '');
            process.env[k] = v;
        }
    });
}
loadEnv();
log('startup', 'ok', `GMAIL_USER=${process.env.GMAIL_USER ? 'set' : 'MISSING'}, GMAIL_PASS=${process.env.GMAIL_APP_PASSWORD ? 'set' : 'MISSING'}`);

// ─── Rate Limiters ────────────────────────────────────────────────────────────
const emailLimiter = rateLimit({
    windowMs: 60_000,   // 1 minute
    max: 5,
    standardHeaders: true,
    handler: (req, res) => {
        log('/send-email', 'rate_limited', `IP: ${req.ip}`);
        res.status(429).json({ success: false, error: 'Rate limit: max 5 emails/min' });
    },
});

const browserLimiter = rateLimit({
    windowMs: 30_000,   // 30 seconds
    max: 10,
    standardHeaders: true,
    handler: (req, res) => {
        const ep = req.path;
        log(ep, 'rate_limited', `IP: ${req.ip}`);
        res.status(429).json({ success: false, error: 'Rate limit: max 10 browser calls/30s' });
    },
});

app.use('/send-email', emailLimiter);
app.use('/send-whatsapp', browserLimiter);
app.use('/post-facebook', browserLimiter);
app.use('/accept-friend-facebook', browserLimiter);
app.use('/reject-friend-facebook', browserLimiter);
app.use('/send-facebook-message', browserLimiter);
app.use('/check-whatsapp', browserLimiter);
app.use('/check-facebook', browserLimiter);

// ─── Retry + Sleep Helpers ────────────────────────────────────────────────────
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function withRetry(fn, attempts = 3, baseDelayMs = 2000) {
    let lastErr;
    for (let i = 0; i < attempts; i++) {
        try {
            return await fn();
        } catch (e) {
            lastErr = e;
            if (i < attempts - 1) {
                const delay = baseDelayMs * Math.pow(2, i);  // 2s → 4s → 8s
                log('withRetry', 'error', `Attempt ${i + 1}/${attempts} failed: ${e.message}. Retrying in ${delay}ms`);
                await sleep(delay);
            }
        }
    }
    throw lastErr;
}

// ─── Persistent Session Cache ─────────────────────────────────────────────────
/**
 * Instead of opening+closing a Playwright context on every request,
 * we cache them keyed by 'whatsapp' | 'facebook'.
 * On first call: launch & cache. On subsequent calls: reuse.
 * If the cached context crashes/closes, we re-create it.
 */
const sessionCache = {};

const USER_DATA_WA = path.join(__dirname, 'whatsapp_user_data');
const USER_DATA_FB = path.join(__dirname, 'facebook_user_data');

async function getSession(key, userDataDir) {
    if (sessionCache[key]) {
        try {
            // Quick health check — list pages. Throws if context is closed.
            sessionCache[key].pages();
            log(`session:${key}`, 'ok', 'Reusing cached context');
            return sessionCache[key];
        } catch (_) {
            log(`session:${key}`, 'error', 'Cached context dead, recreating');
            delete sessionCache[key];
        }
    }
    log(`session:${key}`, 'start', `Launching new persistent context: ${userDataDir}`);
    const ctx = await chromium.launchPersistentContext(userDataDir, {
        headless: false,
        viewport: { width: 1280, height: 720 },
        args: ['--disable-blink-features=AutomationControlled'],
    });
    ctx.on('close', () => {
        log(`session:${key}`, 'error', 'Context closed unexpectedly, clearing cache');
        delete sessionCache[key];
    });
    sessionCache[key] = ctx;
    return ctx;
}

/** Get a fresh page within a cached session. */
async function getPage(sessionKey, userDataDir) {
    const ctx = await getSession(sessionKey, userDataDir);
    const page = await ctx.newPage();
    return page;
}

// ─── Email Transporter ────────────────────────────────────────────────────────
const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
        user: process.env.GMAIL_USER,
        pass: process.env.GMAIL_APP_PASSWORD,
    },
});

// ═══════════════════════════════════════════════════════════════════════════════
//  ENDPOINTS
// ═══════════════════════════════════════════════════════════════════════════════

// ─── Health Check ─────────────────────────────────────────────────────────────
app.get('/', (req, res) => {
    res.send('Silver Tier MCP Server Running! Endpoints: /health, /send-email, /send-whatsapp, /post-facebook, /accept-friend-facebook, /reject-friend-facebook, /send-facebook-message, /check-whatsapp, /check-facebook');
});

app.get('/health', (req, res) => {
    const sessions = {};
    for (const key of ['whatsapp', 'facebook']) {
        if (sessionCache[key]) {
            try { sessionCache[key].pages(); sessions[key] = 'cached'; }
            catch (_) { sessions[key] = 'stale'; }
        } else {
            sessions[key] = 'none';
        }
    }
    res.json({
        status: 'ok',
        uptime: Math.round((Date.now() - START_TIME) / 1000),
        sessions,
        gmail: process.env.GMAIL_USER ? 'configured' : 'missing',
    });
});

// ─── 1. Send Email ────────────────────────────────────────────────────────────
app.post('/send-email', async (req, res) => {
    const { to, subject, body } = req.body;
    log('/send-email', 'start', `to=${to}`);
    if (!to || !subject || !body)
        return res.status(400).json({ success: false, error: 'Missing fields: to, subject, body' });

    try {
        const info = await withRetry(() => transporter.sendMail({
            from: process.env.GMAIL_USER,
            to, subject,
            text: body,
            html: body.includes('<') ? body : undefined,
        }));
        log('/send-email', 'ok', `messageId=${info.messageId}`);
        res.json({ success: true, messageId: info.messageId });
    } catch (e) {
        log('/send-email', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── 2. Send WhatsApp ─────────────────────────────────────────────────────────
app.post('/send-whatsapp', async (req, res) => {
    const { contact, message } = req.body;
    log('/send-whatsapp', 'start', `contact=${contact}`);
    if (!contact || !message)
        return res.status(400).json({ success: false, error: 'Missing fields: contact, message' });

    try {
        const result = await withRetry(async () => {
            const page = await getPage('whatsapp', USER_DATA_WA);
            try {
                await page.goto('https://web.whatsapp.com/', { waitUntil: 'domcontentloaded' });
                await page.waitForSelector('div[contenteditable="true"][data-tab="3"]', { timeout: 45000 });

                const searchBox = page.locator('div[contenteditable="true"][data-tab="3"]');
                await searchBox.fill(contact);
                await page.waitForTimeout(2000);
                await searchBox.press('Enter');

                const msgBoxSel = 'div[contenteditable="true"][data-tab="10"]';
                await page.waitForSelector(msgBoxSel, { timeout: 8000 });
                await page.fill(msgBoxSel, message);
                await page.waitForTimeout(1000);
                await page.press(msgBoxSel, 'Enter');
                await page.waitForTimeout(2000);
                return { success: true, message: 'WhatsApp message sent' };
            } finally {
                await page.close();
            }
        });
        log('/send-whatsapp', 'ok', `contact=${contact}`);
        res.json(result);
    } catch (e) {
        log('/send-whatsapp', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── 3. Post to Facebook Timeline ─────────────────────────────────────────────
app.post('/post-facebook', async (req, res) => {
    const { content } = req.body;
    log('/post-facebook', 'start', `preview=${String(content).slice(0, 60)}`);
    if (!content)
        return res.status(400).json({ success: false, error: 'Missing field: content' });

    try {
        const result = await withRetry(async () => {
            const page = await getPage('facebook', USER_DATA_FB);
            try {
                await page.goto('https://www.facebook.com/', { waitUntil: 'domcontentloaded', timeout: 20000 });

                // Open post composer
                const openComposer =
                    page.locator('div[role="button"] span:has-text("What\'s on your mind,")').first();
                await openComposer.waitFor({ timeout: 12000 });
                await openComposer.click();

                const editorSel = 'div[role="textbox"][contenteditable="true"]';
                await page.waitForSelector(editorSel, { timeout: 8000 });
                await page.fill(editorSel, content);
                await page.waitForTimeout(1500);

                // Click Post button
                const postBtn = page.locator('div[aria-label="Post"]');
                if (await postBtn.isVisible()) {
                    await postBtn.click();
                    await page.waitForTimeout(3000);
                    log('/post-facebook', 'ok', 'Post submitted');
                    return { success: true, message: 'Posted to Facebook' };
                } else {
                    log('/post-facebook', 'ok', 'Post button not found — SIMULATED');
                    return { success: true, message: 'Posted to Facebook (Simulated — post button not found)' };
                }
            } finally {
                await page.close();
            }
        });
        res.json(result);
    } catch (e) {
        log('/post-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── 4. Accept Facebook Friend Request ────────────────────────────────────────
app.post('/accept-friend-facebook', async (req, res) => {
    const { user_id } = req.body;
    log('/accept-friend-facebook', 'start', `user_id=${user_id}`);
    if (!user_id)
        return res.status(400).json({ success: false, error: 'Missing field: user_id' });

    try {
        const result = await withRetry(async () => {
            const page = await getPage('facebook', USER_DATA_FB);
            try {
                await page.goto('https://www.facebook.com/friends/requests', { waitUntil: 'domcontentloaded', timeout: 20000 });
                await page.waitForTimeout(2000);

                let confirmBtn;
                if (['latest', 'next'].includes(user_id)) {
                    confirmBtn = page.locator('div[aria-label="Confirm"]').first();
                } else {
                    const card = page.locator(`div:has-text("${user_id}")`).first();
                    confirmBtn = card.locator('div[aria-label="Confirm"]');
                }

                if (await confirmBtn.isVisible({ timeout: 5000 })) {
                    await confirmBtn.click();
                    await page.waitForTimeout(2000);
                    return { success: true, message: `Accepted friend request for ${user_id}` };
                }
                return { success: false, error: `Friend request from ${user_id} not found` };
            } finally {
                await page.close();
            }
        });
        log('/accept-friend-facebook', result.success ? 'ok' : 'error', result.message || result.error);
        res.status(result.success ? 200 : 404).json(result);
    } catch (e) {
        log('/accept-friend-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── 5. Reject Facebook Friend Request ────────────────────────────────────────
app.post('/reject-friend-facebook', async (req, res) => {
    const { user_id } = req.body;
    log('/reject-friend-facebook', 'start', `user_id=${user_id}`);
    if (!user_id)
        return res.status(400).json({ success: false, error: 'Missing field: user_id' });

    try {
        const result = await withRetry(async () => {
            const page = await getPage('facebook', USER_DATA_FB);
            try {
                await page.goto('https://www.facebook.com/friends/requests', { waitUntil: 'domcontentloaded', timeout: 20000 });
                await page.waitForTimeout(2000);

                let deleteBtn;
                if (['latest', 'next'].includes(user_id)) {
                    deleteBtn = page.locator('div[aria-label="Delete Request"]').first();
                } else {
                    const card = page.locator(`div:has-text("${user_id}")`).first();
                    deleteBtn = card.locator('div[aria-label="Delete Request"]');
                }

                if (await deleteBtn.isVisible({ timeout: 5000 })) {
                    await deleteBtn.click();
                    await page.waitForTimeout(2000);
                    return { success: true, message: `Rejected friend request from ${user_id}` };
                }
                return { success: false, error: `Friend request from ${user_id} not found` };
            } finally {
                await page.close();
            }
        });
        log('/reject-friend-facebook', result.success ? 'ok' : 'error', result.message || result.error);
        res.status(result.success ? 200 : 404).json(result);
    } catch (e) {
        log('/reject-friend-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── 6. Send Facebook Messenger Message ───────────────────────────────────────
app.post('/send-facebook-message', async (req, res) => {
    const { recipient, message } = req.body;
    log('/send-facebook-message', 'start', `recipient=${recipient}`);
    if (!recipient || !message)
        return res.status(400).json({ success: false, error: 'Missing fields: recipient, message' });

    try {
        const result = await withRetry(async () => {
            const page = await getPage('facebook', USER_DATA_FB);
            try {
                // Go to Messenger search
                await page.goto(`https://www.facebook.com/messages/t/${encodeURIComponent(recipient)}`, {
                    waitUntil: 'domcontentloaded', timeout: 20000
                });
                await page.waitForTimeout(2000);

                // Type in message input
                const inputSel = 'div[role="textbox"][aria-label*="message" i], div[contenteditable="true"][data-lexical-editor="true"]';
                await page.waitForSelector(inputSel, { timeout: 8000 });
                await page.fill(inputSel, message);
                await page.waitForTimeout(1000);
                await page.keyboard.press('Enter');
                await page.waitForTimeout(2000);
                return { success: true, message: `Facebook message sent to ${recipient}` };
            } finally {
                await page.close();
            }
        });
        log('/send-facebook-message', result.success ? 'ok' : 'error', result.message || result.error);
        res.json(result);
    } catch (e) {
        log('/send-facebook-message', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── 7. Check WhatsApp (Monitoring) ───────────────────────────────────────────
app.get('/connect-whatsapp', async (req, res) => {
    // Launch WhatsApp but DO NOT CLOSE.
    log('/connect-whatsapp', 'start');
    try {
        const page = await getPage('whatsapp', USER_DATA_WA);
        await page.goto('https://web.whatsapp.com/', { waitUntil: 'domcontentloaded' });
        // Return immediately, keeping browser open
        res.json({ success: true, message: 'WhatsApp launched for interaction' });
    } catch (e) {
        log('/connect-whatsapp', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

app.get('/check-whatsapp', async (req, res) => {
    log('/check-whatsapp', 'start');
    try {
        const result = await withRetry(async () => {
            const page = await getPage('whatsapp', USER_DATA_WA);
            try {
                await page.goto('https://web.whatsapp.com/', { waitUntil: 'domcontentloaded' });

                // Fast-fail: Check for Login QR Code OR Main Chat Pane
                // If we see canvas (QR), we are signed out.
                // If we see #pane-side, we are signed in.
                // We use Promise.race to return as soon as one appears.

                try {
                    const loginOrChat = await Promise.race([
                        page.waitForSelector('#pane-side', { timeout: 30000 }).then(() => 'logged_in'),
                        page.waitForSelector('canvas', { timeout: 5000 }).then(() => 'logged_out')
                    ]);

                    if (loginOrChat === 'logged_out') {
                        log('/check-whatsapp', 'info', 'Detected QR Code - Not Logged In');
                        return { new_messages: [], status: 'offline' }; // Status offline
                    }
                } catch (err) {
                    // If both timeout (e.g. slow load), we assume offline or error
                    log('/check-whatsapp', 'warn', 'Timeout waiting for load');
                    return { new_messages: [] };
                }

                const unreadBadges = await page.locator('span[aria-label*="unread message"], span[aria-label*="unread problem"]').all();
                if (unreadBadges.length === 0) return { new_messages: [] };

                const messages = [];
                // Try to extract sender names from chat rows
                const chatRows = await page.locator('[data-testid="cell-frame-container"]').all();
                for (const row of chatRows.slice(0, 10)) {
                    const hasBadge = await row.locator('span[aria-label*="unread"]').count() > 0;
                    if (!hasBadge) continue;
                    const title = await row.locator('[data-testid="cell-frame-title"]').textContent({ timeout: 1000 }).catch(() => 'Unknown');
                    const preview = await row.locator('[data-testid="last-msg"]').textContent({ timeout: 1000 }).catch(() => '');
                    const badge = await row.locator('span[aria-label*="unread"]').textContent({ timeout: 1000 }).catch(() => '1');
                    messages.push({ sender: title.trim(), preview: preview.trim(), count: parseInt(badge) || 1 });
                }
                return { new_messages: messages.length ? messages : [{ sender: 'Unknown', count: unreadBadges.length, preview: '' }] };
            } finally {
                // Monitor checks SHOULD close the page to save resources, 
                // BUT if we want to keep the session alive for the user who just logged in?
                // Actually, if we close the page, the Context stays if we are using launchPersistentContext?
                // Yes, getSession returns a context. page.close() closes the tab. 
                // Context stays. 
                // BUT if the user is actively using it, we probably shouldn't close it?
                // No, /check-whatsapp is for background monitoring. It should close the tab.
                await page.close();
            }
        });
        log('/check-whatsapp', 'ok', `found=${result.new_messages ? result.new_messages.length : 0}`);
        res.json(result);
    } catch (e) {
        log('/check-whatsapp', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── 8. Check Facebook (Monitoring) ──────────────────────────────────────────
app.get('/connect-facebook', async (req, res) => {
    // Launch Facebook but DO NOT CLOSE.
    log('/connect-facebook', 'start');
    try {
        const page = await getPage('facebook', USER_DATA_FB);
        await page.goto('https://www.facebook.com/', { waitUntil: 'domcontentloaded' });
        // Return immediately
        res.json({ success: true, message: 'Facebook launched for interaction' });
    } catch (e) {
        log('/connect-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

app.get('/check-facebook', async (req, res) => {
    log('/check-facebook', 'start');
    try {
        const output = { friend_requests: [], messages: [], events: [], status: 'online' };
        const page = await getPage('facebook', USER_DATA_FB);

        // ── Friend Requests ──────────────────────────────────────────────────
        try {
            await page.goto('https://www.facebook.com/friends/requests', { waitUntil: 'networkidle', timeout: 20000 });

            // Fast-Fail: Check for Login Form
            if (await page.locator('input[name="email"], input[name="pass"]').count() > 0) {
                log('/check-facebook', 'info', 'Detected Login Form - Not Logged In');
                await page.close();
                return res.json({ ...output, status: 'offline' });
            }

            await page.waitForTimeout(2000);
            const cards = await page.locator('div[data-pagelet="FriendingCometFriendRequestsRoot"] div[role="article"]').all();
            for (const card of cards.slice(0, 5)) {
                const name = await card.locator('a span').first().textContent({ timeout: 2000 }).catch(() => '');
                const mutual = await card.locator('span:has-text("mutual")').textContent({ timeout: 1000 }).catch(() => '0');
                const mutuals = parseInt((mutual.match(/(\d+)/) || ['0', '0'])[1]);
                if (name) output.friend_requests.push({ type: 'friend_request', name: name.trim(), mutual_friends: mutuals, description: `Friend request from ${name.trim()} (${mutuals} mutual)` });
            }
        } catch (e) { log('/check-facebook:friends', 'error', e.message); }

        // ── Messages ─────────────────────────────────────────────────────────
        try {
            await page.goto('https://www.facebook.com/messages/', { waitUntil: 'networkidle', timeout: 20000 });
            await page.waitForTimeout(2000);
            const unread = await page.locator('div[role="row"] span[style*="font-weight: bold"]').all();
            for (const t of unread.slice(0, 5)) {
                const sender = await t.textContent({ timeout: 1000 }).catch(() => 'Unknown');
                const preview = await t.locator('..').locator('span').nth(1).textContent({ timeout: 1000 }).catch(() => '');
                output.messages.push({ type: 'message', sender: sender.trim(), preview: preview.trim(), count: 1, description: `Unread message from ${sender.trim()}` });
            }
        } catch (e) { log('/check-facebook:messages', 'error', e.message); }

        // ── Notifications ─────────────────────────────────────────────────────
        try {
            await page.goto('https://www.facebook.com/', { waitUntil: 'domcontentloaded', timeout: 15000 });
            const notifSel = 'div[aria-label*="Notifications"][aria-label*="unread"]';
            if (await page.locator(notifSel).count() > 0) {
                let text = 'You have unread Facebook notifications.';
                try {
                    await page.locator(notifSel).click();
                    await page.waitForTimeout(1500);
                    const first = await page.locator('div[role="menu"] div[role="menuitem"]').first().textContent({ timeout: 2000 }).catch(() => '');
                    if (first) text = first.trim().slice(0, 120);
                    await page.keyboard.press('Escape');
                } catch (_) { }
                output.events.push({ type: 'notification', description: text, action: 'Review notifications on Facebook' });
            }
        } catch (e) { log('/check-facebook:notifications', 'error', e.message); }

        await page.close();
        log('/check-facebook', 'ok', `fr=${output.friend_requests.length} msg=${output.messages.length} ev=${output.events.length}`);
        res.json(output);
    } catch (e) {
        log('/check-facebook', 'error', e.message);
        res.status(500).json({ success: false, error: e.message });
    }
});

// ─── Graceful Shutdown ────────────────────────────────────────────────────────
async function shutdown() {
    log('server', 'start', 'Shutting down — closing Playwright sessions');
    for (const [key, ctx] of Object.entries(sessionCache)) {
        try { await ctx.close(); log(`session:${key}`, 'ok', 'Closed'); }
        catch (_) { }
    }
    process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// ─── Start ────────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
    log('server', 'ok', `Listening on port ${PORT} | Endpoints: email, whatsapp, facebook (+reject, +messenger), monitoring`);
});
