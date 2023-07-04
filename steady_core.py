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
    def __init__(self, screen_size, is_mac):
        """
        A setup program that is OS independent, spins off the main processes of the demo

        :param screen_size: lst : (screen_width_in_pixels, screen_height_in_pixels)
        :param is_mac: bool : A flag for if the automatic OS check logic has determined we are on a mac device, as mac
        seems to like handcuffing python scripts for security.
        """
        DEBUG = False
        self.SCREENSIZE = screen_size
        self.IS_MAC = is_mac
        print("[STEADY CORE INITIALIZED]: Setup complete, welcome to the demo...")
        self.video_sources = self.get_video_sources()
        self.live_cameras = self.find_changing_sources()
        self.camera_source = self.select_most_eventful_camera()

        camera_to_feature_queue = multiprocessing.Queue()
        camera_to_ui_queue = multiprocessing.Queue()
        feature_to_ui_queue = multiprocessing.Queue()
        termination_queue = multiprocessing.Queue()
        termination_queue.put(0)
        camera_process = multiprocessing.Process(target=multiprocessing_camera_process, args=(termination_queue, camera_to_feature_queue, camera_to_ui_queue,self.camera_source, self.IS_MAC))
        feature_process = multiprocessing.Process(target=multiprocessing_feature_process, args=(termination_queue, camera_to_feature_queue, feature_to_ui_queue,))
        user_interface_process = multiprocessing.Process(target=multiprocessing_ui_process, args=(termination_queue, camera_to_ui_queue, feature_to_ui_queue,self.SCREENSIZE,))

        camera_process.start()
        feature_process.start()
        user_interface_process.start()

        camera_process.join()
        feature_process.join()
        user_interface_process.join()

        if DEBUG:
            debug_process = multiprocessing.Process(target=debug_queue_printer, args=(camera_to_feature_queue))
            debug_process.start()
            debug_process.join()

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
    """
    A function which reads a FIFO queue until it is empty, and returns the most recent value, effectively turning it
    into a LIFO (last in first out) queue, only operating in a small <5ms time window.
    :param queue: multiprocessing.Queue object : FIFO queue of storing any datatype, can be empty.
    :return: any : Returns the most recent value regardless of datatype.
    """
    value = None
    while value is None:
        try:
            value = queue.get_nowait()
        except:
            continue
        while value is not None:
            prev_val = value
            try:
                value = queue.get_nowait()
            except:
                return prev_val



def multiprocessing_camera_process(termination_queue, camera_to_feature_queue, camera_to_ui_queue, camera_source, is_mac_os):
    web_cam = cv2.VideoCapture(camera_source)
    # if not is_mac_os:
    #     while True:
    #         ret, img = web_cam.read()
    #         # Mac prevents non-Apple developers from reading webcam :(
    #         if not ret and img.size.width > 0:
    #             camera_to_feature_queue.put(img)
    #         else:
    #             camera_to_feature_queue.put(None)
    #         time.sleep(0.001)
    # else:
    #     img = debug_image_loader()
    #     while True:
    #         camera_to_feature_queue.put(img)
    #         time.sleep(0.005)
    while True:
        # @TO-DO WHERE I LEFT OFF ON PLANE
        ret, img = web_cam.read()
        if ret:
            if img.shape[0] > 0:
                camera_to_feature_queue.put(img)
        time.sleep(0.003)

def multiprocessing_feature_process(termination_queue, camera_to_feature_queue, feature_to_ui_queue):
    # TO-DO
    while True:
        img = look_and_clear(camera_to_feature_queue)
        if img is not None:
            feature_to_ui_queue.put(img)
        else:
            continue


def multiprocessing_ui_process(termination_queue, camera_to_ui_queue, feature_to_ui_queue, SCREEN_SIZE):
    # cv2.namedWindow("Ken's Demo", cv2.WINDOW_NORMAL)  # Create window with freedom of dimensions
    # TO DO CREATE LAST_CONTENT AND CONTENT AS BLACK IMAGES WITH SIZE SCREEN_SIZE
    content = np.zeros((SCREEN_SIZE[1], SCREEN_SIZE[0], 3))
    while True:
        last_content = content
        content = look_and_clear(feature_to_ui_queue)
        if content is None:
            content = last_content
        cv2.imshow("Ken's Demo", content)
        cv2.waitKey(5)
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


def debug_image_loader():
    return cv2.imread(os.path.join("src", "mac_debug_img.png"))

def debug_queue_printer(queue):
    while True:
        val = queue.get()
        print(type(val))
        queue.put(val)