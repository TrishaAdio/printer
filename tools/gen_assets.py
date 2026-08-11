"""Generate every binary asset the app ships: sound effects, grain, icon.

Everything is synthesised here rather than sourced from a library, so there is
nothing to license and the results are reproducible: the noise is seeded, so
running this twice produces identical files.

Run: python tools/gen_assets.py
"""

from __future__ import annotations

import math
import random
import struct
import sys
import wave
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "app" / "assets"
SOUNDS = ASSETS / "sounds"
IMAGES = ASSETS / "images"

RATE = 44100

# --------------------------------------------------------------------------- #
# A very small synthesis toolkit. Samples are plain float lists in -1..1.
# --------------------------------------------------------------------------- #


def silence(duration: float) -> list[float]:
    return [0.0] * int(RATE * duration)


def sine(freq: float, duration: float, phase: float = 0.0) -> list[float]:
    count = int(RATE * duration)
    step = 2.0 * math.pi * freq / RATE
    return [math.sin(phase + step * i) for i in range(count)]


def sweep(f0: float, f1: float, duration: float, curve: float = 1.0) -> list[float]:
    """Sine with an exponential-ish frequency glide from f0 to f1."""
    count = max(1, int(RATE * duration))
    out: list[float] = []
    phase = 0.0
    for i in range(count):
        t = (i / count) ** curve
        freq = f0 * (1.0 - t) + f1 * t
        phase += 2.0 * math.pi * freq / RATE
        out.append(math.sin(phase))
    return out


def noise(duration: float, rng: random.Random) -> list[float]:
    return [rng.uniform(-1.0, 1.0) for _ in range(int(RATE * duration))]


def envelope(
    samples: Sequence[float],
    attack: float = 0.005,
    decay: float = 0.2,
    sustain: float = 0.0,
    release: float = 0.05,
    peak: float = 1.0,
) -> list[float]:
    """Straightforward ADSR shaping, lengths in seconds."""
    count = len(samples)
    attack_n = max(1, int(RATE * attack))
    decay_n = max(1, int(RATE * decay))
    release_n = max(1, int(RATE * release))
    sustain_n = max(0, count - attack_n - decay_n - release_n)

    out: list[float] = []
    for i, value in enumerate(samples):
        if i < attack_n:
            gain = (i / attack_n) ** 0.7
        elif i < attack_n + decay_n:
            t = (i - attack_n) / decay_n
            gain = 1.0 - (1.0 - sustain) * t
        elif i < attack_n + decay_n + sustain_n:
            gain = sustain
        else:
            t = min(1.0, (i - attack_n - decay_n - sustain_n) / release_n)
            gain = sustain * (1.0 - t)
        out.append(value * gain * peak)
    return out


def decay_env(samples: Sequence[float], half_life: float, peak: float = 1.0) -> list[float]:
    """Percussive exponential decay, which is what a struck body actually does."""
    k = math.log(2.0) / max(1e-4, half_life)
    return [
        value * peak * math.exp(-k * (i / RATE)) for i, value in enumerate(samples)
    ]


def mix(*tracks: Sequence[float]) -> list[float]:
    length = max((len(t) for t in tracks), default=0)
    out = [0.0] * length
    for track in tracks:
        for i, value in enumerate(track):
            out[i] += value
    return out


def at(offset: float, samples: Sequence[float], length: float = 0.0) -> list[float]:
    """Place a sound at a time offset inside a buffer."""
    start = int(RATE * offset)
    total = max(start + len(samples), int(RATE * length))
    out = [0.0] * total
    for i, value in enumerate(samples):
        out[start + i] = value
    return out


def gain(samples: Sequence[float], amount: float) -> list[float]:
    return [value * amount for value in samples]


def saturate(samples: Sequence[float], drive: float = 1.5) -> list[float]:
    """Soft clip. Adds body without the crunch of hard clipping."""
    return [math.tanh(value * drive) / math.tanh(drive) for value in samples]


def lowpass(samples: Sequence[float], cutoff: float) -> list[float]:
    """One pole low pass, plenty for taking the edge off noise."""
    if not samples:
        return []
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / RATE)
    out = [samples[0]]
    for value in samples[1:]:
        out.append(out[-1] + alpha * (value - out[-1]))
    return out


