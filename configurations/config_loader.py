import json
import os

# Path to credentials.json (in same folder)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")

def load_credentials():
    """Load sensitive credentials from credentials.json"""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

# Global variable so agents can just `from config_loader import creds`
creds = load_credentials()
