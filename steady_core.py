import multiprocessing
import numpy as np
import os
import time

import cv2

from face_detector import FaceDetector


class SteadyCore:
    """

    A setup program that is OS independent.

    """
    def __init__(self, screen_size, is_mac):
        """
        A setup program that is OS independent, spins off the main processes of the demo

        :param screen_size: lst : (screen_width_in_pixels, screen_height_in_pixels)
        :param is_mac: bool : A flag for if the automatic OS check logic has determined we are on macOS, as mac
        seems to like handcuffing python scripts for security.
        """
        self.IS_MAC = is_mac
        self.is_duplicate = False
        self.SCREENSIZE = screen_size
        print("[STATUS]: Steady core initialized, welcome to the demo...")

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
        user_interface_process = multiprocessing.Process(target=multiprocessing_ui_process, args=(termination_queue, camera_to_ui_queue, feature_to_ui_queue, self.SCREENSIZE,))

        camera_process.start()
        feature_process.start()
        user_interface_process.start()

        # camera_process.join()
        # feature_process.join()
        user_interface_process.join()

        camera_process.kill()
        feature_process.kill()
        user_interface_process.kill()
        print("[STATUS] Demo closed successfully. Thank you for checking out my software competency demo!")

    @staticmethod
    def get_video_sources():
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
                if not self.is_duplicate[0]:
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

    @staticmethod
    def find_duplicates(img_1, img_2):
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


def termination_check(queue):
    """
    A function which is designed to check termination queue, while retaining its queue size of 1.
    :param queue: multiprocessing.Queue : A queue, most likely termination_queue.
    :return: bool : The value that was in, and is still in, the queue.
    """
    try:
        value = queue.get_nowait()
        queue.put(value)
        return value
    except:
        return False


def request_termination(queue):
    """
    The function a parallel process can call to kill all other processes, and hence the demo.
    :param queue: multiprocessing.Queue : A queue, most likely termination_queue.
    :return: Nothing, every process will see this value is now true when they next call termination_check.
    """
    look_and_clear(queue)
    queue.put(True)


def clear_queue(queue):
    """
    A function that reads the queue rapidly until it is empty.
    :param queue: multiprocessing.Queue :
    :return:
    """
    value = 0
    while value is not None:
        try:
            value = queue.get_nowait()
        except:
            return True
    return True
def multiprocessing_camera_process(termination_queue, camera_to_feature_queue, camera_to_ui_queue, camera_source, is_mac_os):
    """
    The process which continously reads the selected camera source, most likely a webcam.
    :param termination_queue: multiprocessing.Queue : A shared queue of size 1 which when holding False, allows the demo to continue.
    :param camera_to_feature_queue: multiprocessing.Queue : A shared queue transferring the image to the  feature logic parallel process.
    :param camera_to_ui_queue: multiprocessing.Queue : A shared queue allowing transfer of the raw image straight to the UI parallel process.
    :param camera_source: int : The index of the selected camera, most likely a webcam.
    :param is_mac_os: bool : Mac has some strange behaviour, so we're passing a flag from core to allow this bugfix here in the future.
    :return: Nothing. All I/O is handled by queues.
    """
    # @TODO fix camera failure when called from command line on macOS
    web_cam = cv2.VideoCapture(camera_source)
    while True:
        termination_requested = termination_check(termination_queue)
        if termination_requested:
            exit()
        ret, img = web_cam.read()
        if ret:
            if img.shape[0] > 0:
                clear_queue(camera_to_feature_queue)
                clear_queue(camera_to_ui_queue)
                camera_to_feature_queue.put(img)
                camera_to_ui_queue.put(img)


def multiprocessing_feature_process(termination_queue, camera_to_feature_queue, feature_to_ui_queue):
    """
    The process which computes the entire feature logic.
    :param termination_queue: multiprocessing.Queue : A shared queue of size 1 which when holding False, allows the demo to continue.
    :param camera_to_feature_queue: multiprocessing.Queue : A shared queue transferring the image to the  feature logic parallel process.
    :param feature_to_ui_queue: multiprocessing.Queue : A shared queue passing the result of the feature logic to the UI parallel process.
    :return: Nothing, all I/O is handled by queues.
    """
    face_detect = FaceDetector()
    feature_input_count = 0     # @TODO Only run expensive algos every few frames.
    feature_output_count = 0    # @TODO Only run expensive algos every few frames.
    while True:
        termination_requested = termination_check(termination_queue)
        if termination_requested:
            exit()
        img = camera_to_feature_queue.get()
        if img is not None:
            face_detect.detect(img)
            img = face_detect.draw_faces()
            clear_queue(feature_to_ui_queue)
            feature_to_ui_queue.put(img)
        else:
            continue


def multiprocessing_ui_process(termination_queue, camera_to_ui_queue, feature_to_ui_queue, screensize):
    """
    The queue which handles all UI logic, including the ability for the user to escape the demo.
    :param termination_queue: multiprocessing.Queue : A shared queue of size 1 which when holding False, allows the demo to continue.
    :param camera_to_feature_queue: multiprocessing.Queue : A shared queue transferring the image to the  feature logic parallel process.
    :param feature_to_ui_queue: multiprocessing.Queue : A shared queue passing the result of the feature logic to the UI parallel process.
    :param screensize: (height, width)
    :return: Nothing, all I/O is handled by queues.
    """
    # cv2.namedWindow("Ken's Demo", cv2.WINDOW_NORMAL) @TODO Create window with freedom of dimensions
    content = np.zeros((screensize[1], screensize[0], 3))
    while True:
        termination_requested = termination_check(termination_queue)
        if termination_requested:
            exit()
        last_content = content
        content = feature_to_ui_queue.get()
        if content is None:
            content = last_content
        cv2.imshow("Ken's Demo", content)
        if cv2.waitKey(5) == ord("q"):
            request_termination(termination_queue)
            cv2.destroyAllWindows()
        clear_queue(feature_to_ui_queue)
