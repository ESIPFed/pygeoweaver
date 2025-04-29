import json
from typing import Any, Dict, Optional
import requests

GEOWEAVER_PREFIX="/Geoweaver/web"

class BaseAPI:
    def __init__(self, base_url):
        self.base_url = base_url

    def _call_api(self, endpoint: str, method: str = 'GET', 
                  data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Sends an HTTP request to the specified API endpoint.

        Parameters:
        - endpoint (str): The API endpoint to send the request to.
        - method (str): The HTTP method to use ('GET', 'POST', 'PUT', 'DELETE'). Defaults to 'GET'.
        - data (Optional[Dict[str, Any]]): The data to send with the request. For 'POST' and 'PUT', it should be a dictionary.

        Returns:
        - Optional[Dict[str, Any]]: The JSON response from the server, parsed into a dictionary. Returns None if an error occurs.

        Raises:
        - ValueError: If an unsupported HTTP method is specified.
        """
        url = self.base_url + GEOWEAVER_PREFIX + endpoint
        headers = {
            'Content-Type': 'application/json'
        }

        try:
            if method.upper() == 'POST':
                response = requests.post(url, headers=headers, data=json.dumps(data))
            elif method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=data)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, data=json.dumps(data))
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=headers, data=json.dumps(data))
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            print("return is ", response)
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
            return None
        except Exception as err:
            print(f"An error occurred: {err}")
            return None