def highpass(samples: Sequence[float], cutoff: float) -> list[float]:
    low = lowpass(samples, cutoff)
    return [value - low[i] for i, value in enumerate(samples)]


def reverb(samples: Sequence[float], amount: float = 0.3, size: float = 0.09) -> list[float]:
    """Cheap multi tap feedback delay. Enough to imply a room."""
    if amount <= 0:
        return list(samples)
    tail = int(RATE * 1.2)
    out = list(samples) + [0.0] * tail
    for _index, (delay, level) in enumerate(
        ((size, 0.42), (size * 1.7, 0.31), (size * 2.6, 0.22), (size * 3.9, 0.14))
    ):
        offset = int(RATE * delay)
        feedback = level * amount
        for i in range(offset, len(out)):
            out[i] += out[i - offset] * feedback * 0.55
    return out


def trim_tail(samples: Sequence[float], threshold: float = 0.0015) -> list[float]:
    """Cut trailing near silence.

    The reverb helper always appends a fixed tail, which leaves short interface
    sounds several times longer than the part anyone hears. Overlapping playback
    then sounds muddy, so the dead air goes.
    """
    end = len(samples)
    while end > 1 and abs(samples[end - 1]) < threshold:
        end -= 1
    return list(samples[:end])


def normalise(samples: Sequence[float], target: float = 0.89) -> list[float]:
    peak = max((abs(v) for v in samples), default=0.0)
    if peak <= 1e-9:
        return list(samples)
    factor = target / peak
    return [value * factor for value in samples]


def fade_edges(samples: Sequence[float], ms: float = 4.0) -> list[float]:
    """Always fade in and out a little; a hard edge is an audible click."""
    out = list(samples)
    count = max(1, int(RATE * ms / 1000.0))
    count = min(count, len(out) // 2)
    for i in range(count):
        factor = i / count
        out[i] *= factor
        out[-1 - i] *= factor
    return out


def write_wav(name: str, samples: Sequence[float], stereo_spread: float = 0.0) -> Path:
    """16 bit PCM. QSoundEffect wants plain uncompressed wav and so does winsound."""
    SOUNDS.mkdir(parents=True, exist_ok=True)
    path = SOUNDS / name
    data = fade_edges(normalise(samples))

    if stereo_spread > 0:
        # Widen by delaying one side a few samples: a hint of space, no phasing.
        offset = int(RATE * stereo_spread / 1000.0)
        left = data + [0.0] * offset
        right = [0.0] * offset + data
        frames = bytearray()
        for i in range(len(left)):
            for channel in (left[i], right[i]):
                frames += struct.pack("<h", int(max(-1.0, min(1.0, channel)) * 32767))
        channels = 2
    else:
        frames = bytearray()
        for value in data:
            frames += struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767))
        channels = 1

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(bytes(frames))
    return path


# --------------------------------------------------------------------------- #
# The sounds
# --------------------------------------------------------------------------- #


def make_intro(rng: random.Random) -> list[float]:
    """Two low hits with a metallic shimmer, for the opening animation.

    A cinematic sting in the same spirit as the openers everyone knows, composed
    from scratch: sub bass with a downward glide, a filtered noise transient for
    the strike, and a detuned high cluster that rings out through a small reverb.
    """
    def hit(root: float, brightness: float, length: float) -> list[float]:
        sub = decay_env(sweep(root * 1.35, root, length, curve=0.35), length * 0.30, 1.0)
        body = decay_env(sine(root * 2.0, length), length * 0.22, 0.42)
        third = decay_env(sine(root * 3.01, length), length * 0.14, 0.20)
        strike = decay_env(
            highpass(lowpass(noise(0.11, rng), 5200), 900), 0.028, brightness
        )
        return saturate(mix(sub, body, third, strike), 1.35)

    # Air before the first hit so the strike lands rather than starts.
    riser = gain(
        envelope(
            lowpass(noise(0.42, rng), 2600),
            attack=0.38, decay=0.03, sustain=0.0, release=0.01, peak=0.16,
        ),
        1.0,
    )

    shimmer_parts = []
    for freq, level, delay in (
        (1174.7, 0.16, 0.60), (1568.0, 0.13, 0.615), (2349.3, 0.09, 0.63),
        (3136.0, 0.06, 0.65),
    ):
        tone = decay_env(sine(freq, 1.5), 0.34, level)
        shimmer_parts.append(at(delay, tone, 2.6))

    track = mix(
        at(0.02, riser, 2.6),
        at(0.30, hit(55.0, 0.55, 1.5), 2.6),      # ta
        at(0.60, hit(82.4, 0.75, 1.9), 2.6),      # dum
        *shimmer_parts,
    )
    return trim_tail(reverb(track, amount=0.42, size=0.075))


