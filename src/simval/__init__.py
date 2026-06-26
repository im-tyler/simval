from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("simval")
except PackageNotFoundError:  # not installed (e.g. running from source without -e)
    __version__ = "0.0.0"
