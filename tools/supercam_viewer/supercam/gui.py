"""gui.py - tkinter dual-stream viewer with PCBtool-style thermal controls.

Top: camera IP / palette / auto-scale. Middle canvas: CAMERA | IR panels
(crosshair jumps between hot spots within 5C). Bottom: adaptive X set-point
scale (Lo/Hi cutoffs, min 20-70C; in auto it follows the autoscale).
Hotspot needle + readout.
"""
import base64
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox

import numpy as np
from PIL import Image, ImageTk

try:
    import cv2
except ImportError:
    cv2 = None

from . import render as R
from .camera import CameraClient
from .settings import Settings
from .version import BUILD_DATE, VERSION


def _asset_path(name):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return root / 'assets' / name


class TempSetpoints(tk.Frame):
    """Bottom X temperature scale. The axis DOMAIN adapts (shrink/expand) to
    the live temperature / cutoff range, always covering at least the 20..70C
    base band -- never a fixed 0..200. Lo/Hi handles are set points in MANUAL
    mode (draggable); in AUTO they follow the autoscale and are display-only.
    White needle = live max hotspot. Regions outside [Lo,Hi] dimmed = cutoff."""

    def __init__(self, master, lo=20.0, hi=70.0, on_change=None,
                 on_manual=None, auto_var=None, on_auto=None,
                 palette='inferno', d0=15.0, d1=75.0):
        super().__init__(master, bg='#0b0e12',
                         highlightthickness=1, highlightbackground='#273442')
        self._auto_check = tk.Checkbutton(
            self, text='AUTO RANGE', variable=auto_var, command=on_auto,
            bg='#0b0e12', fg='#d7e0ea', activebackground='#0b0e12',
            activeforeground='#19c7f3', selectcolor='#273442',
            relief=tk.FLAT, font=('Segoe UI', 8, 'bold')) if auto_var else None
        if self._auto_check is not None:
            self._auto_check.pack(side=tk.LEFT, anchor=tk.N, padx=(8, 4), pady=8)
        self.canvas = tk.Canvas(self, height=108, bg='#0b0e12',
                                highlightthickness=0)
        self.canvas.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.lo = float(lo)
        self.hi = float(hi)
        self.disp_lo = float(lo)
        self.disp_hi = float(hi)
        self.d0_ = float(d0)
        self.d1_ = float(d1)
        self.on_change = on_change
        self.on_manual = on_manual
        self.auto_var = auto_var
        self.on_auto = on_auto
        self.palette = palette
        self.bar_lo = float(d0)
        self.bar_hi = float(d1)
        self.max_deg = 0.0
        self.auto = False
        self.shortcut_hint = 'drag Lo/Hi = cutoffs (below blacked / above whited)'
        self._drag = None
        self._grad_key = None
        self._grad_img = None
        self.x0 = 12
        self.x1 = 90
        self.bar_y = 18
        self.bar_h = 22
        self.canvas.bind('<Configure>', lambda e: self._dirty_grad())
        self.canvas.bind('<Button-1>', self._press)
        self.canvas.bind('<B1-Motion>', self._motion)
        self.canvas.bind('<ButtonRelease-1>', self._release)
        self.redraw()

    # ---- geometry -------------------------------------------------------
    def _layout(self):
        w = self.canvas.winfo_width()
        self.x1 = max(self.x0 + 120, w - 60)

    def _dirty_grad(self):
        self._grad_key = None

    # ---- adaptive domain ------------------------------------------------
    def set_domain(self, d0, d1):
        d0, d1 = float(d0), float(d1)
        if d0 != self.d0_ or d1 != self.d1_:
            self.d0_, self.d1_ = d0, d1
            self._dirty_grad()

    def _frac(self, deg):
        span = self.d1_ - self.d0_
        return np.clip((deg - self.d0_) / span, 0.0, 1.0) if span > 0 else 0.0

    # ---- drawing --------------------------------------------------------
    def _gradient_photo(self):
        self._layout()
        w = max(16, self.x1 - self.x0)
        key = (w, self.palette, self.d0_, self.d1_)
        if key == self._grad_key and self._grad_img is not None:
            return self._grad_img
        import cv2 as cv
        lut = np.zeros((self.bar_h, w, 3), np.uint8)
        interp = np.rint(np.linspace(0, 255, w)).astype(np.uint8)
        lut[:, :] = cv.applyColorMap(interp, R._lut(self.palette))[0]
        ok, png = cv.imencode('.png', lut)
        photo = tk.PhotoImage(data=base64.b64encode(png.tobytes()).decode('ascii'))
        self._grad_img = photo
        self._grad_key = key
        return photo

    def redraw(self, bar_lo=None, bar_hi=None, lo=None, hi=None, max_deg=None,
               auto=None):
        if bar_lo is not None:
            self.bar_lo = bar_lo
        if bar_hi is not None:
            self.bar_hi = bar_hi
        if lo is not None:
            self.disp_lo = float(lo)
        if hi is not None:
            self.disp_hi = float(hi)
        if max_deg is not None:
            self.max_deg = max_deg
        if auto is not None:
            self.auto = auto
        c = self.canvas
        c.delete('all')
        self._layout()
        w = max(16, self.x1 - self.x0)
        grad = self._gradient_photo()
        c.create_image(self.x0, self.bar_y, image=grad, anchor=tk.NW)
        c.create_rectangle(self.x0 - 1, self.bar_y - 1,
                           self.x1 + 1, self.bar_y + self.bar_h + 1,
                           outline='#c8ccd4')
        # dim outside the Lo/Hi band
        lx = self.x0 + int(self._frac(self.disp_lo) * w)
        hx = self.x0 + int(self._frac(self.disp_hi) * w)
        if lx > self.x0:
            c.create_rectangle(self.x0, self.bar_y, lx,
                               self.bar_y + self.bar_h, fill='#10141a',
                               stipple='gray50')
        if hx < self.x1:
            c.create_rectangle(hx, self.bar_y, self.x1,
                               self.bar_y + self.bar_h, fill='#10141a',
                               stipple='gray50')
        c.create_line(lx, self.bar_y, lx, self.bar_y + self.bar_h,
                      fill='#4aa3ff', width=3)
        c.create_line(hx, self.bar_y, hx, self.bar_y + self.bar_h,
                      fill='#ff5a4a', width=3)
        # needle = current max hotspot
        fx = self.x0 + int(self._frac(self.max_deg) * w)
        c.create_line(fx, self.bar_y - 8, fx, self.bar_y + self.bar_h + 4,
                      fill='#ffffff', width=2)
        self._outlined_text(fx, self.bar_y + self.bar_h / 2,
                            '%.1fC' % self.max_deg, '#ffffff')
        # handles (Lo/Hi -> display positions; grabbable only in manual mode)
        self._handle(lx, self.bar_y + self.bar_h, '#4aa3ff', self.disp_lo, 'Lo')
        self._handle(hx, self.bar_y + self.bar_h, '#ff5a4a', self.disp_hi, 'Hi')
        # axis tick labels (domain bounds)
        c.create_text(self.x0, self.bar_y + self.bar_h + 43, anchor=tk.W,
                      text='X-axis %.0fC .. %.0fC (adapts; min 20-70)' % (self.d0_, self.d1_),
                      fill='#aab0ba', font=('Consolas', 9))
        c.create_text(self.x1, self.bar_y + self.bar_h + 43, anchor=tk.E,
                      text='MAX %.1fC  auto: %s' % (
                          self.max_deg, 'ON' if self.auto else 'OFF'),
                      fill='#aab0ba', font=('Consolas', 9, 'bold'))
        c.create_text(self.x0 + 285, self.bar_y + self.bar_h + 43,
                      anchor=tk.W, text='|  ' + self.shortcut_hint,
                      fill='#aab0ba', font=('Consolas', 9))
    def _handle(self, x, y, color, value, tag):
        c = self.canvas
        pts = [x, y + 2, x - 7, y + 16, x + 7, y + 16]
        c.create_polygon(pts, fill=color, outline=color)

    def _outlined_text(self, x, y, text, fill, anchor=tk.CENTER):
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self.canvas.create_text(x + dx, y + dy, text=text, anchor=anchor,
                                    fill='#000000', font=('Consolas', 9, 'bold'))
        self.canvas.create_text(x, y, text=text, anchor=anchor, fill=fill,
                                font=('Consolas', 9, 'bold'))

    # ---- interaction -----------------------------------------------------
    def _press(self, e):
        if self.auto:
            if self.on_manual:
                self.on_manual()
            self.auto = False
        self._layout()
        w = self.x1 - self.x0
        if w <= 0:
            return
        lx = self.x0 + int(self._frac(self.disp_lo) * w)
        hx = self.x0 + int(self._frac(self.disp_hi) * w)
        if abs(e.x - hx) <= 15:
            self._drag = 'hi'
        elif abs(e.x - lx) <= 15:
            self._drag = 'lo'
        else:
            self._drag = None

    def _motion(self, e):
        if not self._drag:
            return
        self._layout()
        w = self.x1 - self.x0
        if w <= 0:
            return
        frac = np.clip((e.x - self.x0) / w, 0.0, 1.0)
        deg = self.d0_ + frac * (self.d1_ - self.d0_)
        if self._drag == 'lo':
            self.lo = np.clip(min(deg, self.hi - 2.0), self.d0_, self.d1_)
        else:
            self.hi = np.clip(max(deg, self.lo + 2.0), self.d0_, self.d1_)
        self.disp_lo, self.disp_hi = self.lo, self.hi
        self.redraw()

    def _release(self, e):
        if self._drag:
            self._drag = None
            if self.on_change:
                self.on_change(self.lo, self.hi)


