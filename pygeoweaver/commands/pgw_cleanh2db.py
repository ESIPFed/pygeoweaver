"""Module for cleaning and reducing the size of the H2 database used by Geoweaver."""

import logging
import os
import shutil
import subprocess
import re
import urllib.request
import platform
import tempfile
from pathlib import Path

from pygeoweaver.server import stop, start, check_geoweaver_status
from pygeoweaver.utils import get_spinner, safe_exit, get_home_dir
from pygeoweaver.jdk_utils import check_java, download_file
from pygeoweaver.config_utils import get_database_url_from_properties

logger = logging.getLogger(__name__)

def clean_h2db(h2_jar_path=None, temp_dir=None, db_path=None, username="geoweaver", password=None):
    """
    Clean and reduce the size of the H2 database used by Geoweaver.
    
    This function follows these steps:
    1. Stop Geoweaver if it's running
    2. Create a temporary directory if one is not provided
    3. Copy database files to the temporary directory
    4. Export data from the database to a SQL file
    5. Remove the original database files
    6. Import the SQL file into a new database
    7. Start Geoweaver
    
    Args:
        h2_jar_path (str, optional): Path to the H2 database JAR file. If not provided, will use h2-2.2.224.jar in the current directory.
        temp_dir (str, optional): Path to a temporary directory for the recovery process. If not provided, will create one.
        db_path (str, optional): Path to the H2 database files. If not provided, will use ~/h2_hopper_amd_1/gw.
        username (str, optional): Username for the H2 database. Defaults to "geoweaver".
        password (str, optional): Password for the H2 database. If not provided, will prompt the user.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """
    # Check if Java is installed
    check_java()
    
    # Step 1: Stop Geoweaver if it's running
    with get_spinner(text="Checking if Geoweaver is running...", spinner="dots"):
        if check_geoweaver_status():
            logger.info("Stopping Geoweaver...")
            stop(exit_on_finish=False)
        else:
            logger.info("Geoweaver is not running.")
    
    # Set default paths if not provided
    home_dir = os.path.expanduser("~")
    if not db_path:
        # Check if there's a custom database URL in application.properties
        custom_db_url = get_database_url_from_properties()
        if custom_db_url and "jdbc:h2:" in custom_db_url:
            # Extract the file path from the JDBC URL
            # Format is typically: jdbc:h2:file:/path/to/database
            # or jdbc:h2:/path/to/database
            match = re.search(r'jdbc:h2:(?:file:)?(.+?)(?:;|$)', custom_db_url)
            if match:
                db_path = match.group(1)
                logger.info(f"Using database path from application.properties: {db_path}")
            else:
                logger.warning(f"Could not parse database path from URL: {custom_db_url}")
                # Use default path with 'h2' instead of 'h2_hopper_amd_1'
                db_path = os.path.join(home_dir, "h2", "gw")
        else:
            # Use default path with 'h2' instead of 'h2_hopper_amd_1'
            db_path = os.path.join(home_dir, "h2", "gw")
        
        logger.info(f"Using database path: {db_path}")
    
    # Set default H2 JAR path and version
    h2_version = "2.2.224"
    if not h2_jar_path:
        # First check in current directory
        h2_jar_path = f"h2-{h2_version}.jar"
        
        # If not in current directory, check in home directory
        if not os.path.exists(h2_jar_path):
            home_h2_jar_path = os.path.join(get_home_dir(), f"h2-{h2_version}.jar")
            
            # If not in home directory, download it
            if not os.path.exists(home_h2_jar_path):
                with get_spinner(text=f"Downloading H2 database JAR file (version {h2_version})...", spinner="dots"):
                    try:
                        # URL for the H2 database JAR file
                        h2_download_url = f"https://repo1.maven.org/maven2/com/h2database/h2/{h2_version}/h2-{h2_version}.jar"
                        
                        # Download the file
                        download_file(h2_download_url, home_h2_jar_path)
                        logger.info(f"H2 JAR file downloaded to {home_h2_jar_path}")
                    except Exception as e:
                        logger.error(f"Failed to download H2 JAR file: {str(e)}")
                        return False
            
            # Use the JAR file in the home directory
            h2_jar_path = home_h2_jar_path
            
        logger.info(f"Using H2 JAR file at {h2_jar_path}")
        
        # Final check to ensure the JAR file exists
        if not os.path.exists(h2_jar_path):
            logger.error(f"H2 JAR file not found at {h2_jar_path} and could not be downloaded")
            return False
    
    # Create a temporary directory if not provided
    if not temp_dir:
        # Try to use system temp directory first as it usually has more space
        system_temp = tempfile.gettempdir()
        username = os.environ.get('USER', os.environ.get('USERNAME', 'user'))
        
        # Check if we're on a cluster system that might have a scratch directory
        potential_dirs = [
            # Standard system temp directory
            system_temp,
            # User-specific scratch directory on clusters
            f"/scratch/{username}",
            # Alternative scratch locations
            f"/tmp/{username}",
            # Fallback to home directory
            os.path.join(home_dir, "geoweaver", "h2")
        ]
        
        # Find the first directory that exists and has sufficient space
        for potential_dir in potential_dirs:
            if os.path.exists(os.path.dirname(potential_dir)):
                try:
                    # Check available disk space (in bytes)
                    if platform.system() == "Windows":
                        free_bytes = shutil.disk_usage(os.path.dirname(potential_dir)).free
                    else:
                        # Unix systems
                        stat = os.statvfs(os.path.dirname(potential_dir))
                        free_bytes = stat.f_frsize * stat.f_bavail
                    
                    # Require at least 1GB of free space (adjust as needed)
                    required_space = 1 * 1024 * 1024 * 1024  # 1GB in bytes
                    
                    if free_bytes > required_space:
                        temp_dir = os.path.join(potential_dir, "geoweaver_h2_temp")
                        logger.info(f"Using temporary directory with {free_bytes / (1024**3):.2f}GB free space: {temp_dir}")
                        break
                    else:
                        logger.warning(f"Insufficient disk space in {potential_dir}: {free_bytes / (1024**3):.2f}GB free")
                except Exception as e:
                    logger.warning(f"Error checking disk space in {potential_dir}: {str(e)}")
                    continue
        
        # If no suitable directory was found, use system temp as last resort
        if not temp_dir:
            temp_dir = os.path.join(system_temp, f"geoweaver_h2_temp_{username}")
            logger.warning(f"No directory with sufficient space found, using system temp as last resort: {temp_dir}")
    
    # Ensure the temporary directory exists
    os.makedirs(temp_dir, exist_ok=True)
    
    logger.info(f"Using temporary directory: {temp_dir}")
    
    # Step 2: Copy database files to the temporary directory
    with get_spinner(text="Copying database files to temporary directory...", spinner="dots"):
        db_dir = os.path.dirname(db_path)
        
        # Check if the directory exists before trying to list its contents
        if not os.path.exists(db_dir):
            logger.warning(f"Database directory does not exist: {db_dir}")
            logger.info(f"Creating directory: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)
            # Since the directory didn't exist, there are no files to copy
            logger.info(f"No database files to copy from {db_dir}")
        else:
            # Directory exists, copy any matching files
            files_copied = False
            for file in os.listdir(db_dir):
                if file.startswith(os.path.basename(db_path)):
                    src_file = os.path.join(db_dir, file)
                    dst_file = os.path.join(temp_dir, file)
                    shutil.copy2(src_file, dst_file)
                    logger.info(f"Copied {src_file} to {dst_file}")
                    files_copied = True
            
            if not files_copied:
                logger.info(f"No database files found in {db_dir} matching pattern {os.path.basename(db_path)}*")
    
    # Step 3: Export data from the database to a SQL file
    sql_file = os.path.join(temp_dir, "gw_backup.sql")
    
    # Prompt for password if not provided - moved outside of spinner context
    if not password:
        import getpass
        password = getpass.getpass("Enter database password: ")
        
    with get_spinner(text="Exporting database to SQL file...", spinner="dots"):
        # Build the command to export the database
        export_cmd = [
            "java", "-cp", h2_jar_path, 
            "org.h2.tools.Script", 
            "-url", f"jdbc:h2:{os.path.join(temp_dir, os.path.basename(db_path))}", 
            "-user", username, 
            "-script", sql_file, 
            "-password", password
        ]
        
        try:
            subprocess.run(export_cmd, check=True, capture_output=True, text=True)
            logger.info(f"Database exported to {sql_file}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to export database: {e.stderr}")
            return False
    
    # Step 4: Remove the original database files
    with get_spinner(text="Removing original database files...", spinner="dots"):
        # Check if the directory exists before trying to remove files
        if not os.path.exists(db_dir):
            logger.warning(f"Database directory does not exist: {db_dir}")
            # Create the directory for the import step
            os.makedirs(db_dir, exist_ok=True)
        else:
            # Directory exists, remove any matching files
            files_removed = False
            for file in os.listdir(db_dir):
                if file.startswith(os.path.basename(db_path)):
                    os.remove(os.path.join(db_dir, file))
                    logger.info(f"Removed {os.path.join(db_dir, file)}")
                    files_removed = True
            
            if not files_removed:
                logger.info(f"No database files found to remove in {db_dir}")
    
    # Step 5: Import the SQL file into a new database
    with get_spinner(text="Importing SQL file into new database...", spinner="dots"):
        # Ensure the target directory exists
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            logger.info(f"Creating database directory: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)
            
        # Build the command to import the database
        import_cmd = [
            "java", "-cp", h2_jar_path, 
            "org.h2.tools.RunScript", 
            "-url", f"jdbc:h2:{db_path}", 
            "-user", username, 
            "-script", sql_file, 
            "-password", password
        ]
        
        try:
            subprocess.run(import_cmd, check=True, capture_output=True, text=True)
            logger.info(f"Database imported from {sql_file}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to import database: {e.stderr}")
            return False
    
    # Step 6: Start Geoweaver
    with get_spinner(text="Starting Geoweaver...", spinner="dots"):
        start(exit_on_finish=False)
    
    print("\nH2 database cleanup completed successfully!")
    print(f"Temporary files are stored in {temp_dir}")
    print("You can delete these files if the database is working correctly.")
    
    return True