import unittest
import subprocess
import sys

class TestPythonInstallation(unittest.TestCase):

  def test_installation(self):
    # Attempt to install your package
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'pygeoweaver'],
                            capture_output=True, text=True)

    self.assertEqual(result.returncode, 0, "Installation failed")

    # Optionally, try importing your package
    try:
      import pygeoweaver
    except ImportError:
      self.fail("Failed to import pygeoweaver after installation")

if __name__ == '__main__':
  unittest.main()
