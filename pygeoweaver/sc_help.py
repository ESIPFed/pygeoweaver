import subprocess
from pygeoweaver.utils import get_geoweaver_jar_path, get_java_bin_path, get_root_dir


def helpwith(command_list: list = [],):
    target_cmd_args = [get_java_bin_path(), "-jar", get_geoweaver_jar_path()]
    if len(command_list) > 0:
        for i in range(len(command_list) - 1):
            target_cmd_args.append(command_list[i])
        target_cmd_args.append("help")
        target_cmd_args.append(command_list[-1])
    else:
        target_cmd_args.append("help")
    subprocess.run(target_cmd_args, cwd=f"{get_root_dir()}/")
