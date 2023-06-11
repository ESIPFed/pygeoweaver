import subprocess
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
)


def export_workflow(workflow_id, mode, target_file_path):
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
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "export",
            "workflow",
            f"--mode={mode}",
            workflow_id,
            target_file_path,
        ],
        cwd=f"{get_root_dir()}/",
    )
