"""
Classes in this file:
  GenerateWallpaper
   - For generating the wallpaper based on the users settings
  Wallpaper
   - For setting a new wallpaper and saving the current wallpaper
    as the default wallpaper
"""


import os, sys, glob, shutil, collections, numpy, scipy.cluster, sklearn.cluster, random, functools
from typing import Optional
from PIL import Image
from config import ConfigManager, get_app_dir
from misc import timer, HashableImage
import structs
import logging

log = logging.getLogger("app")

if sys.platform == "win32":
    import ctypes
else:
    import linux_desktop

# rust functions
import albumpaper_rs

# Use app directory for writable files
_app_dir = get_app_dir()
DEFAULT_WALLPAPER_PATH = os.path.join(_app_dir, "images/default_wallpaper.jpg")
GENERATED_WALLPAPER_PATH = os.path.join(_app_dir, "images/generated_wallpaper.png")


def rust_image(method):
    @functools.wraps(method)  # keeps method name, docstring etc
    def _wrapper(
        self,
        artwork: Optional[Image.Image],
        *args,
        **kwargs,
    ):
        if artwork is not None:
            artwork_buf = artwork.tobytes("raw")
            buf_size: tuple = artwork.size
        else:
            artwork_buf = None
            buf_size = None

        method(
            artwork_buf,
            buf_size,
            self.foreground_size if self.foreground_enabled else None,
            self.display_geometry[:2],
            self.available_geometry,
            *args,
            **kwargs,
        )

    return _wrapper


