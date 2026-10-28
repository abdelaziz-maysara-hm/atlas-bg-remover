"""GUI failure paths under Xvfb: model download offline -> error dialog;
then real download of u2netp with progress; RAM warning dialog decline."""
import os, sys, time, dataclasses, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
cache = tempfile.mkdtemp()
os.environ["ATLAS_BG_MODELS"] = cache
from PIL import ImageGrab
import atlas_bg.models as M
M.search_dirs = lambda: [M.cache_dir()]           # pretend nothing is installed
good = M.MODELS["u2netp"]
M.MODELS["u2netp"] = dataclasses.replace(good, url="http://127.0.0.1:9/u2netp.onnx")
import atlas_bg_gui as G
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
dialogs = []
G.messagebox.showerror = lambda title, msg, **k: dialogs.append(("error", msg))
G.messagebox.askyesno = lambda title, msg, **k: (dialogs.append(("ask", msg)), False)[1]
app = G.App(); app.geometry("1260x780+0+0")
if app.lang != "en": app.toggle_lang()

def shot(n):
    app.update(); x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()), xdisplay=os.environ["DISPLAY"]).save(f"{out}/{n}.png")

def wait(cond, t=300):
    t0 = time.time()
    while not cond() and time.time() - t0 < t:
        app.update(); time.sleep(0.03)

def pump():
    for _ in range(10): app.update(); time.sleep(0.05)

def run():
    app.set_model("u2netp"); app.build()
    shot("f1_not_installed")
    app.add_paths(["/workspace/testimgs/src/cat.jpg"])
    app.start(); wait(lambda: not app.busy()); pump()
    shot("f2_offline")
    print("offline dialog:", dialogs[-1][1][:90].replace("\n", " ") if dialogs else None)
    M.MODELS["u2netp"] = good
    app.start(); seen = []
    wait(lambda: "Downloading" in app.status.cget("text") or not app.busy(), 60)
    seen.append(app.status.cget("text")); shot("f3_downloading")
    wait(lambda: not app.busy()); pump()
    seen.append(app.status.cget("text")); shot("f4_after_download")
    print("download statuses:", seen, "file:", os.path.getsize(os.path.join(cache, good.filename)))
    # RAM warning: fake low RAM, user says No -> nothing starts
    G.ram_warning = lambda k: (7000, 3000)
    app.start(); print("after RAM decline busy=", app.busy(), "dialog:", dialogs[-1][0])
    app.set_model(G.DEFAULT_MODEL); app.destroy()

app.after(400, run); app.mainloop()
