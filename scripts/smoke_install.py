"""Verify a built wheel using the complete generated-media README workflow."""

import json
import os
import shutil
import subprocess
import tempfile
import venv
import wave
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheels = list((root / "dist").glob("*.whl"))
if len(wheels) != 1:
    raise SystemExit("Build exactly one wheel first.")
with tempfile.TemporaryDirectory(prefix="playlist-relocate-smoke-") as folder:
    work = Path(folder)
    venv.EnvBuilder(with_pip=True).create(work / "env")
    binary = work / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    subprocess.run(
        [str(binary), "-m", "pip", "install", str(wheels[0])], cwd=work, env=env, check=True
    )
    shutil.copyfile(root / "examples" / "make_demo.py", work / "make_demo.py")
    subprocess.run([str(binary), "make_demo.py"], cwd=work, env=env, check=True)
    args = [
        str(binary),
        "-m",
        "playlist_relocate",
        "playlist-demo/old.m3u8",
        "--map",
        "playlist-demo/mounts.json",
        "--output",
        "playlist-demo/moved.m3u8",
        "--json",
    ]
    for flags, status in [([], "ready"), (["--write"], "written")]:
        run = subprocess.run([*args, *flags], cwd=work, env=env, capture_output=True, text=True)
        if run.returncode != 0 or json.loads(run.stdout)["status"] != status:
            raise SystemExit(f"Demo failed: {run.returncode} {run.stderr} {run.stdout}")
        if status == "ready" and (work / "playlist-demo/moved.m3u8").exists():
            raise SystemExit("Preview wrote output")
    playlist = work / "playlist-demo/moved.m3u8"
    media = playlist.parent / playlist.read_text(encoding="utf-8").splitlines()[-1]
    with wave.open(str(media)) as audio:
        if audio.getnframes() != 800:
            raise SystemExit("Relocated playlist did not resolve to the intended WAV")
    subprocess.run(
        [str(binary), "-m", "pip", "uninstall", "-y", "playlist-relocate"],
        cwd=work,
        env=env,
        check=True,
    )
print("Isolated install, preview, atomic write, resolved WAV and uninstall: PASS")
