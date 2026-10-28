"""Core engine tests. Run: python -m pytest -q tests"""
import threading, http.server, socketserver, functools, re
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageDraw

from conftest import real
from atlas_bg import engine as E, batch as B, models as M
from atlas_bg.engine import Options, ImageLoadError


def product(path, size=(640, 480), mode="RGB", **save):
    """Synthetic 'product shot': dark rounded object on a light backdrop."""
    im = Image.new("RGB", size, (236, 236, 230))
    d = ImageDraw.Draw(im)
    w, h = size
    d.rounded_rectangle((w * .3, h * .25, w * .7, h * .8), radius=40, fill=(40, 60, 120))
    d.ellipse((w * .38, h * .3, w * .62, h * .5), fill=(200, 40, 40))
    if mode != "RGB":
        im = im.convert(mode)
    im.save(path, **save)
    return path


# ----------------------------------------------------------------- loading
def test_load_errors(tmp_path):
    (tmp_path / "t.jpg").write_text("hello, not an image")
    (tmp_path / "z.png").write_bytes(b"")
    good = product(tmp_path / "g.jpg")
    data = good.read_bytes()
    (tmp_path / "trunc.jpg").write_bytes(data[: len(data) // 3])
    cases = {"t.jpg": "not_image", "z.png": "not_image", "missing.png": "not_found", "trunc.jpg": "corrupt"}
    for name, code in cases.items():
        with pytest.raises(ImageLoadError) as ei:
            E.load_image(tmp_path / name)
        assert ei.value.code == code, name


def test_too_large_rejected_before_decode(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "MAX_PIXELS", 100 * 100)
    p = product(tmp_path / "big.png", size=(200, 200))
    with pytest.raises(ImageLoadError) as ei:
        E.load_image(p)
    assert ei.value.code == "too_large"


@pytest.mark.parametrize("orient,expect", [(1, (300, 200)), (3, (300, 200)), (6, (200, 300)), (8, (200, 300))])
def test_exif_orientation(tmp_path, orient, expect):
    im = Image.new("RGB", (300, 200), "white")
    ImageDraw.Draw(im).rectangle((0, 0, 60, 60), fill="red")
    ex = Image.Exif(); ex[0x0112] = orient
    p = tmp_path / f"o{orient}.jpg"; im.save(p, exif=ex)
    rgb, alpha, info = E.load_image(p)
    assert rgb.size == expect


@pytest.mark.parametrize("mode", ["L", "P", "CMYK", "LA", "RGBA", "I;16", "1"])
def test_modes_normalised(tmp_path, mode):
    src = Image.new("RGB", (64, 48), (200, 100, 50))
    im = src.convert("L").convert("I;16") if mode == "I;16" else src.convert(mode)
    p = tmp_path / ("m.tif" if mode == "CMYK" else "m.png")
    im.save(p)
    rgb, alpha, _ = E.load_image(p)
    assert rgb.mode == "RGB" and rgb.size == (64, 48)
    assert alpha is None or alpha.mode == "L"


def test_cmyk_jpeg_colour(tmp_path):
    Image.new("RGB", (32, 32), (220, 30, 30)).convert("CMYK").save(tmp_path / "c.jpg")
    rgb, _, _ = E.load_image(tmp_path / "c.jpg")
    r, g, b = rgb.getpixel((16, 16))
    assert r > 150 and g < 90 and b < 90       # still red, not inverted


def test_existing_alpha_kept(tmp_path):
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((20, 20, 80, 80), fill=(250, 0, 0, 255))
    im.save(tmp_path / "a.png")
    rgb, alpha, _ = E.load_image(tmp_path / "a.png")
    assert alpha is not None and alpha.getpixel((2, 2)) == 0 and alpha.getpixel((50, 50)) == 255


def test_opaque_alpha_dropped(tmp_path):
    Image.new("RGBA", (10, 10), (1, 2, 3, 255)).save(tmp_path / "o.png")
    assert E.load_image(tmp_path / "o.png")[1] is None


# ----------------------------------------------------------------- helpers
def test_parse_color():
    assert E.parse_color("white") == (255, 255, 255)
    assert E.parse_color("#00ff00") == (0, 255, 0)
    assert E.parse_color(None) is None
    with pytest.raises(Exception):
        E.parse_color("not-a-colour")


def test_box_mean_matches_naive():
    a = np.random.default_rng(0).random((37, 53)).astype(np.float32)
    r = 3
    pad = np.pad(a, r, mode="edge")
    naive = np.array([[pad[y:y + 2 * r + 1, x:x + 2 * r + 1].mean() for x in range(53)] for y in range(37)])
    got = E.box_mean(a, r)
    assert got.shape == a.shape
    assert np.abs(got[r:-r, r:-r] - naive[r:-r, r:-r]).max() < 1e-4


def test_jpg_forces_white_background():
    assert Options(out_format="jpg").effective_bg() == (255, 255, 255)
    assert Options(out_format="png").effective_bg() is None
    assert Options(out_format="jpg", bg_color=(1, 2, 3)).effective_bg() == (1, 2, 3)


# ----------------------------------------------------------------- pipeline
def test_png_has_alpha_and_same_size(tmp_path, remover):
    p = product(tmp_path / "p.jpg")
    res = E.process(p, remover, Options(model="u2netp"))
    im = Image.open(E.save(res, tmp_path / "o.png", Options()))
    assert im.mode == "RGBA" and im.size == (640, 480)
    a = np.asarray(im)[..., 3]
    assert a[5, 5] < 20, "corner background should be transparent"
    assert a[240, 320] > 235, "object centre should be opaque"


def test_jpg_white(tmp_path, remover):
    p = product(tmp_path / "p.jpg")
    opts = Options(model="u2netp", out_format="jpg")
    im = Image.open(E.save(E.process(p, remover, opts), tmp_path / "o.jpg", opts))
    assert im.format == "JPEG" and im.mode == "RGB"
    assert min(im.getpixel((3, 3))) > 245


def test_webp_alpha(tmp_path, remover):
    p = product(tmp_path / "p.jpg")
    opts = Options(model="u2netp", out_format="webp")
    im = Image.open(E.save(E.process(p, remover, opts), tmp_path / "o.webp", opts))
    assert im.format == "WEBP" and im.mode == "RGBA"


EXPECT = {"square1080": (1080, 1080), "square2000": (2000, 2000), "story1080x1920": (1080, 1920),
          "passport4x6": (472, 709), "passport35x45": (413, 531)}


@pytest.mark.parametrize("preset", [k for k in E.PRESETS if k != "none"])
def test_presets(tmp_path, remover, preset):
    p = product(tmp_path / "p.jpg", size=(1200, 900))
    opts = Options(model="u2netp", preset=preset, bg_color=(255, 255, 255))
    im = Image.open(E.save(E.process(p, remover, opts), tmp_path / "o.png", opts))
    if preset.startswith("max"):
        assert max(im.size) == int(preset[3:]) or max(im.size) <= 1200
        assert max(im.size) <= int(preset[3:])
    else:
        assert im.size == EXPECT[preset]
    if preset.startswith("passport"):
        assert round(im.info["dpi"][0]) == 300


def test_crop_to_subject(tmp_path, remover):
    p = product(tmp_path / "p.jpg")
    res = E.process(p, remover, Options(model="u2netp", crop=True))
    w, h = res.image.size
    assert 200 < w < 400 and 200 < h < 400            # object is ~256x264


def test_tiny_image(tmp_path, remover):
    Image.new("RGB", (1, 1), "gray").save(tmp_path / "one.png")
    res = E.process(tmp_path / "one.png", remover, Options(model="u2netp", crop=True))
    assert res.image.size == (1, 1)


def test_rotated_photo_output_upright(tmp_path, remover):
    im = Image.new("RGB", (400, 200), (240, 240, 240))
    ImageDraw.Draw(im).ellipse((150, 50, 250, 150), fill=(20, 20, 20))
    ex = Image.Exif(); ex[0x0112] = 6
    im.save(tmp_path / "r.jpg", exif=ex)
    res = E.process(tmp_path / "r.jpg", remover, Options(model="u2netp"))
    assert res.image.size == (200, 400)


def test_real_portrait_quality(isnet):
    """Real photo: face kept, background corner removed."""
    res = E.process(real("portrait_red_curly_hair.jpg"), isnet, Options())
    a = np.asarray(res.image)[..., 3].astype(float) / 255
    h, w = a.shape
    assert a[int(h * .55), w // 2] > .95
    assert a[:int(h * .05), :int(w * .05)].mean() < .2


# ----------------------------------------------------------------- batch
def test_collect_files(tmp_path):
    d = tmp_path / "in"; (d / "sub").mkdir(parents=True)
    product(d / "a.jpg"); product(d / "sub" / "b.PNG", format="PNG")
    (d / "notes.txt").write_text("x"); product(d / "a_nobg.png", format="PNG")
    assert sorted(f.name for f in B.collect_files([d])) == ["a.jpg", "b.PNG"]
    assert [f.name for f in B.collect_files([d], recursive=False)] == ["a.jpg"]
    assert len(B.collect_files([d / "notes.txt", d / "a.jpg", d / "a.jpg"])) == 2
    out = d / "out"; out.mkdir(); product(out / "c.jpg")
    assert "c.jpg" not in [f.name for f in B.collect_files([d], skip_dir=out)]


def test_batch_mixed_and_unique_names(tmp_path, remover):
    d = tmp_path / "in"; (d / "x").mkdir(parents=True)
    product(d / "same.jpg"); product(d / "x" / "same.jpg"); (d / "bad.jpg").write_text("nope")
    product(d / "صورة.jpg")
    files = B.collect_files([d / "same.jpg", d / "x" / "same.jpg", d / "bad.jpg", d / "صورة.jpg"])
    seen = []
    res = B.run_batch(files, tmp_path / "out", Options(model="u2netp"), remover,
                      progress=lambda i, n, r: seen.append((i, n)))
    assert [r.ok for r in res] == [True, True, False, True]
    assert res[2].error_code == "not_image"
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert names == sorted(["same_nobg (1).png", "same_nobg.png", "صورة_nobg.png"])
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]
    B.run_batch(files[:1], tmp_path / "out", Options(model="u2netp"), remover)
    assert (tmp_path / "out" / "same_nobg (2).png").exists()          # never overwrites
    assert not list((tmp_path / "out").glob("*.tmp"))


def test_batch_cancel(tmp_path, remover):
    files = [product(tmp_path / f"{i}.jpg") for i in range(5)]
    cancel = threading.Event()
    res = B.run_batch(files, tmp_path / "out", Options(model="u2netp"), remover,
                      progress=lambda i, n, r: cancel.set() if i == 2 else None, cancel=cancel)
    assert len(res) == 2 and all(r.ok for r in res)


def test_unwritable_output(tmp_path, remover):
    p = product(tmp_path / "p.jpg")
    blocker = tmp_path / "file_not_dir"; blocker.write_text("x")
    with pytest.raises(OSError):
        B.run_batch([p], blocker / "out", Options(model="u2netp"), remover)


# ----------------------------------------------------------------- models
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture
def server(tmp_path):
    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown(); srv.server_close()


def test_download_paths(tmp_path, monkeypatch, server):
    src = M.find_model("u2netp")
    if not src:
        pytest.skip("u2netp not available")
    cache = tmp_path / "cache"; monkeypatch.setenv("ATLAS_BG_MODELS", str(cache))
    (tmp_path / "good.onnx").write_bytes(Path(src).read_bytes())
    (tmp_path / "bad.onnx").write_bytes(b"0" * 1000)
    with pytest.raises(M.ModelDownloadError) as ei:
        M.download_model("u2netp", url="http://127.0.0.1:9/x.onnx", timeout=3)
    assert ei.value.code == "offline"
    with pytest.raises(M.ModelDownloadError) as ei:
        M.download_model("u2netp", url=server + "/bad.onnx")
    assert ei.value.code == "checksum" and not list(cache.iterdir())
    ev = threading.Event(); ev.set()
    with pytest.raises(M.ModelError):
        M.download_model("u2netp", url=server + "/good.onnx", cancel=ev)
    assert not list(cache.iterdir())
    prog = []
    p = M.download_model("u2netp", url=server + "/good.onnx", progress=lambda d, t: prog.append((d, t)))
    assert p.exists() and prog[-1][0] == prog[-1][1] == p.stat().st_size


def test_ensure_model_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_BG_MODELS", str(tmp_path))
    monkeypatch.setattr(M, "search_dirs", lambda: [tmp_path])
    with pytest.raises(M.ModelError):
        M.ensure_model("u2net", allow_download=False)
    with pytest.raises(M.ModelError) as ei:
        M.ensure_model("nope")
    assert ei.value.code == "unknown"


def test_bad_model_file(tmp_path):
    (tmp_path / "broken.onnx").write_bytes(b"garbage")
    with pytest.raises(M.ModelError) as ei:
        E.Remover("u2netp", model_path=tmp_path / "broken.onnx")
    assert ei.value.code == "bad_model"


def test_model_specs():
    for k, s in M.MODELS.items():
        assert s.key == k and s.url.startswith("https://") and len(s.md5) == 32
        assert "non-commercial" not in s.license.lower()


# ----------------------------------------------------------------- i18n / cli
def test_i18n_parity_and_placeholders():
    from atlas_bg.i18n import T, shape
    assert set(T["en"]) == set(T["ar"])
    for k in T["en"]:
        assert set(re.findall(r"{(\w+)", T["en"][k])) == set(re.findall(r"{(\w+)", T["ar"][k])), k
    assert shape("abc", True) == "abc"
    assert shape("مرحبا", False) == "مرحبا"


def test_cli(tmp_path, remover):
    from atlas_bg.cli import main
    product(tmp_path / "a.jpg"); (tmp_path / "b.jpg").write_text("x")
    rc = main([str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg"), "-o", str(tmp_path / "o"), "-m", "u2netp", "-f", "jpg"])
    assert rc == 1
    assert (tmp_path / "o" / "a_nobg.jpg").exists()
    assert main(["--list-models"]) == 0


def test_core_has_no_gui_imports():
    import sys, subprocess
    code = "import atlas_bg.engine, atlas_bg.batch, atlas_bg.cli, sys; print(any(m.split('.')[0] in ('tkinter','customtkinter') for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(Path(__file__).resolve().parent.parent)).stdout.strip()
    assert out == "False"
