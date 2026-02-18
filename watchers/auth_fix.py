import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Scopes required for reading, sending, and drafting Gmail
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify'
]

def reauthenticate():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
    TOKEN_FILE = os.path.join(BASE_DIR, 'token.pickle')

    print(f"Starting re-authentication process...")
    print(f"Credentials file: {CREDENTIALS_FILE}")
    print(f"Token file target: {TOKEN_FILE}")

    if os.path.exists(TOKEN_FILE):
        print("Removing existing token file to force clean auth...")
        try:
            os.remove(TOKEN_FILE)
            print("Token file removed.")
        except Exception as e:
            print(f"Error removing token file: {e}")

    creds = None
    
    try:
        if not os.path.exists(CREDENTIALS_FILE):
             print(f"CRITICAL: Credentials file not found at {CREDENTIALS_FILE}")
             return

        print("Initiating OAuth flow...")
        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE, SCOPES)
        
        # Using port 0 allows the OS to select an open port
        creds = flow.run_local_server(port=0)
        
        print("Authentication successful!")
        
        # Save credentials for next run
        print(f"Saving new token to {TOKEN_FILE}...")
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
        print("Token saved successfully.")
        
    except Exception as e:
        print(f"Authentication failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reauthenticate()
