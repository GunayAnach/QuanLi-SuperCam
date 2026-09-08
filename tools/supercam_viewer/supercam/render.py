"""render.py - palette mapping, cutoff limits, hotspot crosshair, temp gauge.

Panels: LEFT = CAMERA (VIS) / RIGHT = IR, two equal 16:9 boxes. A horizontal
temperature gauge spans the bottom, with a needle at the current max-hotspot.
"""
import numpy as np
import cv2

PALETTES = ('inferno', 'jet', 'gray')
FACTORY_ALIGN = (21.0, 5.0, 1.0, 0.0)


def _lut(name):
    cvmap = {'inferno': cv2.COLORMAP_INFERNO,
             'jet': cv2.COLORMAP_JET,
             'gray': cv2.COLORMAP_BONE}   # bone approximates gray on dark
    return cvmap.get(name, cv2.COLORMAP_INFERNO)


def raw_to_temp(raw, offset=0.0, gain=0.01):
    """Linear raw-count model -> degC. Placeholder pending 0x6051 calibration."""
    return (raw.astype(np.float32) - offset) * gain


def smooth_temp_frame(temp, previous=None, alpha=0.35):
    """Reduce sensor noise before palette expansion.

    PCBtool-style fusion is steadier because it does not palette-map every raw
    frame independently.  A small bilateral filter removes isolated pixel
    noise while preserving hot components, then an EMA damps frame-to-frame
    shimmer without making hotspot response sluggish.
    """
    temp = np.asarray(temp, dtype=np.float32)
    valid = np.isfinite(temp)
    if not valid.any():
        return temp.copy()
    fill = temp.copy()
    fill[~valid] = float(np.nanmedian(temp))
    spatial = cv2.bilateralFilter(fill, 5, 0.8, 1.2)
    spatial[~valid] = np.nan
    if previous is None or previous.shape != spatial.shape:
        return spatial
    both = valid & np.isfinite(previous)
    out = spatial.copy()
    out[both] = (1.0 - alpha) * previous[both] + alpha * spatial[both]
    return out


def analyze(temp, lo_deg, hi_deg, manual):
    """Returns (max_deg, (x,y) of hottest pixel, lo_now, hi_now)."""
    v = temp[~np.isnan(temp)]
    if v.size == 0:
        return 0.0, (80, 60), float(lo_deg), float(hi_deg)
    deg_max = float(v.max())
    flat = np.where(np.isnan(temp), np.nanmin(temp), temp)
    y, x = np.unravel_index(int(np.argmax(flat)), temp.shape)
    if manual:
        lo_now, hi_now = float(lo_deg), float(hi_deg)
    else:
        lo_now = float(np.nanpercentile(v, 2))
        hi_now = max(deg_max, float(np.nanpercentile(v, 98)))
        if lo_now == hi_now:
            lo_now, hi_now = float(v.min()), float(v.max())
        if lo_now == hi_now:
            lo_now, hi_now = lo_now - 20.0, hi_now + 20.0
    return deg_max, (int(x), int(y)), lo_now, hi_now


def find_hotspots(temp, deg_max, max_delta=5.0, min_frac=0.012, max_spots=4):
    """Connected hot regions within max_delta of the hottest pixel, sorted by
    temperature descending -> [(deg, x, y), ...]. The crosshair jumps between
    these when the temperature difference is under max_delta."""
    mask = (~np.isnan(temp)) & (temp >= deg_max - max_delta)
    if not mask.any():
        return [(deg_max, 80, 60)]
    n, labels = cv2.connectedComponents(mask.astype(np.uint8))
    min_area = max(3, int(mask.sum() * min_frac))
    comps = []
    for c in range(1, n):
        ys, xs = np.where(labels == c)
        if ys.size < min_area:
            continue
        vals = temp[ys, xs]
        i = int(np.argmax(vals))
        comps.append((float(vals[i]), int(xs[i]), int(ys[i])))
    comps.sort(reverse=True, key=lambda t: t[0])
    if not comps:
        return [(deg_max, 80, 60)]
    best = comps[0][0]
    comps = [c for c in comps if best - c[0] <= max_delta]
    return comps[:max_spots]


