
import subprocess
from pygeoweaver.utils import download_geoweaver_jar, get_geoweaver_jar_path, get_root_dir


def reset_password():
  """
  Usage: <main class> resetpassword
  Reset password for localhost
  """
  download_geoweaver_jar()
  subprocess.run(["java", "-jar", get_geoweaver_jar_path(), "resetpassword",])

