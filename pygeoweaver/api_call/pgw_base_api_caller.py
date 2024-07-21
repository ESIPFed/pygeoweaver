import requests


class BaseAPI:
    def __init__(self, base_url):
        self.base_url = base_url

    def _call_api(self, endpoint, method='GET', data=None):
        url = self.base_url + endpoint
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
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except Exception as err:
            print(f"An error occurred: {err}")
