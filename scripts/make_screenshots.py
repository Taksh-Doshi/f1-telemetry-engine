r"""Create the README screenshots using the project virtual environment.

Run this from the repository root with:
    .venv\Scripts\python.exe scripts\make_screenshots.py
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(
    ROOT / ".venv" / "playwright-browsers"
)

from playwright.sync_api import sync_playwright


IMAGE_DIR = ROOT / "docs" / "img"
PLAN_DIR = ROOT / "docs" / "explain"
BENCHMARK_OUTPUT = ROOT / "docs" / "cache_benchmark.txt"
DASHBOARD_URL = "http://localhost:3001"
IMAGE_WIDTH = 1400
MAX_IMAGE_BYTES = 2 * 1024 * 1024
SENSITIVE_TEXT = re.compile(
    r"(?i)\b(?:password|passwd|secret|token|api[_ -]?key)\b\s*[:=]\s*\S+"
    r"|(?:postgres(?:ql)?|redis|rediss|mysql)://\S+"
)
HOST_TEXT = re.compile(
    r"(?i)\b(?:localhost|127(?:\.\d{1,3}){3}|"
    r"[a-z0-9.-]+\.(?:local|internal|test))\b"
)


def project_command(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a project command without echoing any captured output."""
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def wrap_code_line(line: str, max_chars: int) -> list[str]:
    """Wrap one source line without dropping or changing any of its characters."""
    original = line
    segments: list[str] = []
    while len(line) > max_chars:
        break_at = line.rfind(" ", 1, max_chars + 1)
        if break_at < 1:
            break_at = max_chars
        segments.append(line[:break_at])
        line = line[break_at:]
    segments.append(line)
    if "".join(segments) != original:
        raise RuntimeError("Visual line wrapping changed source text")
    return segments


def make_plan_image(source: Path, destination: Path) -> None:
    """Render every source line in a simple dark, monospaced editor view."""
    text = source.read_text(encoding="utf-8")
    if SENSITIVE_TEXT.search(text):
        raise RuntimeError(f"Refusing to render sensitive text from {source.name}")

    windows_fonts = Path("C:/Windows/Fonts")
    font_path = windows_fonts / "consola.ttf"
    if not font_path.exists():
        font_path = windows_fonts / "CascadiaMono.ttf"
    font = (
        ImageFont.truetype(str(font_path), 17)
        if font_path.exists()
        else ImageFont.load_default(size=17)
    )
    title_font = (
        ImageFont.truetype(str(font_path), 14)
        if font_path.exists()
        else ImageFont.load_default(size=14)
    )

    padding = 28
    max_chars = max(20, int((IMAGE_WIDTH - 2 * padding) / font.getlength("M")))
    visual_lines: list[str] = []
    for line in text.splitlines():
        visual_lines.extend(wrap_code_line(line, max_chars))

    line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1] + 7
    title_height = 44
    image_height = title_height + 2 * padding + len(visual_lines) * line_height
    image = Image.new("RGB", (IMAGE_WIDTH, image_height), "#1e1e1e")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, IMAGE_WIDTH, title_height), fill="#252526")
    for index, color in enumerate(("#f16c6c", "#e5c07b", "#98c379")):
        x = 20 + index * 19
        draw.ellipse((x, 16, x + 10, 26), fill=color)
    draw.text((82, 13), source.name, font=title_font, fill="#cccccc")

    y = title_height + padding
    for line in visual_lines:
        draw.text((padding, y), line, font=font, fill="#d4d4d4")
        y += line_height

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG")


def run_requested_activity() -> None:
    """Run the cache and leaderboard examples, preserving a pre-existing edit."""
    benchmark_existed = BENCHMARK_OUTPUT.exists()
    benchmark_before = BENCHMARK_OUTPUT.read_bytes() if benchmark_existed else b""
    commands = [
        (sys.executable, "-m", "f1engine.bench_cache"),
        (sys.executable, "-m", "f1engine.bench_cache"),
        (sys.executable, "-m", "f1engine.bench_cache"),
        (sys.executable, "-m", "f1engine.leaderboard", "2024", "1"),
    ]
    try:
        for index, command in enumerate(commands, start=1):
            result = project_command(*command)
            if result.returncode:
                raise RuntimeError(
                    f"Activity command {index} failed with exit code "
                    f"{result.returncode}; captured output was not printed."
                )
            print(f"Activity command {index}/{len(commands)} completed.")
    finally:
        # bench_cache writes a report file; keep its pre-run contents unchanged.
        if benchmark_existed:
            BENCHMARK_OUTPUT.write_bytes(benchmark_before)
        elif BENCHMARK_OUTPUT.exists():
            BENCHMARK_OUTPUT.unlink()


