import os

GEOWEAVER_PORT=os.getenv("GEOWEAVER_PORT", "8070")
GEOWEAVER_DEFAULT_ENDPOINT_URL = f"http://localhost:{GEOWEAVER_PORT}/Geoweaver"
COMMON_API_HEADER = {"Content-Type": "application/json"}
GEOWEAVER_URL = (
    "https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar"
)
GEOWEAVER_DEFAULT_DB_USERNAME = "geoweaver"
GEOWEAVER_DEFAULT_DB_PASSWORD = "DFKHH9V6ME"