def make_hover(rng: random.Random) -> list[float]:
    tone = decay_env(sine(1250.0, 0.05), 0.011, 0.5)
    air = decay_env(highpass(noise(0.02, rng), 4000), 0.005, 0.10)
    return gain(mix(tone, air), 0.30)


def make_click(rng: random.Random) -> list[float]:
    body = decay_env(sweep(880.0, 1480.0, 0.07, curve=0.6), 0.022, 0.8)
    tick = decay_env(highpass(noise(0.02, rng), 3000), 0.004, 0.35)
    return gain(mix(body, tick), 0.7)


def make_drop(rng: random.Random) -> list[float]:
    thud = decay_env(sweep(190.0, 96.0, 0.28, curve=0.4), 0.075, 1.0)
    paper = decay_env(lowpass(highpass(noise(0.16, rng), 1400), 7000), 0.045, 0.30)
    click = decay_env(sine(620.0, 0.06), 0.02, 0.18)
    return saturate(mix(thud, paper, at(0.01, click, 0.28)), 1.2)


def make_start(rng: random.Random) -> list[float]:
    first = decay_env(sine(523.25, 0.22), 0.075, 0.55)
    second = decay_env(sine(783.99, 0.30), 0.10, 0.45)
    air = decay_env(highpass(noise(0.05, rng), 2500), 0.014, 0.12)
    return trim_tail(reverb(mix(first, at(0.085, second, 0.42), air), 0.18, 0.05))


def make_complete(rng: random.Random) -> list[float]:
    notes = ((659.25, 0.0), (830.61, 0.075), (987.77, 0.15), (1318.51, 0.235))
    parts = []
    for freq, delay in notes:
        parts.append(at(delay, decay_env(sine(freq, 0.7), 0.16, 0.42), 0.95))
        parts.append(at(delay, decay_env(sine(freq * 2, 0.4), 0.07, 0.10), 0.95))
    sparkle = at(0.24, decay_env(highpass(noise(0.1, rng), 6000), 0.03, 0.07), 0.95)
    return trim_tail(reverb(mix(*parts, sparkle), 0.26, 0.06))


def make_error(rng: random.Random) -> list[float]:
    low = decay_env(sweep(330.0, 233.08, 0.34, curve=0.8), 0.13, 0.75)
    grit = decay_env(lowpass(noise(0.12, rng), 1600), 0.05, 0.16)
    second = at(0.12, decay_env(sine(220.0, 0.3), 0.1, 0.35), 0.5)
    return saturate(mix(low, grit, second), 1.25)


def make_toast(rng: random.Random) -> list[float]:
    tone = decay_env(sine(1046.5, 0.14), 0.035, 0.4)
    upper = at(0.045, decay_env(sine(1396.9, 0.12), 0.03, 0.22), 0.2)
    return gain(mix(tone, upper), 0.55)


SOUND_BUILDERS = {
    "intro.wav": (make_intro, 12.0),
    "hover.wav": (make_hover, 0.0),
    "click.wav": (make_click, 0.0),
    "drop.wav": (make_drop, 0.0),
    "start.wav": (make_start, 6.0),
    "complete.wav": (make_complete, 7.0),
    "error.wav": (make_error, 0.0),
    "toast.wav": (make_toast, 0.0),
}


def build_sounds() -> None:
    print("sounds")
    for name, (builder, spread) in SOUND_BUILDERS.items():
        rng = random.Random(hash(name) & 0xFFFF)
        samples = builder(rng)
        path = write_wav(name, samples, spread)
        seconds = len(samples) / RATE
        print(f"  {name:14s} {seconds:5.2f}s  {path.stat().st_size / 1024:6.1f} KB")


# --------------------------------------------------------------------------- #
# Grain texture
# --------------------------------------------------------------------------- #


