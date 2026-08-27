import os

GEOWEAVER_PORT=os.getenv("GEOWEAVER_PORT", "8070")
GEOWEAVER_DEFAULT_ENDPOINT_URL = f"http://localhost:{GEOWEAVER_PORT}/Geoweaver"
COMMON_API_HEADER = {"Content-Type": "application/json"}
GEOWEAVER_URL = (
    "https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar"
)
GEOWEAVER_DEFAULT_DB_USERNAME = "geoweaver"
GEOWEAVER_DEFAULT_DB_PASSWORD = "DFKHH9V6ME"

# Latest Geoweaver (2.2+ / Spring Boot 3) requires Java 17+.
GEOWEAVER_MIN_JAVA_MAJOR = 17
GEOWEAVER_LEGACY_JAVA11_LINE = "Geoweaver 2.1.x"
GEOWEAVER_RELEASES_URL = "https://github.com/ESIPFed/Geoweaver/releases"
GEOWEAVER_LEGACY_JAR_URL = (
    "https://github.com/ESIPFed/Geoweaver/releases/download/v2.1.7/geoweaver.jar"
)
