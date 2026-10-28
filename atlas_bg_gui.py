#!/usr/bin/env python3
"""Atlas BG Remover - customtkinter GUI. The engine lives in atlas_bg/."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw

from atlas_bg import APP_NAME, __version__
from atlas_bg.batch import collect_files, run_batch
from atlas_bg.engine import (PRESETS, SUPPORTED_EXT, Options, Remover, finish, load_image, make_cutout,
                             matting_available)
from atlas_bg.i18n import T, needs_shaping, shape
from atlas_bg.models import (BUNDLED, DEFAULT_MODEL, MODELS, ModelError, cache_dir, find_model,
                             ram_warning)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND = True
except Exception:  # missing package or tkdnd binary
    _DND = False

CFG = Path.home() / "AtlasRecordings" / "atlas_settings.json"
OUT_DEFAULT = Path.home() / "AtlasRecordings" / "BgRemover"
MODEL_ORDER = ["isnet-general-use", "birefnet-lite", "u2net", "u2netp"]
PRESET_ORDER = list(PRESETS)
EDGE_ORDER = ["refine", "matting", "off"] if matting_available() else ["refine", "off"]
BG_ORDER = ["none", "white", "custom"]

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


def load_cfg() -> dict:
    try:
        return json.loads(CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def checker(w: int, h: int, s: int = 10) -> Image.Image:
    im = Image.new("RGB", (w, h), (205, 205, 205))
    d = ImageDraw.Draw(im)
    for y in range(0, h, s):
        for x in range((y // s) % 2 * s, w, 2 * s):
            d.rectangle((x, y, x + s - 1, y + s - 1), fill=(160, 160, 160))
    return im


def fit_preview(img: Image.Image, box: int) -> Image.Image:
    im = img.copy()
    im.thumbnail((box, box), Image.LANCZOS)
    bg = checker(im.width, im.height)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    bg.paste(im, (0, 0), im)
    return bg


_Base = (ctk.CTk, TkinterDnD.DnDWrapper) if _DND else (ctk.CTk,)


class App(*_Base):
    def __init__(self):
        super().__init__()
        self.dnd_ok = False
        if _DND:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ok = True
            except Exception:
                self.dnd_ok = False
        self._fam: dict = {}
        self.cfg = load_cfg()
        s = self.cfg.get("bg_remover", {})
        self.lang = self.cfg.get("lang", "en") if self.cfg.get("lang") in T else "en"
        self.shaping = needs_shaping(self.tk.call("tk", "windowingsystem"))
        self.files: list[Path] = []
        self.status_of: dict[str, tuple] = {}     # path -> ("ok", out) | ("err", msg)
        self.v_model = s.get("model", DEFAULT_MODEL) if s.get("model") in MODELS else DEFAULT_MODEL
        self.v_format = s.get("format", "png") if s.get("format") in ("png", "jpg", "webp") else "png"
        self.v_bg = s.get("bg", "none") if s.get("bg") in BG_ORDER else "none"
        self.v_color = tuple(s.get("color", (255, 255, 255)))[:3]
        self.v_crop = bool(s.get("crop", False))
        self.v_preset = s.get("preset", "none") if s.get("preset") in PRESETS else "none"
        self.v_edges = s.get("edges", "refine") if s.get("edges") in EDGE_ORDER else "refine"
        self.v_halo = bool(s.get("halo", True))
        self.out_dir = Path(s.get("out_dir", str(OUT_DEFAULT)))
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel = threading.Event()
        self.removers: dict[str, Remover] = {}
        self.preview_cache: dict = {}
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1260x780")
        self.minsize(1040, 680)
        self.build()
        self.after(100, self.poll)

    # ------------------------------------------------------------ helpers
    def t(self, k, **kw) -> str:
        txt = T[self.lang].get(k, T["en"].get(k, k))
        if kw:
            txt = txt.format(**kw)
        return shape(txt, self.shaping)

    def disp(self, text: str) -> str:
        """User data (file names, paths): paragraph direction follows the UI."""
        return shape(text, self.shaping, "R" if self.rtl else "L")

    @property
    def rtl(self) -> bool:
        return self.lang == "ar"

    def font_family(self) -> str:
        """Segoe UI (Windows) covers Arabic and Latin. Elsewhere pick the
        first installed family; Xft falls back per glyph for the rest."""
        key = "ar" if self.rtl else "en"
        if key not in self._fam:
            import tkinter.font as tkfont
            have = set(tkfont.families(self))
            if sys.platform == "win32":
                prefs = ["Segoe UI", "Tahoma", "Arial"]
            elif sys.platform == "darwin":
                prefs = ["Geeza Pro", "SF Pro Text", "Helvetica Neue"] if self.rtl else ["SF Pro Text", "Helvetica Neue"]
            else:
                prefs = (["Noto Sans Arabic UI", "Noto Sans Arabic", "Noto Naskh Arabic", "DejaVu Sans"] if self.rtl
                         else ["Noto Sans", "DejaVu Sans", "Liberation Sans"])
            self._fam[key] = next((f for f in prefs if f in have), "TkDefaultFont")
        return self._fam[key]

    def font(self, size=13, weight="normal"):
        return ctk.CTkFont(family=self.font_family(), size=size, weight=weight)

    def persist(self):
        self.cfg = load_cfg()
        self.cfg["lang"] = self.lang
        self.cfg["bg_remover"] = {
            "model": self.v_model, "format": self.v_format, "bg": self.v_bg,
            "color": list(self.v_color), "crop": self.v_crop, "preset": self.v_preset,
            "edges": self.v_edges, "halo": self.v_halo, "out_dir": str(self.out_dir)}
        try:
            CFG.parent.mkdir(parents=True, exist_ok=True)
            CFG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def side(self):          # first element of a row
        return "right" if self.rtl else "left"

    def oside(self):
        return "left" if self.rtl else "right"

    def anchor(self):
        return "e" if self.rtl else "w"

    # ------------------------------------------------------------ layout
    def build(self):
        for w in self.winfo_children():
            w.destroy()
        busy = self.worker is not None and self.worker.is_alive()
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=18, pady=(14, 4))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side=self.side())
        ctk.CTkLabel(titles, text=self.t("title"), font=self.font(22, "bold"), anchor=self.anchor()).pack(anchor=self.anchor())
        ctk.CTkLabel(titles, text=self.t("tagline"), text_color="gray", font=self.font(12), anchor=self.anchor()).pack(anchor=self.anchor())
        ctk.CTkButton(head, text=self.t("lang"), width=70, font=self.font(13), command=self.toggle_lang).pack(side=self.oside())

        files_col, settings_col = (2, 0) if self.rtl else (0, 2)
        self.build_files(files_col)
        self.build_preview(1)
        self.build_settings(settings_col)
        self.build_footer()
        self.refresh_list()
        self.update_model_note()
        self.set_busy(busy)

    def build_files(self, col):
        f = ctk.CTkFrame(self, width=300)
        f.grid(row=1, column=col, sticky="nsew", padx=10, pady=8)
        f.grid_propagate(False)
        f.pack_propagate(False)
        ctk.CTkLabel(f, text=self.t("files"), font=self.font(15, "bold")).pack(anchor=self.anchor(), padx=12, pady=(10, 2))
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=8)
        self.b_add = ctk.CTkButton(row, text=self.t("add"), width=128, font=self.font(13), command=self.add_files)
        self.b_add.pack(side=self.side(), padx=4, pady=4)
        self.b_dir = ctk.CTkButton(row, text=self.t("add_dir"), width=128, font=self.font(13), command=self.add_dir)
        self.b_dir.pack(side=self.side(), padx=4, pady=4)
        hint = self.t("drop") if self.dnd_ok else self.t("drop_off")
        self.drop_lbl = ctk.CTkLabel(f, text=hint, text_color="#60a5fa", font=self.font(12))
        self.drop_lbl.pack(pady=(4, 2))
        row2 = ctk.CTkFrame(f, fg_color="transparent")
        row2.pack(side="bottom", fill="x", padx=8, pady=(2, 8))   # before the list so it never gets clipped
        lf = tk.Frame(f, bg="#1e1e1e")
        lf.pack(fill="both", expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(lf)
        self.lb = tk.Listbox(lf, bg="#1e1e1e", fg="#e5e7eb", selectbackground="#1f6aa5", highlightthickness=0,
                             borderwidth=0, activestyle="none", selectmode="extended",
                             font=(self.font(12).cget("family"), 11), yscrollcommand=sb.set,
                             justify="right" if self.rtl else "left")
        sb.config(command=self.lb.yview)
        sb.pack(side=self.oside(), fill="y")
        self.lb.pack(side=self.side(), fill="both", expand=True)
        self.lb.bind("<<ListboxSelect>>", lambda e: self.on_select())
        self.lb.bind("<Double-Button-1>", lambda e: self.preview_selected())
        self.lb.bind("<Delete>", lambda e: self.remove_sel())
        self.count_lbl = ctk.CTkLabel(row2, text="", text_color="gray", font=self.font(12))
        self.count_lbl.pack(side=self.side(), padx=4)
        self.b_clear = ctk.CTkButton(row2, text=self.t("clear"), width=80, fg_color="#1e293b", font=self.font(12), command=self.clear)
        self.b_clear.pack(side=self.oside(), padx=3)
        self.b_rm = ctk.CTkButton(row2, text=self.t("remove"), width=70, fg_color="#1e293b", font=self.font(12), command=self.remove_sel)
        self.b_rm.pack(side=self.oside(), padx=3)
        if self.dnd_ok:
            for w in (f, self.lb, self.drop_lbl):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self.on_drop)
                except Exception:
                    pass

    def build_preview(self, col):
        p = ctk.CTkFrame(self)
        p.grid(row=1, column=col, sticky="nsew", padx=4, pady=8)
        p.grid_columnconfigure((0, 1), weight=1)
        p.grid_rowconfigure(1, weight=1)
        a, b = (1, 0) if self.rtl else (0, 1)      # "before" comes first in reading order
        ctk.CTkLabel(p, text=self.t("before"), font=self.font(14, "bold")).grid(row=0, column=a, pady=(10, 0))
        ctk.CTkLabel(p, text=self.t("after"), font=self.font(14, "bold")).grid(row=0, column=b, pady=(10, 0))
        self.pv_src = {}                      # label -> image or fill colour, re-rendered on resize
        self.pv_box = getattr(self, "pv_box", 240)
        self.pv_before = ctk.CTkLabel(p, text="")
        self.pv_before.grid(row=1, column=a, padx=8, pady=8)
        self.pv_after = ctk.CTkLabel(p, text="")
        self.pv_after.grid(row=1, column=b, padx=8, pady=8)
        self.pv_info = ctk.CTkLabel(p, text=self.t("preview_hint"), text_color="gray", font=self.font(12), wraplength=640)
        self.pv_info.grid(row=2, column=0, columnspan=2)
        self.b_prev = ctk.CTkButton(p, text=self.t("preview"), font=self.font(13), command=self.preview_selected)
        self.b_prev.grid(row=3, column=0, columnspan=2, pady=(4, 12))
        self.pv_frame = p
        self.blank(self.pv_before)
        self.blank(self.pv_after)
        p.bind("<Configure>", self.on_pv_resize)

    def labeled(self, parent, key):
        ctk.CTkLabel(parent, text=self.t(key), font=self.font(13, "bold"), anchor=self.anchor()).pack(
            fill="x", padx=12, pady=(10, 2))

    def option(self, parent, keys, prefix, current, cmd, width=250):
        labels = [self.t(prefix + k) for k in keys]
        m = ctk.CTkOptionMenu(parent, values=labels, width=width, font=self.font(12),
                              dropdown_font=self.font(12), anchor=self.anchor(),
                              command=lambda lab: cmd(keys[labels.index(lab)]))
        m.set(labels[keys.index(current)])
        m.pack(anchor=self.anchor(), padx=12)
        return m

    def build_settings(self, col):
        s = ctk.CTkScrollableFrame(self, width=290, label_text=self.disp(T[self.lang]["settings"]),
                                   label_font=self.font(15, "bold"))
        s.grid(row=1, column=col, sticky="nsew", padx=10, pady=8)
        self.labeled(s, "model")
        self.m_model = self.option(s, MODEL_ORDER, "m_", self.v_model, self.set_model, 270)
        self.model_note = ctk.CTkLabel(s, text="", text_color="gray", font=self.font(11), anchor=self.anchor())
        self.model_note.pack(fill="x", padx=12)

        self.labeled(s, "format")
        fm = ctk.CTkSegmentedButton(s, values=["PNG", "JPG", "WebP"], font=self.font(12),
                                    command=lambda v: self.set_format(v.lower()))
        fm.set({"png": "PNG", "jpg": "JPG", "webp": "WebP"}[self.v_format])
        fm.pack(anchor=self.anchor(), padx=12)
        self.fmt_note = ctk.CTkLabel(s, text="", text_color="#fbbf24", font=self.font(11), wraplength=260,
                                     justify="right" if self.rtl else "left", anchor=self.anchor())
        self.fmt_anchor = fm

        self.labeled(s, "bg")
        row = ctk.CTkFrame(s, fg_color="transparent")
        row.pack(fill="x", padx=12)
        labels = [self.t("bg_" + k) for k in BG_ORDER]
        self.m_bg = ctk.CTkOptionMenu(row, values=labels, width=170, font=self.font(12), dropdown_font=self.font(12),
                                      anchor=self.anchor(), command=lambda lab: self.set_bg(BG_ORDER[labels.index(lab)]))
        self.m_bg.set(labels[BG_ORDER.index(self.v_bg)])
        self.m_bg.pack(side=self.side())
        self.swatch = ctk.CTkButton(row, text=self.t("pick"), width=80, font=self.font(12), command=self.pick_color,
                                    fg_color="#%02x%02x%02x" % self.v_color, text_color=self.contrast(self.v_color),
                                    border_width=1, border_color="#64748b")
        self.swatch.pack(side=self.side(), padx=6)

        self.labeled(s, "size")
        self.option(s, PRESET_ORDER, "p_", self.v_preset, self.set_preset, 270)
        self.sw_crop = ctk.CTkSwitch(s, text=self.t("crop"), font=self.font(12), command=self.set_crop)
        self.sw_crop.pack(anchor=self.anchor(), padx=12, pady=(8, 0))
        if self.v_crop:
            self.sw_crop.select()

        self.labeled(s, "edges")
        self.option(s, EDGE_ORDER, "e_", self.v_edges, self.set_edges, 270)
        self.sw_halo = ctk.CTkSwitch(s, text=self.t("halo"), font=self.font(12), command=self.set_halo)
        self.sw_halo.pack(anchor=self.anchor(), padx=12, pady=(8, 0))
        if self.v_halo:
            self.sw_halo.select()

        self.labeled(s, "out")
        self.out_lbl = ctk.CTkLabel(s, text=str(self.out_dir), font=self.font(11), text_color="#93c5fd",
                                    wraplength=260, anchor=self.anchor(), justify="right" if self.rtl else "left")
        self.out_lbl.pack(fill="x", padx=12)
        ctk.CTkButton(s, text=self.t("browse"), width=100, font=self.font(12), fg_color="#1e293b",
                      command=self.pick_out).pack(anchor=self.anchor(), padx=12, pady=(4, 12))
        self.update_fmt_note()

    def build_footer(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid(row=2, column=0, columnspan=3, sticky="ew", padx=18, pady=(4, 14))
        f.grid_columnconfigure(0, weight=1)
        self.pbar = ctk.CTkProgressBar(f, height=12)
        self.pbar.set(0)
        self.pbar.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        self.status = ctk.CTkLabel(f, text=self.t("ready"), text_color="gray", font=self.font(12),
                                   anchor=self.anchor(), wraplength=620,
                                   justify="right" if self.rtl else "left")
        btns = ctk.CTkFrame(f, fg_color="transparent")
        self.b_start = ctk.CTkButton(btns, text=self.t("start"), width=190, height=40, font=self.font(14, "bold"),
                                     fg_color="#16a34a", hover_color="#15803d", command=self.start)
        self.b_cancel = ctk.CTkButton(btns, text=self.t("cancel"), width=100, height=40, font=self.font(13),
                                      fg_color="#dc2626", hover_color="#b91c1c", command=self.do_cancel)
        self.b_open = ctk.CTkButton(btns, text=self.t("open"), width=110, height=40, font=self.font(13),
                                    fg_color="#1e293b", command=self.open_out)
        for b in (self.b_start, self.b_cancel, self.b_open):
            b.pack(side=self.oside() if self.rtl else "left", padx=5)
        if self.rtl:
            btns.grid(row=1, column=0, sticky="w")
            self.status.grid(row=1, column=1, sticky="e", padx=8)
            f.grid_columnconfigure(0, weight=0)
            f.grid_columnconfigure(1, weight=1)
        else:
            self.status.grid(row=1, column=0, sticky="w", padx=8)
            btns.grid(row=1, column=1, sticky="e")

    # ------------------------------------------------------------ settings
    @staticmethod
    def contrast(c):
        return "#000000" if (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) > 140 else "#ffffff"

    def update_model_note(self):
        spec = MODELS[self.v_model]
        txt = self.t("installed") if find_model(self.v_model) else self.t("will_dl", mb=spec.size_mb)
        self.model_note.configure(text=txt + f"  ·  {spec.license.split(' ')[0]}")

    def update_fmt_note(self):
        show = self.v_format == "jpg" and self.v_bg == "none"
        self.fmt_note.configure(text=self.t("jpg_note") if show else "")
        if show:
            self.fmt_note.pack(fill="x", padx=12, after=self.fmt_anchor)
        else:
            self.fmt_note.pack_forget()

    def set_model(self, k):
        self.v_model = k
        self.update_model_note()
        self.persist()

    def set_format(self, v):
        self.v_format = v
        self.update_fmt_note()
        self.persist()

    def set_bg(self, k):
        self.v_bg = k
        if k == "custom":
            self.pick_color()
        elif k == "white":
            self.v_color = (255, 255, 255)
            self.swatch.configure(fg_color="#ffffff", text_color="#000000")
        self.update_fmt_note()
        self.persist()

    def pick_color(self):
        res = colorchooser.askcolor(color="#%02x%02x%02x" % self.v_color, parent=self)
        if res and res[0]:
            self.v_color = tuple(int(v) for v in res[0])
            self.swatch.configure(fg_color="#%02x%02x%02x" % self.v_color, text_color=self.contrast(self.v_color))
            if self.v_bg == "none":
                self.v_bg = "custom"
                self.m_bg.set(self.t("bg_custom"))
            self.update_fmt_note()
            self.persist()

    def set_preset(self, k):
        self.v_preset = k
        self.persist()

    def set_crop(self):
        self.v_crop = bool(self.sw_crop.get())
        self.persist()

    def set_edges(self, k):
        self.v_edges = k
        self.persist()

    def set_halo(self):
        self.v_halo = bool(self.sw_halo.get())
        self.persist()

    def pick_out(self):
        d = filedialog.askdirectory(initialdir=str(self.out_dir), parent=self)
        if d:
            self.out_dir = Path(d)
            self.out_lbl.configure(text=str(self.out_dir))
            self.persist()

    def options(self) -> Options:
        bg = None if self.v_bg == "none" else ((255, 255, 255) if self.v_bg == "white" else self.v_color)
        return Options(model=self.v_model, out_format=self.v_format, bg_color=bg, crop=self.v_crop,
                       preset=self.v_preset, refine=self.v_edges == "refine",
                       matting=self.v_edges == "matting", decontaminate=self.v_halo)

    def toggle_lang(self):
        self.lang = "ar" if self.lang == "en" else "en"
        self.persist()
        self.build()

    # ------------------------------------------------------------ files
    def add_paths(self, paths):
        new = collect_files(paths, skip_dir=self.out_dir)
        have = {os.path.normcase(str(p.resolve())) for p in self.files}
        for p in new:
            k = os.path.normcase(str(p.resolve()))
            if k not in have:
                have.add(k)
                self.files.append(p)
        self.refresh_list()
        if new and not self.lb.curselection():
            self.lb.selection_set(0)
            self.on_select()

    def add_files(self):
        exts = " ".join("*" + e for e in sorted(SUPPORTED_EXT))
        paths = filedialog.askopenfilenames(parent=self, filetypes=[("Images", exts), ("All files", "*.*")])
        if paths:
            self.add_paths(paths)

    def add_dir(self):
        d = filedialog.askdirectory(parent=self)
        if d:
            self.add_paths([d])

    def on_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        self.add_paths([p for p in paths if p])
        return getattr(event, "action", "copy")

    def remove_sel(self):
        if self.busy():
            return
        for i in sorted(self.lb.curselection(), reverse=True):
            del self.files[i]
        self.refresh_list()

    def clear(self):
        if self.busy():
            return
        self.files.clear()
        self.status_of.clear()
        self.preview_cache.clear()
        self.refresh_list()

    def row_text(self, p: Path) -> str:
        st = self.status_of.get(str(p))
        mark = "" if st is None else ("✓ " if st[0] == "ok" else "✗ ")
        return self.disp(mark + p.name) if not self.rtl else self.disp(p.name + (" " + mark.strip() if mark else ""))

    def refresh_list(self):
        sel = self.lb.curselection()
        self.lb.delete(0, "end")
        for i, p in enumerate(self.files):
            self.lb.insert("end", self.row_text(p))
            st = self.status_of.get(str(p))
            if st:
                self.lb.itemconfig(i, fg="#4ade80" if st[0] == "ok" else "#f87171")
        for i in sel:
            if i < len(self.files):
                self.lb.selection_set(i)
        self.count_lbl.configure(text=self.t("count1") if len(self.files) == 1 and "count1" in T[self.lang]
                               else self.t("count", n=len(self.files)))

    def selected(self) -> Path | None:
        sel = self.lb.curselection()
        return self.files[sel[0]] if sel else None

    # ------------------------------------------------------------ preview
    def on_pv_resize(self, event=None):
        sc = self._get_window_scaling() if hasattr(self, "_get_window_scaling") else 1.0
        w = self.pv_frame.winfo_width() / sc
        h = self.pv_frame.winfo_height() / sc
        box = int(max(120, min((w - 48) / 2, h - 140)))
        if abs(box - self.pv_box) >= 6:
            self.pv_box = box
            for lab, src in list(self.pv_src.items()):
                self.render(lab, src)

    def render(self, label, src):
        b = self.pv_box
        if isinstance(src, Image.Image):
            im = fit_preview(src, b)
        else:
            im = Image.new("RGB", (b, b), src)
        label.configure(image=ctk.CTkImage(im, size=im.size))

    def show(self, label, img):
        img = img.copy()
        img.thumbnail((900, 900), Image.LANCZOS)    # keep a small copy for re-rendering on resize
        self.pv_src[label] = img
        self.render(label, img)

    def blank(self, label, colour=(40, 40, 40)):
        self.pv_src[label] = colour
        self.render(label, colour)

    def on_select(self):
        p = self.selected()
        if not p:
            return
        try:
            rgb, alpha, _ = load_image(p)
            if alpha is not None:
                rgb = rgb.convert("RGBA")
                rgb.putalpha(alpha)
            self.show(self.pv_before, rgb)
        except Exception as e:
            self.blank(self.pv_before, (60, 20, 20))
        st = self.status_of.get(str(p))
        if st and st[0] == "ok" and Path(st[1]).exists():
            try:
                with Image.open(st[1]) as im:
                    im.load()
                    self.show(self.pv_after, im)
                self.pv_info.configure(text=self.disp(Path(st[1]).name), text_color="#4ade80")
            except Exception:
                pass
        elif st and st[0] == "err":
            self.pv_info.configure(text=self.disp(p.name + " — ") + st[1], text_color="#f87171")
            self.blank_after()
        else:
            self.blank_after()
            self.pv_info.configure(text=self.t("preview_hint"), text_color="gray")

    def blank_after(self):
        self.blank(self.pv_after)

    def preview_selected(self):
        p = self.selected()
        if not p:
            messagebox.showinfo(APP_NAME, self.t("need"), parent=self)
            return
        if self.busy() or not self.check_ram():
            return
        self.cancel.clear()
        self.pv_info.configure(text=self.t("previewing"), text_color="gray")
        self.set_busy(True)
        opts = self.options()
        self.worker = threading.Thread(target=self.preview_job, args=(p, opts), daemon=True)
        self.worker.start()

    def get_remover(self, key):
        if key not in self.removers:
            def prog(done, total):
                if total:
                    self.q.put(("dl", done, total))
            self.removers.clear()      # keep only one model in memory
            self.removers[key] = Remover(key, progress=prog, cancel=self.cancel)
            self.q.put(("model_ready",))
        return self.removers[key]

    def preview_job(self, p, opts):
        try:
            r = self.get_remover(opts.model)
            rgb, alpha, _ = load_image(p)
            res = finish(make_cutout(rgb, alpha, r, opts), opts)
            self.q.put(("preview", p, res.image, res.warnings))
        except ModelError as e:
            self.q.put(("model_error", e))
        except Exception as e:
            code = getattr(e, "code", "internal")
            self.q.put(("preview_err", p, code, str(e)))
        finally:
            self.q.put(("idle",))

    # ------------------------------------------------------------ batch
    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def set_busy(self, b: bool):
        st = "disabled" if b else "normal"
        for w in (getattr(self, n, None) for n in ("b_start", "b_prev", "b_add", "b_dir", "b_rm", "b_clear")):
            if w is not None:
                w.configure(state=st)
        if getattr(self, "b_cancel", None) is not None:
            self.b_cancel.configure(state="normal" if b else "disabled")

    def check_ram(self) -> bool:
        rw = ram_warning(self.v_model)
        if rw:
            return messagebox.askyesno(APP_NAME, self.t("ram_warn", need=rw[0], free=rw[1]), parent=self)
        return True

    def start(self):
        if self.busy():
            return
        if not self.files:
            messagebox.showinfo(APP_NAME, self.t("need"), parent=self)
            return
        if not self.check_ram():
            return
        self.cancel.clear()
        self.set_busy(True)
        self.pbar.set(0)
        opts = self.options()
        files = list(self.files)
        self.t0 = time.perf_counter()
        self.status.configure(text=self.t("loading_model"), text_color="gray")
        self.worker = threading.Thread(target=self.batch_job, args=(files, opts, self.out_dir), daemon=True)
        self.worker.start()

    def batch_job(self, files, opts, out_dir):
        try:
            r = self.get_remover(opts.model)
            def prog(i, n, res):
                self.q.put(("item", i, n, res))
            res = run_batch(files, out_dir, opts, r, prog, self.cancel)
            self.q.put(("batch_done", res, len(files)))
        except ModelError as e:
            self.q.put(("model_error", e))
        except Exception as e:
            self.q.put(("fatal", f"{type(e).__name__}: {e}"))
        finally:
            self.q.put(("idle",))

    def do_cancel(self):
        if self.busy():
            self.cancel.set()
            self.status.configure(text=self.t("cancelling"), text_color="#fbbf24")

    def err_text(self, code, extra=""):
        key = "e_" + code
        if key in T["en"]:
            return self.t(key, dir=str(cache_dir()), path=extra)
        return self.disp(extra) or code

    # ------------------------------------------------------------ queue
    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                self.handle(msg)
        except queue.Empty:
            pass
        self.after(80, self.poll)

    def handle(self, msg):
        kind = msg[0]
        if kind == "dl":
            _, done, total = msg
            self.pbar.set(done / total)
            self.status.configure(text=self.t("downloading", p=done * 100 // total, mb=total // 1048576), text_color="#60a5fa")
        elif kind == "model_ready":
            self.update_model_note()
            self.pbar.set(0)
        elif kind == "item":
            _, i, n, r = msg
            self.pbar.set(i / n)
            if r.ok:
                self.status_of[str(r.src)] = ("ok", str(r.out))
            else:
                self.status_of[str(r.src)] = ("err", self.err_text(r.error_code, r.error))
            try:
                idx = self.files.index(r.src)
                self.lb.delete(idx)
                self.lb.insert(idx, self.row_text(r.src))
                self.lb.itemconfig(idx, fg="#4ade80" if r.ok else "#f87171")
                self.lb.see(idx)
            except ValueError:
                pass
            nxt = self.files[i].name if i < len(self.files) else ""
            self.status.configure(text=self.t("processing", i=min(i + 1, n), n=n, name=nxt) if i < n else "",
                                  text_color="gray")
            if self.selected() == r.src:
                self.on_select()
        elif kind == "batch_done":
            _, res, total = msg
            ok = sum(x.ok for x in res)
            bad = len(res) - ok
            sec = time.perf_counter() - self.t0
            if self.cancel.is_set() and len(res) < total:
                self.status.configure(text=self.t("cancelled", ok=ok), text_color="#fbbf24")
            else:
                self.status.configure(text=self.t("done", ok=ok, bad=bad, sec=sec),
                                      text_color="#4ade80" if bad == 0 else "#fbbf24")
            self.on_select()
        elif kind == "preview":
            _, p, img, warns = msg
            self.show(self.pv_after, img)
            info = self.disp(p.name)
            if warns:
                info += "  ·  " + ", ".join(self.t("w_" + w) for w in warns)
            self.pv_info.configure(text=info, text_color="#4ade80" if not warns else "#fbbf24")
        elif kind == "preview_err":
            _, p, code, text = msg
            self.blank_after()
            self.pv_info.configure(text=self.err_text(code, text), text_color="#f87171")
        elif kind == "model_error":
            e = msg[1]
            self.status.configure(text=self.err_text(e.code, str(e)), text_color="#f87171")
            self.pbar.set(0)
            if e.code != "cancelled":
                messagebox.showerror(self.t("err_title"), self.err_text(e.code, str(e)), parent=self)
        elif kind == "fatal":
            self.status.configure(text=msg[1], text_color="#f87171")
        elif kind == "idle":
            self.set_busy(False)

    def open_out(self):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(self.out_dir))  # noqa
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.out_dir)])
            else:
                subprocess.Popen(["xdg-open", str(self.out_dir)])
        except Exception:
            pass


def main():
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        from atlas_bg.selftest import run
        sys.exit(run(sys.argv[2:]))
    app = App()
    if len(sys.argv) > 1:
        app.add_paths(sys.argv[1:])
    app.mainloop()


if __name__ == "__main__":
    main()