class ViewerApp:
    def __init__(self, root, host=None):
        self.root = root
        self.settings = Settings()
        self.bg = '#0a0e13'
        self.panel = '#121820'
        self.panel2 = '#171f29'
        self.text = '#d7e0ea'
        self.muted = '#7f8b98'
        self.cyan = '#19c7f3'
        self.red = '#ff4d66'
        if host:
            self.settings.data['ip'] = host
        self.settings.save()
        root.title('SUPERCAM | Thermal Diagnostics')
        root.geometry(self.settings.get('window_geometry', '1064x855'))
        root.minsize(900, 650)
        root.configure(bg=self.bg)
        self._window_icon = ImageTk.PhotoImage(
            Image.open(_asset_path('icon.png')).convert('RGBA').resize(
                (64, 64), Image.Resampling.LANCZOS))
        root.iconphoto(True, self._window_icon)
        self._geometry_job = None
        root.bind('<Configure>', self._geometry_changed)

        self.nav_width = 220
        control_area = tk.Frame(root, bg=self.panel)
        control_area.pack(side=tk.TOP, fill=tk.X)
        controls = tk.Frame(control_area, bg=self.panel)
        controls.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # The banner shares the two header rows and matches the IR ALIGN width.
        banner = tk.Frame(control_area, width=self.nav_width, height=104,
                          bg=self.panel, highlightthickness=1,
                          highlightbackground='#273442')
        banner.pack(side=tk.RIGHT, fill=tk.Y)
        banner.pack_propagate(False)
        self._banner_label = tk.Label(banner, bg=self.panel, bd=0)
        self._banner_label.pack(expand=True, padx=2, pady=2)
        banner.bind('<Configure>', self._resize_banner)

        top = tk.Frame(controls, padx=14, pady=9, bg=self.panel)
        top.pack(side=tk.TOP, fill=tk.X)
        tk.Label(top, text='SUPER', fg=self.text, bg=self.panel,
                 font=('Segoe UI', 12, 'bold')).pack(side=tk.LEFT)
        tk.Label(top, text='CAM', fg=self.cyan, bg=self.panel,
                 font=('Segoe UI', 12, 'bold')).pack(side=tk.LEFT, padx=(0, 18))
        tk.Label(top, text='DEVICE', fg=self.muted, bg=self.panel,
                 font=('Segoe UI', 8, 'bold')).pack(side=tk.LEFT)
        self.ipvar = tk.StringVar(value=self.settings.get('ip'))
        self.entry = tk.Entry(top, textvariable=self.ipvar, width=17,
                              bg='#0c1117', fg=self.text, insertbackground=self.cyan,
                              relief=tk.FLAT, highlightthickness=1,
                              highlightbackground='#2a3542',
                              highlightcolor=self.cyan)
        self.entry.pack(side=tk.LEFT, padx=(2, 8))
        self.btn = tk.Button(top, text='CONNECT', command=self.toggle,
                             bg=self.cyan, fg='#061017', activebackground='#72e2ff',
                             activeforeground='#061017', relief=tk.FLAT,
                             padx=10, font=('Segoe UI', 8, 'bold'))
        self.btn.pack(side=tk.LEFT)
        tk.Button(top, text='SAVE', command=self._save_settings,
                  bg='#2a3542', fg=self.text, activebackground='#3b4b5d',
                  relief=tk.FLAT, font=('Segoe UI', 8, 'bold'),
                  padx=8).pack(side=tk.LEFT, padx=(5, 0))

        tk.Label(top, text='IR PALETTE', fg=self.muted, bg=self.panel,
                 font=('Segoe UI', 8, 'bold')).pack(side=tk.LEFT, padx=(24, 2))
        self.palvar = tk.StringVar(value=self.settings.get('palette'))
        for p in R.PALETTES:
            tk.Radiobutton(top, text=p.upper(), variable=self.palvar, value=p,
                           command=self._save_settings, bg=self.panel, fg=self.text,
                           activebackground=self.panel, activeforeground=self.cyan,
                           selectcolor='#273442', relief=tk.FLAT,
                           font=('Segoe UI', 8)).pack(side=tk.LEFT, padx=2)
        self.autovar = tk.BooleanVar(value=self.settings.get('auto_deg'))
        self.smoothvar = tk.BooleanVar(value=self.settings.get('smooth'))
        tk.Checkbutton(top, text='SMOOTHEN IR', variable=self.smoothvar,
                       command=self._save_settings, bg=self.panel, fg=self.text,
                       activebackground=self.panel, activeforeground=self.cyan,
                        selectcolor='#273442', relief=tk.FLAT,
                        font=('Segoe UI', 8, 'bold')).pack(side=tk.LEFT, padx=(10, 0))
        self.mainvar = tk.StringVar(value=self.settings.get('main_light', 'vis'))
        tk.Button(top, text='?', command=self._show_shortcuts,
                  bg='#2a3542', fg=self.text, activebackground='#3b4b5d',
                  activeforeground='#ffffff', relief=tk.FLAT,
                  font=('Segoe UI', 9, 'bold'), width=2,
                  padx=0).pack(side=tk.LEFT, padx=(8, 0))

        self._banner_src = Image.open(_asset_path('banner.png')).convert('RGBA')
        self._banner_photo = None
        self._resize_banner()

        # ---- registration bar (VIS<->IR alignment) -----------------------
        ab = tk.Frame(controls, padx=14, pady=5, bg=self.panel2)
        ab.pack(side=tk.TOP, fill=tk.X)
        tk.Label(ab, text='FUSION CALIBRATION', fg=self.cyan, bg=self.panel2,
                 font=('Segoe UI', 8, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        self.alignvar = {}
        self.alignvar['z'] = tk.DoubleVar(
            value=self.settings.get('align_z', 1.0))
        specs = (('x', -80, 80, 1, 0, 'X'), ('y', -60, 60, 1, 0, 'Y'),
                 ('r', -45, 45, 0.5, 0, 'Rot'))
        for key, lo, hi, step, dflt, label in specs:
            v = tk.DoubleVar(value=self.settings.get('align_' + key, dflt))
            self.alignvar[key] = v
            tk.Label(ab, text=label, fg=self.muted, bg=self.panel2,
                     font=('Segoe UI', 8, 'bold')).pack(side=tk.LEFT, padx=(8, 0))
            tk.Scale(ab, orient=tk.HORIZONTAL, from_=lo, to=hi,
                     resolution=step, variable=v, command=self._align_changed,
                     length=123, bg=self.panel2, fg=self.text,
                     troughcolor='#2b3744', activebackground=self.cyan,
                     highlightthickness=0, showvalue=False).pack(side=tk.LEFT, padx=(2, 0))
        tk.Button(ab, text='CAM ALIGN', command=self._auto_align,
                  bg=self.cyan, fg='#061017', activebackground='#72e2ff',
                  relief=tk.FLAT, font=('Segoe UI', 8, 'bold'),
                  padx=8).pack(side=tk.LEFT, padx=(12, 3))
        tk.Button(ab, text='RESET', command=self._align_reset,
                  bg='#2a3542', fg=self.text, activebackground='#3b4b5d',
                  relief=tk.FLAT, font=('Segoe UI', 8, 'bold'),
                  padx=8).pack(side=tk.LEFT)
        self.edgevar = tk.DoubleVar(value=self.settings.get('edge_strength', 50.0))

        self.bar = tk.Label(root, text='IDLE', anchor=tk.W, padx=14,
                            bg='#0d131a', fg=self.muted,
                            relief=tk.FLAT, font=('Consolas', 9))
        self.bar.pack(side=tk.BOTTOM, fill=tk.X)

        view = tk.Frame(root, bg='#070a0e')
        self.view = view
        view.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        view.pack_propagate(False)
        self.canvas = tk.Canvas(view, bg='#070a0e', highlightthickness=1,
                                highlightbackground='#273442')
        self.canvas.pack(side=tk.LEFT, fill=tk.Y, expand=False)
        self.canvas.bind('<Configure>', lambda e: self._dirty())
        self.canvas.bind('<ButtonPress-1>', self._view_press)
        self.canvas.bind('<B1-Motion>', self._view_motion)
        self.canvas.bind('<ButtonRelease-1>', self._view_release)
        self.canvas.bind('<MouseWheel>', self._view_wheel)
        self.canvas.bind('<Button-4>', lambda e: self._view_wheel(e, 1))
        self.canvas.bind('<Button-5>', lambda e: self._view_wheel(e, -1))

        nav = tk.Frame(view, width=self.nav_width, bg=self.panel,
                       highlightthickness=1, highlightbackground='#273442')
        self.nav = nav
        nav.pack(side=tk.RIGHT, anchor=tk.N)
        tk.Label(nav, text='CAMERA OVERLAY', fg=self.cyan, bg=self.panel,
                 font=('Segoe UI', 9, 'bold')).pack(pady=(10, 2))
        source = tk.Frame(nav, bg=self.panel)
        source.pack(anchor=tk.CENTER)
        for m, mtxt in (('vis', 'VIS'), ('ir', 'IR')):
            tk.Radiobutton(source, text=mtxt, variable=self.mainvar, value=m,
                           command=self._save_settings, bg=self.panel, fg=self.text,
                           activebackground=self.panel, activeforeground=self.cyan,
                           selectcolor='#273442', relief=tk.FLAT,
                           font=('Segoe UI', 8, 'bold')).pack(side=tk.LEFT, padx=2)
        tk.Label(nav, text='IR ALIGN', fg=self.cyan, bg=self.panel,
                 font=('Segoe UI', 9, 'bold')).pack(pady=(7, 4))
        tk.Label(nav, text='move thermal over VIS', fg=self.muted, bg=self.panel,
                 font=('Consolas', 9)).pack(pady=(0, 10))
        pad = tk.Frame(nav, bg=self.panel)
        pad.pack()
        button_opts = dict(bg='#2a3542', fg=self.text,
                           activebackground='#3b4b5d', activeforeground='#ffffff',
                           relief=tk.FLAT, font=('Segoe UI', 12, 'bold'),
                           width=4, height=1)
        tk.Button(pad, text='^', command=lambda: self._nudge_align(0, -1),
                  **button_opts).grid(row=0, column=1, padx=2, pady=2)
        tk.Button(pad, text='<', command=lambda: self._nudge_align(-1, 0),
                  **button_opts).grid(row=1, column=0, padx=2, pady=2)
        self.edge_text = tk.StringVar(value='%.0f%%' % self.edgevar.get())
        tk.Button(pad, textvariable=self.edge_text,
                  command=self._outline_center, bg=self.cyan, fg='#061017',
                  activebackground='#72e2ff', relief=tk.FLAT,
                  font=('Segoe UI', 9, 'bold'), width=5).grid(
                      row=1, column=1, padx=2, pady=2)
        tk.Button(pad, text='>', command=lambda: self._nudge_align(1, 0),
                  **button_opts).grid(row=1, column=2, padx=2, pady=2)
        tk.Button(pad, text='v', command=lambda: self._nudge_align(0, 1),
                  **button_opts).grid(row=2, column=1, padx=2, pady=2)
        sliders = tk.Frame(nav, bg=self.panel)
        sliders.pack(anchor=tk.CENTER, pady=(12, 0))
        slider_opts = dict(orient=tk.VERTICAL, length=165,
                           bg=self.panel, fg=self.text, troughcolor='#2b3744',
                           activebackground=self.cyan, highlightthickness=0,
                           showvalue=False, width=24)
        outline = tk.Frame(sliders, bg=self.panel)
        outline.grid(row=0, column=0, padx=(8, 3))
        tk.Label(outline, text='VIS OUTLINE', fg=self.muted, bg=self.panel,
                 font=('Segoe UI', 8, 'bold')).pack()
        tk.Scale(outline, from_=100, to=0, resolution=1,
                 variable=self.edgevar, command=self._edge_changed,
                 **slider_opts).pack()
        tk.Button(outline, text='R', command=self._outline_center,
                  bg='#2a3542', fg=self.text, activebackground='#3b4b5d',
                  activeforeground='#ffffff', relief=tk.FLAT,
                  font=('Segoe UI', 8, 'bold'), width=3, height=1,
                  padx=0, pady=0).pack(pady=(3, 0), fill=tk.X)
        zoom = tk.Frame(sliders, bg=self.panel)
        zoom.grid(row=0, column=1, padx=(3, 8))
        tk.Label(zoom, text='ZOOM', fg=self.muted, bg=self.panel,
                 font=('Segoe UI', 8, 'bold')).pack()
        tk.Scale(zoom, from_=2.0, to=0.5, resolution=0.01,
                 variable=self.alignvar['z'], command=self._align_changed,
                 **slider_opts).pack()
        tk.Button(zoom, text='R', command=self._zoom_reset,
                  bg='#2a3542', fg=self.text, activebackground='#3b4b5d',
                  activeforeground='#ffffff', relief=tk.FLAT,
                  font=('Segoe UI', 8, 'bold'), width=3, height=1,
                  padx=0, pady=0).pack(pady=(3, 0), fill=tk.X)
        tk.Label(nav, text='HOTSPOT SEARCH', fg=self.muted, bg=self.panel,
                 font=('Segoe UI', 8, 'bold')).pack(pady=(12, 4))
        tk.Button(nav, text='🔥  FIND HOTSPOT', command=self._find_hotspot,
                  bg=self.red, fg='#ffffff', activebackground='#ff8091',
                  activeforeground='#ffffff', relief=tk.FLAT,
                  font=('Segoe UI', 10, 'bold'),
                  padx=8, pady=10).pack(padx=12, fill=tk.X)
        tk.Button(nav, text='RESET HOTSPOT', command=self._reset_hotspot,
                  bg='#2a3542', fg=self.text, activebackground='#3b4b5d',
                  activeforeground='#ffffff', relief=tk.FLAT,
                  font=('Segoe UI', 8, 'bold'),
                  padx=8, pady=5).pack(padx=12, pady=(5, 0), fill=tk.X)

        nav.update_idletasks()
        self._nav_min_height = nav.winfo_reqheight()
        nav.pack_propagate(False)
        self.temps = TempSetpoints(root,
                                   lo=self.settings.get('lo_deg'),
                                   hi=self.settings.get('hi_deg'),
                                   on_change=self._temp_changed,
                                   on_manual=self._manual_temp,
                                   auto_var=self.autovar,
                                   on_auto=self._save_settings,
                                   palette=self.settings.get('palette'))
        self.temps.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        self._shortcut_hints = (
            'Space  switch VIS / IR source',
            'Arrows  move IR alignment',
            'H  locate hotspot    R  reset hotspot',
            'A  toggle auto range    C  camera align',
            'Z  zoom in    X  zoom out',
        )
        self._shortcut_hint_index = 0
        self._rotate_shortcut_hint()
        root.update_idletasks()
        min_w = max(900, self.nav_width + 320, control_area.winfo_reqwidth())
        min_h = (control_area.winfo_reqheight() +
                 max(120, self._nav_min_height) +
                 self.temps.winfo_reqheight() + self.bar.winfo_reqheight() + 20)
        root.minsize(min_w, min_h)

        self.client = None
        self._img_ref = None
        self._ir = None
        self._vis = None
        self._temp_live = None
        self._dirty_flag = True
        self._hot_sel = 0
        self._hot_tick = 0
        self._view_pan = [0.0, 0.0]
        self._pan_drag = None
        self._hotspot_view_state = None

        root.protocol('WM_DELETE_WINDOW', self._close)
        root.bind_all('<KeyPress>', self._shortcut)
        self._pulse()
        if host:
            root.after(250, self.connect)

    def _resize_banner(self, event=None):
        w, h = self._banner_src.size
        max_h = max(1, self._banner_label.master.winfo_height() - 4)
        max_w = max(1, self._banner_label.master.winfo_width() - 4)
        scale = min(max_w / w, max_h / h)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        image = self._banner_src.resize(size, Image.Resampling.LANCZOS)
        self._banner_photo = ImageTk.PhotoImage(image)
        self._banner_label.configure(image=self._banner_photo)

    def _zoom_reset(self):
        self.alignvar['z'].set(1.0)
        self._align_changed()

    def _shortcut(self, event):
        key = event.keysym.lower()
        if key == 'space':
            self.mainvar.set('ir' if self.mainvar.get() == 'vis' else 'vis')
            self._save_settings()
        elif key in ('left', 'right', 'up', 'down'):
            dx = -1 if key == 'left' else 1 if key == 'right' else 0
            dy = -1 if key == 'up' else 1 if key == 'down' else 0
            self._nudge_align(dx, dy)
        elif key == 'h':
            self._find_hotspot()
        elif key == 'r':
            self._reset_hotspot()
        elif key == 'a':
            self.autovar.set(not self.autovar.get())
            self._save_settings()
            self._dirty()
        elif key == 'c':
            self._auto_align()
        elif key == 'z':
            self.alignvar['z'].set(np.clip(self.alignvar['z'].get() + 0.05, 0.5, 2.0))
            self._align_changed()
        elif key == 'x':
            self.alignvar['z'].set(np.clip(self.alignvar['z'].get() - 0.05, 0.5, 2.0))
            self._align_changed()

    def _show_shortcuts(self):
        win = tk.Toplevel(self.root)
        win.title('SuperCam Shortcuts')
        win.transient(self.root)
        win.resizable(False, False)
        win.configure(bg=self.panel)
        banner_image = self._banner_src.copy()
        banner_image.thumbnail((300, 120), Image.Resampling.LANCZOS)
        win._banner_photo = ImageTk.PhotoImage(banner_image)
        tk.Label(win, image=win._banner_photo, bg=self.panel, bd=0).pack(
            padx=8, pady=(8, 2))
        tk.Button(win, text='OPEN SOURCE REPO', command=self._open_repo,
                  bg=self.panel, fg=self.cyan, activebackground=self.panel,
                  activeforeground='#72e2ff', relief=tk.FLAT, bd=0,
                  cursor='hand2', font=('Segoe UI', 9, 'bold', 'underline'),
                  padx=4).pack(pady=(0, 7))
        tk.Label(win, text=('CREDITS - IT-SOLVE\nWWW.IT-SOLVE.AU\n'
                            'SUPPORT@IT-SOLVE.AU\n'
                            'HTTPS://GITHUB.COM/GUNAYANACH/QUANLI-SUPERCAM\n'
                            'SUPERCAM V%s  |  BUILD %s' % (VERSION, BUILD_DATE)),
                 justify=tk.CENTER, fg=self.cyan, bg=self.panel,
                 font=('Segoe UI', 9, 'bold')).pack(pady=(0, 10))
        tk.Label(win, text='KEYBOARD SHORTCUTS', fg=self.cyan, bg=self.panel,
                 font=('Segoe UI', 10, 'bold')).pack(padx=18, pady=(14, 8))
        text = ('Space    Switch between VIS and IR\n'
                'Arrows   Move IR alignment\n'
                'H        Locate hotspot\n'
                'R        Reset hotspot\n'
                'A        Toggle auto range\n'
                'C        Camera align\n'
                'Z        Zoom in\n'
                'X        Zoom out')
        tk.Label(win, text=text, justify=tk.LEFT, anchor=tk.W,
                 fg=self.text, bg=self.panel, font=('Consolas', 10)).pack(
                     padx=18, pady=(0, 14))
        tk.Button(win, text='CLOSE', command=win.destroy,
                  bg='#2a3542', fg=self.text, activebackground='#3b4b5d',
                  relief=tk.FLAT, font=('Segoe UI', 8, 'bold'),
                  padx=12).pack(pady=(0, 12))
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry('+%d+%d' % (max(0, x), max(0, y)))

    def _open_repo(self):
        webbrowser.open('https://github.com/GunayAnach/QuanLi-SuperCam')

    def _rotate_shortcut_hint(self):
        self.temps.shortcut_hint = self._shortcut_hints[self._shortcut_hint_index]
        self._shortcut_hint_index = (self._shortcut_hint_index + 1) % len(self._shortcut_hints)
        self.temps.redraw()
        self.root.after(5000, self._rotate_shortcut_hint)

    # ---- transport ------------------------------------------------------
    def toggle(self):
        if self.client:
            self.stop()
        else:
            self.connect()

    def connect(self):
        ip = self.ipvar.get().strip()
        if not ip:
            messagebox.showerror('SuperCam', 'Enter the camera IP/hostname.')
            return
        v = self.settings.data.copy()
        v.update(ip=ip)
        self.settings.data = v
        self.settings.save(ip=ip)
        self.client = (CameraClient(ip, port=int(self.settings.get('port')),
                                    on_ir_frame=self._on_ir,
                                    on_vis_frame=self._on_vis,
                                    on_state=self._on_state)
                       .start())
        self.btn.config(text='Stop', state=tk.NORMAL)

    def stop(self):
        if self.client:
            self.client.stop()
            self.client = None
        self.btn.config(text='Connect', state=tk.NORMAL)
        self.bar.config(text='stopped')

    def _close(self):
        self._save_geometry()
        self.stop()
        self.root.destroy()

    def _geometry_changed(self, event):
        if event.widget is not self.root:
            return
        if self._geometry_job is not None:
            self.root.after_cancel(self._geometry_job)
        self._geometry_job = self.root.after(700, self._save_geometry)

    def _save_geometry(self):
        self._geometry_job = None
        self.settings.save(window_geometry=self.root.geometry())

    # ---- callbacks (threads) -------------------------------------------
    def _on_ir(self, img, stats, rate):
        self._ir = img
        raw_temp = R.raw_to_temp(img, self.settings.get('t_offset'),
                                 self.settings.get('t_gain'))
        self._temp_live = R.smooth_temp_frame(raw_temp, self._temp_live)
        self._dirty()

    def _on_vis(self, frame, rate):
        self._vis = frame
        self._dirty()

    def _on_state(self, state, err):
        if state == 'error':
            messagebox.showerror('SuperCam', 'Connection error: %s' % err)
        self._dirty()

    def _temp_changed(self, lo, hi):
        self.settings.save(lo_deg=float(lo), hi_deg=float(hi))
        self._dirty()

    def _manual_temp(self):
        if self.autovar.get():
            self.autovar.set(False)
            self._save_settings()

    def _save_settings(self):
        self.settings.save(palette=self.palvar.get(),
                           smooth=self.smoothvar.get(),
                           auto_deg=self.autovar.get(),
                           main_light=self.mainvar.get(),
                           edge_strength=self.edgevar.get())
        self._save_geometry()
        if hasattr(self, 'bar'):
            self.bar.config(text='settings saved: %s' % self.settings.ini_path)

    def _align_params(self):
        return (self.alignvar['x'].get(), self.alignvar['y'].get(),
                self.alignvar['z'].get(), self.alignvar['r'].get())

    def _align_changed(self, _v=None):
        p = self._align_params()
        self.settings.save(align_x=p[0], align_y=p[1], align_z=p[2],
                           align_r=p[3])
        self._dirty()

    def _nudge_align(self, dx, dy):
        self.alignvar['x'].set(np.clip(self.alignvar['x'].get() + dx, -80, 80))
        self.alignvar['y'].set(np.clip(self.alignvar['y'].get() + dy, -60, 60))
        self._align_changed()

    def _edge_changed(self, _v=None):
        value = float(self.edgevar.get())
        self.edge_text.set('%.0f%%' % value)
        self.settings.save(edge_strength=value)
        self._dirty()

    def _outline_center(self):
        self.edgevar.set(50.0)
        self._edge_changed()

    def _find_hotspot(self):
        if self._ir is None:
            return
        if self._hotspot_view_state is None:
            self._hotspot_view_state = (
                float(self.alignvar['z'].get()),
                float(self._view_pan[0]), float(self._view_pan[1]),
                bool(self.autovar.get()))
        temp = np.asarray(self._temp_fn()(self._ir), dtype=np.float32)
        if temp.shape[0] > 2 and temp.shape[1] > 2:
            temp[[0, -1], :] = np.nan
            temp[:, [0, -1]] = np.nan
        if not np.isfinite(temp).any():
            return
        deg_max = float(np.nanmax(temp))
        spots = R.find_hotspots(temp, deg_max)
        self._hot_sel = 0
        if self.alignvar['z'].get() <= 1.001:
            self.alignvar['z'].set(1.25)
            self._align_changed()
        zoom = float(self.alignvar['z'].get())
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        sx, sy = spots[0][1] / 160.0 * w, spots[0][2] / 120.0 * h
        max_x = max(0.0, (zoom - 1.0) * w / 2.0)
        max_y = max(0.0, (zoom - 1.0) * h / 2.0)
        self._view_pan[0] = np.clip((w / 2.0 - sx) * zoom, -max_x, max_x)
        self._view_pan[1] = np.clip((h / 2.0 - sy) * zoom, -max_y, max_y)
        self.autovar.set(True)
        self._save_settings()
        self._dirty()
        self.bar.config(text='hotspot centered: %.1fC' % spots[0][0])

    def _reset_hotspot(self):
        state = self._hotspot_view_state
        if state is None:
            self._view_pan[:] = (0.0, 0.0)
            self._dirty()
            return
        zoom, px, py, was_auto = state
        self.alignvar['z'].set(zoom)
        self._view_pan[:] = (px, py)
        self.autovar.set(was_auto)
        self._hotspot_view_state = None
        self._align_changed()
        self._save_settings()
        self._dirty()
        self.bar.config(text='hotspot view reset')

    def _align_reset(self):
        for k, d in zip(('x', 'y', 'z', 'r'), R.FACTORY_ALIGN):
            self.alignvar[k].set(d)
        self._view_pan[:] = (0.0, 0.0)
        self._align_changed()

    def _auto_align(self):
        if self._ir is None or self._vis is None:
            return
        try:
            ir_bgr = R.ir_to_rgb(self._ir, self._temp_fn()(self._ir),
                                 self.palvar.get(),
                                 float(self.temps.lo), float(self.temps.hi), True)
            x, y, z, r = self._align_params()
            x, y, z, r = R.auto_align(ir_bgr, self._vis, x, y, z, r)
            self.alignvar['x'].set(min(80, max(-80, x)))
            self.alignvar['y'].set(min(60, max(-60, y)))
            self.alignvar['z'].set(min(2.0, max(0.5, z)))
            self.alignvar['r'].set(min(45, max(-45, r)))
            self._align_changed()
            self.bar.config(text='factory calibration: X %.1f Y %.1f Z %.2f R %.1f' % (
                x, y, z, r))
        except Exception as e:
            self.bar.config(text='auto-align failed: %s' % e)

    # ---- rendering ------------------------------------------------------
    def _view_press(self, event):
        self._pan_drag = (event.x, event.y, self._view_pan[0], self._view_pan[1])

    def _view_wheel(self, event, direction=None):
        if direction is None:
            direction = 1 if event.delta > 0 else -1
        zoom = np.clip(self.alignvar['z'].get() + direction * 0.05, 0.5, 2.0)
        self.alignvar['z'].set(float(zoom))
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        max_x = max(0.0, (zoom - 1.0) * w / 2.0)
        max_y = max(0.0, (zoom - 1.0) * h / 2.0)
        self._view_pan[0] = np.clip(self._view_pan[0],
                                    -max_x, max_x)
        self._view_pan[1] = np.clip(self._view_pan[1],
                                    -max_y, max_y)
        self._align_changed()

    def _view_motion(self, event):
        if self._pan_drag is None:
            return
        sx, sy, px, py = self._pan_drag
        zoom = float(self.alignvar['z'].get())
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        max_x = max(0.0, (zoom - 1.0) * w / 2.0)
        max_y = max(0.0, (zoom - 1.0) * h / 2.0)
        self._view_pan[0] = np.clip(px + event.x - sx, -max_x, max_x)
        self._view_pan[1] = np.clip(py + event.y - sy, -max_y, max_y)
        self._dirty()

    def _view_release(self, _event):
        self._pan_drag = None

    def _dirty(self):
        self._dirty_flag = True

    def _temp_fn(self):
        def convert(raw):
            if raw is self._ir and self._temp_live is not None:
                return self._temp_live
            return R.raw_to_temp(raw, self.settings.get('t_offset'),
                                 self.settings.get('t_gain'))
        return convert

    def _pulse(self):
        st = self.client.status if self.client else {}
        manual = not self.autovar.get()
        if self._dirty_flag and self._ir is not None:
            self._dirty_flag = False
            try:
                view_w = max(80, self.view.winfo_width() - self.nav_width)
                view_h = max(1, self.view.winfo_height())
                pane_h = max(self._nav_min_height,
                             min(view_h, int(view_w * 3 / 4)))
                cw = int(round(pane_h * 4 / 3))
                ch = pane_h
                self.canvas.config(width=cw, height=ch)
                self.nav.config(height=ch)
                bgr, deg_max, lo_now, hi_now, spots = R.composite(
                    self._ir, self._vis,
                    palette=self.palvar.get(),
                    smooth=self.smoothvar.get(),
                    height=pane_h,
                    temp_fn=self._temp_fn(),
                    lo_deg=self.temps.lo, hi_deg=self.temps.hi,
                    manual=manual, focus_index=self._hot_sel,
                     main=self.mainvar.get(), align=self._align_params(),
                     edge_strength=self.edgevar.get(), view_pan=self._view_pan)
                # cycle the crosshair between hot spots (within 5C) ~every 0.45s
                if len(spots) > 1:
                    self._hot_tick += 1
                    if self._hot_tick >= 14:
                        self._hot_tick = 0
                        self._hot_sel += 1
                else:
                    self._hot_tick = 0
                # X axis adapts to the driving band (autoscale or cutoffs),
                # min range is always the 20..70C base band
                if manual:
                    d0, d1 = R.xdomain(self.temps.lo, self.temps.hi)
                    plo, phi = self.temps.lo, self.temps.hi
                else:
                    d0, d1 = R.xdomain(lo_now, hi_now)
                    plo, phi = lo_now, hi_now
                self.temps.set_domain(d0, d1)
                w, h = bgr.shape[1], bgr.shape[0]
                if cw and cw < w:
                    sc = cw / w
                    bgr = cv2.resize(bgr, (cw, max(1, int(h * sc))),
                                     interpolation=cv2.INTER_LINEAR)
                png = base64.b64encode(R.to_png(bgr)).decode('ascii')
                photo = tk.PhotoImage(data=png)
                self.canvas.delete('all')
                self.canvas.create_image(0, 0, image=photo, anchor=tk.NW)
                self._img_ref = photo
                self.temps.redraw(bar_lo=lo_now, bar_hi=hi_now,
                                  lo=plo, hi=phi,
                                  max_deg=deg_max, auto=not manual)
                if self.client:
                    self.bar.config(text='SUPERCAM v%s | %s | sid=%s | IR %.0ffps | VIS %.0ffps | hot %.1fC | scale %.1f..%.1fC | %s' % (
                        VERSION, st.get('state', '-'), st.get('sid', '-'),
                        st.get('ir', 0), st.get('vis', 0),
                        deg_max, lo_now, hi_now,
                        'manual' if manual else 'auto'))
            except Exception as e:
                self.bar.config(text='render: %s' % e)
        elif self._dirty_flag:
            self._dirty_flag = False
            self.temps.redraw()
            if self.client:
                self.bar.config(text='SUPERCAM v%s | %s | sid=%s | IR %.0ffps | VIS %.0ffps' % (
                    VERSION, st.get('state', '-'), st.get('sid', '-'),
                    st.get('ir', 0), st.get('vis', 0)))
        self.root.after(33, self._pulse)


def run(host=None):
    root = tk.Tk()
    ViewerApp(root, host)
    root.mainloop()
