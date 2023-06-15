import subprocess
from pygeoweaver.utils import (
    check_ipython,
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
)

def get_password_twice():
    while True:
        password1 = getpass('Enter password: ')
        password2 = getpass('Re-enter password: ')
        
        if password1 == password2:
            return password1
        else:
            print("Passwords don't match. Please try again.")


def reset_password():
    """
    Usage: <main class> resetpassword
    Reset password for localhost
    """
    download_geoweaver_jar()
    
    if check_ipython():
        password = get_password_twice()
        subprocess.run(
            [
                get_java_bin_path(),
                "-jar",
                get_geoweaver_jar_path(),
                "resetpassword",
                "-p",
                password
            ]
        )
    else:
        subprocess.run(
            [
                get_java_bin_path(),
                "-jar",
                get_geoweaver_jar_path(),
                "resetpassword",
            ]
        )
