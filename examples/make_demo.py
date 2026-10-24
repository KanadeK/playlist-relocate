"""Create a fresh, synthetic library and foreign-path playlist for the README."""

import json
import struct
import wave
from pathlib import Path

root = Path("playlist-demo")
root.mkdir(exist_ok=False)
library = root / "library" / "Artist"
library.mkdir(parents=True)
with wave.open(str(library / "Tone.wav"), "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(8000)
    # A deliberately synthetic square wave, 0.1 seconds long.
    audio.writeframes(
        b"".join(struct.pack("<h", 1000 if i % 20 < 10 else -1000) for i in range(800))
    )
(root / "old.m3u8").write_text(
    "#EXTM3U\n#EXTINF:0,Synthetic demo tone\nM:\\Music\\Artist\\Tone.wav\n", encoding="utf-8"
)
(root / "mounts.json").write_text(
    json.dumps(
        {
            "version": 1,
            "source_style": "windows",
            "mappings": [{"from": "M:\\Music", "to": "library"}],
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("Created playlist-demo with a synthetic 0.1-second WAV, playlist and mount map.")
