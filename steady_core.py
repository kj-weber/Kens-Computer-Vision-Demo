import ctypes
import multiprocessing
import numpy as np
import os
from sys import platform, version
import time #TO-DO remove

import cv2


class SteadyCore:
    """

    A setup program that is OS independant

    """
    def __init__(self, screen_size):
        """

        A setup program that is OS independent, spins off the main processes of the demo

        """
        SCREENSIZE = screen_size
        print("[STEADY CORE INITIALIZED]: Setup complete, welcome to the demo...")
        self.video_sources = self.get_video_sources()
        self.live_cameras = self.find_changing_sources()
        self.camera_source = self.select_most_eventful_camera()
        print(self.camera_source)

        camera_to_feature_queue = multiprocessing.Queue()
        camera_to_ui_queue = multiprocessing.Queue()
        feature_to_ui_queue = multiprocessing.Queue()
        termination_queue = multiprocessing.Queue()
        termination_queue.put(0)
        camera_process = multiprocessing.Process(target=multiprocessing_camera_process, args=(termination_queue, camera_to_feature_queue, camera_to_ui_queue,self.camera_source))
        feature_process = multiprocessing.Process(target=multiprocessing_feature_process, args=(termination_queue, camera_to_feature_queue, feature_to_ui_queue,))
        user_interface_process = multiprocessing.Process(target=multiprocessing_ui_process, args=(termination_queue, camera_to_ui_queue, feature_to_ui_queue,SCREENSIZE,))

        camera_process.start()
        feature_process.start()
        user_interface_process.start()

        camera_process.join()
        feature_process.join()
        user_interface_process.join()

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
                    cap.release()
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
                camera_test = cv2.VideoCapture(camera)
                ret_2, frame_1 = camera_test.read()
                time.sleep(1)
                ret_2, frame_2 = camera_test.read()
                self.is_duplicate = self.find_duplicates(frame_1, frame_2)
                if self.is_duplicate[0] == False:
                    arr.append([camera, self.is_duplicate[1]])
                    camera_test.release()
                else:
                    camera_test.release()
            finally:
                try:
                    camera_test.release()
                except:
                    print("[STATUS}: Camera test closed...")
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
        return current_leader[0]


def look_and_clear(queue):
    value = None
    while True:
        try:
            value = queue.get_nowait()
        except:
            return value



def multiprocessing_camera_process(termination_queue, camera_to_feature_queue, camera_to_ui_queue, camera_source):
    web_cam = cv2.VideoCapture(camera_source)
    while True:
        ret, img = web_cam.read()
        camera_to_feature_queue.put(img)


def multiprocessing_feature_process(termination_queue, camera_to_feature_queue, feature_to_ui_queue):
    # TO-DO
    while True:
        img = look_and_clear(camera_to_feature_queue)
        feature_to_ui_queue.put(img)


def multiprocessing_ui_process(termination_queue, camera_to_ui_queue, feature_to_ui_queue, SCREEN_SIZE):
    cv2.namedWindow("Ken's Demo", cv2.WINDOW_NORMAL)  # Create window with freedom of dimensions
    # TO DO CREATE LAST_CONTENT AND CONTENT AS BLACK IMAGES WITH SIZE SCREEN_SIZE
    while True:
        last_content = content
        content = look_and_clear(feature_to_ui_queue)
        if content is None:
            last_content = content
        cv2.imshow("Ken's Demo", content)
        cv2.waitKey(10)
        # try:
        #     termination = termination_queue.get_nowait()
        #     empty = False
        # except:
        #     termination = False
        #     empty = True
        # if empty and not termination:
        #     exit()
        # try:
        #     img = camera_to_ui_queue.get_nowait()
        #     print(img)
        # except:
        #     continue
        # output = feature_to_ui_queue.get_nowait()
