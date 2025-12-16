import os, json
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.core.audio import SoundLoader
from kivy.properties import StringProperty, NumericProperty
from kivymd.app import MDApp
from kivymd.uix.list import OneLineAvatarListItem

# ----------- PATH DEL PROGETTO -----------
DATA_DIR = "data"
AUDIO_DIR = "audio"
IMG_DIR = "images"
BADGE_DIR = "medaglie"

USER_DB = os.path.join(DATA_DIR, "users.json")
LESSON_DB = os.path.join(DATA_DIR, "lessons.json")

ALLOWED_DOMAINS = ["@primaria.scuola.it", "@media.scuola.it"]


# ----------- GENERAZIONE AUTOMATICA FILE E CARTELLE -----------
def setup_project():
    folders = [
        DATA_DIR,
        AUDIO_DIR,
        os.path.join(AUDIO_DIR, "primaria"),
        os.path.join(AUDIO_DIR, "media"),
        IMG_DIR,
        BADGE_DIR,
    ]

    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)

    # --- USERS FILE ---
    if not os.path.exists(USER_DB):
        with open(USER_DB, "w") as f:
            json.dump({}, f, indent=4)

    # --- LESSONS FILE ---
    if not os.path.exists(LESSON_DB):
        lessons = {
            "primaria": [
                {
                    "title": "Colori",
                    "word": "Red",
                    "image": "images/red.png",
                    "audio": "audio/primaria/red.mp3"
                },
                {
                    "title": "Animali",
                    "word": "Cat",
                    "image": "images/cat.png",
                    "audio": "audio/primaria/cat.mp3"
                }
            ],
            "media": [
                {
                    "title": "Frasi Base",
                    "word": "How are you?",
                    "image": "images/how.png",
                    "audio": "audio/media/how.mp3"
                },
                {
                    "title": "Verbi",
                    "word": "Study",
                    "image": "images/study.png",
                    "audio": "audio/media/study.mp3"
                }
            ]
        }
        with open(LESSON_DB, "w") as f:
            json.dump(lessons, f, indent=4)

    # --- PLACEHOLDER MEDAGLIE ---
    for badge in ["bronzo.txt", "argento.txt", "oro.txt"]:
        path = os.path.join(BADGE_DIR, badge)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write("badge placeholder")


# ----------- FUNZIONI DATABASE -----------
def load_db(path):
    with open(path) as f:
        return json.load(f)

def save_db(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def is_school_email(email):
    return any(email.endswith(dom) for dom in ALLOWED_DOMAINS)


# ----------- SCHERMATE -----------
class LoginScreen(Screen):
    def register(self):
        users = load_db(USER_DB)
        email = self.ids.email.text
        password = self.ids.password.text

        if not is_school_email(email):
            self.ids.msg.text = "Serve un'email scolastica."
            return

        if email in users:
            self.ids.msg.text = "Account già registrato."
            return

        users[email] = {
            "password": password,
            "xp": 0,
            "streak": 0,
            "current_unit": 0,
            "badges": [],
            "school_level": "primaria" if "primaria" in email else "media"
        }

        save_db(USER_DB, users)
        self.ids.msg.text = "Registrazione completata!"

    def login(self):
        users = load_db(USER_DB)
        email = self.ids.email.text
        password = self.ids.password.text

        if email in users and users[email]["password"] == password:
            self.manager.current_user = email
            self.manager.current = "home"
        else:
            self.ids.msg.text = "Credenziali errate."


class HomeScreen(Screen):
    username = StringProperty("")
    xp = NumericProperty(0)
    streak = NumericProperty(0)

    def on_pre_enter(self):
        users = load_db(USER_DB)
        user = users[self.manager.current_user]

        self.username = self.manager.current_user.split("@")[0]
        self.xp = user["xp"]
        self.streak = user["streak"]

    def start_learning(self):
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = "units"


class UnitScreen(Screen):
    def on_pre_enter(self):
        self.ids.unit_list.clear_widgets()

        lessons = load_db(LESSON_DB)
        users = load_db(USER_DB)
        
        user = users[self.manager.current_user]
        level = user["school_level"]

        for i, lesson in enumerate(lessons[level]):
            name = lesson["title"]
            item = OneLineAvatarListItem(text=f"Unità {i+1}: {name}")
            item.bind(on_release=lambda x, idx=i: self.open_lesson(idx))
            self.ids.unit_list.add_widget(item)

    def open_lesson(self, index):
        self.manager.current_lesson = index
        self.manager.current = "lesson"


class LessonScreen(Screen):
    text_word = StringProperty("")
    image_path = StringProperty("")
    audio_file = StringProperty("")

    def on_pre_enter(self):
        lessons = load_db(LESSON_DB)
        users = load_db(USER_DB)
        user = users[self.manager.current_user]

        level = user["school_level"]
        lesson_index = self.manager.current_lesson
        lesson = lessons[level][lesson_index]

        self.text_word = lesson["word"]
        self.audio_file = lesson["audio"]
        self.image_path = lesson["image"]

    def play_audio(self):
        sound = SoundLoader.load(self.audio_file)
        if sound:
            sound.play()

    def go_quiz(self):
        self.manager.current = "quiz"


class QuizScreen(Screen):
    correct_answer = StringProperty("")

    def on_pre_enter(self):
        lessons = load_db(LESSON_DB)
        users = load_db(USER_DB)
        user = users[self.manager.current_user]

        level = user["school_level"]
        lesson_index = self.manager.current_lesson
        lesson = lessons[level][lesson_index]

        self.correct_answer = lesson["word"]

    def check_answer(self):
        ans = self.ids.answer.text.lower().strip()
        users = load_db(USER_DB)
        user = users[self.manager.current_user]

        if ans == self.correct_answer.lower():
            self.ids.result.text = "Corretto! +10 XP"
            user["xp"] += 10
            user["streak"] += 1

            # Medaglie basate su XP
            if user["xp"] >= 50 and "bronzo" not in user["badges"]:
                user["badges"].append("bronzo")
            if user["xp"] >= 120 and "argento" not in user["badges"]:
                user["badges"].append("argento")
            if user["xp"] >= 200 and "oro" not in user["badges"]:
                user["badges"].append("oro")

        else:
            self.ids.result.text = "Risposta errata."
            user["streak"] = 0

        users[self.manager.current_user] = user
        save_db(USER_DB, users)


# ----------- MAIN APP -----------
class LinguaBoostSchool(MDApp):
    def build(self):
        setup_project()  # CREA TUTTO AUTOMATICAMENTE

        sm = ScreenManager()
        sm.current_user = None
        sm.current_lesson = None

        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(UnitScreen(name="units"))
        sm.add_widget(LessonScreen(name="lesson"))
        sm.add_widget(QuizScreen(name="quiz"))

        return sm


if __name__ == "__main__":
    LinguaBoostSchool().run()