class GenerateWallpaper:
    def __init__(self, app):
        self.foreground_size = ConfigManager.settings["foreground"]["size"]
        background_type = ConfigManager.settings["background"]["type"]

        self.gen_background = {
            "Solid": self.color_background,
            "Linear Gradient": self.linear_gradient_background,
            "Radial Gradient": self.radial_gradient_background,
            "Colored Noise": self.colored_noise_background,
            "Art": self.art_background,
            "Wallpaper": self.wallpaper_background,
            "Random": self.random_background,
        }[background_type]

        self.blur_enabled = ConfigManager.settings["background"]["blur_enabled"]
        self.blur_strength = ConfigManager.settings["background"]["blur_strength"]

        self.foreground_enabled = ConfigManager.settings["foreground"]["enabled"]

        Geometry = collections.namedtuple("Geometry", ["w", "h", "left", "top"])
        dw = app.primaryScreen()
        self.display_geometry = Geometry(dw.size().width(), dw.size().height(), 0, 0)
        self.available_geometry = Geometry(
            dw.availableGeometry().width(),
            dw.availableGeometry().height(),
            dw.availableGeometry().left(),
            dw.availableGeometry().top(),
        )

        self.dominant_colors = functools.lru_cache(10)(self.dominant_colors)

    @timer
    def dominant_colors(self, hashable_image: HashableImage):
        """
        Input: PIL image
        Output: A list of 10 colors in the image from most dominant to least dominant
        Adaptation of https://stackoverflow.com/a/3244061/7274182
        """
        ar = numpy.asarray(hashable_image.image.resize((150, 150), 0))
        shape = ar.shape
        ar = ar.reshape(numpy.prod(shape[:2]), shape[2]).astype(
            float
        )  # flatten to shape (width*height, 3)

        kmeans = sklearn.cluster.MiniBatchKMeans(
            n_clusters=10, init="k-means++", max_iter=20, random_state=1000
        ).fit(ar)
        codes = kmeans.cluster_centers_

        vecs, _dist = scipy.cluster.vq.vq(ar, codes)  # assign codes
        counts, _bins = numpy.histogram(vecs, len(codes))  # count occurrences

        Color = collections.namedtuple("Color", ["r", "g", "b"])
        colors = []
        for index in numpy.argsort(counts)[::-1]:
            color_tuple = tuple([int(code) for code in codes[index]])
            colors.append(Color(*color_tuple))
        return colors  # returns colors in order of dominance

    @staticmethod
    def color_difference(c1, c2):
        """
        Input: RGB named tuples
        Output: An aproximation of perceived color difference of two colors
        https://www.compuphase.com/cmetric.htm
        """
        r = (c1.r + c2.r) / 2
        delta_r = c1.r - c2.r
        delta_g = c1.g - c2.g
        delta_b = c1.b - c2.b
        return (
            (2 + r / 256) * delta_r**2
            + 4 * delta_g**2
            + (2 + (255 - r) / 256) * delta_b**2
        ) ** 0.5

    @staticmethod
    def color_luminosity(color):
        min_rgb = min(color) / 255
        max_rgb = max(color) / 255
        return (max_rgb + min_rgb) / 2

    def color_saturation(self, color):
        """
        Input: RGB named tuple
        Output: Perceived vibrancy of the color, 0-1 (HSV saturation * value)

        Raw HSV/HSL saturation is scale-invariant with brightness, so a
        near-black pixel like (9, 0, 2) - e.g. JPEG shadow noise - scores
        saturation 1.0 (min channel is 0) even though it reads as black,
        not vivid. That previously let near-black pixels outscore genuinely
        vivid colors and get picked as the "most saturated" gradient
        endpoint. Weighting saturation by value (brightness) suppresses
        near-black/near-white pixels while still ranking true vivid colors
        highest, matching how palette-extraction tools (e.g. Android's
        Palette API "vibrant" swatch) score vibrancy.
        """
        max_rgb = max(color) / 255
        min_rgb = min(color) / 255
        if max_rgb == 0:
            return 0
        saturation = (max_rgb - min_rgb) / max_rgb
        value = max_rgb
        return saturation * value

    def gradient_colors(
        self, image: Image.Image
    ):  # https://stackoverflow.com/questions/30608035/plot-circular-gradients-using-pil-in-python
        """
        Determine best colours for the gradient
        Firstly get the 7 most dominant colours and pick the most saturated
        Pair the most saturated colour with the colour that has the largest perceived difference
        """
        dominant_colors = self.dominant_colors(HashableImage(image))

        saturations = [
            {"color": color, "saturation": self.color_saturation(color)}
            for color in dominant_colors[:7]
        ]
        sorted_saturations = sorted(
            saturations, key=lambda x: x["saturation"], reverse=True
        )
        # e.g. [{"color":(255,0,0),"saturation":0.75},{"color":(255,255,255),"saturation":0} ...]
        most_saturated = sorted_saturations[0]["color"]

        color_differences = [
            {
                "color pair": (most_saturated, saturation_dict["color"]),
                "score": self.color_difference(
                    most_saturated, saturation_dict["color"]
                ) * (0.5 + saturation_dict["saturation"]),
            }
            for saturation_dict in sorted_saturations[1:]
        ]
        sorted_color_differences = sorted(
            color_differences, key=lambda x: x["score"], reverse=True
        )

        return sorted_color_differences[0]["color pair"]

        # example return data:
        # (Color(r=120, g=50, b=12), Color(r=190, g=200, b=203))

    @timer
    def linear_gradient_background(self, image: Image.Image):
        from_color, to_color = self.gradient_colors(image)
        albumpaper_rs.generate_save_wallpaper(
            structs.RequiredArguments(
                "LinearGradient",
                structs.Foreground(image, self.foreground_size, self.foreground_enabled),
                self.display_geometry[:2],
                self.available_geometry,
            ),
            structs.OptionalArguments(None, from_color, to_color),
        )

    @timer
    def radial_gradient_background(self, image: Image.Image):
        from_color, to_color = self.gradient_colors(image)
        albumpaper_rs.generate_save_wallpaper(
            structs.RequiredArguments(
                "RadialGradient",
                structs.Foreground(image, self.foreground_size, self.foreground_enabled),
                self.display_geometry[:2],
                self.available_geometry,
            ),
            structs.OptionalArguments(None, from_color, to_color),
        )

    @timer
    def color_background(self, image: Image.Image):
        color = self.dominant_colors(HashableImage(image))[0]
        albumpaper_rs.generate_save_wallpaper(
            structs.RequiredArguments(
                "SolidColor",
                structs.Foreground(image, self.foreground_size, self.foreground_enabled),
                self.display_geometry[:2],
                self.available_geometry,
            ),
            structs.OptionalArguments(None, color, None),
        )

    @timer
    def colored_noise_background(self, image: Image.Image):
        blur: Optional[int] = int(self.blur_strength) if self.blur_enabled else None
        color1, color2 = self.gradient_colors(image)
        albumpaper_rs.generate_save_wallpaper(
            structs.RequiredArguments(
                "ColoredNoise",
                structs.Foreground(image, self.foreground_size, self.foreground_enabled),
                self.display_geometry[:2],
                self.available_geometry,
            ),
            structs.OptionalArguments(blur, color1, color2),
        )

    @timer
    def art_background(self, image: Image.Image):
        blur: Optional[int] = int(self.blur_strength) if self.blur_enabled else None
        albumpaper_rs.generate_save_wallpaper(
            structs.RequiredArguments(
                "Artwork",
                structs.Foreground(image, self.foreground_size, self.foreground_enabled),
                self.display_geometry[:2],
                self.available_geometry,
            ),
            structs.OptionalArguments(blur, None, None),
        )

    @timer
    def wallpaper_background(self, image: Image.Image):
        blur: Optional[int] = int(self.blur_strength) if self.blur_enabled else None
        albumpaper_rs.generate_save_wallpaper(
            structs.RequiredArguments(
                "DefaultWallpaper",
                structs.Foreground(image, self.foreground_size, self.foreground_enabled),
                self.display_geometry[:2],
                self.available_geometry,
            ),
            structs.OptionalArguments(blur, None, None),
        )

    def random_background(self, album_art: Image) -> Image.Image:
        backgound = random.choice(
            [
                self.color_background,
                self.linear_gradient_background,
                self.radial_gradient_background,
                self.colored_noise_background,
                self.art_background,
            ]
        )
        backgound(album_art)

    def generate(self, image: Image.Image):
        if isinstance(image, Image.Image):
            print("========== Generating new image ==========")
            self.gen_background(image)

            if sys.platform != "win32" and ConfigManager.settings["system_theme"]["sync_enabled"]:
                try:
                    # most saturated dominant color - the same color picked as the
                    # primary hue for the gradient/colored-noise backgrounds
                    color, _ = self.gradient_colors(image)
                    linux_desktop.sync_system_theme((color.r, color.g, color.b))
                except Exception as e:
                    log.error(f"System theme sync failed: {e}")

            Wallpaper.set(is_default=False)
        elif image == "default":
            Wallpaper.set(is_default=True)
        elif image == "generated":
            Wallpaper.set(is_default=False)


