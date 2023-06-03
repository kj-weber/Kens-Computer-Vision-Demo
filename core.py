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
            Recursion could work here, python could call a bach sript to setup venv, then tbd
            sudo_password = input("On Mac, your password is required to install demo dependancies, please enter for "
                                    "tmp use only")
            # DEBUG
            try:
                command = 'sudo pip install virtualenv'
                p = os.system('echo %s|sudo -S %s' % (sudo_password, command))
            except:
                try:
                    command = 'sudo -H pip install virtualenv'
                    p = os.system('echo %s|sudo -S %s' % (sudo_password, command))
                except:
                    print("Incorrect password or skipped")
            # DEBUG
            print("[DEBUG] [1] ", os.system("which python"))
            print("[DEBUG] [2] ", os.system("which pip"))
            os.system("virtualenv venv_ken")
            os.system("source venv_ken/bin/activate")
            path_to_venv = os.path.join(os.getcwd(), 'venv_ken', "bin")
            # IN-PROGRESS point pip to correct interpreter
            os.system('export PATH=%s:${PATH}' % path_to_venv)
            print("[DEBUG] [3] ", 'export PATH=%s' % path_to_venv)
            # DEBUG
            print("[DEBUG] [4] ", os.system("which python"))
            # os.system("export PATH=/Library/Frameworks/Python.framework/Versions/2.7/bin/python:${PATH}")
            print("[DEBUG] [5] ", os.system("which pip"))
            exit()
            os.system("python -m pip install --upgrade pip")
            os.system("python -m pip install pip-review")
            os.system("pip-review --auto")
            os.system("python -m pip install numpy")
            os.system("python -m pip install opencv-python")
            # os.system("python -m pip install --upgrade pip")
            # os.system("python -m pip install pip-review")
            # os.system("pip-review --auto")
            # os.system("python -m pip install numpy")
            # os.system("python -m pip install opencv-python")
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