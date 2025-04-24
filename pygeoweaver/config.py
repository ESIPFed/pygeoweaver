import os

# Default H2 version
H2_VERSION = os.getenv('H2_VERSION', '2.2.224')

H2_DOWNLOAD_URL = f"https://repo1.maven.org/maven2/com/h2database/h2/{H2_VERSION}/h2-{H2_VERSION}.jar"
ORG_H2_TOOLS_RUNSCRIPT = "org.h2.tools.RunScript"
JAVA = "java"
ORG_H2_TOOLS_SCRIPT = "org.h2.tools.Script"
GEOWEAVER_H2_TEMP = "geoweaver_h2_temp"
GW_BACKUP_SQL = "gw_backup.sql"
GW_WORKSPACE = "gw-workspace"