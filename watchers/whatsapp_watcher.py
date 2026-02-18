import asyncio
import os
import time
import argparse
import sys
from datetime import datetime
from playwright.async_api import async_playwright
import random

# Configuration
WATCH_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Needs_Action")
USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whatsapp_user_data")

async def monitor_whatsapp():
    print("[WHATSAPP] Starting WhatsApp Watcher...")
    async with async_playwright() as p:
        # Launch browser with persistent context to save login session
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False, # Must be False initially for QR code scan, can be True later if session is saved?? Actually handling headless whatsapp is tricky due to auth. Keeping false for now or letting user decide. 
            # User request said "Run in background", but WhatsApp Web needs a visible window or at least a very good headless setup. 
            # I will set headless=False for the first run logic, but realistically for a "watcher" it might need to hide.
            # However, for stability, let's keep it visible or minimized.
        )
        
        page = await browser.new_page()
        await page.goto("https://web.whatsapp.com/")
        
        print("[WHATSAPP] Please scan QR code if not logged in.")
        try:
            await page.wait_for_selector("div[role='textbox']", timeout=60000) # Wait for chat list or search box
            print("[WHATSAPP] Login detected / Successful.")
        except:
            print("[WHATSAPP] Timeout waiting for login. Please restart and scan QR code quickly.")
            return

        print("[WHATSAPP] Monitoring for new messages...")
        
        # Main loop
        while True:
            try:
                # Detect unread badges
                unread_chats = await page.query_selector_all("span[aria-label*='unread']")
                
                for chat_badge in unread_chats:
                    try:
                        # Click the chat to open it (careful, this marks as read)
                        # To be "autonomous" and "monitor", we need to open it to read content.
                        
                        # Get parent element that is clickable (the chat row)
                        chat_row = await chat_badge.xpath("./../../../../..") # Adjust xpath based on current DOM structure which changes often
                        if chat_row:
                            await chat_row[0].click()
                            await asyncio.sleep(1) # Wait for chat to load
                            
                            # Get last message
                            messages = await page.query_selector_all("div.message-in")
                            if messages:
                                last_message = messages[-1]
                                text_element = await last_message.query_selector("span._11JPr") # Class names change, need reliable selector or text content
                                # Better strategy: Get all text content of the last message container
                                message_text = await last_message.inner_text()
                                
                                # Clean up metadata (time, etc) from text if needed
                                
                                print(f"[WHATSAPP] New message detected: {message_text[:50]}...")
                                
                                # Auto-response logic for simple messages
                                if message_text.lower().strip() in ["hi", "hello", "test"]:
                                    await page.keyboard.type("Auto-reply: Received, processing.")
                                    await page.keyboard.press("Enter")
                                    print("[WHATSAPP] Sent auto-reply.")
                                else:
                                    # Save to Needs_Action for complex messages
                                    save_to_needs_action(message_text, "Unknown_Sender") # Sender name extraction is complex, skipping for MVP
                                
                                # Go back to list (optional, or just stay)
                                
                    except Exception as e:
                        print(f"[WHATSAPP] Error processing chat: {e}")
                
                await asyncio.sleep(5)
                
            except Exception as e:
                print(f"[WHATSAPP] Loop error: {e}")
                await asyncio.sleep(5)

def save_to_needs_action(text, sender):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_whatsapp.md"
    filepath = os.path.join(WATCH_FOLDER, filename)
    
    content = f"""---
type: whatsapp
sender: "{sender}"
received: "{datetime.now().isoformat()}"
status: pending
---

## WhatsApp Message

**From:** {sender}
**Content:**
{text}

---
*Processed by WhatsApp Watcher*
"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[WHATSAPP] Saved task: {filename}")

async def send_message(contact, message):
    print(f"[WHATSAPP] Starting WhatsApp Sender... To: {contact}")
    async with async_playwright() as p:
        # Launch browser with persistent context
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
        )
        
        page = await browser.new_page()
        
        try:
            await page.goto("https://web.whatsapp.com/")
            
            print("[WHATSAPP] Waiting for login / Search box...")
            try:
                await page.wait_for_selector("div[contenteditable='true'][data-tab='3']", timeout=60000) # Search box
                print("[WHATSAPP] Login detected.")
            except:
                print("[WHATSAPP] Not logged in. Please run monitor mode to login first.")
                return

            # Search for contact
            search_box = page.locator("div[contenteditable='true'][data-tab='3']")
            await search_box.click()
            await search_box.fill(contact)
            await asyncio.sleep(2)
            await page.keyboard.press("Enter")
            
            # Wait for chat to open (check for message input)
            message_box_selector = "div[contenteditable='true'][data-tab='10']"
            try:
                await page.wait_for_selector(message_box_selector, timeout=10000)
                print(f"[WHATSAPP] Chat opened for {contact}.")
            except:
                print(f"[WHATSAPP] Could not open chat for {contact}.")
                return
            
            # Type message
            await page.fill(message_box_selector, message)
            await asyncio.sleep(1)
            await page.keyboard.press("Enter")
            
            print("[WHATSAPP] Message sent.")
            await asyncio.sleep(3)

        except Exception as e:
            print(f"[WHATSAPP] Error sending message: {e}")

if __name__ == "__main__":
    if not os.path.exists(WATCH_FOLDER):
        os.makedirs(WATCH_FOLDER)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", nargs=2, metavar=('CONTACT', 'MESSAGE'), help="Send a WhatsApp message")
    args = parser.parse_args()

    if args.send:
        contact, message = args.send
        try:
            asyncio.run(send_message(contact, message))
        except Exception as e:
            print(f"[WHATSAPP] Error: {e}")
    else:
        try:
            asyncio.run(monitor_whatsapp())
        except KeyboardInterrupt:
            print("[WHATSAPP] Stopped.")
