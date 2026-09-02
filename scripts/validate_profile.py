#!/usr/bin/env python3
"""Validate the GitHub profile candidate in real Chrome viewports via CDP.

Install the pinned Python dependency from scripts/requirements-validation.txt.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import socket
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import websocket


REPOSITORY = Path(__file__).resolve().parents[1]
ROOT = REPOSITORY / "docs"
DEFAULT_TARGET = ROOT.joinpath("index.html").as_uri()
ARTIFACTS = REPOSITORY / "artifacts"
APPROVED_README_VIBE_TEXT = (
    "## Vibe Coding, with a gate ~~~text Claude Code / Codex / Kimi ↓ "
    "Human review: code review ↓ Verification: automated tests · logs · benchmarks ~~~ "
    "I use Claude Code, Codex, and Kimi as coding tools. Generated changes go through "
    "human review and verification with automated tests, logs, and benchmarks."
)
APPROVED_PAGES_VIBE_RAIL_TEXT = (
    "01 Build Claude Code · Codex · Kimi 02 Human Review code review "
    "03 Verify tests · logs · benchmarks"
)
APPROVED_PAGES_VIBE_METHOD_TEXT = (
    "03 / VIBE CODING Fast iteration still needs a gate. I use Claude Code, Codex, and Kimi "
    "as coding tools. Generated changes go through human review and verification with automated "
    "tests, logs, and benchmarks. AI-assisted changes still pass through the same review and "
    "verification gate. BUILD AI Coding Claude Code · Codex · Kimi → REVIEW Human review "
    "code review → VERIFY Verification automated tests · logs · benchmarks"
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_html_text(source: str, pattern: str, label: str) -> str:
    match = re.search(pattern, source, re.DOTALL)
    if not match:
        raise AssertionError(f"Pages is missing the approved {label} structure")
    return normalize_text(re.sub(r"<[^>]+>", " ", match.group("body")))


def validate_repository_contract() -> None:
    readme = REPOSITORY.joinpath("README.md").read_text(encoding="utf-8")
    required_companies = ("Hygon", "Iluvatar CoreX", "Intel", "Baidu", "Shannon Systems")
    missing = [company for company in required_companies if company not in readme]

    failures = []
    if missing:
        failures.append(f"README is missing selected companies: {', '.join(missing)}")
    if re.search(r"\bPPIO\b", readme, re.IGNORECASE):
        failures.append("README contains PPIO")
    if re.search(r"\b20(?:1[6-9]|2[0-9])\b", readme):
        failures.append("README contains employment-style years")
    if re.search(
        r"Performance Engineering|Systems Performance|measurable and fast|Virtualization × Performance",
        readme,
        re.IGNORECASE,
    ):
        failures.append("README regressed to a performance identity")

    hygon_row = re.search(r"^\|\s*\*\*Hygon\*\*\s*\|(?P<work>.*)\|\s*$", readme, re.MULTILINE)
    if readme.count("130+ Gbps") != 1:
        failures.append("README must contain the secondary 130+ Gbps fact exactly once")
    elif not hygon_row:
        failures.append("README must keep the secondary 130+ Gbps fact inside the Hygon table cell")
    else:
        hygon_work = hygon_row.group("work")
        secondary_fragments = re.findall(r"<sub>(.*?)</sub>", hygon_work, re.IGNORECASE | re.DOTALL)
        if len(secondary_fragments) != 1 or "130+ Gbps" not in secondary_fragments[0]:
            failures.append("README must keep 130+ Gbps inside the single Hygon <sub> fact")
        primary_hygon_text = re.sub(r"<sub>.*?</sub>", "", hygon_work, flags=re.IGNORECASE | re.DOTALL)
        if "130+ Gbps" in primary_hygon_text:
            failures.append("README must not promote 130+ Gbps into Hygon primary copy")

    readme_vibe = re.search(
        r"^## Vibe Coding, with a gate\n.*?(?=^## Public work)", readme, re.MULTILINE | re.DOTALL
    )
    if not readme_vibe or normalize_text(readme_vibe.group(0)) != APPROVED_README_VIBE_TEXT:
        failures.append("README Vibe Coding section differs from the human-approved content contract")
    if "https://huix-shh.github.io/huix-shh/" not in readme:
        failures.append("README is missing the interactive Pages entry")
    if not ROOT.joinpath("index.html").is_file():
        failures.append("GitHub Pages entry is missing")

    try:
        hero = ET.parse(REPOSITORY / "assets" / "hero.svg")
        hero_text = " ".join(hero.getroot().itertext())
        for label in ("Linux Systems", "Virtualization", "Cloud Native", "VIBE CODING"):
            if label not in hero_text:
                failures.append(f"Hero SVG is missing {label}")
    except (ET.ParseError, OSError) as error:
        failures.append(f"Hero SVG is invalid: {error}")

    if failures:
        raise AssertionError("; ".join(failures))


def validate_pages_contract() -> None:
    index = ROOT.joinpath("index.html").read_text(encoding="utf-8")
    failures = []
    rail_text = extract_html_text(
        index, r'<ol class="rail-flow">(?P<body>.*?)</ol>', "Vibe Coding rail"
    )
    method_text = extract_html_text(
        index,
        r'<section class="section method-section" id="vibe-method".*?>(?P<body>.*?)</section>',
        "Vibe Coding method section",
    )
    if rail_text != APPROVED_PAGES_VIBE_RAIL_TEXT:
        failures.append("Pages Vibe Coding rail differs from the human-approved content contract")
    if method_text != APPROVED_PAGES_VIBE_METHOD_TEXT:
        failures.append("Pages Vibe Coding method differs from the human-approved content contract")
    if failures:
        raise AssertionError("; ".join(failures))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the interactive Pages site and the Profile README contract."
    )
    parser.add_argument(
        "--pages-only",
        action="store_true",
        help="Validate docs/ without requiring the second-stage README and Hero changes.",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=(
            "Page URL to validate; defaults to local docs/index.html and also accepts a deployed HTTP(S) URL."
        ),
    )
    return parser.parse_args()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class CDP:
    def __init__(self, websocket_url: str) -> None:
        self.connection = websocket.create_connection(websocket_url, timeout=8, origin="http://localhost")
        self.sequence = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.sequence += 1
        message_id = self.sequence
        self.connection.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))

        while True:
            response = json.loads(self.connection.recv())
            if response.get("id") != message_id:
                continue
            if "error" in response:
                raise RuntimeError(f"{method}: {response['error']}")
            return response.get("result", {})

    def close(self) -> None:
        self.connection.close()


def wait_for_debugger(port: int) -> None:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    for _ in range(80):
        try:
            with urlopen(endpoint, timeout=0.4):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Chrome DevTools endpoint did not start")


def new_page(port: int) -> CDP:
    request = Request(
        f"http://127.0.0.1:{port}/json/new?{quote('about:blank', safe=':/')}",
        method="PUT",
    )
    with urlopen(request, timeout=3) as response:
        page = json.load(response)
    return CDP(page["webSocketDebuggerUrl"])


def evaluate(cdp: CDP, expression: str):
    result = cdp.call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    return result["result"].get("value")


def press_key(cdp: CDP, *, key: str, code: str, key_code: int) -> None:
    for event_type in ("keyDown", "keyUp"):
        cdp.call(
            "Input.dispatchKeyEvent",
            {
                "type": event_type,
                "key": key,
                "code": code,
                "windowsVirtualKeyCode": key_code,
                "nativeVirtualKeyCode": key_code,
            },
        )
    time.sleep(0.08)


def navigate(
    cdp: CDP,
    *,
    target: str,
    width: int,
    height: int,
    javascript: bool,
    reduced_motion: bool,
) -> None:
    cdp.call("Page.enable")
    cdp.call("Runtime.enable")
    cdp.call(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": width <= 680,
        },
    )
    cdp.call(
        "Emulation.setEmulatedMedia",
        {
            "media": "screen",
            "features": [
                {"name": "prefers-reduced-motion", "value": "reduce" if reduced_motion else "no-preference"}
            ],
        },
    )
    cdp.call("Emulation.setScriptExecutionDisabled", {"value": not javascript})
    cdp.call("Page.navigate", {"url": target})

    for _ in range(80):
        state = evaluate(cdp, "document.readyState")
        if state == "complete":
            return
        time.sleep(0.05)
    raise RuntimeError("Prototype did not finish loading")


def collect(cdp: CDP) -> dict:
    return evaluate(
        cdp,
        r"""
        (() => {
          const root = document.documentElement;
          const bodyText = document.body.innerText;
          const readColor = (value) => {
            const values = (value.match(/[\d.]+/g) || []).map(Number);
            if (value.startsWith('color(srgb')) {
              return {r: values[0] * 255, g: values[1] * 255, b: values[2] * 255, a: values[3] ?? 1};
            }
            return {r: values[0] || 0, g: values[1] || 0, b: values[2] || 0, a: values[3] ?? 1};
          };
          const composite = (top, bottom) => {
            const alpha = top.a + bottom.a * (1 - top.a);
            return {
              r: (top.r * top.a + bottom.r * bottom.a * (1 - top.a)) / alpha,
              g: (top.g * top.a + bottom.g * bottom.a * (1 - top.a)) / alpha,
              b: (top.b * top.a + bottom.b * bottom.a * (1 - top.a)) / alpha,
              a: alpha,
            };
          };
          const backgroundFor = (node) => {
            const ancestors = [];
            for (let current = node; current; current = current.parentElement) ancestors.unshift(current);
            let background = {r: 255, g: 255, b: 255, a: 1};
            ancestors.forEach((ancestor) => {
              const layer = readColor(getComputedStyle(ancestor).backgroundColor);
              if (layer.a > 0) background = composite(layer, background);
            });
            return background;
          };
          const luminance = ({r, g, b}) => {
            const channel = (value) => {
              const normalized = value / 255;
              return normalized <= 0.04045
                ? normalized / 12.92
                : Math.pow((normalized + 0.055) / 1.055, 2.4);
            };
            return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
          };
          const contrastFor = (node) => {
            const foreground = readColor(getComputedStyle(node).color);
            const background = backgroundFor(node);
            const lighter = Math.max(luminance(foreground), luminance(background));
            const darker = Math.min(luminance(foreground), luminance(background));
            return Number(((lighter + 0.05) / (darker + 0.05)).toFixed(2));
          };
          const coreSelectors = [
            '#hero-title', '#system-title', '#experience-title', '#method-title', '#public-title',
            '[data-card]'
          ];
          const allVisible = coreSelectors.every((selector) =>
            [...document.querySelectorAll(selector)].every((node) => {
              const style = getComputedStyle(node);
              const rect = node.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            })
          );

          return {
            innerWidth: innerWidth,
            documentClientWidth: root.clientWidth,
            documentScrollWidth: root.scrollWidth,
            bodyClientWidth: document.body.clientWidth,
            bodyScrollWidth: document.body.scrollWidth,
            coreVisible: allVisible,
            selectedCompanies: document.querySelectorAll('.experience-card').length,
            vibeMethodCount: (bodyText.match(/Vibe Coding/gi) || []).length,
            throughputCount: (bodyText.match(/130\+ Gbps/gi) || []).length,
            hasPPIO: /PPIO/i.test(bodyText),
            hasYear: /\b20(?:1[6-9]|2[0-9])\b/.test(bodyText),
            hasPerformanceIdentity: /Performance Engineering|Systems Performance|measurable and fast|Virtualization × Performance/i.test(bodyText),
            hasFakeVibeEvidence: /Open-source contributor|expected merge|planned PR|activity graph/i.test(bodyText),
            hasOverclaimVerbs: /Built a repeatable VM test-environment|Validated distributed-storage designs/i.test(bodyText),
            vibeRailText: document.querySelector('.rail-flow').textContent.replace(/\s+/g, ' ').trim(),
            vibeMethodText: document.querySelector('#vibe-method').textContent.replace(/\s+/g, ' ').trim(),
            hygonPrimaryItems: document.querySelectorAll('.experience-card:first-child > ul > li').length,
            hygonPerformanceUnits: document.querySelectorAll('.experience-card:first-child > .performance-note').length,
            minCardOpacity: Math.min(...[...document.querySelectorAll('[data-card]')].map((card) => Number(getComputedStyle(card).opacity))),
            performanceMinContrast: Math.min(
              contrastFor(document.querySelector('.performance-note span')),
              contrastFor(document.querySelector('.performance-note p'))
            ),
            secondaryCardTextContrast: contrastFor(document.querySelectorAll('.experience-card')[1].querySelector('li')),
            jsClass: root.classList.contains('js'),
            jsOnlyDisplay: getComputedStyle(document.querySelector('.js-only')).display,
            motionAnimationDuration: getComputedStyle(document.querySelector('.hero-sidecar'), '::before').animationDuration,
          };
        })()
        """,
    )


def capture(cdp: CDP, name: str) -> Path:
    result = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    path = ARTIFACTS / f"{name}.png"
    path.write_bytes(base64.b64decode(result["data"]))
    return path


def capture_at(cdp: CDP, name: str, selector: str) -> Path:
    evaluate(
        cdp,
        f"""
        (() => {{
          document.documentElement.style.scrollBehavior = 'auto';
          document.querySelector({json.dumps(selector)}).scrollIntoView({{block: 'start'}});
        }})()
        """,
    )
    time.sleep(0.12)
    return capture(cdp, name)


def assert_base(name: str, result: dict) -> None:
    failures = []
    if result["documentScrollWidth"] > result["documentClientWidth"]:
        failures.append("document horizontal overflow")
    if result["bodyScrollWidth"] > result["bodyClientWidth"]:
        failures.append("body horizontal overflow")
    if not result["coreVisible"]:
        failures.append("core content hidden")
    if result["selectedCompanies"] != 5:
        failures.append("selected company count is not five")
    if result["throughputCount"] != 1:
        failures.append("130+ Gbps fact is missing or over-emphasized")
    if result["hygonPrimaryItems"] != 1 or result["hygonPerformanceUnits"] != 1:
        failures.append("Hygon performance is not a single secondary unit")
    if result["minCardOpacity"] < 1:
        failures.append("card opacity lowers content readability")
    if result["performanceMinContrast"] < 4.5 or result["secondaryCardTextContrast"] < 4.5:
        failures.append(
            "text contrast is below 4.5:1 "
            f"(performance={result['performanceMinContrast']}, secondary={result['secondaryCardTextContrast']})"
        )
    if result["vibeRailText"] != APPROVED_PAGES_VIBE_RAIL_TEXT:
        failures.append("rendered Vibe Coding rail differs from the approved content contract")
    if result["vibeMethodText"] != APPROVED_PAGES_VIBE_METHOD_TEXT:
        failures.append("rendered Vibe Coding method differs from the approved content contract")
    if (
        result["hasPPIO"]
        or result["hasYear"]
        or result["hasPerformanceIdentity"]
        or result["hasFakeVibeEvidence"]
        or result["hasOverclaimVerbs"]
    ):
        failures.append("content boundary regression")
    if failures:
        raise AssertionError(f"{name}: {', '.join(failures)}")


def main() -> None:
    args = parse_args()
    validate_pages_contract()
    if not args.pages_only:
        validate_repository_contract()

    chrome = shutil.which("google-chrome")
    if not chrome:
        raise RuntimeError("google-chrome is required")

    ARTIFACTS.mkdir(exist_ok=True)
    port = free_port()

    with tempfile.TemporaryDirectory(prefix="profile-prototype-chrome-", ignore_cleanup_errors=True) as profile_dir:
        process = subprocess.Popen(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile_dir}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            wait_for_debugger(port)
            report = {}

            scenarios = [
                ("desktop", 1440, 1100, True, False),
                ("mobile-430-reduced", 430, 1100, True, True),
                ("mobile-430-no-js", 430, 1100, False, True),
                # Theme interaction writes localStorage, so keep it last.
                ("mobile-430", 430, 1100, True, False),
            ]

            for name, width, height, javascript, reduced_motion in scenarios:
                cdp = new_page(port)
                try:
                    navigate(
                        cdp,
                        target=args.target,
                        width=width,
                        height=height,
                        javascript=javascript,
                        reduced_motion=reduced_motion,
                    )
                    if javascript:
                        # Keep scenarios independent. The light-theme interaction
                        # is asserted explicitly below instead of leaking through
                        # localStorage into reduced-motion coverage.
                        evaluate(
                            cdp,
                            "localStorage.removeItem('profile-prototype-theme'); "
                            "document.documentElement.removeAttribute('data-theme')",
                        )
                    result = collect(cdp)
                    assert_base(name, result)

                    if javascript and result["jsOnlyDisplay"] == "none":
                        raise AssertionError(f"{name}: JavaScript controls did not appear")
                    if not javascript and (result["jsClass"] or result["jsOnlyDisplay"] != "none"):
                        raise AssertionError(f"{name}: no-JavaScript fallback is inconsistent")
                    if reduced_motion and result["motionAnimationDuration"] not in {"0s", "1e-05s"}:
                        raise AssertionError(f"{name}: motion was not reduced")

                    if name == "mobile-430":
                        capture(cdp, name)
                        evaluate(cdp, "document.documentElement.style.scrollBehavior = 'auto'")
                        interaction = evaluate(
                            cdp,
                            r"""
                            (() => {
                              document.querySelector('[data-filter="virtualization"]').click();
                              const cards = [...document.querySelectorAll('[data-card]')];
                              document.querySelector('.theme-toggle').click();
                              return {
                                activeLayers: document.querySelectorAll('[data-filter].is-active').length,
                                relatedCards: cards.filter((card) => card.classList.contains('is-related')).length,
                                hiddenCards: cards.filter((card) => getComputedStyle(card).display === 'none').length,
                                minOpacity: Math.min(...cards.map((card) => Number(getComputedStyle(card).opacity))),
                                theme: document.documentElement.dataset.theme,
                                targetTop: Math.round(document.querySelector('#selected-experience').getBoundingClientRect().top),
                              };
                            })()
                            """,
                        )
                        if (
                            interaction["activeLayers"] != 1
                            or interaction["relatedCards"] != 4
                            or interaction["hiddenCards"] != 0
                            or interaction["minOpacity"] != 1
                            or interaction["theme"] != "light"
                            or not 0 <= interaction["targetTop"] <= 110
                        ):
                            raise AssertionError(f"mobile interaction mismatch: {interaction}")
                        light_result = collect(cdp)
                        assert_base("mobile-430-light-interaction", light_result)
                        result["interaction"] = interaction

                        capture_at(cdp, "mobile-430-interaction", "#selected-experience")

                        clear_mouse = evaluate(
                            cdp,
                            r"""
                            (() => {
                              document.querySelector('[data-clear-filter]').click();
                              return {
                                activeLayers: document.querySelectorAll('[data-filter].is-active').length,
                                relatedCards: document.querySelectorAll('[data-card].is-related').length,
                                mutedCards: document.querySelectorAll('[data-card].is-muted').length,
                              };
                            })()
                            """,
                        )
                        if clear_mouse != {"activeLayers": 0, "relatedCards": 0, "mutedCards": 0}:
                            raise AssertionError(f"mouse clear mismatch: {clear_mouse}")

                        vibe_mouse = evaluate(
                            cdp,
                            r"""
                            (() => {
                              document.querySelector('[data-filter="vibe"]').click();
                              return {
                                activeLayers: document.querySelectorAll('[data-filter].is-active').length,
                                relatedCards: document.querySelectorAll('[data-card].is-related').length,
                                methodRelated: document.querySelector('#vibe-method').classList.contains('is-related'),
                                targetTop: Math.round(document.querySelector('#vibe-method').getBoundingClientRect().top),
                              };
                            })()
                            """,
                        )
                        if (
                            vibe_mouse["activeLayers"] != 1
                            or vibe_mouse["relatedCards"] != 1
                            or not vibe_mouse["methodRelated"]
                            or not 0 <= vibe_mouse["targetTop"] <= 110
                        ):
                            raise AssertionError(f"Vibe mouse target mismatch: {vibe_mouse}")

                        evaluate(
                            cdp,
                            "document.querySelector('[data-clear-filter]').click(); document.querySelector('.layer-systems').focus()",
                        )
                        press_key(cdp, key="Tab", code="Tab", key_code=9)
                        tab_target = evaluate(cdp, "document.activeElement?.dataset?.filter || ''")
                        if tab_target != "vibe":
                            raise AssertionError(f"Tab did not reach Vibe rail: {tab_target}")

                        press_key(cdp, key="Enter", code="Enter", key_code=13)
                        vibe_keyboard = evaluate(
                            cdp,
                            r"""
                            (() => ({
                              activeLayers: document.querySelectorAll('[data-filter].is-active').length,
                              relatedCards: document.querySelectorAll('[data-card].is-related').length,
                              methodRelated: document.querySelector('#vibe-method').classList.contains('is-related'),
                              targetTop: Math.round(document.querySelector('#vibe-method').getBoundingClientRect().top),
                            }))()
                            """,
                        )
                        if (
                            vibe_keyboard["activeLayers"] != 1
                            or vibe_keyboard["relatedCards"] != 1
                            or not vibe_keyboard["methodRelated"]
                            or not 0 <= vibe_keyboard["targetTop"] <= 110
                        ):
                            raise AssertionError(f"Vibe keyboard target mismatch: {vibe_keyboard}")

                        evaluate(cdp, "document.querySelector('[data-clear-filter]').focus()")
                        press_key(cdp, key=" ", code="Space", key_code=32)
                        clear_keyboard = evaluate(
                            cdp,
                            "({activeLayers: document.querySelectorAll('[data-filter].is-active').length, relatedCards: document.querySelectorAll('[data-card].is-related').length, mutedCards: document.querySelectorAll('[data-card].is-muted').length})",
                        )
                        if clear_keyboard != {"activeLayers": 0, "relatedCards": 0, "mutedCards": 0}:
                            raise AssertionError(f"keyboard clear mismatch: {clear_keyboard}")

                        result["lightContrast"] = {
                            "performance": light_result["performanceMinContrast"],
                            "secondaryCardText": light_result["secondaryCardTextContrast"],
                        }
                        result["vibeMouse"] = vibe_mouse
                        result["vibeKeyboard"] = vibe_keyboard
                        result["clearMouse"] = clear_mouse
                        result["clearKeyboard"] = clear_keyboard

                    elif name == "desktop":
                        capture(cdp, name)
                        capture_at(cdp, "desktop-system-map", "#system-map")
                        capture_at(cdp, "desktop-experience", "#selected-experience")
                        capture_at(cdp, "desktop-vibe-method", "#vibe-method")

                    elif name == "mobile-430-no-js":
                        capture(cdp, name)
                        no_js_anchor = evaluate(
                            cdp,
                            r"""
                            (() => {
                              document.documentElement.style.scrollBehavior = 'auto';
                              const link = document.querySelector('[data-filter="vibe"]');
                              link.click();
                              return {
                                href: link.getAttribute('href'),
                                hash: location.hash,
                                targetTop: Math.round(document.querySelector('#vibe-method').getBoundingClientRect().top),
                              };
                            })()
                            """,
                        )
                        if (
                            no_js_anchor["href"] != "#vibe-method"
                            or no_js_anchor["hash"] != "#vibe-method"
                            or not 0 <= no_js_anchor["targetTop"] <= 110
                        ):
                            raise AssertionError(f"no-JavaScript Vibe anchor mismatch: {no_js_anchor}")
                        result["noJsVibeAnchor"] = no_js_anchor

                    else:
                        capture(cdp, name)
                    report[name] = result
                finally:
                    cdp.close()

            print(json.dumps(report, indent=2, ensure_ascii=False))
        finally:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
