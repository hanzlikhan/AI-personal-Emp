"""
Gmail Watcher - Monitors Gmail for new important emails

This script uses the Google Gmail API to monitor a Gmail account for new unread emails,
particularly focusing on important messages. When new emails are detected, it creates
a markdown file in the /Needs_Action folder with proper YAML frontmatter for processing.

Installation Instructions:
1. Enable Gmail API in Google Cloud Console
2. Download credentials.json from Google Cloud Console
3. Install required packages: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Usage Instructions:
1. Place credentials.json in the same directory as this script
2. Run the script: python gmail_watcher.py
3. Authorize the application in your browser when prompted
4. The script will continuously monitor for new emails

Testing Instructions:
1. Send yourself a test email with "Test" in the subject
2. Run the script and verify it detects the email
3. Check that a corresponding .md file appears in /Needs_Action/
"""

import os
import pickle
import time
from datetime import datetime
from pathlib import Path
import base64
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scopes required for reading, sending, and drafting Gmail
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose'
]

def authenticate_gmail():
    """
    Authenticate and return Gmail service object
    """
    creds = None
    
    # Token file stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no valid credentials, request authorization
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('gmail', 'v1', credentials=creds)

def decode_email_body(message_part):
    """
    Decode email body from base64 encoding
    """
    if 'data' in message_part['body']:
        encoded_data = message_part['body']['data']
        decoded_bytes = base64.urlsafe_b64decode(encoded_data)
        decoded_str = decoded_bytes.decode('utf-8')
        return decoded_str
    return ""

def get_email_details(service, msg_id):
    """
    Get detailed information about a specific email
    """
    try:
        message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        
        # Extract headers
        headers = {header['name'].lower(): header['value'] for header in message['payload']['headers']}
        
        # Extract body if available
        body = ""
        payload = message.get('payload', {})
        parts = payload.get('parts', [])
        
        if parts:
            # Look for plain text part
            for part in parts:
                if part.get('mimeType') == 'text/plain':
                    body = decode_email_body(part)
                    break
            # If no plain text, try HTML
            if not body:
                for part in parts:
                    if part.get('mimeType') == 'text/html':
                        body = decode_email_body(part)
                        break
        else:
            # Single part message
            body = decode_email_body(payload)
        
        return {
            'id': msg_id,
            'from': headers.get('from', ''),
            'to': headers.get('to', ''),
            'subject': headers.get('subject', ''),
            'date': headers.get('date', ''),
            'body': body[:500],  # Limit body length
            'labels': message.get('labelIds', []),
            'threadId': message.get('threadId', '')
        }
    except Exception as e:
        print(f"Error getting email details: {e}")
        return None

def create_message(to, subject, body, thread_id=None):
    """
    Create a message for an email.
    """
    from email.mime.text import MIMEText
    
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject
    
    raw = base64.urlsafe_b64encode(message.as_bytes())
    raw = raw.decode()
    
    result = {'raw': raw}
    if thread_id:
        result['threadId'] = thread_id
        
    return result

def create_draft(service, email_data):
    """
    Create a draft email as a reply.
    """
    try:
        to = email_data['from']
        subject = f"Re: {email_data['subject']}"
        body = email_data.get('reply_body', "This is a drafted reply.")
        thread_id = email_data.get('threadId')
        
        message = create_message(to, subject, body, thread_id)
        draft = service.users().drafts().create(userId='me', body={'message': message}).execute()
        
        print(f"Draft created with ID: {draft['id']}")
        return draft
    except Exception as e:
        print(f"Error creating draft: {e}")
        return None

def send_email(service, email_data):
    """
    Send an email.
    """
    try:
        to = email_data['from']
        subject = f"Re: {email_data['subject']}"
        body = email_data.get('reply_body', "This is an automated reply.")
        thread_id = email_data.get('threadId')
        
        message = create_message(to, subject, body, thread_id)
        sent_message = service.users().messages().send(userId='me', body=message).execute()
        
        print(f"Message sent with ID: {sent_message['id']}")
        return sent_message
    except Exception as e:
        print(f"Error sending email: {e}")
        return None

def create_needs_action_file(email_data):
    """
    Create a markdown file in /Needs_Action with email data
    """
    try:
        # Determine priority based on labels or other factors
        priority = 'high' if 'IMPORTANT' in email_data['labels'] else 'normal'
        
        # Create filename based on subject and timestamp
        subject_clean = "".join(c for c in email_data['subject'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not subject_clean:
            subject_clean = "email_no_subject"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{subject_clean}.md"
        
        # Ensure /Needs_Action directory exists
        needs_action_dir = Path("../Needs_Action")
        needs_action_dir.mkdir(exist_ok=True)
        
        filepath = needs_action_dir / filename
        
        # Create YAML frontmatter
        yaml_frontmatter = f"""---
type: email
from: "{email_data['from']}"
subject: "{email_data['subject']}"
received: "{datetime.now().isoformat()}"
priority: {priority}
status: pending
---

## Email Details

**From:** {email_data['from']}
**Subject:** {email_data['subject']}
**Date:** {email_data['date']}

## Body Preview

{email_data['body']}

---
*Processed by Gmail Watcher at {datetime.now().isoformat()}*
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(yaml_frontmatter)
        
        print(f"Created file: {filepath} for email from {email_data['from']}")
        return filepath
    
    except Exception as e:
        print(f"Error creating needs action file: {e}")
        return None

def check_new_emails(service):
    """
    Check for new unread emails and process them
    """
    try:
        # Query for unread emails
        results = service.users().messages().list(
            userId='me',
            q='is:unread',
            maxResults=10  # Limit to last 10 unread emails
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            print("No new unread emails found.")
            return
        
        print(f"Found {len(messages)} new unread emails")
        
        for msg in messages:
            email_details = get_email_details(service, msg['id'])
            
            if email_details:
                # Create needs action file for the email
                create_needs_action_file(email_details)
                
                # Mark as read after processing
                service.users().messages().modify(
                    userId='me',
                    id=msg['id'],
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
                
                print(f"Processed and marked as read: {email_details['subject']}")
    
    except HttpError as error:
        print(f"Gmail API error: {error}")

def main():
    """
    Main function to run the Gmail watcher
    """
    print("Starting Gmail Watcher...")
    
    try:
        # Authenticate with Gmail
        service = authenticate_gmail()
        print("Successfully authenticated with Gmail API")
        
        # Check for new emails
        check_new_emails(service)
        
        print("Gmail Watcher completed check.")
        
    except Exception as e:
        print(f"Error in Gmail Watcher: {e}")

if __name__ == "__main__":
    main()