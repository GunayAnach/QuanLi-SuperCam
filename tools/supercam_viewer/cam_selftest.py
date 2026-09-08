"""cam_selftest.py - headless dual-stream soak (8s) without the GUI."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supercam.camera import CameraClient  # noqa: E402


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else '192.168.2.32'
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
    got_ir = got_vis = 0
    t0 = time.time()

    def on_ir(img, stats, rate):
        nonlocal got_ir
        got_ir += 1
        if got_ir % 10 == 0:
            print('IR  %s   rate=%.1f  raw_avg=%.1f' % (img.shape, rate, stats[1]))

    def on_vis(frame, rate):
        nonlocal got_vis
        got_vis += 1
        if got_vis % 10 == 0:
            print('VIS %s   rate=%.1f' % (frame.shape, rate))

    def on_state(state, err):
        print('STATE', state, err or '')

    c = CameraClient(host, on_ir_frame=on_ir, on_vis_frame=on_vis,
                     on_state=on_state)
    c.start()
    try:
        while time.time() - t0 < dur and c.status.get('state') != 'error':
            time.sleep(0.2)
        time.sleep(0.5)
    finally:
        c.stop()
    st = c.status
    print('DONE  state=%s  IR_frames=%d  VIS_frames=%d' % (st.get('state'), got_ir, got_vis))
    sys.exit(0 if got_ir else 1)


if __name__ == '__main__':
    main()