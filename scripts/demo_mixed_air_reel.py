#!/usr/bin/env python3
"""Hands-off Mixed Air demo for screen recording / social reels.

Drives the real V2 page: login → type two airstreams → Calculate → hold the
result table and psychrometric chart → fill report meta → Download PDF → open
the PDF. You do not interact.

Install (once, outside the Flask venv is fine):

    pip install playwright
    playwright install chromium

Run against a local server (headed, slow typing — record this window with OBS
or let Playwright write a WebM):

    export DEMO_EMAIL='you@example.com'
    export DEMO_PASSWORD='…'
    python scripts/demo_mixed_air_reel.py --base-url http://127.0.0.1:5000 --record

Local ACCESS_DEV_TIER preview login (no password):

    python scripts/demo_mixed_air_reel.py --base-url http://127.0.0.1:5000 --preview

Production:

    python scripts/demo_mixed_air_reel.py --base-url https://hvac-calcs.app --record
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

MIXED_AIR_PATH = "/v2/psychrometrics/mixed-air"

# Visible demo values (same story as the reel: hot outdoor + cooler return).
STREAM_A = {"a_t": "28", "a_val": "50", "flow_a": "1500"}
STREAM_B = {"b_t": "20", "b_val": "50", "flow_b": "3500"}
REPORT = {
    "report_project": "Riverside Office",
    "report_system": "AHU-1 mixed air",
    "report_revision": "A",
    "report_author": "Demo",
}


def _type_field(page: Page, name: str, value: str, delay_ms: int) -> None:
    loc = page.locator(f'form.psychro-inputs input[name="{name}"]')
    loc.click()
    loc.fill("")
    loc.press_sequentially(value, delay=delay_ms)


def _hold(seconds: float) -> None:
    time.sleep(seconds)


def run(page: Page, args: argparse.Namespace) -> Path | None:
    delay = args.type_delay_ms
    pdf_path: Path | None = None

    if args.preview:
        page.goto(f"{args.base_url}/login?preview=1", wait_until="networkidle")
    else:
        page.goto(f"{args.base_url}/login", wait_until="networkidle")
        page.locator('input[name="email"]').fill(args.email)
        page.locator('input[name="password"]').fill(args.password)
        page.locator('form.auth-form button[type="submit"]').click()
        page.wait_for_url("**/v2/**")

    page.goto(f"{args.base_url}{MIXED_AIR_PATH}", wait_until="networkidle")
    page.locator("form.psychro-inputs").wait_for()
    _hold(args.hold)

    # Clear-and-type so the recording shows input, not a pre-filled submit.
    _type_field(page, "a_t", STREAM_A["a_t"], delay)
    page.locator('form.psychro-inputs select[name="a_prop"]').select_option("rh")
    _type_field(page, "a_val", STREAM_A["a_val"], delay)
    _type_field(page, "flow_a", STREAM_A["flow_a"], delay)

    _type_field(page, "b_t", STREAM_B["b_t"], delay)
    page.locator('form.psychro-inputs select[name="b_prop"]').select_option("rh")
    _type_field(page, "b_val", STREAM_B["b_val"], delay)
    _type_field(page, "flow_b", STREAM_B["flow_b"], delay)
    _hold(args.hold)

    page.locator('form.psychro-inputs button[type="submit"]').click()
    page.locator("table.results").wait_for()
    page.locator("table.results strong").filter(has_text="Mixed").wait_for()
    _hold(args.hold * 1.5)

    chart = page.locator(".psychro-chart")
    chart.scroll_into_view_if_needed()
    chart.locator("svg").wait_for()
    _hold(args.hold * 2)

    report = page.locator("form").filter(has=page.locator('input[name="report_project"]'))
    report.scroll_into_view_if_needed()
    for name, value in REPORT.items():
        field = report.locator(f'input[name="{name}"]')
        field.click()
        field.fill("")
        field.press_sequentially(value, delay=delay)
    _hold(args.hold)

    with page.expect_download() as pending:
        report.locator('button[type="submit"]').filter(has_text="Download PDF").click()
    download = pending.value
    args.out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = args.out_dir / (download.suggested_filename or "psychrometrics-mixed-air.pdf")
    download.save_as(pdf_path)

    page.goto(pdf_path.resolve().as_uri())
    _hold(args.hold * 3)
    return pdf_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Hands-off Mixed Air reel driver")
    parser.add_argument("--base-url", default=os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:5000"))
    parser.add_argument("--email", default=os.environ.get("DEMO_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("DEMO_PASSWORD", ""))
    parser.add_argument("--preview", action="store_true", help="Use /login?preview=1 (ACCESS_DEV_TIER only)")
    parser.add_argument("--headed", action="store_true", default=True)
    parser.add_argument("--headless", action="store_true", help="No window (video still records)")
    parser.add_argument("--record", action="store_true", help="Write Playwright WebM under --out-dir")
    parser.add_argument("--out-dir", type=Path, default=Path("demo-output"))
    parser.add_argument("--slow-mo", type=int, default=80, help="Playwright action delay (ms)")
    parser.add_argument("--type-delay-ms", type=int, default=70)
    parser.add_argument("--hold", type=float, default=1.6, help="Pause between beats (seconds)")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    if not args.preview and (not args.email or not args.password):
        raise SystemExit("Set DEMO_EMAIL and DEMO_PASSWORD, or pass --email/--password, or use --preview")

    headed = not args.headless
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, slow_mo=args.slow_mo)
        context_kwargs: dict = {
            "viewport": {"width": args.width, "height": args.height},
            "accept_downloads": True,
        }
        if args.record:
            context_kwargs["record_video_dir"] = str(args.out_dir)
            context_kwargs["record_video_size"] = {"width": args.width, "height": args.height}
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        pdf_path = run(page, args)
        video_path = page.video.path() if args.record else None
        context.close()
        browser.close()

    print("PDF:", pdf_path)
    if video_path:
        print("Video:", video_path)


if __name__ == "__main__":
    main()
