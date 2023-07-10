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
        for (x, y, w, h) in self.faces:
            cv2.rectangle(self.img, (x, y), (x + w, y + h), (255, 0, 0), 2)
            return self.img

    def look_within_face(self):
        (x, y, w, h) = self.faces[0]
        self.face_img = self.gray[x:x+w, y:y+h]