def xdomain(lo, hi):
    """Adaptive X-axis domain for the bottom gauge. Always covers at least the
    20..70C base band (the main working range) and expands up to 400C+ when the
    scene or the cutoffs demand it. Returns (d0, d1) quantized to 0.5C steps."""
    a = min(float(lo), 20.0)
    b = max(float(hi), 70.0)
    m = max(5.0, 0.08 * (b - a))
    d0 = max(0.0, a - m)
    d1 = b + m
    return round(d0 * 2) / 2.0, round(d1 * 2) / 2.0


def ir_to_rgb(img, temp, palette, lo_now, hi_now, manual):
    """IR image with NaN -> dark; manual mode also black-outs below Lo and
    saturates above Hi (the PCBtool cutoff behaviour)."""
    span = hi_now - lo_now
    if span < 1e-6:
        span = 1.0
    idx = ((temp - lo_now) * 255.0 / span).clip(0, 255)
    out = cv2.applyColorMap(np.nan_to_num(idx, nan=0.0).astype(np.uint8),
                            _lut(palette))
    out[~np.isfinite(temp)] = (20, 20, 20)     # dead/border pixels -> dark
    if manual:
        out[temp < lo_now] = (5, 5, 5)         # below cutoff -> black
        out[temp > hi_now] = (250, 250, 250)   # above upper -> white
    return out


