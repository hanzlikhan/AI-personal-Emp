import os
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify'
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, 'token.pickle')
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')

print(f"Checking for token file at: {TOKEN_FILE}")

if os.path.exists(TOKEN_FILE):
    print("Token file found.")
    try:
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
            print("Token loaded successfully.")
            # If pickle.load succeeds, creds is a Credentials object
            if hasattr(creds, 'valid'):
                print(f"Valid: {creds.valid}")
                print(f"Expired: {creds.expired}")
                print(f"Refresh Token present: {bool(creds.refresh_token)}")
                
                try:
                    if creds.expired and creds.refresh_token:
                        print("Token is expired, attempting refresh...")
                        creds.refresh(Request())
                        print("Refresh successful!")
                    elif not creds.valid:
                        if creds.expired and creds.refresh_token:
                             print("Invalid but has refresh token, trying refresh...")
                             creds.refresh(Request())
                             print("Refresh successful!")
                        else:
                             print("Token is invalid and cannot be refreshed.")
                    else:
                        print("Token appears valid.")
                except Exception as e:
                    print(f"Refresh failed with error: {e}")
                    # If refresh fails, it's often a 400 Bad Request error from Google
                    print("This confirms the refresh token is invalid or revoked.")
            else:
                print("Loaded object is not a valid Credentials object.")

    except Exception as e:
        print(f"Error loading token pickle: {e}")
else:
    print("Token file NOT found.")

if os.path.exists(CREDENTIALS_FILE):
    print(f"Credentials file found at: {CREDENTIALS_FILE}")
else:
    print("Credentials file NOT found.")
