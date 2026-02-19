/**
 * Email MCP Server (HTTP)
 * Listens on port 3000 for POST requests to perform actions.
 */

const express = require('express');
const bodyParser = require('body-parser');
const nodemailer = require('nodemailer');
const fs = require('fs');
const path = require('path');
const { postToLinkedIn } = require('./linkedin_mcp');

const app = express();

const port = 3000;

app.use(bodyParser.json());

// Endpoint: Root (Health Check)
app.get('/', (req, res) => {
    res.send('Silver Tier MCP Server is Running! 🚀');
});

// Load environment variables
function loadEnv() {
    const envPath = path.join(__dirname, '..', '.env');
    if (fs.existsSync(envPath)) {
        const envConfig = fs.readFileSync(envPath, 'utf-8');
        envConfig.split('\n').forEach(line => {
            const match = line.match(/^([^=]+)=(.*)$/);
            if (match) {
                const key = match[1].trim();
                const value = match[2].trim().replace(/^['"]|['"]$/g, '');
                process.env[key] = value;
            }
        });
    }
}

loadEnv();

const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
        user: process.env.GMAIL_USER,
        pass: process.env.GMAIL_APP_PASSWORD
    }
});

// Endpoint: Send Email
app.post('/send-email', async (req, res) => {
    console.log(`[MCP] Received send-email request`);
    const { to, subject, body } = req.body;

    if (!to || !subject || !body) {
        return res.status(400).json({ success: false, error: "Missing required fields: to, subject, body" });
    }

    try {
        const info = await transporter.sendMail({
            from: process.env.GMAIL_USER,
            to: to,
            subject: subject,
            text: body
        });
        console.log(`[MCP] Email sent: ${info.messageId}`);
        res.json({ success: true, messageId: info.messageId });
    } catch (error) {
        console.error(`[MCP] Error sending email: ${error.message}`);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Endpoint: Send WhatsApp (Stub)
app.post('/send-whatsapp', (req, res) => {
    console.log(`[MCP] Received send-whatsapp request`);
    const { contact, message } = req.body;
    console.log(`[Whatsapp Stub] Sending to ${contact}: ${message}`);
    res.json({ success: true, status: "Stubbed - Message logged" });
});

// Endpoint: Post LinkedIn
app.post('/post-linkedin', async (req, res) => {
    console.log(`[MCP] Received post-linkedin request`);
    const { content } = req.body;

    if (!content) {
        return res.status(400).json({ success: false, error: "Missing required content" });
    }

    // Call the Playwright module
    const result = await postToLinkedIn(content);

    if (result.success) {
        res.json({ success: true, status: result.message });
    } else {
        res.status(500).json({ success: false, error: result.error });
    }
});

app.listen(port, () => {
    console.log(`[MCP Server] Listening at http://localhost:${port}`);
});
