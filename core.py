import os
from sys import platform, version
import subprocess

class Core:
    """

    A setup program that does some python-os interfacing, for a more stable demo.

    """
    def __init__(self, debug):
        """

        A fairly complete init function which checks the OS, stops the program until linux is supported, downloads
        dependencies with pip if the user is on windows, and does a nifty shell->recursion approach if on mac to get
        around the fact python cannot download pip modules from a python script on mac for security purposes.

        @TO-DO: When user has no wifi, pip install calls take way too long to timeout. In the future, we should create
        a last_updated local file and check the date, if it's recent, we can skip all the pip installs. For Mac, this
        will require more shell script logic.

        :param debug: @TO-DO A debug parameter which uses pre-set values for each input and queue to test new code changes.
        """
        print("[STATUS]: CORE INITIALIZED, Kenneth's DEMO core application created...")
        self.screensize = [0, 0]
        if platform == "linux" or platform == "linux2":
            # TO-DO linux
            print("Please try this demo from a windows device")
            exit()
        elif platform == "darwin":
            if self.check_if_user_has_wifi():
                os.system("bash setup.sh")
            else:
                try:
                    os.system("bash run.sh")
                except:
                    print("[STATUS] ERROR: Hi there, please run once with wifi to download dependencies")
            if debug:
                print("[DEBUG] [1] ", os.system("which python"))
        elif platform == "win32":
            import ctypes
            self.user32 = ctypes.windll.user32
            self.screensize = self.user32.GetSystemMetrics(78), self.user32.GetSystemMetrics(79)
            print("[STATUS]: CORE, Checking local Python, pip, and python versions and updating as required...")
            os.system('cmd /c "python.exe -m pip install --upgrade pip"')
            os.system('cmd /c "pip install pip-review"')
            os.system('cmd /c "pip-review --auto"')
            os.system('cmd /c "pip install opencv-python"')
            print("[STATUS] CORE COMPLETE. Your system's pip installer version and every dependancy of this software has been checked for updates automatically.")
        self.version = version[0:4].rstrip(".")
        from steady_core import SteadyCore
        SteadyCore(self.screensize)

    def check_if_user_has_wifi(self, timeout=5):
        try:
            response = subprocess.run(
                ['networksetup', '-getairportnetwork', 'en0'],
                timeout=timeout,
                capture_output=True,
            )
            if "You are not associated" not in response.stdout.decode('utf-8'):
                return True
            else:
                return False
        except subprocess.TimeoutExpired:
            return False


if __name__ == "__main__":
    import sys
    from steady_core import SteadyCore
    print("[STATUS] Loading... Please wait...")
    res = sys.argv[1].split(",")
    IS_MAC = True
    screensize = [int(res[0]), int(res[1])]
    SteadyCore(screensize, IS_MAC)