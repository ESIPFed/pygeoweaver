import subprocess
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
)


def reset_password():
    """
  Usage: <main class> resetpassword
  Reset password for localhost
  """
    download_geoweaver_jar()
    subprocess.run(
        [get_java_bin_path(), "-jar", get_geoweaver_jar_path(), "resetpassword",]
    )
