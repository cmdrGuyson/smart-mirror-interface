from kivy.network.urlrequest import UrlRequest
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen

import imutils
from requests_toolbelt import MultipartEncoder
import cv2
import os

FACE_IDENTIFICATION_URL = os.environ["FACE_IDENTIFICATION_URL"]


class IdleWindow(Screen):
    def __init__(self, stream, **kwargs):
        super(IdleWindow, self).__init__(**kwargs)
        self.stream = stream
        self.pending_response = False

        self.detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml')

        # Clock.schedule_interval(self.change_screen, 5)
        # Clock.schedule_interval(self.detect_face, 1)

    def on_pre_enter(self, **kwargs):
        Clock.schedule_interval(self.detect_face, 1)

    def change_screen(self, user):
        self.manager.transition.direction = 'up'
        self.manager.get_screen('main').set_stuff(user)
        self.manager.current = "main"

    def detect_face(self, t):
        frame = self.stream.read()
        frame = imutils.resize(frame, width=500)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = self.detector.detectMultiScale(
            gray, minSize=(20, 20), scaleFactor=1.5, minNeighbors=5)

        for (x, y, w, h) in faces:
            print("face detected")
            # region of interest
            roi_gray = gray[y:y + h, x:x + w]
            cv2.imwrite("image.png", roi_gray)
            if not self.pending_response:
                self.identify_face(roi_gray)
            # Clock.unschedule(self.detect_face)
            # print("Uncheduled")

    def identify_face(self, frame):
        self.pending_response = True
        imencoded = cv2.imencode(".jpg", frame)[1]
        payload = MultipartEncoder(
            fields={
                'files[]': (
                    'image.jpg',
                    imencoded.tostring(),
                    "image/jpeg"
                )
            }
        )
        headers = {
            'Content-Type': payload.content_type
        }
        UrlRequest(
            FACE_IDENTIFICATION_URL,
            req_headers=headers,
            on_success=self.handle_success,
            on_failure=self.handle_fail,
            on_error=self.handle_error,
            req_body=payload
        )

    def handle_success(self, request, result):
        print("success ", result)
        self.change_screen(result["user"])
        Clock.unschedule(self.detect_face)
        self.pending_response = False

    def handle_fail(self, request, result):
        print("fail ", result)
        self.pending_response = False

    def handle_error(self, request, result):
        print("error ", result)
        self.pending_response = False