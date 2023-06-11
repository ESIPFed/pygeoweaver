import subprocess
from pygeoweaver.utils import (
    download_geoweaver_jar,
    get_geoweaver_jar_path,
    get_java_bin_path,
    get_root_dir,
)


def import_workflow(workflow_zip_file_path):
    """
  Usage: <main class> import workflow <workflow_zip_file_path>
  import a workflow from file
        <workflow_zip_file_path>
          Geoweaver workflow zip file path
  """
    if not workflow_zip_file_path:
        raise RuntimeError("Workflow zip file path is missing")
    download_geoweaver_jar()
    subprocess.run(
        [
            get_java_bin_path(),
            "-jar",
            get_geoweaver_jar_path(),
            "import",
            "workflow",
            workflow_zip_file_path,
        ],
        cwd=f"{get_root_dir()}/",
    )
