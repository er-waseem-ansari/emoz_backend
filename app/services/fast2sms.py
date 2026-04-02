import requests
from app.config import get_settings
import logging


logger = logging.getLogger(__name__)

class Fast2SMS:

    @staticmethod
    def send_sms(to: str, message: str):
        try:
            settings = get_settings()

            payload = {
                "message" : message,
                "route": "q",
                "numbers": to

            }
            headers = {
                "accept": "application/json",
                "authorization": settings.FAST2SMS_API_KEY,
                "content-type": "application/json"
            }


            logger.error(payload)
            response = requests.post(settings.FAST2SMS_URL, json=payload, headers=headers, timeout=10)

            # Check if request was successful
            response.raise_for_status()

            response_data = response.json()

            return {
                "success": True,
                "data": response_data
            }


        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "SMS service timeout - request took too long"
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": "Failed to connect to SMS service"
            }

        except requests.exceptions.HTTPError as e:
            return {
                "success": False,
                "error": f"SMS API error: {e.response.status_code}",
                "details": e.response.text
            }

        except ValueError as e:
            return {
                "success": False,
                "error": str(e)
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}"
            }