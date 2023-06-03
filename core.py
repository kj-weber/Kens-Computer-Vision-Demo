import os
from sys import version


class Core:
    """

    A setup program that does some python-os interfacing, for a more stable demo.

    """
    def __init__(self):
        from sys import platform
        print("[CORE INITIALIZED]: Kenneth's DEMO core application created...")
        if platform == "linux" or platform == "linux2":
            # TO-DO linux
            print("Please try this demo from a windows device")
            exit()
        elif platform == "darwin":
            os.system("bash setup.sh")
            print("[DEBUG] [1] ", os.system("which python"))
            exit()

            self.screensize = [0,0]
        elif platform == "win32":
            import ctypes
            self.user32 = ctypes.windll.user32
            self.screensize = self.user32.GetSystemMetrics(78), self.user32.GetSystemMetrics(79)
            print("[CORE STATUS]: Checking local Python, pip, and python versions and updating as required...")
            os.system('cmd /c "python.exe -m pip install --upgrade pip"')
            os.system('cmd /c "pip install pip-review"')
            os.system('cmd /c "pip-review --auto"')
            os.system('cmd /c "pip install opencv-python"')
            print("[CORE COMPLETE] Your system's pip installer version and every dependancy of this software has been checked for updates automatically.")
        self.version = version[0:4].rstrip(".")
        from steady_core import SteadyCore
        SteadyCore(self.screensize)
if __name__ == "__main__":
    import sys
    from steady_core import SteadyCore
    print("calling steady core")
    SteadyCore(sys.argv[1])