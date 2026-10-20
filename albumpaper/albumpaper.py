# external imports
import os, sys, spotipy, requests, logging, logging.handlers, threading, time
from packaging.version import parse as parse_version
from PySide6 import QtWidgets, QtGui, QtCore
from PIL import Image, ImageChops
from io import BytesIO

# In this directory
from ui import SystemTrayIcon, SettingsWindow
from config import ConfigManager, ConfigValidationError, get_resource_path, get_app_dir
from wallpaper import Wallpaper, GenerateWallpaper
from spotifyauth import SpotifyAuth
import winapi, misc, top_played

VERSION = "v4.1.0"  # as tagged on github

# logging
log_path = os.path.join(get_app_dir(), "debug.log")
app_log = logging.getLogger("app")
app_log.setLevel(logging.DEBUG)

# Add rotating file handler (10MB per file, keep 3 backups)
try:
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10*1024*1024, backupCount=3, encoding='utf-8', errors='replace'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    app_log.addHandler(file_handler)
except Exception as e:
    print(f"Could not setup file logging: {e}")

# Add console handler too
console = logging.StreamHandler()
console.setLevel(logging.INFO)
app_log.addHandler(console)

"""
Displays a toast message if a new release is detected
"""
def check_for_updates(tray_icon):
    if not ConfigManager.settings["updates"]["check_for_updates"]:
        return

    try:
        response = requests.get(
            "https://api.github.com/repos/jac0b-w/AlbumPaper/releases/latest",
        )
        latest_version: str = response.json()["tag_name"]
    except Exception:
        return
    if any(substring in latest_version for substring in ["alpha", "beta"]):
        return

    if parse_version(VERSION) < parse_version(latest_version):
        tray_icon.showMessage("New update", f"Update {latest_version} available")


class CurrentArt:
    def __init__(self, service: str):
        if service == "last.fm":  # using lastfm
            self.art_url = self.lastfm_art_url
        else:
            self.art_url = self.spotify_art_url
            self.spotify = SpotifyAuth(tray_icon.showMessage)

        self.missing_art = Image.open(get_resource_path("assets/missing_art.jpg")).convert("RGB")
        self.previous_image_url = None
        self.previously_generated_url = None

    def spotify_art_url(self) -> str:
        try:
            self.spotify.refresh_token()
            current = self.spotify.api.currently_playing()
            if current and current.get("is_playing"):
                item = current.get("item")
                if item:
                    album = item.get("album")
                    if album:
                        images = album.get("images")
                        if images and len(images) > 0:
                            return images[0].get("url", "default")
            return "default"
        except spotipy.client.SpotifyException as e:
            if e.http_status == 429:
                raise e
            try:
                self.spotify.refresh_token()
                current = self.spotify.api.currently_playing()
                if current and current.get("is_playing"):
                    item = current.get("item")
                    if item:
                        album = item.get("album")
                        if album:
                            images = album.get("images")
                            if images and len(images) > 0:
                                return images[0].get("url", "default")
                return "default"
            except Exception as inner_e:
                if isinstance(inner_e, spotipy.client.SpotifyException) and inner_e.http_status == 429:
                    raise inner_e
                return self.previous_image_url if self.previous_image_url else "default"
        except Exception as e:
            print(f"Spotify API Error: {e}")
            return self.previous_image_url if self.previous_image_url else "default"

    def lastfm_request(self):
        try:
            # define headers and URL
            headers = {"user-agent": "AlbumPaper"}
            url = "http://ws.audioscrobbler.com/2.0/"

            payload = {
                "method": "user.getRecentTracks",
                "limit": 1,
                "user": ConfigManager.services["last.fm"]["username"],
                "api_key": ConfigManager.services["last.fm"]["api_key"],
                "format": "json",
            }

            response = requests.get(url, headers=headers, params=payload)
            return response.json()
        except:
            print("[ERROR] Last.fm request error")
            return None

    def lastfm_art_url(self):
        try:
            request_data = self.lastfm_request()
            if not request_data:
                return self.previous_image_url if self.previous_image_url else "default"
            
            tracks = request_data.get("recenttracks", {}).get("track", [])
            if not tracks:
                return self.previous_image_url if self.previous_image_url else "default"
            
            current = tracks[0]
            if current.get("@attr", {}).get("nowplaying", "").lower() == "true":
                images = current.get("image", [])
                if images and isinstance(images, list):
                    url = images[0].get("#text", "")
                    if url:
                        return url.replace("/i/u/34s/", "/i/u/600x600/")
            
            return "default"
        except Exception as e:
            print(f"[ERROR] Last.fm art parsing error: {e}")
            return self.previous_image_url if self.previous_image_url else "default"

    @staticmethod
    @misc.timer
    def get_image(url: str) -> Image.Image:
        try:
            response_content = misc.download_image(url)
            return Image.open(BytesIO(response_content)).convert("RGB")
        except requests.exceptions.MissingSchema:
            return None

    def get_current_art(self):
        """
        3 possible inputs (from self.art_url):
        url string   | Set wallpaper to this image (if it's not lastfm missing image)
        "default"    | Set default wallpaper
        None         | Do not change wallpaper

        4 Possible outputs
        Image.Image  | Generate and set wallpaper to this image
        "default"    | Set default wallpaper
        "generated"  | Set wallpaper to last generated wallpaper
        None         | Do not change wallpaper
        """
        image_url = self.art_url()
        if image_url == self.previous_image_url:  # Image hasn't changed
            return None

        self.previous_image_url = image_url

        if image_url in ("default", None):
            return image_url
        else:  # setting a new non-default wallpaper
            if (
                self.previously_generated_url == image_url
            ):  # wallpaper has already been generated
                return "generated"

            art = self.get_image(image_url)
            if art is None:  # If image couldn't be downloaded
                return "default"
                return art
            # if downloaded image is last.fm missing_art image
            elif ImageChops.difference(art, self.missing_art).getbbox() is None:
                app_log.debug("Downloaded image matches missing_art")
                return "default"
            else:
                self.previously_generated_url = image_url
                app_log.debug(f"Returning new art image. URL: {image_url}")
                return art


