"""Module for upgrading Geoweaver by downloading the latest JAR file."""

import logging
import os

from pygeoweaver.server import stop, start, check_geoweaver_status
from pygeoweaver.utils import get_spinner, get_geoweaver_jar_path, download_geoweaver_jar
from pygeoweaver.jdk_utils import check_java

logger = logging.getLogger(__name__)

def upgrade_geoweaver(force=False, no_start=False):
    """
    Upgrade Geoweaver by downloading the latest JAR file.
    
    This function follows these steps:
    1. Ask for confirmation as the process will stop Geoweaver if running (unless force=True)
    2. Stop Geoweaver if it's running
    3. Force download the latest Geoweaver JAR file
    4. Start Geoweaver (unless no_start=True)
    
    Args:
        force (bool): If True, skip the confirmation prompt
        no_start (bool): If True, don't start Geoweaver after upgrade
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    # Check if Java is installed
    check_java()
    
    # Ask for confirmation before proceeding (unless force=True)
    if not force:
        print("\nWARNING: This upgrade will stop Geoweaver if it's currently running.")
        confirmation = input("Are you sure you want to upgrade Geoweaver right now? (yes/no): ")
        
        if confirmation.lower() != 'yes':
            print("Upgrade cancelled.")
            return False
    
    # Step 1: Stop Geoweaver if it's running
    with get_spinner(text="Checking if Geoweaver is running...", spinner="dots"):
        if check_geoweaver_status():
            logger.info("Stopping Geoweaver...")
            stop(exit_on_finish=False)
        else:
            logger.info("Geoweaver is not running.")
    
    # Step 2: Force download the latest Geoweaver JAR file
    jar_path = get_geoweaver_jar_path()
    if os.path.exists(jar_path):
        with get_spinner(text="Removing existing Geoweaver JAR file...", spinner="dots"):
            try:
                os.remove(jar_path)
                logger.info(f"Removed existing JAR file at {jar_path}")
            except Exception as e:
                logger.error(f"Failed to remove existing JAR file: {str(e)}")
                return False
    
    with get_spinner(text="Downloading latest Geoweaver JAR file...", spinner="dots"):
        try:
            download_geoweaver_jar(overwrite=True)
            logger.info("Successfully downloaded the latest Geoweaver JAR file")
        except Exception as e:
            logger.error(f"Failed to download Geoweaver JAR file: {str(e)}")
            return False
    
    # Step 3: Start Geoweaver (unless no_start=True)
    if not no_start:
        with get_spinner(text="Starting Geoweaver...", spinner="dots"):
            start(exit_on_finish=False)
    else:
        print("\nSkipping Geoweaver startup as requested.")
    
    print("\nGeoweaver upgrade completed successfully!")
    print(f"The latest Geoweaver JAR file has been downloaded to {jar_path}")
    
    return True