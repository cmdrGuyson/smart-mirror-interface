from kivy.properties import ObjectProperty
from kivy.network.urlrequest import UrlRequest
from kivy.loader import Loader
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from requests_toolbelt import MultipartEncoder

from statistics import mode
import datetime
from datetime import date
import imutils
import time
import cv2
import os

from utils import StringUtils
from dotenv import load_dotenv

from emotion_recognizer import EmotionRecognizer

load_dotenv()

CITY = "Colombo"
WEATHER_API_KEY = os.environ["WEATHER_API_KEY"]
UNITS = "metric"


weather = {"main": {"temp": 25.5}, "weather": [{
    "main": "Thunder", "description": "broken clouds"}]}


class MainWindow(Screen):
    # References to view attributes
    greeting = ObjectProperty(None)
    date = ObjectProperty(None)
    time = ObjectProperty(None)
    weather_type = ObjectProperty(None)
    temperature = ObjectProperty(None)
    weather_icon = ObjectProperty(None)
    news_rv = ObjectProperty(None)
    tweets_rv = ObjectProperty(None)
    emotion = ObjectProperty(None)
    events = ObjectProperty(None)

    def __init__(self, stream, **kwargs):
        super(MainWindow, self).__init__(**kwargs)

        # Stream, detector, and identifiers
        self.stream = stream
        self.detector = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml')
        self.emotionRecognizer = EmotionRecognizer()

        # Booleans
        self.idle = False
        self.identifying_emotion = False

        # Array to store emotional changes
        self.emotions = []

        # API endpoints
        self.EMOTION_IDENTIFICATION_URL = f"{os.environ['API_BASE_URL']}/emotion"
        self.CALENDAR_EVENTS_URL = f"{os.environ['API_BASE_URL']}/calendar"
        self.REFRESH_JWT_URL = f"{os.environ['API_BASE_URL']}/auth"

        # Timezone
        self.LOCAL_TIMEZONE = datetime.datetime.now(
            datetime.timezone.utc).astimezone().tzinfo

    # Setup timed events on enter
    def on_pre_enter(self, **kwargs):
        Clock.schedule_interval(self.change_screen, 60*5)
        Clock.schedule_interval(self.monitor_activity, 1)
        Clock.schedule_interval(self.update_time, 1)
        Clock.schedule_once(self.initial_tweet_request, 10)
        Clock.schedule_interval(self.refresh_jwt, 50*60)
        pass

    # Configure attributes and displays when arriving from idle screen
    def configure_screen(self, user):
        self.greeting.text = "Hello "+user["firstName"]+"!"
        self.user = user
        self.token = user["token"]
        self.refresh_token = user["refreshToken"]

        # Get news and calendar events
        self.get_news()
        self.get_calendar()

        # If user has configured location get weather information
        if "locationId" in user:
            if user["locationId"] != -1:
                self.city = user["locationId"]
                self.WEATHER_API_URL = f"http://api.openweathermap.org/data/2.5/weather?id={self.city}&appid={WEATHER_API_KEY}&units={UNITS}"
                self.get_weather()
            else:
                self.weather_type.font_size = "16sp"
                self.weather_type.text = "Please configure location for weather"
        else:
            self.weather_type.font_size = "16sp"
            self.weather_type.text = "Please configure location for weather"

    # Refresh the JWT token every 50 minutes before expiry
    def refresh_jwt(self, t):
        if self.token is not None:
            headers = {
                'Authorization': 'Bearer ' + self.refresh_token
            }
            UrlRequest(
                self.REFRESH_JWT_URL,
                req_headers=headers,
                on_success=self.handle_refresh_success,
                on_failure=self.handle_refresh_fail,
                on_error=self.handle_refresh_fail,
            )

    # On successful result set new jwt token
    def handle_refresh_success(self, request, result):
        if "token" in result:
            self.token = result["token"]

    # On unsuccessful result when refreshing token logout user
    def handle_refresh_fail(self, request, result):
        print("[INFO] Something went wrong while refreshing token")
        self.change_screen()

    # If not idling unchedule timed events and logout to idle screen
    def check_idle(self, t):
        if self.idle is True:
            self.change_screen()

    # Handle changing screens
    def change_screen(self):
        try:
            # Unschedule events
            Clock.unschedule(self.change_screen)
            Clock.unschedule(self.retrieve_tweets)
            Clock.unschedule(self.monitor_activity)
            Clock.unschedule(self.refresh_jwt)
        except Exception as e:
            print("[INFO] Error unscheduling events ", e)

        self.manager.transition.direction = 'down'
        self.manager.current = "idle"
        self.idle = False

    # Call method on NewsRV class and get news articles
    def get_news(self):
        self.news_rv.get_data(self.token)

    # Make request to endpoint to get calendar events
    def get_calendar(self):
        headers = {
            'Authorization': 'Bearer ' + self.token
        }
        UrlRequest(
            self.CALENDAR_EVENTS_URL,
            req_headers=headers,
            on_success=self.handle_cal_success,
            on_failure=self.handle_cal_fail,
            on_error=self.handle_cal_error,
        )

    # Display calendar events
    def handle_cal_success(self, request, result):
        events = result["events"]

        if events is not None:
            if len(events) > 0:
                self.events.text = StringUtils.get_event_string(events)

    # Failed request while getting calendar events
    def handle_cal_fail(self, request, result):
        self.events.text = "Something went wrong while getting calendar events"

    # Error while getting calendar events
    def handle_cal_error(self, request, result):
        self.events.text = "An error occured while getting calendar events"

    # Check if user is still infornt of mirror
    def monitor_activity(self, t):
        frame = self.stream.read()
        frame = imutils.resize(frame, width=228)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = self.detector.detectMultiScale(
            gray, minSize=(20, 20), scaleFactor=1.5, minNeighbors=5)

        for (x, y, w, h) in faces:
            # region of interest
            roi_gray = gray[y:y + h, x:x + w]
            self.idle = False
            self.handle_emotion_identification(roi_gray)

        if len(faces) == 0:
            self.idle = True

    # Identify user emtoion
    def handle_emotion_identification(self, frame):
        self.current_emotion = self.emotionRecognizer.identify_emotion(
            cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
        self.emotions.append(self.current_emotion)
        self.emotion.source = "images/"+self.current_emotion+".png"

    # Retrieve tweets on user emotion
    def retrieve_tweets(self):
        if len(self.emotions) > 0:
            prominent_emotion = mode(self.emotions)
            self.tweets_rv.get_data(self.token, prominent_emotion)

    # Scheduled event for initial emotion classification and tweet request
    def initial_tweet_request(self, t):

        # Get tweets on prominent emotion
        self.retrieve_tweets()

        # Schedule event for 5 min intervals
        Clock.schedule_interval(self.initial_tweet_request, 5*60)

    # Call weather endpoint and get weather information
    def get_weather(self):
        UrlRequest(self.WEATHER_API_URL, on_success=self.handle_weather_success,
                   on_error=self.handle_weather_error, on_failure=self.handle_weather_fail)
        # self.handle_weather_success(None, weather)

    # Update view after successfully getting weather information
    def handle_weather_success(self, request, result):
        self.temperature.text = str(round(result["main"]["temp"], 1)) + "°C"
        self.weather_type.text = result["weather"][0]["description"].title()
        self.weather_icon.source = "images/" + \
            result["weather"][0]["main"] + ".gif"

    # Failed request while getting weather information
    def handle_weather_fail(self, request, response):
        self.weather_type.text = "Something went wrong!"

    # Error while getting weather information
    def handle_weather_error(self, request, response):
        self.weather_type.text = "Error while getting weather!"

    # Update date time in each second
    def update_time(self, t):
        today = date.today()
        current_time = datetime.datetime.now(self.LOCAL_TIMEZONE).time()
        self.time.text = current_time.strftime("%H:%M")
        self.date.text = today.strftime(
            "%A, %d" + StringUtils.get_suffix(today) + " of %B")

    '''
    Methods to be used by lower spec Raspberry Pi device to identify emotion with RESTful API
    '''

    def identify_emotion(self, frame):
        if not self.identifying_emotion:
            self.identifying_emotion = True

            # Encode image to be sent
            imencoded = cv2.imencode(".jpg", frame)[1]

            # Create multipart form data for request
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
                'Content-Type': payload.content_type,
                'Authorization': 'Bearer ' + self.token
            }
            UrlRequest(
                self.EMOTION_IDENTIFICATION_URL,
                req_headers=headers,
                on_success=self.handle_success,
                on_failure=self.handle_fail,
                on_error=self.handle_error,
                req_body=payload
            )

    def handle_success(self, request, result):
        print("[INFO] Successfully identified emotion", result["emotion"])
        self.current_emotion = result["emotion"]
        self.identifying_emotion = False
        self.emotion.source = "images/"+self.current_emotion+".png"

    def handle_fail(self, request, result):
        print("[INFO] Failed while identifying emotion")
        self.identifying_emotion = False

    def handle_error(self, request, result):
        print("[INFO] Error while identifying emotion")
        self.identifying_emotion = False
