import ctypes
import os
from sys import platform, version

from steady_core import steadyCore

class Core:
    def __init__(self):
        '''

        A setup program that does some python-os interfacing, for a more stable demo.

        '''
        from sys import platform
        print("CORE OPENED")
        if platform == "linux" or platform == "linux2":
            # TO-DO linux
            print("Please try this demo from a windows device")
            exit()
        elif platform == "darwin":
            # TO-DO darwin
            print("Please try this demo from a windows device")
            exit()
        elif platform == "win32":
            self.user32 = ctypes.windll.user32
            self.screensize = self.user32.GetSystemMetrics(78), self.user32.GetSystemMetrics(79)
            self.version = version[0:4].rstrip(".")
            print("os.system calls beginning")
            os.system('cmd /c "pip install --upgrade pip"')
            os.system('cmd /c "pip install pip-review"')
            os.system('cmd /c "pip-review --auto"')
            print("Your system's pip installer version and every dependancy of this software has been checked for updates automatically.")
        steadyCore()