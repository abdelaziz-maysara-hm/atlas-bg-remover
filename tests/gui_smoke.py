"""Drive the GUI under Xvfb and take screenshots (not a pytest test).
Usage: xvfb-run -s "-screen 0 1280x860x24" python tests/gui_smoke.py OUTDIR [ar|en] [scenario]"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageGrab
import atlas_bg_gui as G

out = sys.argv[1]; lang = sys.argv[2] if len(sys.argv) > 2 else "en"
scen = sys.argv[3] if len(sys.argv) > 3 else "full"
os.makedirs(out, exist_ok=True)
SRC = "/workspace/testimgs/src"
app = G.App()
if app.lang != lang:
    app.toggle_lang()
app.geometry("1260x780+0+0")
log = []

def shot(name):
    app.update_idletasks(); app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ["DISPLAY"]).save(f"{out}/{lang}_{name}.png")
    log.append(name)

def wait_idle(timeout=300):
    t = time.time()
    while app.busy() and time.time() - t < timeout:
        app.update(); time.sleep(0.05)
    for _ in range(10):
        app.update(); time.sleep(0.05)

def run():
    shot("01_empty")
    files = [f"{SRC}/{n}.jpg" for n in ["portrait_red_curly_hair", "cat", "shoe_product", "watch_product", "dog_golden_fur"]]
    files += ["/workspace/testimgs/edge/notes.png", "/workspace/testimgs/edge/صورة تجربة عربي.jpg"]
    app.add_paths(files)
    app.lb.selection_clear(0, "end"); app.lb.selection_set(0); app.on_select()
    shot("02_added")
    app.preview_selected(); wait_idle()
    shot("03_preview")
    if scen == "full":
        app.out_dir = G.Path("/tmp/gui_out_" + lang)
        app.v_bg = "white"; app.v_preset = "square1080"; app.v_format = "jpg"; app.build()
        app.lb.selection_set(2); app.on_select()
        shot("04_settings_changed")
        app.start()
        for _ in range(30):
            app.update(); time.sleep(0.05)
        shot("05_running")
        wait_idle()
        app.lb.selection_clear(0, "end"); app.lb.selection_set(2); app.on_select()
        shot("06_done")
        app.lb.selection_clear(0, "end"); app.lb.selection_set(5); app.on_select()
        shot("07_failed_item")
        # cancel test: start again and cancel immediately
        app.start(); app.update(); app.do_cancel(); wait_idle()
        shot("08_cancelled")
        app.v_bg = "none"; app.v_preset = "none"; app.v_format = "png"; app.persist()
    print("shots:", log, "status:", app.status.cget("text"))
    app.destroy()

app.after(500, run)
app.mainloop()
