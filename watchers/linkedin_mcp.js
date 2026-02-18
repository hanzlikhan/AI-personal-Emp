const { chromium } = require('playwright');
const path = require('path');

// Should match where user data is stored for the watcher
const USER_DATA_DIR = path.join(__dirname, 'linkedin_user_data');

async function postToLinkedIn(content) {
    console.log(`[LinkedIn MCP] Starting post... Content: ${content.substring(0, 30)}...`);

    let browserContext;
    try {
        // Use persistent context to reuse login session
        // Note: headless: false requires a display environment.
        browserContext = await chromium.launchPersistentContext(USER_DATA_DIR, {
            headless: false,
            viewport: { width: 1280, height: 720 }
        });

        const page = await browserContext.newPage();
        await page.goto('https://www.linkedin.com/feed/');

        // Check login
        try {
            await page.waitForSelector('.share-box-feed-entry__trigger, button.share-box-feed-entry__trigger', { timeout: 15000 });
        } catch (e) {
            console.error("[LinkedIn MCP] Not logged in or selector mismatch.");
            await browserContext.close();
            return { success: false, error: "Not logged in to LinkedIn. Please run watcher to login." };
        }

        // Click Start Post
        await page.click('.share-box-feed-entry__trigger, button.share-box-feed-entry__trigger');

        // Wait for editor
        const editorSelector = '.ql-editor, .share-creation-state__text-editor .ql-editor';
        await page.waitForSelector(editorSelector);

        // Type content
        await page.fill(editorSelector, content);
        await page.waitForTimeout(2000);

        // Click Post (Uncomment for real action)
        const postButtonSelector = 'button.share-actions__primary-action';
        const postButton = await page.$(postButtonSelector);

        if (postButton && !(await postButton.isDisabled())) {
            // await postButton.click(); 
            console.log("[LinkedIn MCP] (SIMULATION) Clicked Post.");
        } else {
            console.log("[LinkedIn MCP] Post button disabled or missing.");
            await browserContext.close();
            return { success: false, error: "Post button disabled" };
        }

        await page.waitForTimeout(3000);
        await browserContext.close();

        return { success: true, message: "Posted successfully (Simulated)" };

    } catch (error) {
        console.error(`[LinkedIn MCP] Error: ${error.message}`);
        if (browserContext) await browserContext.close();
        return { success: false, error: error.message };
    }
}

module.exports = { postToLinkedIn };
