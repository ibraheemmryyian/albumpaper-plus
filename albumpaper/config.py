import ast, configobj, sys, os
from configobj import validate
from pathlib import Path

# Handle PyInstaller bundled paths
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = sys._MEIPASS
    else:
        # Running in normal Python environment
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# Get the directory where the EXE is located (for writable configs)
def get_app_dir():
    """Get the directory where writable configs should be stored"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

class ConfigValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


class ConfigManager:
    _app_dir = get_app_dir()
    _settings_path = os.path.join(_app_dir, "settings.ini")
    
    # use developer API keys if the file exists
    _dev_services_path = os.path.join(_app_dir, "services-dev.ini")
    _services_path = os.path.join(_app_dir, "services.ini")
    _configspec_path = get_resource_path("configspec.ini")

    _validator = validate.Validator()
    
    dev_services_file = Path(_dev_services_path)
    if dev_services_file.is_file():
        print("Using developer API keys")
        services = configobj.ConfigObj(_dev_services_path)
    else:
        services = configobj.ConfigObj(_services_path)

    settings = configobj.ConfigObj(_settings_path, configspec=_configspec_path)
    settings.validate(_validator)
    
    @classmethod
    def validate_service(cls):
        if cls.settings["service"]["name"] == "spotify":
            for key in ["client_id", "client_secret"]:
                try:
                    cls._validator.check(
                        "string(min=32, max=32)",
                        cls.services["spotify"][key],
                    )
                except validate.ValidateError:
                    raise ConfigValidationError("Set valid Spotify API keys")

        elif cls.settings["service"]["name"] == "last.fm":
            try:
                cls._validator.check(
                    "string(min=32, max=32)",
                    cls.services["last.fm"]["api_key"],
                )
                cls._validator.check(
                    "string(min=2, max=15)",
                    cls.services["last.fm"]["username"],
                )
            except validate.ValidateError:
                raise ConfigValidationError("Set valid Last.fm API key and username")

        else:
            raise ConfigValidationError("Set a valid service")

    @classmethod
    def save(cls) -> None:
        cls.validate_service()
        
        cls.settings.write()
        cls.services.write()

    @classmethod
    def theme(cls) -> dict:
        # Default theme values to prevent KeyError crashes
        default_theme = {
            "icon_color": "white",
            "background_color": "#2b2b2b",
            "text_color": "#ffffff"
        }
        theme_name = cls.settings["theme"]["name"]
        try:
            theme_path = get_resource_path(f"themes/{theme_name}.py")
            with open(theme_path) as f:
                loaded_theme = ast.literal_eval(f.read())
                # Merge with defaults to ensure all keys exist
                return {**default_theme, **loaded_theme}
        except (FileNotFoundError, SyntaxError, ValueError) as e:
            print(f"Warning: Could not load theme '{theme_name}': {e}")
            return default_theme