class BatterySaverCheckThread(QtCore.QThread):
    # https://stackoverflow.com/a/33150936
    def __init__(self, pause_state_manager, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.pause_state_manager = pause_state_manager

    def run(self):
        try:
            # if disable_on_battery_saver disabled then kill this thread
            if not ConfigManager.settings["power"]["disable_on_battery_saver"]:
                return

            self.sleep = threading.Event()
            battery_saver_enabled_previous = None
            while True:
                battery_saver_enabled = winapi.battery_saver_enabled()
                # To prevent constantly setting desktop to default/generated
                # TODO implement a more elegant solution
                if battery_saver_enabled_previous is not battery_saver_enabled:
                    self.pause_state_manager.set_battery_saver(battery_saver_enabled)

                battery_saver_enabled_previous = battery_saver_enabled
                self.sleep.wait(1)
        except Exception as e:
            app_log.exception("BatterySaverCheck Error")
            if __debug__:
                raise e


class ThrottleManager:
    _path = os.path.join(get_app_dir(), "last_api_call.timestamp")

    @classmethod
    def can_make_call(cls, interval: float) -> bool:
        if not os.path.exists(cls._path):
            return True
        try:
            with open(cls._path, "r") as f:
                last_call = float(f.read().strip())
            return (time.time() - last_call) >= interval
        except:
            return True

    @classmethod
    def record_call(cls):
        try:
            with open(cls._path, "w") as f:
                f.write(str(time.time()))
        except Exception as e:
            app_log.warning(f"Could not update throttle timestamp: {e}")


class WorkerThread(QtCore.QThread):
    auth_ready = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sleep = threading.Event()  # Initialize here to avoid race condition
        self.disabled = False
        self.get_art = None

    def run(self):
        try:
            self.sleep.set()  # Start in running state

            self._pause_request = ConfigManager.settings["miscellaneous"]["paused"]
            self._battery_saver = (
                winapi.battery_saver_enabled()
                and not ConfigManager.settings["power"]["disable_on_battery_saver"]
            )

            self.disabled = ConfigManager.settings["miscellaneous"]["paused"]

            self.get_art = CurrentArt(service=ConfigManager.settings["service"]["name"])
            if hasattr(self.get_art, 'spotify'):
                self.auth_ready.emit(self.get_art.spotify)

            request_interval = ConfigManager.settings["service"]["request_interval"]

            wallaper_generator = GenerateWallpaper(app)

            while True:
                try:
                    if self.disabled:
                        self.sleep.wait()

                    start = time.time()
                    
                    # Global Throttle Check
                    if not ThrottleManager.can_make_call(request_interval):
                        app_log.debug("Skipping iteration: Global throttle active")
                        time.sleep(1)
                        continue

                    app_log.debug("Worker iteration start")
                    image = self.get_art.get_current_art()
                    ThrottleManager.record_call()
                    
                    app_log.debug(f"get_current_art returned type: {type(image)}")

                    if image and image != "default":
                        wallaper_generator.generate(image)
                    elif image == "default":
                         Wallpaper.set(is_default=True)

                    if (
                        ConfigManager.settings["service"]["name"] == "spotify"
                        and hasattr(self.get_art, "spotify")
                        and top_played.should_refresh()
                    ):
                        try:
                            if top_played.refresh_default_wallpaper(
                                self.get_art.spotify.api, wallaper_generator
                            ):
                                ConfigManager.settings["default_wallpaper"]["last_refresh"] = time.time()
                                ConfigManager.save()
                                if self.get_art.previous_image_url in ("default", None):
                                    Wallpaper.set(is_default=True)
                        except Exception as e:
                            app_log.warning(f"Top-played wallpaper refresh failed: {e}")

                    if type(image) == Image.Image:
                        duration = time.time() - start
                        app_log.info(f"Wallpaper generation took {duration:.2f}s")
                        print(f"TOTAL TIME = {duration}")

                except Exception as e:
                    # Check for rate limit
                    if "rate limit" in str(e).lower() or "429" in str(e):
                        app_log.warning(f"Rate limited by Spotify: {e}")
                        # Default to 60s if we can't parse the time
                        sleep_time = 60
                        try:
                            import re
                            match = re.search(r"Retry will occur after: (\d+) s", str(e))
                            if match:
                                sleep_time = int(match.group(1)) + 5
                        except: pass
                        
                        tray_icon.showMessage("Rate Limited", f"Spotify API limited. Sleeping for {sleep_time}s")
                        time.sleep(sleep_time)
                    else:
                        app_log.exception(f"Worker Loop Error: {e}")
                        # Don't crash the thread, just wait a bit and retry
                        time.sleep(5)

                # Correct wait logic: Sleep for interval. 
                # self.sleep.wait returns instantly if set (running).
                # So we must use time.sleep.
                # Use small increments to verify 'disabled' flag more responsively
                slept = 0
                while slept < request_interval:
                    if self.disabled:
                         break
                    time.sleep(1)
                    slept += 1

        except Exception as e:
            app_log.exception("Fatal Worker Error")
            if __debug__:
                raise e

    def check_state(self):
        if self.disabled:
            self.sleep.clear()
            Wallpaper.set(is_default=True)
        else:
            self.sleep.set()
            try:
                self.get_art.previous_image_url = None
            except AttributeError:
                pass

    @QtCore.Slot(str)
    def pause_state(self, state: str):
        if state in ("disabled", "battery_saver"):
            self.disabled = True
        else:
            self.disabled = False
        self.check_state()


class PauseStateSignals(QtCore.QObject):
    pause_state = QtCore.Signal(str)


class PauseStateManager:
    def __init__(self, signal):
        self.user_pause = ConfigManager.settings["miscellaneous"]["paused"]
        self.battery_saver = False

        mutex = QtCore.QMutex()
        self.locker = QtCore.QMutexLocker(mutex)
        self.signal = signal

    def toggle_pause(self):
        with self.locker:
            self.user_pause = not self.user_pause
            ConfigManager.settings["miscellaneous"]["paused"] = self.user_pause
            ConfigManager.save()
        self._send_signal()

    def set_battery_saver(self, enabled: bool):
        with self.locker:
            self.battery_saver = enabled
        self._send_signal()

    def _state(self) -> str:
        with self.locker:
            if self.battery_saver:
                return "battery_saver"
            elif self.user_pause:
                return "disabled"
            else:
                return "enabled"

    def _send_signal(self):
        self.signal.pause_state.emit(self._state())


"""
Some methods to run when the program starts
"""


class OnStartup:
    @staticmethod
    def start_logger():
        try:
            handler = logging.handlers.RotatingFileHandler(
                "errors.log",
                maxBytes=500 * 1024,  # 500 kB
                backupCount=1,
            )
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            handler.setLevel(logging.ERROR)
            app_log = logging.getLogger("root")
            app_log.setLevel(logging.ERROR)
            app_log.addHandler(handler)
            return app_log

        except Exception as e:
            if __debug__:
                raise e

    @staticmethod
    def start_QApplication():
        # High DPI scaling is enabled by default in PySide6
        try:
            app = QtWidgets.QApplication(sys.argv)
        except RuntimeError:  # occurs on restart
            app = QtWidgets.QApplication.instance()

        app.setQuitOnLastWindowClosed(False)

        return app


"""
exit_code = 1, restart app
exit_code = 0, quit app
"""

if __name__ == "__main__":
    app_log.info(f"Module loaded. Version {VERSION}")
    
    exit_code = 1
    
    # Global exception handler
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        app_log.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    sys.excepthook = handle_exception

    # Single-instance guard for the OS process. Must be acquired exactly once,
    # outside the restart loop below: restarting (exit_code=1) re-runs this
    # process's own loop body, and re-acquiring the same lock from the same
    # process every restart would self-deadlock (the previous iteration's
    # lock is only released after the loop ends).
    try:
        mutex = winapi.NamedMutex(b"AlbumPaper")
        app_log.info("App started successfully (Mutex acquired)")
    except winapi.MutexNotAquiredError:
        app_log.warning("App already running (mutex locked)")
        sys.exit(0)

    while exit_code == 1:
        exit_code = 0
        try:
            # We skip OnStartup.start_logger() as we configured logging manually

            # Start QApplication manually to ensure we control it
            try:
                app = QtWidgets.QApplication(sys.argv)
            except RuntimeError:
                app = QtWidgets.QApplication.instance()

            app.setQuitOnLastWindowClosed(False)

            widget = QtWidgets.QWidget()
            pause_state_signals = PauseStateSignals()

            pause_state_manager = PauseStateManager(pause_state_signals)

            tray_icon = SystemTrayIcon(
                icon=QtGui.QIcon(get_resource_path("assets/icons/enabled.png")),
                parent=widget,
                signal=pause_state_signals,
                version=VERSION,
                pause_state_manager=pause_state_manager,
            )

            tray_icon.show()

            if not os.path.exists("images"):
                os.makedirs("images")
            if not os.path.exists("images/default_wallpaper.jpg"):
                Wallpaper.set_default()

            check_for_updates(tray_icon=tray_icon)

            try:
                ConfigManager.validate_service()
            except ConfigValidationError as e:
                tray_icon.showMessage(e.message, "")
                settings_window = SettingsWindow(tray_icon)
                exit_code = settings_window.exec()
            else:
                battery_saver_check_thread = BatterySaverCheckThread(
                    pause_state_manager
                )
                battery_saver_check_thread.start(priority=QtCore.QThread.LowestPriority)

                worker_thread = WorkerThread()
                pause_state_signals.pause_state.connect(worker_thread.pause_state)

                pause_state_signals.pause_state.connect(tray_icon.pause_state)


                worker_thread.finished.connect(app.exit)
                worker_thread.start(priority=QtCore.QThread.LowPriority)

                pause_state_manager._send_signal()
                
                app_log.info("Entering Main Event Loop")
                exit_code = app.exec()

                worker_thread.terminate()

        except Exception as e:
            app_log.exception("Fatal Main Error")
            if __debug__:
                 # Keep window open if possible or just log?
                 pass
            # If crash, exit loop to avoid infinite restart loop on fatal error
            exit_code = 0
            
    if 'mutex' in locals():
        mutex.release()
