"""settings.py - persistent viewer settings (IP, palette, upscale).

Storage: JSON at
  Windows: %APPDATA%/SuperCamViewer/settings.json
  macOS  : ~/Library/Application Support/SuperCamViewer/settings.json
"""
import json
import os
import sys
import configparser

DEFAULTS = dict(ip='192.168.2.32', port=3000, window_geometry='1064x855',
                palette='inferno', smooth=True,
                width=0, height=0, last_session='',
                lo_deg=25.834951456310677, hi_deg=40.78817733990148,
                auto_deg=False,
                t_gain=0.01, t_offset=0.0,
                main_light='ir', edge_strength=53.0,
                align_x=21.0, align_y=5.0, align_z=1.0, align_r=0.0)


def _dir():
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        return os.path.join(base, 'SuperCamViewer')
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library',
                            'Application Support', 'SuperCamViewer')
    return os.path.join(os.path.expanduser('~'), '.config', 'SuperCamViewer')


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(_dir(), 'settings.json')
        self.ini_path = os.path.splitext(self.path)[0] + '.ini'
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            parser = configparser.ConfigParser()
            if parser.read(self.ini_path, encoding='utf-8') and parser.has_section('SuperCam'):
                section = parser['SuperCam']
                for key, default in DEFAULTS.items():
                    if key not in section:
                        continue
                    raw = section[key]
                    try:
                        if isinstance(default, bool):
                            self.data[key] = raw.lower() in ('1', 'true', 'yes', 'on')
                        elif isinstance(default, int) and not isinstance(default, bool):
                            self.data[key] = int(raw)
                        elif isinstance(default, float):
                            self.data[key] = float(raw)
                        else:
                            self.data[key] = raw
                    except ValueError:
                        pass
                return self
        except (OSError, configparser.Error):
            pass
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update({k: stored[k] for k in DEFAULTS if k in stored})
        except (OSError, ValueError):
            pass
        return self

    def save(self, **kw):
        self.data.update(kw or {})
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            parser = configparser.ConfigParser()
            parser['SuperCam'] = {k: str(self.data.get(k, v))
                                  for k, v in DEFAULTS.items()}
            with open(self.ini_path, 'w', encoding='utf-8') as f:
                parser.write(f)
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)
        except OSError as e:
            print('[settings] save failed: %s' % e)

    def get(self, key, default=None):
        return self.data.get(key, default if default is not None else DEFAULTS.get(key))
