"""
Classes in this file:
  SystemTrayIcon
  SettingsWindow
"""

from PySide6 import QtWidgets, QtGui, QtCore
import os, sys, subprocess

from config import ConfigManager, ConfigValidationError, get_resource_path
from wallpaper import Wallpaper

GITHUB_LINK = "https://github.com/ibraheemmryyian/AlbumPaper-Plus/"
BACKGROUND_TYPES = (
    "Solid",
    "Linear Gradient",
    "Radial Gradient",
    "Colored Noise",
    "Art",
    "Wallpaper",
    "Random",
)
# background types that are built from album art, so blur applies to them
BLUR_BACKGROUNDS = ("Colored Noise", "Art", "Wallpaper", "Random")


def asset_path(relative_path):
    """Helper to get asset paths that works with PyInstaller"""
    return get_resource_path(relative_path)


def themes_dir():
    return get_resource_path("themes")


def list_themes():
    """Theme names are the .py filenames in the themes folder (same folder ConfigManager reads)"""
    try:
        names = os.listdir(themes_dir())
    except FileNotFoundError:
        return []
    return sorted(os.path.splitext(name)[0] for name in names if name.endswith(".py"))


class SystemTrayIcon(QtWidgets.QSystemTrayIcon):
    def __init__(self, icon, parent, signal, version, pause_state_manager):
        QtWidgets.QSystemTrayIcon.__init__(self, icon, parent)
        self.setToolTip("AlbumPaper-Plus")
        self.context_menu = QtWidgets.QMenu(parent)
        self.signal = signal
        self.VERSION = version
        self.icon_color = ConfigManager.theme()["icon_color"]
        self.pause_state_manager = pause_state_manager

        try:
            self.context_menu.setStyleSheet(ConfigManager.theme()["menu"])
        except KeyError:
            pass

        default_wallpaper_item = self.context_menu.addAction(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/wallpaper.png")),
            "Set Default Wallpaper",
        )
        default_wallpaper_item.triggered.connect(self.set_default_wallpaper)

        self.context_menu.addSeparator()

        settings_item = self.context_menu.addAction(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/settings.png")), "Settings"
        )
        settings_item.triggered.connect(self.settings)
        self.settings_window = SettingsWindow(self)

        self.context_menu.addSeparator()

        self.help_menu = self.context_menu.addMenu(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/help.png")), "Help"
        )
        help_latest = self.help_menu.addAction("Latest Release")
        help_current = self.help_menu.addAction("This Release")
        help_latest.triggered.connect(self.open_link(f"{GITHUB_LINK}blob/main/README.md"))
        help_current.triggered.connect(
            self.open_link(f"{GITHUB_LINK}releases/tag/{self.VERSION}")
        )
        help_original = self.help_menu.addAction("Original AlbumPaper (jac0b-w)")
        help_original.triggered.connect(self.open_link("https://github.com/jac0b-w/AlbumPaper/"))

        bug_report_item = self.context_menu.addAction(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/bug_report.png")), "Bug Report"
        )
        bug_report_item.triggered.connect(self.open_link(f"{GITHUB_LINK}issues"))

        release_item = self.context_menu.addAction(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/update.png")), f"{self.VERSION}"
        )
        release_item.triggered.connect(self.open_link(f"{GITHUB_LINK}releases"))

        self.context_menu.addSeparator()

        self.pause_item = self.context_menu.addAction(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/pause.png")), "Pause"
        )
        self.pause_item.triggered.connect(self.toggle_pause)

        restart_item = self.context_menu.addAction(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/restart.png")), "Restart"
        )
        restart_item.triggered.connect(self.exit(1))

        exit_item = self.context_menu.addAction(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/close.png")), "Quit"
        )
        exit_item.triggered.connect(self.exit(0))

        self.setContextMenu(self.context_menu)
        self.activated.connect(self.clicked)

        self.messageClicked.connect(self.open_link(f"{GITHUB_LINK}releases"))

    def clicked(self, reason):
        # self.Trigger is left click
        if reason == self.DoubleClick:
            self.toggle_pause()

    def settings(self):
        self.settings_window.show()
        self.settings_window.activateWindow()

    def toggle_pause(self):
        self.pause_state_manager.toggle_pause()

    @QtCore.Slot(str)
    def pause_state(self, state: str):
        options = {
            "disabled": {"text": "Continue", "icon": "play", "enabled": True},
            "enabled": {"text": "Pause", "icon": "pause", "enabled": True},
            "battery_saver": {
                "text": "Battery Saving",
                "icon": "battery_saver",
                "enabled": False,
            },
        }[state]

        self.pause_item.setText(options["text"])
        self.pause_item.setIcon(
            QtGui.QIcon(asset_path(f"assets/icons/{self.icon_color}/{options['icon']}.png"))
        )
        self.pause_item.setEnabled(options["enabled"])

        self.setIcon(QtGui.QIcon(asset_path(f"assets/icons/{state}.png")))

    def set_default_wallpaper(self):
        Wallpaper.set_default()
        self.showMessage("Saved", "Wallpaper saved as default")

    def open_link(self, link):
        return lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(link))

    def exit(self, exit_code):
        def exit_function():
            Wallpaper.set(is_default=True)
            QtWidgets.QApplication.exit(exit_code)

        return exit_function


