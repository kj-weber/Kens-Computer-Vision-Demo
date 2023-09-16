import cv2


class FaceDetector:
    def __init__(self):
        """
        A class containing a logic related to face detection, perhaps used in the future
        for my very own intrinsic and/or extrinsic camera calibration logic for the webcam.
        (google online camera alignment)

        """
        self.face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
        self.face_detected = False
        self.faces = ()
        self.faces_detected = 0

    def detect(self, img):
        """
        A function which accepts an image and returns information for each face found within the image..

        :param img: cv_mat : Input image.
        :return: self.faces : list_of_lists : A list of size faces, with each element containing x,y,w,h of the face.
        """
        self.img = img
        self.gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        self.faces = self.face_cascade.detectMultiScale(self.gray, 1.1, 4)
        self.faces_detected = len(self.faces)
        if self.faces_detected == 0:
            return None
        else:
            self.face_detected = True
            return self.faces

    def draw_faces(self):
        """
        A function which draws a bounding box on each face.
        :return: self.img : The image, now with bounding boxes.
        """
        for (x, y, w, h) in self.faces:
            cv2.rectangle(self.img, (x, y), (x + w, y + h), (255, 0, 0), 2)
            return self.img

    def look_within_face(self):
        """
        A function which creates a sub-image containing the grayscale pixels defined in each bounding box.
        :return: self.face_img : cv_mat : See above.
        """
        (x, y, w, h) = self.faces[0]
        self.face_img = self.gray[x:x+w, y:y+h]