def _draw_crosshair(canvas, cx, cy, deg, color=(255, 255, 0)):
    L = 14
    cv2.line(canvas, (cx - L, cy), (cx + L, cy), color, 1, cv2.LINE_AA)
    cv2.line(canvas, (cx, cy - L), (cx, cy + L), color, 1, cv2.LINE_AA)
    cv2.circle(canvas, (cx, cy), 2, color, -1, cv2.LINE_AA)
    lbl = '%.1fC' % deg
    cv2.putText(canvas, lbl, (cx + 14, cy - 8), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(canvas, lbl, (cx + 14, cy - 8), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, color, 1, cv2.LINE_AA)


def _draw_hot_dot(canvas, cx, cy, color=(120, 255, 200)):
    cv2.circle(canvas, (cx, cy), 3, color, 1, cv2.LINE_AA)


def _mark_pos(x, y, W, H, margin=0.05):
    """Keep marks ~5% away from the window edges so they stay fully visible."""
    return (int(np.clip(x, W * margin, W * (1 - margin))),
            int(np.clip(y, H * margin, H * (1 - margin))))


def _detail_light(bgr, clip=2.5, strength=1.5):
    """VIS 'light-change' filter: CLAHE on luminance lifts the dark/light
    structure PCBtool-style (board vs desk contrast, component bodies,
    shields), then unsharp sharpens fine detail."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a_, b_ = cv2.split(lab)
    cl = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(l)
    u = cv2.GaussianBlur(cl, (0, 0), 2.0)
    sh = cv2.addWeighted(cl, strength, u, 1.0 - strength, 0)
    return cv2.cvtColor(cv2.merge((sh, a_, b_)), cv2.COLOR_LAB2BGR)


def _edge_accent(bgr, thresh=0.32, blend=0.30):
    """Brighten strong luminance edges (component / shield outlines) so they
    read clearly through the heat overlay."""
    g = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3),
                        cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    mag = cv2.normalize(mag, None, 0, 1, cv2.NORM_MINMAX)
    e = mag > thresh
    if not e.any():
        return bgr
    out = bgr.astype(np.float32)
    out[e] = out[e] * (1.0 - blend) + 235.0 * blend
    return out.astype(np.uint8)


def _heat_alpha(temp, lo_now, hi_now, floor=0.35):
    """Per pixel IR overlay opacity: cold -> transparent (VIS shows through),
    hot -> opaque. smoothstep alpha avoids banding. NaN/dead = transparent."""
    lo, hi = float(lo_now), float(hi_now)
    span = hi - lo
    if span < 1e-3:
        return np.zeros(temp.shape, np.float32)
    t0 = lo + floor * span
    a = np.clip((temp - t0) / (span * (1.0 - floor)), 0.0, 1.0)
    a = a * a * (3.0 - 2.0 * a)            # smoothstep
    a[np.isnan(temp)] = 0.0
    return a.astype(np.float32)


def _heat_color(temp, palette, lo_now, hi_now, size):
    """Palette colouring of temperature across [lo_now, hi_now], upscaled."""
    span = float(hi_now) - float(lo_now)
    idx = np.zeros(temp.shape, np.uint8)
    if span >= 1e-3:
        idx = np.clip((temp - lo_now) * 255.0 / span, 0, 255).astype(np.uint8)
    lut = cv2.applyColorMap(np.arange(256, dtype=np.uint8), _lut(palette))[0]
    return cv2.resize(lut[idx], size, interpolation=cv2.INTER_CUBIC)


def _overlay_vis_edges(base, vis_bgr, t_low=0.17, t_high=0.42, blend=0.62):
    """Brighten strong luminance edges of a same-size VIS layer onto base,
    using a SOFT gradient alpha (no hard threshold -> no flicker/jitter from
    sub-pixel motion)."""
    h, w = base.shape[:2]
    if vis_bgr.shape[:2] != (h, w):
        vis_bgr = cv2.resize(vis_bgr, (w, h), interpolation=cv2.INTER_LINEAR)
    g = cv2.GaussianBlur(cv2.cvtColor(vis_bgr, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3),
                        cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    mag = cv2.normalize(mag, None, 0, 1, cv2.NORM_MINMAX)
    a = np.clip((mag - t_low) / (t_high - t_low), 0.0, 1.0)[..., None]
    if a.max() <= 0:
        return base
    out = base.astype(np.float32) * (1.0 - blend * a) + 248.0 * blend * a
    return out.astype(np.uint8)


def _warp_vis(vis_bgr, out_w, out_h, x, y, z, rot, interp=cv2.INTER_LINEAR):
    """Warp VIS through the calibrated 160x120 IR reference plane.

    PCBtool first clips the 16:9 VIS image to the thermal FOV, then maps that
    clipped image to the IR raster.  The old implementation fit VIS inside
    the IR raster, leaving a letterboxed 16:9 view and a wrong registration.
    """
    import math
    vh, vw = vis_bgr.shape[:2]
    ref_w, ref_h = 160.0, 120.0
    # Registration moves the clipped VIS plane. Increase the crop scale just
    # enough to replace the exposed edge with a real image edge, matching the
    # vendor's post-registration crop behavior.
    crop_z = _alignment_crop_zoom(x, y)
    s0 = max(ref_h / float(vh), ref_w / float(vw)) * z * crop_z
    cx_in, cy_in = vw / 2.0, vh / 2.0
    s_display = min(out_w / ref_w, out_h / ref_h)
    cx_display, cy_display = out_w / 2.0, out_h / 2.0
    a = math.cos(math.radians(rot)) * s0
    b = math.sin(math.radians(rot)) * s0
    Mref = np.array([[a, b, ref_w / 2.0 - a * cx_in - b * cy_in + x],
                     [-b, a, ref_h / 2.0 + b * cx_in - a * cy_in + y]],
                    np.float32)
    M = np.array([[s_display * Mref[0, 0], s_display * Mref[0, 1],
                   cx_display + s_display * (Mref[0, 2] - ref_w / 2.0)],
                  [s_display * Mref[1, 0], s_display * Mref[1, 1],
                   cy_display + s_display * (Mref[1, 2] - ref_h / 2.0)]],
                 np.float32)
    return cv2.warpAffine(vis_bgr, M, (out_w, out_h), flags=interp,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def _warp_ir_overlay(src, vis_w, vis_h, out_w, out_h, x, y, z, rot,
                     interp=cv2.INTER_LINEAR):
    """Map IR heat/alpha through the same calibrated reference plane as VIS.

    The IR reference is stretched to the display canvas, matching the vendor
    viewer's full-frame presentation.  Alignment offsets remain in IR pixels.
    """
    import math
    # _warp_vis maps VIS -> IR. This function maps IR -> VIS, so invert the
    # calibration instead of applying the same translation in the same way.
    c0 = math.cos(math.radians(rot))
    s0_inv = math.sin(math.radians(rot))
    x, y, rot = (-c0 * x + s0_inv * y,
                 -s0_inv * x - c0 * y, -rot)
    sh, sw = src.shape[:2]
    ref_w, ref_h = 160.0, 120.0
    s0 = min(ref_w / float(sw), ref_h / float(sh)) * z
    cx_in, cy_in = sw / 2.0, sh / 2.0
    s_display = min(out_w / ref_w, out_h / ref_h)
    cx_display, cy_display = out_w / 2.0, out_h / 2.0
    a = math.cos(math.radians(rot)) * s0
    b = math.sin(math.radians(rot)) * s0
    Mref = np.array([[a, b, ref_w / 2.0 - a * cx_in - b * cy_in + x],
                     [-b, a, ref_h / 2.0 + b * cx_in - a * cy_in + y]],
                    np.float32)
    M = np.array([[s_display * Mref[0, 0], s_display * Mref[0, 1],
                   cx_display + s_display * (Mref[0, 2] - ref_w / 2.0)],
                  [s_display * Mref[1, 0], s_display * Mref[1, 1],
                   cy_display + s_display * (Mref[1, 2] - ref_h / 2.0)]],
                 np.float32)
    return cv2.warpAffine(src, M, (out_w, out_h), flags=interp,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def _grad_map(bgr):
    """Normalized luminance-gradient map used as the registration signature
    (both streams show the same board-outline / component edges here)."""
    g = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3),
                        cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    return cv2.normalize(mag, None, 0, 1, cv2.NORM_MINMAX).astype(np.float32)


def _match_trans(a, b, max_shift=70.0, pad=48):
    """Coarse translation of a within b by normalized cross-correlation on the
    gradient signatures. Returns (dx, dy) to add to the VIS warp offset."""
    if a.sum() <= 0 or b.sum() <= 0:
        return 0.0, 0.0
    pp = max(4, int(pad))
    padded = cv2.copyMakeBorder(b, pp, pp, pp, pp, cv2.BORDER_CONSTANT, 0)
    res = cv2.matchTemplate(padded, a, cv2.TM_CCORR_NORMED)
    _mn, _mx, _mloc, mloc = cv2.minMaxLoc(res)
    return -float(mloc[0] - pp), -float(mloc[1] - pp)


def auto_align(ir_bgr, vis_bgr, x=0.0, y=0.0, z=1.0, rot=0.0):
    """Apply PCBtool's factory registration model.

    The vendor SDK uses ``VisImageClip`` followed by ``ImageFusion`` and
    applies stored X/Y distances.  It does not compare thermal gradients to
    visible-light edges on every frame.  Those are different modalities, so
    ECC/template matching can confidently choose the wrong PCB feature.
    ``IRParamFile.xml`` contains the factory distances (0, 0); the calibrated
    crop and reference-plane mapping are implemented by ``_warp_vis``.
    """
    return FACTORY_ALIGN


def _alignment_crop_zoom(x, y):
    """Scale both streams equally after registration so shifted edges crop."""
    return max(1.0, 1.0 + 2.0 * abs(float(x)) / 160.0,
               1.0 + 2.0 * abs(float(y)) / 120.0)


def _fit_ir_canvas(ir_bgr, out_w, out_h, interp=cv2.INTER_LINEAR, zoom=1.0):
    """Preserve the 160x120 thermal aspect ratio inside a wide canvas."""
    ih, iw = ir_bgr.shape[:2]
    scale = min(out_w / float(iw), out_h / float(ih)) * float(zoom)
    rw = max(1, int(round(iw * scale)))
    rh = max(1, int(round(ih * scale)))
    small = cv2.resize(ir_bgr, (rw, rh), interpolation=interp)
    out = np.zeros((out_h, out_w, 3), np.uint8)
    x0 = (out_w - rw) // 2
    y0 = (out_h - rh) // 2
    sx0, sy0 = max(0, -x0), max(0, -y0)
    dx0, dy0 = max(0, x0), max(0, y0)
    copy_w = min(rw - sx0, out_w - dx0)
    copy_h = min(rh - sy0, out_h - dy0)
    if copy_w > 0 and copy_h > 0:
        out[dy0:dy0 + copy_h, dx0:dx0 + copy_w] = small[
            sy0:sy0 + copy_h, sx0:sx0 + copy_w]
    return out


def _viewport_point(x, y, out_w, out_h, zoom, pan=(0.0, 0.0)):
    """Map a reference point through the shared viewport transform."""
    px, py = pan
    return (out_w / 2.0 + (float(x) - out_w / 2.0) * float(zoom) + px,
            out_h / 2.0 + (float(y) - out_h / 2.0) * float(zoom) + py)


def _ir_to_vis_point(x, y, out_w, out_h, align):
    """Map an IR point through the same inverse affine as the VIS overlay."""
    ax, ay, _az, rot = align
    c = np.cos(np.radians(float(rot)))
    s = np.sin(np.radians(float(rot)))
    dx = float(x) - out_w / 2.0
    dy = float(y) - out_h / 2.0
    # Keep this identical to _warp_ir_overlay: calibration is in the 160x120
    # reference plane, then scaled into the displayed 4:3 canvas.
    ref_x = c * dx - s * dy - c * float(ax) + s * float(ay)
    ref_y = s * dx + c * dy - s * float(ax) - c * float(ay)
    display_scale = min(float(out_w) / 160.0, float(out_h) / 120.0)
    return (out_w / 2.0 + display_scale * ref_x,
            out_h / 2.0 + display_scale * ref_y)


def _viewport_zoom(bgr, zoom, pan=(0.0, 0.0)):
    """Apply one shared zoom to the already-fused reference viewport."""
    zoom = max(0.5, min(2.0, float(zoom)))
    if abs(zoom - 1.0) < 1e-3 and abs(float(pan[0])) < 1e-3 and abs(float(pan[1])) < 1e-3:
        return bgr
    h, w = bgr.shape[:2]
    tx = (1.0 - zoom) * w / 2.0 + float(pan[0])
    ty = (1.0 - zoom) * h / 2.0 + float(pan[1])
    M = np.array([[zoom, 0.0, tx], [0.0, zoom, ty]], np.float32)
    return cv2.warpAffine(bgr, M, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def composite(ir_img, vis_bgr, palette='inferno', smooth=True, height=480,
              temp_fn=None, lo_deg=20.0, hi_deg=70.0, manual=True,
              focus_index=0, detail=True, main='vis', align=(0.0, 0.0, 1.0, 0.0),
              edge_strength=50.0, view_pan=(0.0, 0.0)):
    """Single biggest fused window (FLIR MSX-style): the VIS stream is the
    base so the camera shows board edges, components and shields (via its
    light-detail filter), while IR heat is overprinted with alpha driven by
    the Lo/Hi cutoffs -- cold transparent, hot opaque. Hotspot dots + a
    crosshair that jumps between hot spots within 5C, kept ~5% off the edges.
    Returns (BGR canvas, max_deg, lo_now, hi_now, spots)."""
    interp = cv2.INTER_LINEAR if smooth else cv2.INTER_NEAREST
    if temp_fn is None:
        temp_fn = raw_to_temp

    temp = np.asarray(temp_fn(ir_img), dtype=np.float32).copy()
    # The RAW sensor perimeter can contain saturated calibration samples.  It
    # is not scene temperature and otherwise becomes a white frame after the
    # manual HI cutoff is applied.
    if temp.shape[0] > 2 and temp.shape[1] > 2:
        temp[[0, -1], :] = np.nan
        temp[:, [0, -1]] = np.nan
    deg_max, (hx, hy), lo_now, hi_now = analyze(temp, lo_deg, hi_deg, manual)
    spots = find_hotspots(temp, deg_max)
    focus = spots[focus_index % len(spots)]
    fdeg, fx0, fy0 = focus

    pane_h = max(120, int(height))
    # Keep the thermal/VIS reference ratio.  PCBtool displays the 4:3 IR
    # raster rather than stretching it to a 16:9 canvas.
    W = int(round(pane_h * 4 / 3.0))
    H = pane_h
    crop_z = _alignment_crop_zoom(align[0], align[1])

    if vis_bgr is None or main == 'ir':
        # IR is the main light: IR thermal upscaled cleanly (Lanczos when
        # smooth); VIS edges warped STRAIGHT to panel resolution (offsets are
        # in IR-space, scaled to panel px) and stamped with a soft edge alpha,
        # so outlines stay crisp instead of double-resampled and jittery.
        up = cv2.INTER_LANCZOS4 if smooth else cv2.INTER_NEAREST
        base = ir_to_rgb(ir_img, temp, palette, lo_now, hi_now, manual)
        base = _fit_ir_canvas(base, W, H, interp=up, zoom=crop_z)
        if vis_bgr is not None:
            reg = _warp_vis(vis_bgr, W, H, align[0], align[1], 1.0, align[3])
            edge_blend = 0.18 + 0.88 * np.clip(float(edge_strength), 0, 100) / 100.0
            base = _overlay_vis_edges(base, reg, blend=edge_blend)
    else:
        # Both streams share the calibrated IR reference plane. VIS-main uses
        # the calibrated/cropped VIS base; IR is already in that plane.
        vis = _warp_vis(vis_bgr, W, H, align[0], align[1], 1.0,
                        align[3], interp=interp)
        base = _detail_light(vis) if detail else vis
        heat = _heat_color(temp, palette, lo_now, hi_now, (160, 120))
        al = _heat_alpha(temp, lo_now, hi_now)
        Hw = _fit_ir_canvas(heat, W, H, interp=interp, zoom=crop_z)
        Aw = _fit_ir_canvas(cv2.cvtColor(al, cv2.COLOR_GRAY2BGR), W, H,
                            interp=interp, zoom=crop_z)[..., :1]
        base = np.clip(base.astype(np.float32) * (1.0 - Aw)
                       + Hw.astype(np.float32) * Aw, 0, 255).astype(np.uint8)
        if detail:
            base = _edge_accent(base)

    canvas = _viewport_zoom(base, align[2], view_pan)

    # faint dots on every qualifying hot spot, crosshair on the focused one
    for d, sx, sy in spots:
        px, py = sx / 160.0 * W, sy / 120.0 * H
        mx, my = _viewport_point(px, py, W, H, crop_z * align[2], view_pan)
        mcx, mcy = _mark_pos(int(mx), int(my), W, H)
        _draw_hot_dot(canvas, mcx, mcy)
    px, py = fx0 / 160.0 * W, fy0 / 120.0 * H
    mx, my = _viewport_point(px, py, W, H, crop_z * align[2], view_pan)
    cx, cy = _mark_pos(int(mx), int(my), W, H)
    _draw_crosshair(canvas, cx, cy, fdeg)

    # banner + scale legend (so the Y axis isn't needed on the image)
    title = 'VIS-MAIN FUSED' if main == 'vis' else 'IR-MAIN FUSED'
    cv2.putText(canvas, title, (12, 26), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (255, 200, 80), 2, cv2.LINE_AA)
    legend = 'LO %.1fC  HI %.1fC' % (lo_now, hi_now)
    (tw, th), _ = cv2.getTextSize(legend, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.putText(canvas, legend, (W - 12 - tw, 26), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(canvas, legend, (W - 12 - tw, 26), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (225, 225, 225), 1, cv2.LINE_AA)
    if not manual:
        cv2.putText(canvas, 'AUTO', (12, H - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 220, 120), 2, cv2.LINE_AA)

    return canvas, deg_max, lo_now, hi_now, spots


def to_png(bgr):
    """BGR ndarray -> encoded PNG bytes (tkinter 8.6 PhotoImage accepts PNG data)."""
    ok, enc = cv2.imencode('.png', bgr)
    if not ok:
        raise ValueError('cv2 PNG encode failed')
    return enc.tobytes()
