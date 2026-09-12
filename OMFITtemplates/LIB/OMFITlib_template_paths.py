"""Linux user paths (XDG), shared by the GUI, CLI and desktop installer."""
from pathlib import Path
import os

APP_ID = 'org.omfit.TemplateManager'


def xdg_path(variable, fallback):
    value = os.environ.get(variable, '')
    candidate = Path(value) if value else None
    # The XDG specification requires relative overrides to be ignored.
    return candidate if candidate is not None and candidate.is_absolute() else Path.home() / fallback


def preferences_path():
    return xdg_path('XDG_CONFIG_HOME', '.config') / 'omfit-template-manager' / 'settings.json'


def legacy_preferences_path():
    return Path.home() / '.omfit-template-manager.json'


def default_library():
    legacy = Path.home() / '.omfit-template-library'
    if legacy.is_dir():
        return legacy
    return xdg_path('XDG_DATA_HOME', '.local/share') / 'omfit-template-manager' / 'templates'


def applications_directory():
    return xdg_path('XDG_DATA_HOME', '.local/share') / 'applications'
