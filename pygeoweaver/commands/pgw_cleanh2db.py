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
from pygeoweaver.utils import get_java_bin_path, get_spinner, safe_exit, get_home_dir
from pygeoweaver.jdk_utils import check_java, download_file
from pygeoweaver.config_utils import get_database_url_from_properties
from pygeoweaver.config import H2_VERSION
from pygeoweaver.pgw_log_config import setup_logging
from pygeoweaver.constants import GEOWEAVER_DEFAULT_DB_USERNAME, GEOWEAVER_DEFAULT_DB_PASSWORD



def clean_h2db(h2_jar_path=None, temp_dir=None, db_path=None, db_username=None, password=None):
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
        db_path (str, optional): Path to the H2 database files. If not provided, will use ~/h2/gw.
        username (str, optional): Username for the H2 database. Defaults to "geoweaver".
        password (str, optional): Password for the H2 database. If not provided, will prompt the user.
    
    Returns:
        bool: True if the operation was successful, False otherwise.
    """

    # Always use a temp directory for logs
    log_dir = os.path.join(tempfile.gettempdir(), 'geoweaver_logs')
    setup_logging(log_dir=log_dir)
    logger = logging.getLogger(__name__)
    
    logger.info("=== Starting clean_h2db function ===")
    logger.info(f"Function parameters: h2_jar_path={h2_jar_path}, temp_dir={temp_dir}, db_path={db_path}, username={db_username}, password={'*' * len(password) if password else 'None'}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Python executable: {os.sys.executable}")
    logger.info(f"Python version: {os.sys.version}")
    logger.info(f"User: {os.environ.get('USER', os.environ.get('USERNAME', 'unknown'))}")
    logger.info(f"HOME directory: {os.environ.get('HOME', os.path.expanduser('~'))}")
    
    # Test if logging is working
    logger.debug("Debug message test")
    logger.info("Info message test")
    logger.warning("Warning message test")
    logger.error("Error message test")
    
    # Check file system permissions
    logger.info("=== File system checks ===")
    logger.info(f"Current directory readable: {os.access('.', os.R_OK)}")
    logger.info(f"Current directory writable: {os.access('.', os.W_OK)}")
    logger.info(f"Current directory executable: {os.access('.', os.X_OK)}")
    
    # Check temporary directory permissions
    temp_dir_system = tempfile.gettempdir()
    logger.info(f"System temp directory: {temp_dir_system}")
    logger.info(f"System temp readable: {os.access(temp_dir_system, os.R_OK)}")
    logger.info(f"System temp writable: {os.access(temp_dir_system, os.W_OK)}")
    
    try:
        # Check if Java is installed
        logger.info("=== Java check ===")
        logger.info("Checking if Java is installed...")
        check_java()
        logger.info("Java check completed successfully")
        
        # Step 1: Stop Geoweaver if it's running
        logger.info("=== Step 1: Geoweaver status check ===")
        logger.info("Step 1: Checking and stopping Geoweaver if running...")
        with get_spinner(text="Checking if Geoweaver is running...", spinner="dots"):
            geoweaver_status = check_geoweaver_status()
            logger.info(f"Geoweaver status check result: {geoweaver_status}")
            if geoweaver_status:
                logger.info("Geoweaver is running, stopping it...")
                stop(exit_on_finish=False)
                logger.info("Geoweaver stopped successfully")
            else:
                logger.info("Geoweaver is not running, proceeding...")
        
        # Set default paths if not provided
        logger.info("=== Path setup ===")
        logger.info("Setting up default paths...")
        home_dir = os.path.expanduser("~")
        logger.info(f"Home directory: {home_dir}")
        logger.info(f"Home directory exists: {os.path.exists(home_dir)}")
        logger.info(f"Home directory readable: {os.access(home_dir, os.R_OK)}")
        logger.info(f"Home directory writable: {os.access(home_dir, os.W_OK)}")
        
        if not db_path:
            logger.info("No db_path provided, determining database path...")
            # Check if there's a custom database URL in application.properties
            custom_db_url = get_database_url_from_properties()
            logger.info(f"Custom database URL from properties: {custom_db_url}")
            
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
                    logger.info(f"Using default database path: {db_path}")
            else:
                # Use default path with 'h2' instead of 'h2_hopper_amd_1'
                db_path = os.path.join(home_dir, "h2", "gw")
                logger.info(f"Using default database path: {db_path}")
        else:
            logger.info(f"Using provided database path: {db_path}")
        
        logger.info(f"Final database path: {db_path}")
        logger.info(f"Database directory: {os.path.dirname(db_path)}")
        logger.info(f"Database directory exists: {os.path.exists(os.path.dirname(db_path))}")
        
        # Set default H2 JAR path and version
        logger.info("=== H2 JAR setup ===")
        logger.info("Setting up H2 JAR path...")
        h2_version = H2_VERSION
        logger.info(f"H2 version: {h2_version}")
        
        if not h2_jar_path:
            logger.info("No h2_jar_path provided, searching for H2 JAR file...")
            # First check in current directory
            h2_jar_path = f"h2-{h2_version}.jar"
            logger.info(f"Checking current directory for: {h2_jar_path}")
            logger.info(f"Current directory: {os.getcwd()}")
            logger.info(f"File exists in current directory: {os.path.exists(h2_jar_path)}")
            
            # If not in current directory, check in home directory
            if not os.path.exists(h2_jar_path):
                logger.info("H2 JAR not found in current directory, checking home directory...")
                home_h2_jar_path = os.path.join(get_home_dir(), f"h2-{h2_version}.jar")
                logger.info(f"Checking home directory for: {home_h2_jar_path}")
                logger.info(f"File exists in home directory: {os.path.exists(home_h2_jar_path)}")
                
                # If not in home directory, download it
                if not os.path.exists(home_h2_jar_path):
                    logger.info("H2 JAR not found in home directory, downloading...")
                    with get_spinner(text=f"Downloading H2 database JAR file (version {h2_version})...", spinner="dots"):
                        try:
                            # URL for the H2 database JAR file
                            h2_download_url = f"https://repo1.maven.org/maven2/com/h2database/h2/{h2_version}/h2-{h2_version}.jar"
                            logger.info(f"Download URL: {h2_download_url}")
                            
                            # Download the file
                            download_file(h2_download_url, home_h2_jar_path)
                            logger.info(f"H2 JAR file downloaded to {home_h2_jar_path}")
                            logger.info(f"Downloaded file exists: {os.path.exists(home_h2_jar_path)}")
                            logger.info(f"Downloaded file size: {os.path.getsize(home_h2_jar_path) if os.path.exists(home_h2_jar_path) else 'N/A'} bytes")
                        except Exception as e:
                            logger.error(f"Failed to download H2 JAR file: {str(e)}")
                            logger.exception("Download exception details:")
                            return False
                else:
                    logger.info(f"H2 JAR found in home directory: {home_h2_jar_path}")
                    logger.info(f"File size: {os.path.getsize(home_h2_jar_path)} bytes")
                
                # Use the JAR file in the home directory
                h2_jar_path = home_h2_jar_path
            else:
                logger.info(f"H2 JAR found in current directory: {h2_jar_path}")
                logger.info(f"File size: {os.path.getsize(h2_jar_path)} bytes")
            
            logger.info(f"Using H2 JAR file at {h2_jar_path}")
            
            # Final check to ensure the JAR file exists
            if not os.path.exists(h2_jar_path):
                logger.error(f"H2 JAR file not found at {h2_jar_path} and could not be downloaded")
                return False
        else:
            logger.info(f"Using provided H2 JAR path: {h2_jar_path}")
            logger.info(f"Provided file exists: {os.path.exists(h2_jar_path)}")
            if os.path.exists(h2_jar_path):
                logger.info(f"Provided file size: {os.path.getsize(h2_jar_path)} bytes")
        
        # Create a temporary directory if not provided
        logger.info("=== Temporary directory setup ===")
        logger.info("Setting up temporary directory...")
        if not temp_dir:
            logger.info("No temp_dir provided, searching for suitable temporary directory...")
            # Try to use system temp directory first as it usually has more space
            system_temp = tempfile.gettempdir()
            username = os.environ.get('USER', os.environ.get('USERNAME', 'user'))
            logger.info(f"System temp directory: {system_temp}")
            logger.info(f"Current user: {username}")
            
            # Check if we're on a cluster system that might have a scratch directory
            potential_dirs = [
                # Standard system temp directory
                system_temp,
                # User-specific scratch directory on clusters
                f"/scratch/{username}",
                # Alternative scratch locations
                f"/tmp/{username}",
                # Fallback to home directory
                # os.path.join(home_dir, "geoweaver", "h2")
            ]
            
            logger.info(f"Potential directories to check: {potential_dirs}")
            
            # Find the first directory that exists and has sufficient space
            for potential_dir in potential_dirs:
                logger.info(f"Checking potential directory: {potential_dir}")
                logger.info(f"Directory exists: {os.path.exists(os.path.dirname(potential_dir))}")
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
                        
                        logger.info(f"Available space in {potential_dir}: {free_bytes / (1024**3):.2f}GB")
                        logger.info(f"Required space: {required_space / (1024**3):.2f}GB")
                        
                        if free_bytes > required_space:
                            temp_dir = os.path.join(potential_dir, "geoweaver_h2_temp")
                            logger.info(f"Using temporary directory with {free_bytes / (1024**3):.2f}GB free space: {temp_dir}")
                            break
                        else:
                            logger.warning(f"Insufficient disk space in {potential_dir}: {free_bytes / (1024**3):.2f}GB free")
                    except Exception as e:
                        logger.warning(f"Error checking disk space in {potential_dir}: {str(e)}")
                        logger.exception("Disk space check exception:")
                        continue
            
            # If no suitable directory was found, use system temp as last resort
            if not temp_dir:
                temp_dir = os.path.join(system_temp, f"geoweaver_h2_temp_{username}")
                logger.warning(f"No directory with sufficient space found, using system temp as last resort: {temp_dir}")
        else:
            logger.info(f"Using provided temporary directory: {temp_dir}")
        
        # Ensure the temporary directory exists
        logger.info(f"Creating temporary directory: {temp_dir}")
        try:
            os.makedirs(temp_dir, exist_ok=True)
            logger.info(f"Temporary directory created/exists: {temp_dir}")
            logger.info(f"Temporary directory writable: {os.access(temp_dir, os.W_OK)}")
        except Exception as e:
            logger.error(f"Failed to create temporary directory: {str(e)}")
            logger.exception("Temporary directory creation exception:")
            return False
        
        logger.info(f"Using temporary directory: {temp_dir}")
        
        # Step 2: Copy database files to the temporary directory
        logger.info("=== Step 2: Database file copy ===")
        logger.info("Step 2: Copying database files to temporary directory...")
        with get_spinner(text="Copying database files to temporary directory...", spinner="dots"):
            db_dir = os.path.dirname(db_path)
            logger.info(f"Database directory: {db_dir}")
            logger.info(f"Database directory exists: {os.path.exists(db_dir)}")
            
            # Check if the directory exists before trying to list its contents
            if not os.path.exists(db_dir):
                logger.warning(f"Database directory does not exist: {db_dir}")
                logger.info(f"Creating directory: {db_dir}")
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logger.info(f"Database directory created: {db_dir}")
                except Exception as e:
                    logger.error(f"Failed to create database directory: {str(e)}")
                    logger.exception("Database directory creation exception:")
                    return False
                # Since the directory didn't exist, there are no files to copy
                logger.info(f"No database files to copy from {db_dir}")
            else:
                logger.info(f"Database directory exists: {db_dir}")
                logger.info(f"Database directory readable: {os.access(db_dir, os.R_OK)}")
                logger.info(f"Database directory writable: {os.access(db_dir, os.W_OK)}")
                
                # Directory exists, copy any matching files
                files_copied = False
                db_basename = os.path.basename(db_path)
                logger.info(f"Looking for files starting with: {db_basename}")
                
                try:
                    files_in_dir = os.listdir(db_dir)
                    logger.info(f"Files in database directory: {files_in_dir}")
                    
                    for file in files_in_dir:
                        logger.info(f"Checking file: {file}")
                        if file.startswith(db_basename):
                            src_file = os.path.join(db_dir, file)
                            dst_file = os.path.join(temp_dir, file)
                            logger.info(f"Copying {src_file} to {dst_file}")
                            logger.info(f"Source file exists: {os.path.exists(src_file)}")
                            logger.info(f"Source file size: {os.path.getsize(src_file) if os.path.exists(src_file) else 'N/A'} bytes")
                            
                            try:
                                shutil.copy2(src_file, dst_file)
                                logger.info(f"Copied {src_file} to {dst_file}")
                                logger.info(f"Destination file exists: {os.path.exists(dst_file)}")
                                logger.info(f"Destination file size: {os.path.getsize(dst_file) if os.path.exists(dst_file) else 'N/A'} bytes")
                                
                                # Verify file size matches
                                src_size = os.path.getsize(src_file)
                                dst_size = os.path.getsize(dst_file)
                                if src_size != dst_size:
                                    logger.error(f"File size mismatch! Source: {src_size} bytes, Destination: {dst_size} bytes")
                                    logger.error(f"Copy operation failed for {src_file}")
                                    return False
                                else:
                                    logger.info(f"File size verification passed: {src_size} bytes")
                                
                                files_copied = True
                            except Exception as e:
                                logger.error(f"Failed to copy file {src_file}: {str(e)}")
                                logger.exception("File copy exception:")
                                return False
                    
                    if not files_copied:
                        logger.info(f"No database files found in {db_dir} matching pattern {db_basename}*")
                except Exception as e:
                    logger.error(f"Failed to list directory {db_dir}: {str(e)}")
                    logger.exception("Directory listing exception:")
                    return False
        
        # Step 3: Export data from the database to a SQL file
        logger.info("=== Step 3: Database export ===")
        logger.info("Step 3: Exporting database to SQL file...")
        sql_file = os.path.join(temp_dir, "gw_backup.sql")
        logger.info(f"SQL backup file: {sql_file}")
        
        # Set default user name
        if not db_username:
            db_username = GEOWEAVER_DEFAULT_DB_USERNAME
            logger.info(f"Using default username: {db_username}")
        else:
            logger.info(f"Using provided H2 db username: {db_username}")

        # Set default password
        if not password:
            password = GEOWEAVER_DEFAULT_DB_PASSWORD
            logger.info("No password provided, using default password from config.")
        else:
            logger.info("Password provided in parameters")
            
        with get_spinner(text="Exporting database to SQL file...", spinner="dots"):
            # Build the command to export the database
            temp_db_path = os.path.join(temp_dir, os.path.basename(db_path))
            logger.info(f"Temporary database path for export: {temp_db_path}")
            
            export_cmd = [
                get_java_bin_path(), "-cp", h2_jar_path, 
                "org.h2.tools.Script", 
                "-url", f"jdbc:h2:{temp_db_path}", 
                "-user", db_username, 
                "-script", sql_file, 
                "-password", password
            ]
            
            logger.info(f"Export command: {' '.join(export_cmd[:3])} ... -url jdbc:h2:{temp_db_path} ... -user {db_username} ... -script {sql_file} ... -password ***")
            
            try:
                logger.info("Executing export command...")
                result = subprocess.run(export_cmd, check=True, capture_output=True, text=True)
                logger.info(f"Export command completed successfully")
                logger.info(f"Export return code: {result.returncode}")
                logger.info(f"Export stdout: {result.stdout}")
                if result.stderr:
                    logger.info(f"Export stderr: {result.stderr}")
                logger.info(f"Database exported to {sql_file}")
                logger.info(f"SQL file exists: {os.path.exists(sql_file)}")
                if os.path.exists(sql_file):
                    logger.info(f"SQL file size: {os.path.getsize(sql_file)} bytes")
                    
                    # Verify SQL file has content
                    sql_file_size = os.path.getsize(sql_file)
                    if sql_file_size == 0:
                        logger.error(f"SQL export file is empty (0 bytes): {sql_file}")
                        print(f"\n❌ ERROR: SQL export file is empty!")
                        print(f"File: {sql_file}")
                        print(f"Size: 0 bytes")
                        print(f"This indicates the database export failed or the database is empty.")
                        print(f"\nPlease check if the database contains data and try again.")
                        print(f"Logs available at: {log_dir}")
                        return False
                    else:
                        # Always read as text
                        with open(sql_file, 'r') as f:
                            lines = f.readlines()
                        if len(lines) < 10:
                            logger.error(f"SQL export file has too few lines: {len(lines)}")
                            print(f"\n❌ ERROR: SQL export file has too few lines!")
                            print(f"File: {sql_file}")
                            print(f"Lines: {len(lines)} (expected >= 10)")
                            print(f"This indicates the database export failed or the database is empty.")
                            print(f"\nPlease check if the database contains data and try again.")
                            print(f"Logs available at: {log_dir}")
                            return False
                        
                        logger.info(f"SQL export successful: {sql_file_size} bytes, {len(lines)} lines")
                        print(f"✅ Database exported successfully: {sql_file_size} bytes, {len(lines)} lines")
                else:
                    logger.error(f"SQL export file was not created: {sql_file}")
                    print(f"\n❌ ERROR: SQL export file was not created!")
                    print(f"Expected file: {sql_file}")
                    print(f"This indicates the database export command failed.")
                    print(f"\nLogs available at: {log_dir}")
                    return False
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to export database: {e.stderr}")
                logger.error(f"Export command return code: {e.returncode}")
                logger.error(f"Export command stdout: {e.stdout}")
                logger.exception("Export command exception:")
                
                # Print error to console for immediate user notification
                print(f"\n❌ ERROR: Database export failed!")
                print(f"Command: {' '.join(export_cmd[:3])} ... -url jdbc:h2:{temp_db_path} ... -user {db_username} ... -script {sql_file} ... -password ***")
                print(f"Return code: {e.returncode}")
                print(f"Error output: {e.stderr}")
                if e.stdout:
                    print(f"Standard output: {e.stdout}")
                print(f"\nPlease check:")
                print(f"1. Database path: {temp_db_path}")
                print(f"2. Username: {db_username}")
                print(f"3. Database file exists and is not corrupted")
                print(f"4. H2 JAR file: {h2_jar_path}")
                print(f"\nLogs available at: {log_dir}")
                
                return False
            except Exception as e:
                logger.error(f"Unexpected error during export: {str(e)}")
                logger.exception("Export exception:")
                
                # Print error to console for immediate user notification
                print(f"\n❌ ERROR: Unexpected error during database export!")
                print(f"Error: {str(e)}")
                print(f"\nLogs available at: {log_dir}")
                
                return False
        
        # Step 4: Remove the original database files
        logger.info("=== Step 4: Remove original files ===")
        logger.info("Step 4: Removing original database files...")
        with get_spinner(text="Removing original database files...", spinner="dots"):
            # Check if the directory exists before trying to remove files
            if not os.path.exists(db_dir):
                logger.warning(f"Database directory does not exist: {db_dir}")
                # Create the directory for the import step
                logger.info(f"Creating directory for import: {db_dir}")
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logger.info(f"Database directory created for import: {db_dir}")
                except Exception as e:
                    logger.error(f"Failed to create database directory for import: {str(e)}")
                    logger.exception("Database directory creation exception:")
                    return False
            else:
                logger.info(f"Database directory exists: {db_dir}")
                # Directory exists, remove any matching files
                files_removed = False
                db_basename = os.path.basename(db_path)
                logger.info(f"Looking for files to remove starting with: {db_basename}")
                
                try:
                    files_in_dir = os.listdir(db_dir)
                    logger.info(f"Files in database directory before removal: {files_in_dir}")
                    
                    for file in files_in_dir:
                        logger.info(f"Checking file for removal: {file}")
                        if file.startswith(db_basename):
                            file_path = os.path.join(db_dir, file)
                            logger.info(f"Removing file: {file_path}")
                            logger.info(f"File exists before removal: {os.path.exists(file_path)}")
                            
                            try:
                                os.remove(file_path)
                                logger.info(f"Removed {file_path}")
                                logger.info(f"File exists after removal: {os.path.exists(file_path)}")
                                files_removed = True
                            except Exception as e:
                                logger.error(f"Failed to remove file {file_path}: {str(e)}")
                                logger.exception("File removal exception:")
                                return False
                    
                    if not files_removed:
                        logger.info(f"No database files found to remove in {db_dir}")
                except Exception as e:
                    logger.error(f"Failed to list directory {db_dir} for removal: {str(e)}")
                    logger.exception("Directory listing for removal exception:")
                    return False
        
        # Step 5: Import the SQL file into a new database
        logger.info("=== Step 5: Database import ===")
        logger.info("Step 5: Importing SQL file into new database...")
        with get_spinner(text="Importing SQL file into new database...", spinner="dots"):
            # Ensure the target directory exists
            db_dir = os.path.dirname(db_path)
            if not os.path.exists(db_dir):
                logger.info(f"Creating database directory: {db_dir}")
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logger.info(f"Database directory created: {db_dir}")
                except Exception as e:
                    logger.error(f"Failed to create database directory: {str(e)}")
                    logger.exception("Database directory creation exception:")
                    return False
            else:
                logger.info(f"Database directory exists: {db_dir}")
                
            # Build the command to import the database
            import_cmd = [
                get_java_bin_path(), "-cp", h2_jar_path, 
                "org.h2.tools.RunScript", 
                "-url", f"jdbc:h2:{db_path}", 
                "-user", db_username, 
                "-script", sql_file, 
                "-password", password
            ]
            
            logger.info(f"Import command: {' '.join(import_cmd[:3])} ... -url jdbc:h2:{db_path} ... -user {db_username} ... -script {sql_file} ... -password ***")
            
            try:
                logger.info("Executing import command...")
                result = subprocess.run(import_cmd, check=True, capture_output=True, text=True)
                logger.info(f"Import command completed successfully")
                logger.info(f"Import return code: {result.returncode}")
                logger.info(f"Import stdout: {result.stdout}")
                if result.stderr:
                    logger.info(f"Import stderr: {result.stderr}")
                logger.info(f"Database imported from {sql_file}")
                
                # Check if database files were created
                db_basename = os.path.basename(db_path)
                logger.info(f"Checking for created database files starting with: {db_basename}")
                try:
                    files_in_dir = os.listdir(db_dir)
                    logger.info(f"Files in database directory after import: {files_in_dir}")
                    for file in files_in_dir:
                        if file.startswith(db_basename):
                            file_path = os.path.join(db_dir, file)
                            logger.info(f"Database file created: {file_path}")
                            logger.info(f"File size: {os.path.getsize(file_path)} bytes")
                except Exception as e:
                    logger.warning(f"Failed to list database directory after import: {str(e)}")
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to import database: {e.stderr}")
                logger.error(f"Import command return code: {e.returncode}")
                logger.error(f"Import command stdout: {e.stdout}")
                logger.exception("Import command exception:")
                return False
            except Exception as e:
                logger.error(f"Unexpected error during import: {str(e)}")
                logger.exception("Import exception:")
                return False
        
        # Step 6: Start Geoweaver
        logger.info("=== Step 6: Start Geoweaver ===")
        logger.info("Step 6: Starting Geoweaver...")
        with get_spinner(text="Starting Geoweaver...", spinner="dots"):
            try:
                start(exit_on_finish=False)
                logger.info("Geoweaver started successfully")
            except Exception as e:
                logger.error(f"Failed to start Geoweaver: {str(e)}")
                logger.exception("Geoweaver start exception:")
                return False
        
        logger.info("=== clean_h2db function completed successfully ===")
        print("\nH2 database cleanup completed successfully!")
        print(f"Temporary files are stored in {temp_dir}")
        print(f"To delete the temporary files, run:")
        print(f"  rm -rf '{temp_dir}'")
        print(f"  rm -f '{sql_file}'")
        print("\nTo verify the cleanup was successful, run:")
        print("  gw list host")
        print("If you see your expected hosts, the cleanup was successful.")
        print("You can delete the temp directory above if everything works.")
        
        return True
        
    except Exception as e:
        logger.error(f"=== clean_h2db function failed with exception: {str(e)} ===")
        logger.exception("Full exception details:")
        return False