class SettingsWindow(QtWidgets.QDialog):
    def __init__(self, tray_icon):
        super().__init__()
        self.tray_icon = tray_icon
        self.setWindowTitle("Settings")
        settings_icon_path = asset_path("assets/icons/black/settings.png")
        if os.path.exists(settings_icon_path):
            self.setWindowIcon(QtGui.QIcon(settings_icon_path))

        # Groups stack vertically; the window sizes itself to the content
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        self.main_layout.addWidget(self.build_service_group())
        self.main_layout.addWidget(self.build_theme_group())
        self.main_layout.addWidget(self.build_wallpaper_group())
        self.main_layout.addWidget(self.build_general_group())
        if sys.platform != "win32":
            self.main_layout.addWidget(self.build_system_theme_group())
        self.main_layout.addWidget(self.build_buttons())

        try:
            self.setStyleSheet(ConfigManager.theme()["settings_window"])
        except KeyError:
            pass

    @staticmethod
    def group(title, layout_rows=None):
        box = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QFormLayout(box)
        layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        for label, widget in layout_rows or []:
            layout.addRow(label, widget)
        return box

    def build_buttons(self):
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.Save).setDefault(True)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        return buttons

    def build_service_group(self):
        self.service_combo = QtWidgets.QComboBox()
        self.service_combo.addItems(["Spotify (recommended)", "Last.fm"])

        # spotify page
        self.spotify_client_id = QtWidgets.QLineEdit()
        self.spotify_client_secret = QtWidgets.QLineEdit()
        self.spotify_client_id.setPlaceholderText("Client ID")
        self.spotify_client_secret.setPlaceholderText("Client Secret")
        self.spotify_client_id.setMaxLength(32)
        self.spotify_client_secret.setMaxLength(32)
        self.spotify_client_id.setText(ConfigManager.services["spotify"]["client_id"])
        self.spotify_client_secret.setText(ConfigManager.services["spotify"]["client_secret"])

        # last.fm page
        self.lastfm_username = QtWidgets.QLineEdit()
        self.lastfm_api_key = QtWidgets.QLineEdit()
        self.lastfm_username.setPlaceholderText("Username")
        self.lastfm_api_key.setPlaceholderText("API Key")
        self.lastfm_api_key.setMaxLength(32)
        self.lastfm_username.setText(ConfigManager.services["last.fm"]["username"])
        self.lastfm_api_key.setText(ConfigManager.services["last.fm"]["api_key"])

        self.api_keys_stacked = QtWidgets.QStackedWidget()
        self.api_keys_stacked.addWidget(
            self.page([("Client ID", self.spotify_client_id),
                       ("Client Secret", self.spotify_client_secret)])
        )
        self.api_keys_stacked.addWidget(
            self.page([("Username", self.lastfm_username),
                       ("API Key", self.lastfm_api_key)])
        )
        self.service_combo.currentIndexChanged.connect(self.api_keys_stacked.setCurrentIndex)
        index = {"spotify": 0, "last.fm": 1}[ConfigManager.settings["service"]["name"]]
        self.service_combo.setCurrentIndex(index)
        self.api_keys_stacked.setCurrentIndex(index)

        help_link = QtWidgets.QLabel(
            '<a href="https://github.com/jac0b-w/AlbumPaper/wiki/Getting-API-Keys">'
            "Where do I find API keys?</a>"
        )
        help_link.linkActivated.connect(
            lambda link: QtGui.QDesktopServices.openUrl(QtCore.QUrl(link))
        )

        box = self.group("Music Service", [("Service", self.service_combo)])
        box.layout().addRow(self.api_keys_stacked)
        box.layout().addRow(help_link)
        return box

    @staticmethod
    def page(rows):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        for label, field in rows:
            layout.addRow(label, field)
        return widget

    def build_theme_group(self):
        self.theme_selector = QtWidgets.QComboBox()
        self.theme_selector.addItems(list_themes())
        self.theme_selector.setCurrentIndex(
            self.theme_selector.findText(
                ConfigManager.settings["theme"]["name"], QtCore.Qt.MatchFixedString
            )
        )
        self.edit_theme_button = QtWidgets.QPushButton("Edit Themes")
        self.edit_theme_button.clicked.connect(self.edit_themes)
        return self.group(
            "Appearance",
            [("Theme", self.theme_selector), ("", self.edit_theme_button)],
        )

    def build_wallpaper_group(self):
        self.foreground_checkbox = QtWidgets.QCheckBox()
        self.foreground_checkbox.setChecked(ConfigManager.settings["foreground"]["enabled"])

        self.foreground_size = QtWidgets.QSpinBox()
        self.foreground_size.setRange(1, 10_000)
        self.foreground_size.setValue(ConfigManager.settings["foreground"]["size"])
        self.foreground_size.setEnabled(self.foreground_checkbox.isChecked())
        self.foreground_checkbox.toggled.connect(self.foreground_size.setEnabled)

        self.background_combo = QtWidgets.QComboBox()
        self.background_combo.addItems(BACKGROUND_TYPES)
        self.background_combo.setCurrentText(ConfigManager.settings["background"]["type"])
        self.background_combo.currentIndexChanged.connect(self.refresh_blur_controls)

        self.blur_checkbox = QtWidgets.QCheckBox()
        self.blur_checkbox.setChecked(ConfigManager.settings["background"]["blur_enabled"])
        self.blur_checkbox.toggled.connect(self.refresh_blur_controls)

        self.blur_strength = QtWidgets.QDoubleSpinBox()
        self.blur_strength.setRange(0.5, 100.0)
        self.blur_strength.setSingleStep(0.5)
        self.blur_strength.setValue(ConfigManager.settings["background"]["blur_strength"])

        self.refresh_blur_controls()
        return self.group(
            "Wallpaper",
            [
                ("Foreground Art", self.foreground_checkbox),
                ("Art Size", self.foreground_size),
                ("Background", self.background_combo),
                ("Background Blur", self.blur_checkbox),
                ("Blur Strength", self.blur_strength),
            ],
        )

    def build_general_group(self):
        self.check_updates_checkbox = QtWidgets.QCheckBox()
        self.check_updates_checkbox.setChecked(
            ConfigManager.settings["updates"]["check_for_updates"]
        )

        self.battery_saver_checkbox = QtWidgets.QCheckBox()
        self.battery_saver_checkbox.setChecked(
            ConfigManager.settings["power"]["disable_on_battery_saver"]
        )
        return self.group(
            "General",
            [
                ("Check for updates", self.check_updates_checkbox),
                ("Pause on Battery Saver", self.battery_saver_checkbox),
            ],
        )

    def build_system_theme_group(self):
        self.system_theme_checkbox = QtWidgets.QCheckBox()
        self.system_theme_checkbox.setChecked(
            ConfigManager.settings["system_theme"]["sync_enabled"]
        )

        self.lockscreen_checkbox = QtWidgets.QCheckBox()
        self.lockscreen_checkbox.setChecked(
            ConfigManager.settings["system_theme"]["update_lockscreen"]
        )
        return self.group(
            "System Theme",
            [
                ("Sync system light/dark + accent color", self.system_theme_checkbox),
                ("Also update lock screen", self.lockscreen_checkbox),
            ],
        )

    def save(self):
        service = ["spotify", "last.fm"][self.service_combo.currentIndex()]
        ConfigManager.settings["service"]["name"] = service

        ConfigManager.services["spotify"]["client_id"] = self.spotify_client_id.text()
        ConfigManager.services["spotify"]["client_secret"] = self.spotify_client_secret.text()

        ConfigManager.services["last.fm"]["api_key"] = self.lastfm_api_key.text()
        ConfigManager.services["last.fm"]["username"] = self.lastfm_username.text()

        # layer settings
        ConfigManager.settings["foreground"]["enabled"] = self.foreground_checkbox.isChecked()
        ConfigManager.settings["foreground"]["size"] = self.foreground_size.value()
        ConfigManager.settings["background"]["type"] = self.background_combo.currentText()
        ConfigManager.settings["background"]["blur_enabled"] = self.blur_checkbox.isChecked()
        ConfigManager.settings["background"]["blur_strength"] = self.blur_strength.value()

        ConfigManager.settings["theme"]["name"] = self.theme_selector.currentText()

        ConfigManager.settings["updates"]["check_for_updates"] = (
            self.check_updates_checkbox.isChecked()
        )
        ConfigManager.settings["power"]["disable_on_battery_saver"] = (
            self.battery_saver_checkbox.isChecked()
        )

        if sys.platform != "win32":
            ConfigManager.settings["system_theme"]["sync_enabled"] = (
                self.system_theme_checkbox.isChecked()
            )
            ConfigManager.settings["system_theme"]["update_lockscreen"] = (
                self.lockscreen_checkbox.isChecked()
            )

        try:
            ConfigManager.save()  # save settings.ini and services.ini
        except ConfigValidationError as e:
            self.tray_icon.showMessage(e.message, "")
        else:
            self.accept()
            QtWidgets.QApplication.exit(1)  # send restart exit code

    def edit_themes(self):
        folder = themes_dir()
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def refresh_blur_controls(self, *_):
        """Blur only applies to album-art based backgrounds"""
        blur_applies = self.background_combo.currentText() in BLUR_BACKGROUNDS
        self.blur_checkbox.setEnabled(blur_applies)
        self.blur_strength.setEnabled(blur_applies and self.blur_checkbox.isChecked())
