"""OPTIONAL: agar computer par Python hai to yeh chala kar YT_REFRESH_TOKEN le sakte hain.
(Bina Python ke tareeqa SETUP guide mein hai: OAuth Playground.)
Usage:  pip install google-auth-oauthlib  &&  python scripts/get_youtube_token.py client_secret.json
"""
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
print("\nYT_CLIENT_ID     =", creds.client_id)
print("YT_CLIENT_SECRET =", creds.client_secret)
print("YT_REFRESH_TOKEN =", creds.refresh_token)