class Wallpaper:
    # GNOME only repaints the desktop when org.gnome.desktop.background's
    # picture-uri value actually *changes*. Since the wallpaper generator
    # always overwrites the same GENERATED_WALLPAPER_PATH file, re-pointing
    # GNOME at that identical path/URI on every track change emits no
    # change signal and the old image stays on screen. Fix: copy each
    # generated wallpaper to a freshly-named file and point GNOME there.
    _GENERATED_VARIANTS_KEPT = 3
    _generated_variant_counter = 0

    @staticmethod
    def _next_generated_variant_path() -> str:
        Wallpaper._generated_variant_counter += 1
        n = Wallpaper._generated_variant_counter % Wallpaper._GENERATED_VARIANTS_KEPT
        base, ext = os.path.splitext(GENERATED_WALLPAPER_PATH)
        return f"{base}_{n}{ext}"

    @staticmethod
    def set(is_default: bool):
        if is_default:
            file_name = DEFAULT_WALLPAPER_PATH
        elif sys.platform != "win32":
            # Use a rotating unique filename so GNOME's picture-uri actually changes.
            file_name = Wallpaper._next_generated_variant_path()
            shutil.copyfile(GENERATED_WALLPAPER_PATH, file_name)
        else:
            file_name = GENERATED_WALLPAPER_PATH

        abs_path = os.path.abspath(file_name)

        log.debug(f"Attempting to set wallpaper. Default={is_default}")
        log.debug(f"Target file: {file_name}")
        log.debug(f"Absolute path: {abs_path}")

        if not os.path.exists(abs_path):
            log.error(f"WALLPAPER FILE MISSING at {abs_path}")
            return

        if sys.platform == "win32":
            # https://stackoverflow.com/a/56976219
            result = ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)

            if result:
                log.info(f"SystemParametersInfoW success for {abs_path}")
            else:
                err = ctypes.GetLastError()
                log.error(f"SystemParametersInfoW failed. Error code: {err}")
        else:
            update_lockscreen = ConfigManager.settings["system_theme"]["update_lockscreen"]
            linux_desktop.set_wallpaper(abs_path, update_lockscreen=update_lockscreen)
            log.info(f"Set GNOME wallpaper (lockscreen={update_lockscreen}) for {abs_path}")

        print("WALLPAPER SET: " + ("Default" if is_default else "Generated"))

    @staticmethod
    def set_default():
        """
        1. First look in %APPDATA%\Microsoft\Windows\Themes\CachedFiles
        and use most recent image (this will have the resolution of the desktop)
        2. If that fails look for %APPDATA%\Microsoft\Windows\Themes\TranscodedWallpaper
        (this will have the resolution of the original image)
        3. If that fails find the original path of the wallpaper and save that image instead
        # https://stackoverflow.com/questions/44867820/
        4. Finally if all fail just save use a blank image as the dafault wallpaper
        """
        if sys.platform == "win32":
            cached_folder = os.path.expandvars(
                r"%APPDATA%\Microsoft\Windows\Themes\CachedFiles\*"
            )
            list_of_files = glob.glob(cached_folder)
            if list_of_files:
                current_wallpaper = max(list_of_files, key=os.path.getctime)
            else:
                current_wallpaper = os.path.expandvars(
                    r"%APPDATA%\Microsoft\Windows\Themes\TranscodedWallpaper"
                )
            try:
                shutil.copy(current_wallpaper, DEFAULT_WALLPAPER_PATH)
            except FileNotFoundError:
                ubuf = ctypes.create_unicode_buffer(200)
                ctypes.windll.user32.SystemParametersInfoW(0x0073, 200, ubuf, 0)
                try:
                    shutil.copy(ubuf.value, DEFAULT_WALLPAPER_PATH)
                except FileNotFoundError:
                    image = Image.new("RGB", (1, 1))
                    image.save(DEFAULT_WALLPAPER_PATH, "JPEG", quality=100)
        else:
            current_wallpaper = linux_desktop.get_current_wallpaper()
            try:
                shutil.copy(current_wallpaper, DEFAULT_WALLPAPER_PATH)
            except (FileNotFoundError, TypeError):
                image = Image.new("RGB", (1, 1))
                image.save(DEFAULT_WALLPAPER_PATH, "JPEG", quality=100)
