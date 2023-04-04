import ctypes
import multiprocessing
import numpy as np
import os
from sys import platform, version

import cv2


class steadyCore:
    """

    A setup program that is OS independant

    """
    def __init__(self):
        """

        A setup program that is OS independent, spins off the main processes of the demo

        """
        print("[STEADY CORE INITIALIZED]: Setup complete, welcome to the demo...")
        self.video_sources = self.get_video_sources()
        self.live_cameras = self.find_changing_sources()

        self.camera_feed = cv2.VideoCapture(self.select_most_eventful_camera())

        self.camera_to_feature_queue = multiprocessing.Queue()
        self.camera_to_ui_queue = multiprocessing.Queue()
        self.feature_to_ui_queue = multiprocessing.Queue()
        self.termination_queue = multiprocessing.Queue()
        self.camera_process = multiprocessing.Process(target=self.multiprocessing_camera_process(), args=(self.termination_queue, self.camera_to_feature_queue, self.camera_to_ui_queue))
        self.feature_process = multiprocessing.Process(target=self.multiprocessing_camera_process(), args=(self.termination_queue, self.camera_to_feature_queue, self.feature_to_ui_queue))
        self.user_interface_process = multiprocessing.Process(target=self.multiprocessing_ui_process(), args=(self.termination_queue, self.camera_to_ui_queue, self.feature_to_ui_queue))

        self.camera_process.start()
        self.feature_process.start()
        self.user_interface_process.start()


    def get_video_sources(self):
        """
        Robustly tries to open camera sources one after the other until we try an index that doesn't exist.

        Returns:
            index : int
                The maximum camera source number that still returns video (for example, two cameras would return int(1))
        """
        index = 0
        arr = []
        while True:
            try:
                cap = cv2.VideoCapture(index)
                if not cap.read()[0]:
                    return index
                else:
                    arr.append(index)
                cap.release()
                index += 1
            finally:
                return index


    def find_changing_sources(self):
        """
        Accesses the list of camera sources available as defined in __init__, and checks to see if they are static.

        Returns:
            arr : list
                A list of live cameras that are experience some kind of refresh formatted [[camera_index, mse],...]
        """
        arr = []
        for camera in range(0, self.video_sources + 1):
            try:
                print("[STATUS]: Reading available camera locally: ", camera)
                camera_test = cv2.VideoCapture(camera)
                ret_2, frame_1 = camera_test.read()
                ret_2, frame_2 = camera_test.read()
                self.is_duplicate = self.find_duplicates()
                if self.find_duplicates(frame_1, frame_2)[0] == False:
                    print("[STATUS]: Camera", camera, "is live and refreshing...")
                    arr.append([camera, self.is_duplicate[1]])
                else:
                    print("[STATUS]: Camera", camera, "is a still image...")
            finally:
                return arr


    def find_duplicates(self, img_1, img_2):
        """
        Checks two images to determine the mean squared error(mse) between them

        Parameters:
            img_1 : cv:mat
                The image taken by the webcam at time = t-1.
            img_2 : cv:mat
                The image taken by the webcam at time = t.

        Returns:
            True/False : bin
                Are the two images exact duplicates?
            err : float
                The exact mse between both images, useful when user has multiple live webcams.
        """
        err = np.sum((img_1.astype("float") - img_2.astype("float")) ** 2)
        err /= float(img_1.shape[0] * img_2.shape[1])
        if abs(err) > 0.1:
            return False, err
        else:
            return True, err


    def select_most_eventful_camera(self):
        """
        Accesses the list of camera sources available as defined in find_changing_sources, and chooses one for the demo.

        Returns:
            current_leader[0] : int
                The index of the camera most likely to be looking at something interesting.
        """
        current_leader = [0, 0]
        for camera_tuple in self.live_cameras:
            if camera_tuple[1] > current_leader[1]:
                current_leader = camera_tuple
        print("[STATUS]: Camera feed",current_leader[0], "selected...")
        return current_leader[0]


    def multiprocessing_camera_process(self):
        # TO-DO
        while True:
            print("hello camera")


    def multiprocessing_feature_process(self):
        # TO-DO
        while True:
            print("hello feature")


    def multiprocessing_ui_process(self):
        # TO-DO
        while True:
            print("hello ui")
