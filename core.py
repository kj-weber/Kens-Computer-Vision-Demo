import os
from sys import version

from steady_core import steadyCore

class Core:
    """

    A setup program that does some python-os interfacing, for a more stable demo.

    """
    def __init__(self):
        from sys import platform
        print("[CORE INITIALIZED]: Kenneth's DEMO core application created...")
        print("[STATUS]: Calling OS.system to obtain OS...")
        if platform == "linux" or platform == "linux2":
            # TO-DO linux
            print("Please try this demo from a windows device")
            exit()
        elif platform == "darwin":
            # TO-DO darwin
            print("Please try this demo from a windows device")
            exit()
        elif platform == "win32":
            import ctypes
            self.user32 = ctypes.windll.user32
            self.screensize = self.user32.GetSystemMetrics(78), self.user32.GetSystemMetrics(79)
            print("[STATUS]: Checking local Python version...")
            self.version = version[0:4].rstrip(".")
            print("[STATUS]: Checking pip version, and upgrading if required...")
            os.system('cmd /c "pip install --upgrade pip"')
            print("[STATUS]: Checking pip module versions, and upgrading if required...")
            os.system('cmd /c "pip install pip-review"')
            os.system('cmd /c "pip-review --auto"')
            print("[STATUS]: Checking opencv version, and upgrading if required...")
            os.system('cmd /c "pip install opencv-python"')
            print("[CORE COMPLETE] Your system's pip installer version and every dependancy of this software has been checked for updates automatically.")
        steadyCore()