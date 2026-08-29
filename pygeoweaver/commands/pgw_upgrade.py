"""Module for upgrading Geoweaver by downloading the appropriate JAR file."""

import logging
import os

from pygeoweaver.constants import GEOWEAVER_JAR_CHANNEL_LATEST, GEOWEAVER_LEGACY_JAVA11_LINE
from pygeoweaver.jdk_utils import ensure_geoweaver_runtime
from pygeoweaver.server import stop, start, check_geoweaver_status
from pygeoweaver.utils import get_spinner, get_geoweaver_jar_path, download_geoweaver_jar

logger = logging.getLogger(__name__)


def upgrade_geoweaver(force=False, no_start=False):
    """
    Upgrade Geoweaver by downloading the JAR matching the resolved Java runtime.

    Steps:
    1. Ask for confirmation (unless force=True)
    2. Resolve Java / jar channel (bump managed JDK to 17 when needed;
       legacy jar if system JDK < 17)
    3. Stop Geoweaver if running
    4. Force download the selected Geoweaver JAR
    5. Start Geoweaver (unless no_start=True)
    """
    runtime = ensure_geoweaver_runtime(force_recheck=True)
    if runtime.channel != GEOWEAVER_JAR_CHANNEL_LATEST:
        print(
            f"\nNOTE: Active Java is {runtime.major}; downloading {GEOWEAVER_LEGACY_JAVA11_LINE} "
            f"instead of latest. Install Java 17+ or run `gw installjdk` for Geoweaver 2.2+."
        )

    if not force:
        print("\nWARNING: This upgrade will stop Geoweaver if it's currently running.")
        confirmation = input("Are you sure you want to upgrade Geoweaver right now? (yes/no): ")

        if confirmation.lower() != "yes":
            print("Upgrade cancelled.")
            return False

    with get_spinner(text="Checking if Geoweaver is running...", spinner="dots"):
        if check_geoweaver_status():
            logger.info("Stopping Geoweaver...")
            stop(exit_on_finish=False)
        else:
            logger.info("Geoweaver is not running.")

    jar_path = get_geoweaver_jar_path()
    if os.path.exists(jar_path):
        with get_spinner(text="Removing existing Geoweaver JAR file...", spinner="dots"):
            try:
                os.remove(jar_path)
                logger.info(f"Removed existing JAR file at {jar_path}")
            except Exception as e:
                logger.error(f"Failed to remove existing JAR file: {str(e)}")
                return False

    with get_spinner(text="Downloading Geoweaver JAR file...", spinner="dots"):
        try:
            download_geoweaver_jar(overwrite=True)
            logger.info("Successfully downloaded Geoweaver JAR file (%s)", runtime.channel)
        except Exception as e:
            logger.error(f"Failed to download Geoweaver JAR file: {str(e)}")
            return False

    if not no_start:
        with get_spinner(text="Starting Geoweaver...", spinner="dots"):
            start(exit_on_finish=False)
    else:
        print("\nSkipping Geoweaver startup as requested.")

    print("\nGeoweaver upgrade completed successfully!")
    print(f"Geoweaver JAR ({runtime.channel}) downloaded to {jar_path}")

    return True
