import os.path
import zipfile
import subprocess
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
)


def export_workflow(
    workflow_id, mode=4, target_file_path=None, unzip=False, unzip_directory_name=None
):
    """
    Usage: <main class> export workflow [--mode=<export_mode>] <workflow_id>
                                    <target_file_path>
      <workflow_id>          Geoweaver workflow ID
      <target_file_path>     target file path to save the workflow zip
      --mode=<export_mode>   exportation model options:
                                1 - workflow only
                                2 - workflow with process code
                                3 - workflow with process code and only good
                               history
                                4 - workflow with process code and all the
                               history.default option is 4.
    """
    if not workflow_id:
        raise RuntimeError("Workflow id is missing")
    download_geoweaver_jar()

    # Resolve the absolute path for the target file
    absolute_target_file_path = os.path.abspath(target_file_path)

    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "export",
            "workflow",
            f"--mode={mode}",
            workflow_id,
            absolute_target_file_path,
        ],
        cwd=f"{get_root_dir()}/",
    )
    if unzip:
        if not unzip_directory_name:
            raise Exception("Please provide unzip directory name")
        with zipfile.ZipFile(absolute_target_file_path, "r") as zip_ref:
            zip_ref.extractall(
                os.path.join(os.path.dirname(absolute_target_file_path), unzip_directory_name)
            )