def build_grain(size: int = 160) -> None:
    from PIL import Image

    IMAGES.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20260811)

    # White specks with varying alpha. Laid over the dark glass at a few percent
    # opacity this reads as fine grain rather than as a grey wash, and because
    # the values are independent per pixel it tiles without a visible seam.
    pixels = []
    for _ in range(size * size):
        roll = rng.random()
        if roll < 0.55:
            alpha = rng.randint(0, 26)      # mostly nothing
        elif roll < 0.93:
            alpha = rng.randint(26, 90)     # fine texture
        else:
            alpha = rng.randint(90, 190)    # occasional bright speck
        pixels.append((255, 255, 255, alpha))

    image = Image.new("RGBA", (size, size))
    image.putdata(pixels)
    path = IMAGES / "noise.png"
    image.save(path, optimize=True)
    print(f"\ngrain\n  noise.png      {size}x{size}  {path.stat().st_size / 1024:6.1f} KB")


# --------------------------------------------------------------------------- #
# Application icon
# --------------------------------------------------------------------------- #


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))


def build_icon() -> None:
    from PIL import Image, ImageDraw, ImageFilter

    IMAGES.mkdir(parents=True, exist_ok=True)
    size = 1024
    accent = (91, 140, 255)
    accent2 = (176, 107, 255)

    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)

    # Rounded tile with a diagonal accent gradient.
    radius = int(size * 0.235)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile)
    for y in range(size):
        for_x = _lerp(accent, accent2, y / size)
        tile_draw.line([(0, y), (size, y)], fill=for_x + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255
    )
    base.paste(tile, (0, 0), mask)

    # Glass sheen: a soft diagonal band across the upper left.
    sheen = Image.new("L", (size, size), 0)
    ImageDraw.Draw(sheen).polygon(
        [(-size * 0.1, size * 0.34), (size * 0.62, -size * 0.12),
         (size * 0.92, size * 0.06), (size * 0.12, size * 0.66)],
        fill=64,
    )
    sheen = sheen.filter(ImageFilter.GaussianBlur(size * 0.05))
    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    sheen_masked = Image.composite(
        white, Image.new("RGBA", (size, size), (0, 0, 0, 0)), sheen
    )
    base = Image.alpha_composite(base, Image.composite(
        sheen_masked, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))

    draw = ImageDraw.Draw(base)

    # A sheet of paper with a folded corner, drawn as the icon's subject.
    left, top = int(size * 0.285), int(size * 0.215)
    right, bottom = int(size * 0.715), int(size * 0.785)
    fold = int(size * 0.145)
    page = [
        (left, top), (right - fold, top), (right, top + fold),
        (right, bottom), (left, bottom),
    ]
    # Soft shadow under the page.
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(
        [(x, y + int(size * 0.022)) for x, y in page], fill=(20, 24, 48, 120)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.022))
    base = Image.alpha_composite(base, shadow)
    draw = ImageDraw.Draw(base)

    draw.polygon(page, fill=(255, 255, 255, 246))
    draw.polygon(
        [(right - fold, top), (right, top + fold), (right - fold, top + fold)],
        fill=(214, 224, 255, 255),
    )

    # Text lines, shortening down the page so it reads as a document.
    line_x0 = left + int(size * 0.055)
    line_w = (right - left) - int(size * 0.11)
    thickness = int(size * 0.030)
    y = top + int(size * 0.205)
    for factor in (1.0, 0.88, 0.96, 0.72, 0.90, 0.55):
        draw.rounded_rectangle(
            [line_x0, y, line_x0 + int(line_w * factor), y + thickness],
            radius=thickness // 2,
            fill=_lerp(accent, accent2, (y - top) / (bottom - top)) + (235,),
        )
        y += int(thickness * 2.35)

    ASSETS.mkdir(parents=True, exist_ok=True)
    png_path = IMAGES / "icon.png"
    base.save(png_path)

    sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    frames = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    ico_path = ASSETS / "icon.ico"
    frames[-1].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
    print(
        f"\nicon\n  icon.png       {size}x{size}  {png_path.stat().st_size / 1024:6.1f} KB"
        f"\n  icon.ico       {min(sizes)}-{max(sizes)}px  "
        f"{ico_path.stat().st_size / 1024:6.1f} KB"
    )
    # A wide banner for the installer sidebar and the readme.
    banner = base.resize((256, 256), Image.LANCZOS)
    banner.save(IMAGES / "icon_256.png")


def main() -> int:
    build_sounds()
    build_grain()
    build_icon()
    print("\nassets written to", ASSETS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
