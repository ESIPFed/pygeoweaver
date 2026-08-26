"""Module for cleaning and reducing the size of the H2 database used by Geoweaver."""

import logging
import os
import tempfile

from pygeoweaver.server import stop, start, check_geoweaver_status
from pygeoweaver.utils import get_spinner
from pygeoweaver.jdk_utils import check_java
from pygeoweaver.pgw_log_config import setup_logging
from pygeoweaver.constants import GEOWEAVER_DEFAULT_DB_USERNAME, GEOWEAVER_DEFAULT_DB_PASSWORD
from pygeoweaver.h2_utils import (
    get_h2_backup_base_dir,
    get_h2_jar_path,
    h2_maintenance_guard,
    rebuild_h2_database_safely,
    resolve_h2_db_path,
)


def clean_h2db(h2_jar_path=None, temp_dir=None, db_path=None, db_username=None, password=None):
    """
    Clean and reduce the size of the H2 database used by Geoweaver.

    Uses the same safe rebuild pipeline as automatic stop/start maintenance:
    backup, export, rebuild in a work directory, verify, then promote.
    Production files are not replaced until the rebuilt database passes verification.
    """
    log_dir = os.path.join(tempfile.gettempdir(), "geoweaver_logs")
    setup_logging(log_dir=log_dir, force_new=True)
    logger = logging.getLogger(__name__)

    logger.info("=== Starting clean_h2db ===")
    logger.info(
        "Parameters: h2_jar_path=%s temp_dir=%s db_path=%s username=%s",
        h2_jar_path,
        temp_dir,
        db_path,
        db_username,
    )

    try:
        check_java()

        with get_spinner(text="Checking if Geoweaver is running...", spinner="dots"):
            if check_geoweaver_status():
                logger.info("Geoweaver is running, stopping before cleanup")
                stop(exit_on_finish=False, maintain_h2=False)

        resolved_db_path = resolve_h2_db_path(db_path)
        db_username = db_username or GEOWEAVER_DEFAULT_DB_USERNAME
        password = password or GEOWEAVER_DEFAULT_DB_PASSWORD
        h2_jar_path = h2_jar_path or get_h2_jar_path()
        if not h2_jar_path:
            logger.error("H2 JAR not available for cleanup")
            print("\n❌ ERROR: H2 JAR file is not available.")
            return False

        work_base_dir = (
            os.path.abspath(os.path.expanduser(temp_dir))
            if temp_dir
            else get_h2_backup_base_dir()
        )

        with get_spinner(text="Safely rebuilding H2 database...", spinner="dots"):
            with h2_maintenance_guard("stop") as should_run:
                if not should_run:
                    logger.error("Another gw process is already maintaining the H2 database")
                    print("\n❌ ERROR: Another Geoweaver maintenance operation is already running.")
                    print("Wait for it to finish, then retry `gw cleanh2db`.")
                    return False
                success, work_dir = rebuild_h2_database_safely(
                    db_path=resolved_db_path,
                    db_username=db_username,
                    password=password,
                    h2_jar_path=h2_jar_path,
                    work_base_dir=work_base_dir,
                    force=True,
                )

        if not success:
            logger.error("Manual H2 cleanup failed")
            print("\n❌ ERROR: H2 database cleanup failed.")
            if work_dir:
                print(f"Backup retained at: {work_dir}")
            print("Production database was left unchanged unless promotion succeeded.")
            print(f"Logs available at: {log_dir}")
            return False

        with get_spinner(text="Starting Geoweaver...", spinner="dots"):
            start(exit_on_finish=False)

        print("\nH2 database cleanup completed successfully!")
        print(f"Safety backup retained at: {work_dir}")
        print("  original/   untouched copy of the pre-cleanup database")
        print("  displaced/  production files replaced during promotion")
        print("  gw_backup.sql  SQL export used for rebuild")
        print("\nVerify your data with:")
        print("  gw list host")
        print("Delete the backup only after verification succeeds:")
        print(f"  rm -rf '{work_dir}'")
        return True

    except Exception as exc:
        logger.error("clean_h2db failed: %s", exc)
        logger.exception("clean_h2db exception:")
        return False
