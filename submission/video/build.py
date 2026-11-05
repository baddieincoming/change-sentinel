"""Narrated demo video from the deck slides and real output pages.

    <python with imageio-ffmpeg> submission/video/build.py

Narration uses macOS `say`; ffmpeg comes from the imageio-ffmpeg wheel.
"""

import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SLIDES = ROOT / "submission" / "deck" / "slides"
WORK = HERE / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
VOICE, RATE, FPS = "Aman", "172", 24
W, H = 1920, 1080


def slide(n):
    return SLIDES / f"slide-{n:02d}.png"


SCENES = json.loads((HERE / "scenes.json").read_text())


def run(*args):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


def duration(path: Path) -> float:
    out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = out.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def segment(i: int, scene: dict) -> Path:
    voice = WORK / f"{i:02d}.aiff"
    subprocess.run(["say", "-v", VOICE, "-r", RATE, "-o", str(voice), scene["say"]], check=True)
    d = round(duration(voice) + 1.2, 2)
    src = scene["image"]
    image = Path(src) if src.startswith("/") else (slide(int(src)) if src.isdigit() else ROOT / src)
    im = Image.open(image).convert("RGB")
    im = im.resize((W, round(im.height * W / im.width)), Image.LANCZOS)
    still = WORK / f"{i:02d}.png"
    im.save(still)
    if im.height > H:  # long page: hold, scroll to the end (or to `scroll_to`), hold
        travel = min(im.height - H, scene.get("scroll_to", im.height) - H)
        y = f"min(max(0\\,(t-1.2)/{d - 2.6})\\,1)*{travel}"
        vf = f"crop={W}:{H}:0:'{y}'"
    else:
        vf = f"scale={W}:{H}"
    vf += f",fade=t=in:st=0:d=0.35,fade=t=out:st={d - 0.35}:d=0.35,format=yuv420p"
    out = WORK / f"{i:02d}.mp4"
    run("-loop", "1", "-framerate", str(FPS), "-i", str(still), "-i", str(voice),
        "-filter_complex", f"[0:v]{vf}[v];[1:a]adelay=500|500,apad,aresample=48000[a]",
        "-map", "[v]", "-map", "[a]", "-t", str(d),
        "-c:v", "libx264", "-preset", "slow", "-tune", "stillimage", "-crf", "22", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-ac", "1", str(out))
    return out


def chrome_shot(page: Path, out: Path, height: int):
    """Screenshot at 1920 px wide, with empty space below the content trimmed off."""
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=8000",
                    f"--screenshot={out}", f"--window-size=1280,{height}", "--force-device-scale-factor=1.5",
                    page.as_uri()], check=True, capture_output=True)
    im = Image.open(out).convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((im.width - 1, im.height - 1)))
    box = ImageChops.difference(im, bg).getbbox()
    if box and box[3] + 60 < im.height:
        im.crop((0, 0, im.width, max(H, box[3] + 60))).save(out)


def terminal(log: Path, cmd: str):
    """A terminal frame built from the real run log (timestamps kept)."""
    lines = [ln for ln in log.read_text().splitlines() if " INFO sentinel." in ln]
    comp = [ln for ln in lines if "sentinel.composites" in ln]
    cases = [ln for ln in lines if "sentinel.pipeline: case " in ln]
    keep = [ln for ln in lines if "sentinel.composites" not in ln and "pipeline: case " not in ln]
    head = [ln for ln in keep if "detect" not in ln and "sites (" not in ln and "top case" not in ln]
    tail = [ln for ln in keep if ln not in head]
    shown = head + comp[:3] + ["…"] + comp[-2:] + tail[:1] + cases[:2] + ["…"] + tail[1:]
    shown = [ln.replace(f"{ROOT}/", "") for ln in shown]
    esc = [ln.replace("&", "&amp;").replace("<", "&lt;").split(" INFO ", 1) for ln in shown]
    body = "\n".join(f'<span class="t">{p[0]}</span> {p[1]}' if len(p) == 2 else f'<span class="t">{p[0]}</span>'
                     for p in esc)
    page = WORK / "terminal.html"
    page.write_text(f"""<!doctype html><meta charset="utf-8"><style>
      body {{ margin:0; background:#161a16; min-height:720px; display:flex; align-items:center; }}
      .win {{ flex:1; margin:0 48px; background:#0f120f; border-radius:14px; border:1px solid #2f352f; overflow:hidden; }}
      .bar {{ height:34px; background:#232823; display:flex; gap:8px; align-items:center; padding-left:14px; }}
      .bar i {{ width:12px; height:12px; border-radius:50%; background:#4a504a; display:block; }}
      pre {{ margin:0; padding:18px 22px 22px; color:#dedcd4; font:14px/1.62 Menlo, monospace; white-space:pre-wrap; }}
      .p {{ color:#e7a35a; }} .t {{ color:#77756e; }}
    </style><div class="win"><div class="bar"><i></i><i></i><i></i></div>
    <pre><span class="p">$</span> {cmd}\n{body}</pre></div>""")
    chrome_shot(page, WORK / "terminal.png", 720)
    im = Image.open(WORK / "terminal.png")
    im.crop((0, 0, im.width, min(im.height, H))).save(WORK / "terminal.png")


def main():
    WORK.mkdir(exist_ok=True)
    run_dir = ROOT / "output" / "nuh-subset"
    terminal(ROOT / "logs" / "subset-rebuild.log",
             ".venv/bin/python -m sentinel config/nuh.yaml --subset 76.86,27.70,77.00,27.86 --top 8")
    chrome_shot(run_dir / "index.html", WORK / "index_page.png", 2400)
    featured = (ROOT / "submission" / "deck" / "featured.txt").read_text().strip()
    chrome_shot(run_dir / "cases" / featured / "case.html", WORK / "case_page.png", 3200)
    parts = [segment(i, s) for i, s in enumerate(SCENES)]
    (WORK / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    out = ROOT / "submission" / "ChangeSentinel_Demo.mp4"
    run("-f", "concat", "-safe", "0", "-i", str(WORK / "list.txt"), "-c", "copy", "-movflags", "+faststart", str(out))
    print(out, f"{out.stat().st_size / 1e6:.1f} MB, {duration(out):.0f} s")


if __name__ == "__main__":
    main()
