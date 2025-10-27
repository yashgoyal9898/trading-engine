import os
import json
import requests
from datetime import date
from dotenv import load_dotenv
from common_utils.error_handling import error_handling
from common_utils.logger import logger

load_dotenv()

@error_handling
class FyersTokenManager:
    def __init__(self, env_path=".env"):
        self.env_path = env_path
        self.url = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
        self.headers = {"Content-Type": "application/json"}

        self.app_id_hash = os.getenv("APP_ID_HASH")
        self.refresh_token = os.getenv("FYERS_REFRESH_TOKEN")
        self.pin = os.getenv("PIN")

        if not all([self.app_id_hash, self.refresh_token, self.pin]):
            raise ValueError(
                "Missing one or more required environment variables: APP_ID_HASH, FYERS_REFRESH_TOKEN, PIN"
            )

    def _build_payload(self):
        return {
            "grant_type": "refresh_token",
            "appIdHash": self.app_id_hash,
            "refresh_token": self.refresh_token,
            "pin": self.pin
        }

    def _update_env_file(self, key, value):
        lines = []
        if os.path.exists(self.env_path):
            with open(self.env_path, "r") as f:
                lines = f.readlines()

        lines = [line for line in lines if not line.strip().startswith(f"{key}=")]
        lines.append(f"{key}={value}\n")

        with open(self.env_path, "w") as f:
            f.writelines(lines)

    def generate_access_token(self):
        logger.info("Requesting new access token from Fyers API...")

        payload = self._build_payload()
        response = requests.post(self.url, headers=self.headers, data=json.dumps(payload))

        if response.status_code != 200:
            logger.error(f"HTTP {response.status_code}: {response.text}")
            return None

        data = response.json()

        if data.get("s") != "ok":
            logger.error(f"API Error: {data}")
            return None

        access_token = data.get("access_token")
        if not access_token:
            logger.error("No access_token found in API response.")
            return None

        self._update_env_file("FYERS_ACCESS_TOKEN", access_token)
        self._update_env_file("FYERS_ACCESS_TOKEN_DATE", str(date.today()))

        logger.info("Access token successfully updated in .env file.")

    def get_access_token(self):
        token_date = os.getenv("FYERS_ACCESS_TOKEN_DATE")
        if token_date != str(date.today()):
            self.generate_access_token()


fyers = FyersTokenManager()
fyers.get_access_token()