def check_image(path: Path) -> int:
    """Verify a saved PNG opens, has visible content, and is small enough."""
    size = path.stat().st_size
    if size >= MAX_IMAGE_BYTES:
        raise RuntimeError(f"{path.name} is not under 2 MB")

    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        image = image.convert("RGB")
        background = Image.new("RGB", image.size, image.getpixel((0, 0)))
        if ImageChops.difference(image, background).getbbox() is None:
            raise RuntimeError(f"{path.name} appears blank")
    return size


def main() -> None:
    """Start the dashboard, generate activity, and save all three screenshots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-activity",
        action="store_true",
        help="Capture images again without rerunning the benchmark commands.",
    )
    args = parser.parse_args()

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    plan_pairs = [
        (
            PLAN_DIR / "before_10_degradation_slope_per_stint.txt",
            IMAGE_DIR / "explain-before.png",
        ),
        (
            PLAN_DIR / "after_10_degradation_slope_per_stint.txt",
            IMAGE_DIR / "explain-after.png",
        ),
    ]
    for source, destination in plan_pairs:
        make_plan_image(source, destination)
        print(
            f"Rendered {source.name}: "
            f"{len(source.read_text(encoding='utf-8').splitlines())} source lines, "
            "no omissions."
        )

    result = project_command("docker", "compose", "up", "-d")
    if result.returncode:
        raise RuntimeError(
            f"docker compose up -d failed with exit code {result.returncode}."
        )
    print("Docker Compose services are running.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1600, "height": 1200},
            device_scale_factor=1,
        )
        response = page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30_000)
        if response is None or response.status >= 400:
            browser.close()
            raise RuntimeError("The BetterDB dashboard did not return a successful response.")

        # Never capture a filled password field or visible connection secret.
        has_password_value = page.locator('input[type="password"]').evaluate_all(
            "(inputs) => inputs.some((input) => input.value.length > 0)"
        )
        body_text = page.locator("body").inner_text()
        if has_password_value or SENSITIVE_TEXT.search(body_text):
            browser.close()
            raise RuntimeError(
                "Screenshot skipped because the dashboard contains credential-like text."
            )

        if args.skip_activity:
            print("Skipping activity commands as requested.")
        else:
            run_requested_activity()
            print("Waiting 30 seconds for dashboard charts to update.")
            page.wait_for_timeout(30_000)

        body_text = page.locator("body").inner_text()
        has_password_value = page.locator('input[type="password"]').evaluate_all(
            "(inputs) => inputs.some((input) => input.value.length > 0)"
        )
        if has_password_value or SENSITIVE_TEXT.search(body_text):
            browser.close()
            raise RuntimeError(
                "Screenshot skipped because the dashboard contains credential-like text."
            )

        dashboard_path = IMAGE_DIR / "betterdb.png"
        page.screenshot(path=str(dashboard_path), full_page=True)
        body_text = page.locator("body").inner_text()
        title_lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        host_text = sorted(set(HOST_TEXT.findall(body_text)))
        hit_rate = "unavailable (no hit-rate card is visible)"
        for index, line in enumerate(title_lines):
            if "hit rate" in line.lower():
                match = re.search(r"(?i)hit\s*rate\s*[: ]+([^\s]+)", line)
                if match:
                    hit_rate = match.group(1)
                elif index + 1 < len(title_lines):
                    hit_rate = title_lines[index + 1]
                break

        print(f"Dashboard page title: {page.title()}")
        print(f"Dashboard visible text: {' | '.join(title_lines)}")
        print(f"Host text visible in dashboard page: {host_text or 'none'}")
        print(f"Credential values visible in dashboard page: none")
        print(f"BetterDB hit rate card: {hit_rate}")
        browser.close()

    result = project_command(
        "docker", "compose", "exec", "valkey", "valkey-cli", "info", "stats"
    )
    if result.returncode:
        raise RuntimeError(
            "Could not read Valkey stats; "
            f"docker compose exec exited with code {result.returncode}."
        )
    stats = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith(("keyspace_hits:", "keyspace_misses:"))
    ]
    print("Valkey stats:")
    print("\n".join(stats) if stats else "No keyspace hit/miss lines were returned.")

    print("Generated image files:")
    for path in [IMAGE_DIR / "betterdb.png", *(pair[1] for pair in plan_pairs)]:
        print(f"{path.relative_to(ROOT)}: {check_image(path)} bytes")


if __name__ == "__main__":
    main()
