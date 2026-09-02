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
CDP_COMMAND_TIMEOUT_SECONDS = 20.0
CHROME_STARTUP_TIMEOUT_SECONDS = 20.0
PAGE_CREATION_TIMEOUT_SECONDS = 20.0
NAVIGATION_TIMEOUT_SECONDS = 30.0
DOM_READY_TIMEOUT_SECONDS = 15.0
POLL_INTERVAL_SECONDS = 0.1
CRITICAL_DOM_SELECTORS = (
    "#hero-title",
    "#system-title",
    "#experience-title",
    "#method-title",
    "#public-title",
)
APPROVED_README_VIBE_TEXT = (
    "Claude Code / Codex / Kimi ↓ Human review: code review ↓ "
    "Verification: automated tests · logs · benchmarks "
    "I use Claude Code, Codex, and Kimi as coding tools. Generated changes go through "
    "human review and verification with automated tests, logs, and benchmarks."
)
APPROVED_WORKFLOW_SVG_TEXT = (
    "VIBE CODING, WITH A GATE Claude Code / Codex / Kimi "
    "Human review: code review Verification: automated tests · logs · benchmarks"
)
APPROVED_EXPERIENCE_FALLBACK_TEXT = (
    "- **Hygon** — Contributed to a repeatable VM test-environment flow around image "
    "preparation, cloud-init, libvirt, boot checks, and Ansible; also handled customer "
    "issue diagnosis. Additional validation: comparable CubeSandbox runs and "
    "passthrough-network tuning; one single-port, one-way test result reached 130+ Gbps. "
    "- **Iluvatar CoreX** — Developed GPU Device Plugin and Container Toolkit components; "
    "built a Dify/RAG workflow for compiler-log retrieval and assisted diagnosis. "
    "- **Intel** — Contributed to ACRN validation, code quality, and upstream changes; "
    "implemented infrastructure-provider integrations and Kubernetes-managed edge "
    "simulations. - **Baidu** — Maintained a libvirt/QEMU platform, diagnosed hot-migration "
    "failures, and improved VF permission controls for virtualized SSD I/O paths. "
    "- **Shannon Systems** — Implemented SSD FTL address translation and metadata handling; "
    "participated in distributed-storage feasibility validation involving ZooKeeper, "
    "consistent hashing, and RDMA."
)
APPROVED_TOOLBOX_FALLBACK_TEXT = (
    "- **code:** C · Python · Go · Bash - **systems:** Linux · KVM · QEMU · libvirt · "
    "Firecracker · cloud-init · systemd - **cloud_native:** Kubernetes · containerd · runc · "
    "Ansible"
)
APPROVED_PUBLIC_WORK_README_TEXT = (
    "Inspect representative changes: - [#3342 — Clean up vCPU code for static "
    "analysis](https://github.com/projectacrn/acrn-hypervisor/pull/3342) - [#3373 — Remove "
    "dead instruction-emulation code](https://github.com/projectacrn/acrn-hypervisor/pull/3373) "
    "- [#3580 — Fix type-conversion and return-value coding-guideline "
    "violations](https://github.com/projectacrn/acrn-hypervisor/pull/3580) New public "
    "contributions will be added here only after the corresponding PR or commit is inspectable."
)
APPROVED_SVG_VISIBLE_TEXT = {
    "hero.svg": (
        "SYSTEMS ENGINEER SYSTEMS WORK, MADE VISIBLE. HUIX-SHH / BUILD · REVIEW · VERIFY "
        "LINUX VIRTUALIZATION CLOUD NATIVE SYSTEM CUTAWAY L3 Cloud Native Kubernetes · "
        "runtimes · edge L2 Virtualization KVM · QEMU · libvirt · ACRN L1 Linux Systems "
        "code · automation · I/O CPU / GPU / STORAGE / NETWORK VIBE CODING BUILD REVIEW "
        "VERIFY HUMAN GATE"
    ),
    "hero-mobile.svg": (
        "SYSTEMS ENGINEER SYSTEMS WORK, MADE VISIBLE. LINUX VIRTUALIZATION CLOUD NATIVE "
        "SYSTEM CUTAWAY L3 Cloud Native Kubernetes · runtimes · edge L2 Virtualization "
        "KVM · QEMU · libvirt · ACRN L1 Linux Systems code · automation · I/O VIBE CODING "
        "BUILD · REVIEW · VERIFY"
    ),
    "experience.svg": (
        "SELECTED EXPERIENCE Systems, virtualization, cloud native, and storage. HYG Hygon "
        "LINUX SYSTEMS · VIRTUALIZATION VM test-environment flow · cloud-init · libvirt · "
        "boot checks · Ansible Customer issue diagnosis · CubeSandbox validation · "
        "passthrough-network tuning IX Iluvatar CoreX GPU · AI INFRASTRUCTURE Device Plugin · "
        "Container Toolkit Dify/RAG compiler-log diagnosis IN Intel VIRTUALIZATION · EDGE "
        "ACRN validation · upstream changes provider integration · edge simulation BD Baidu "
        "VIRTUALIZATION · I/O libvirt/QEMU · hot-migration diagnosis VF controls for "
        "virtualized SSD I/O SS Shannon Systems STORAGE SYSTEMS SSD FTL · address translation · "
        "metadata distributed-storage feasibility validation SELECTED WORK · NOT A COMPLETE "
        "EMPLOYMENT TIMELINE"
    ),
    "experience-mobile.svg": (
        "SELECTED EXPERIENCE Selected systems work Hygon LINUX SYSTEMS · VIRTUALIZATION "
        "VM test-environment flow cloud-init · libvirt · boot checks · Ansible Customer "
        "diagnosis · CubeSandbox · network tuning Iluvatar CoreX GPU · AI INFRASTRUCTURE "
        "Device Plugin · Container Toolkit Dify/RAG compiler-log diagnosis Intel "
        "VIRTUALIZATION · EDGE ACRN validation · upstream changes provider integration · "
        "edge simulation Baidu VIRTUALIZATION · I/O libvirt/QEMU · hot-migration diagnosis "
        "VF controls for virtualized SSD I/O Shannon Systems STORAGE SYSTEMS SSD FTL · address "
        "translation · metadata distributed-storage feasibility validation SELECTED WORK · "
        "TEXT DETAILS BELOW"
    ),
    "workflow.svg": APPROVED_WORKFLOW_SVG_TEXT,
    "workflow-mobile.svg": APPROVED_WORKFLOW_SVG_TEXT,
    "public-work.svg": (
        "PUBLIC EVIDENCE / ACRN HYPERVISOR ACRN Hypervisor · 8 merged pull requests Public "
        "upstream changes focused on code quality and maintainability. 8 MERGED pull requests "
        "PUBLIC · REVIEWED · TRACEABLE #3342 vCPU cleanup for static analysis MERGED #3373 "
        "dead instruction-emulation code removal MERGED #3580 type-conversion and return-value "
        "guideline fixes MERGED"
    ),
    "public-work-mobile.svg": (
        "PUBLIC EVIDENCE / ACRN HYPERVISOR 8 merged pull requests Code quality and "
        "maintainability 8 MERGED pull requests #3342 vCPU cleanup for static analysis #3373 "
        "dead instruction-emulation code removal #3580 coding-guideline fixes"
    ),
    "toolbox.svg": (
        "TOOLBOX / WORKING SET Code, systems, virtualization, and cloud-native tools. CODE C "
        "Python Go Bash AUTOMATE / INTEGRATE SYSTEMS + VIRTUALIZATION Linux · KVM · QEMU · "
        "libvirt · Firecracker cloud-init · systemd CLOUD NATIVE Kubernetes · containerd · "
        "runc Ansible"
    ),
    "toolbox-mobile.svg": (
        "TOOLBOX / WORKING SET Tools used across the stack CODE C · Python · Go · Bash "
        "SYSTEMS + VIRTUALIZATION Linux · KVM · QEMU · libvirt Firecracker cloud-init · "
        "systemd CLOUD NATIVE Kubernetes · containerd · runc Ansible"
    ),
}
PROFILE_PICTURES = {
    "hero.svg": "hero-mobile.svg",
    "experience.svg": "experience-mobile.svg",
    "workflow.svg": "workflow-mobile.svg",
    "public-work.svg": "public-work-mobile.svg",
    "toolbox.svg": "toolbox-mobile.svg",
}
FORBIDDEN_VISUAL_CLAIMS = (
    "Explore · draft · refactor",
    "edge cases · maintainability",
    "NO BLIND MERGE",
    "Produce evidence",
    "Run · observe · explain",
    "ENGINEERING JUDGMENT OWNS THE RESULT",
    "repeatable, observable, and easier to diagnose",
    "Broad enough to follow the system end to end",
    "LEARN AS NEEDED · VERIFY IN CONTEXT",
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


def svg_visible_text(root: ET.Element) -> str:
    return normalize_text(
        " ".join(
            "".join(node.itertext())
            for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "text"
        )
    )


def svg_text_sizes(root: ET.Element) -> list[float]:
    sizes: list[float] = []

    def visit(node: ET.Element, inherited: float | None = None) -> None:
        current = inherited
        if "font-size" in node.attrib:
            current = float(node.attrib["font-size"])
        if node.tag.rsplit("}", 1)[-1] == "text":
            if current is None:
                raise AssertionError("SVG text is missing an explicit or inherited font-size")
            sizes.append(current)
        for child in node:
            visit(child, current)

    visit(root)
    return sizes


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

    hygon_item = re.search(
        r"^- \*\*Hygon\*\*.*?(?=^- \*\*Iluvatar CoreX\*\*)",
        readme,
        re.MULTILINE | re.DOTALL,
    )
    if readme.count("130+ Gbps") != 1:
        failures.append("README must contain the secondary 130+ Gbps fact exactly once")
    elif not hygon_item:
        failures.append("README must keep the secondary 130+ Gbps fact inside the Hygon text fallback")
    else:
        hygon_work = hygon_item.group(0)
        secondary_fragments = re.findall(r"<sub>(.*?)</sub>", hygon_work, re.IGNORECASE | re.DOTALL)
        if len(secondary_fragments) != 1 or "130+ Gbps" not in secondary_fragments[0]:
            failures.append("README must keep 130+ Gbps inside the single Hygon <sub> fact")
        primary_hygon_text = re.sub(r"<sub>.*?</sub>", "", hygon_work, flags=re.IGNORECASE | re.DOTALL)
        if "130+ Gbps" in primary_hygon_text:
            failures.append("README must not promote 130+ Gbps into Hygon primary copy")

    readme_vibe = re.search(
        r"^## Vibe Coding, with a gate\n.*?(?=^## Public work)", readme, re.MULTILINE | re.DOTALL
    )
    vibe_fallback = (
        re.search(
            r"<details>\s*<summary>Text version</summary>(?P<body>.*?)</details>",
            readme_vibe.group(0),
            re.DOTALL,
        )
        if readme_vibe
        else None
    )
    fallback_text = (
        normalize_text(re.sub(r"<[^>]+>", " ", vibe_fallback.group("body")))
        if vibe_fallback
        else ""
    )
    if fallback_text != APPROVED_README_VIBE_TEXT:
        failures.append("README Vibe Coding section differs from the human-approved content contract")

    experience_section = re.search(
        r"^## Selected experience\n(?P<body>.*?)(?=^## Vibe Coding, with a gate)",
        readme,
        re.MULTILINE | re.DOTALL,
    )
    experience_fallback = (
        re.search(
            r"<details>\s*<summary>Text version and details</summary>(?P<body>.*?)</details>",
            experience_section.group("body"),
            re.DOTALL,
        )
        if experience_section
        else None
    )
    experience_fallback_text = (
        normalize_text(re.sub(r"<[^>]+>", " ", experience_fallback.group("body")))
        if experience_fallback
        else ""
    )
    if experience_fallback_text != APPROVED_EXPERIENCE_FALLBACK_TEXT:
        failures.append("README experience fallback differs from its approved exact contract")

    toolbox_section = re.search(
        r"^## Toolbox\n(?P<body>.*?)(?=^## Connect)",
        readme,
        re.MULTILINE | re.DOTALL,
    )
    toolbox_fallback = (
        re.search(
            r"<details>\s*<summary>Text version</summary>(?P<body>.*?)</details>",
            toolbox_section.group("body"),
            re.DOTALL,
        )
        if toolbox_section
        else None
    )
    toolbox_fallback_text = (
        normalize_text(re.sub(r"<[^>]+>", " ", toolbox_fallback.group("body")))
        if toolbox_fallback
        else ""
    )
    if toolbox_fallback_text != APPROVED_TOOLBOX_FALLBACK_TEXT:
        failures.append("README toolbox fallback differs from its approved exact contract")

    public_work_section = re.search(
        r"^## Public work\n(?P<body>.*?)(?=^## Toolbox)",
        readme,
        re.MULTILINE | re.DOTALL,
    )
    public_work_text = (
        normalize_text(
            re.sub(
                r"<picture>.*?</picture>",
                " ",
                public_work_section.group("body"),
                flags=re.DOTALL,
            )
        )
        if public_work_section
        else ""
    )
    if public_work_text != APPROVED_PUBLIC_WORK_README_TEXT:
        failures.append("README public-work text differs from its approved exact contract")

    if readme.count("<details>") != 3 or "<details open" in readme:
        failures.append("README must keep exactly three collapsed text fallback controls")

    if "https://huix-shh.github.io/huix-shh/" not in readme:
        failures.append("README is missing the interactive Pages entry")
    if not ROOT.joinpath("index.html").is_file():
        failures.append("GitHub Pages entry is missing")

    if readme.count("<picture>") != len(PROFILE_PICTURES):
        failures.append("README must use one responsive picture for each visual section")

    parsed_svgs: dict[str, ET.Element] = {}
    for desktop_name, mobile_name in PROFILE_PICTURES.items():
        desktop_reference = f'src="./assets/{desktop_name}"'
        mobile_reference = (
            f'<source media="(max-width: 640px)" srcset="./assets/{mobile_name}" />'
        )
        if readme.count(desktop_reference) != 1 or readme.count(mobile_reference) != 1:
            failures.append(
                f"README responsive picture contract is missing {desktop_name}/{mobile_name}"
            )

        for asset_name in (desktop_name, mobile_name):
            try:
                root = ET.parse(REPOSITORY / "assets" / asset_name).getroot()
                parsed_svgs[asset_name] = root
            except (ET.ParseError, OSError) as error:
                failures.append(f"{asset_name} is invalid: {error}")

        mobile_root = parsed_svgs.get(mobile_name)
        if mobile_root is not None:
            view_box = mobile_root.attrib.get("viewBox", "").split()
            if len(view_box) != 4 or view_box[:3] != ["0", "0", "720"]:
                failures.append(f"{mobile_name} must use a 720px-wide mobile viewBox")
            try:
                sizes = svg_text_sizes(mobile_root)
                if not sizes or min(sizes) < 22:
                    failures.append(f"{mobile_name} contains text smaller than 22 SVG pixels")
            except (AssertionError, ValueError) as error:
                failures.append(f"{mobile_name} font-size contract failed: {error}")

    for asset_name, approved_text in APPROVED_SVG_VISIBLE_TEXT.items():
        root = parsed_svgs.get(asset_name)
        if root is not None and svg_visible_text(root) != approved_text:
            failures.append(f"{asset_name} differs from its approved exact visible-text contract")

    for desktop_name in PROFILE_PICTURES:
        desktop_root = parsed_svgs.get(desktop_name)
        if desktop_root is None:
            continue
        try:
            sizes = svg_text_sizes(desktop_root)
            if not sizes or min(sizes) < 16:
                failures.append(f"{desktop_name} contains text smaller than 16 SVG pixels")
        except (AssertionError, ValueError) as error:
            failures.append(f"{desktop_name} font-size contract failed: {error}")

    for asset_name, root in parsed_svgs.items():
        visible = svg_visible_text(root)
        for forbidden in FORBIDDEN_VISUAL_CLAIMS:
            if forbidden.lower() in visible.lower():
                failures.append(f"{asset_name} contains unsupported visual claim: {forbidden}")

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
        self.connection = websocket.create_connection(
            websocket_url,
            timeout=CDP_COMMAND_TIMEOUT_SECONDS,
            origin="http://localhost",
        )
        self.sequence = 0
        self.events: list[dict] = []

    def _receive(self, *, timeout: float, timeout_message: str) -> dict:
        self.connection.settimeout(timeout)
        try:
            return json.loads(self.connection.recv())
        except websocket.WebSocketTimeoutException as error:
            raise RuntimeError(timeout_message) from error
        finally:
            self.connection.settimeout(CDP_COMMAND_TIMEOUT_SECONDS)

    def call(self, method: str, params: dict | None = None) -> dict:
        self.sequence += 1
        message_id = self.sequence
        deadline = time.monotonic() + CDP_COMMAND_TIMEOUT_SECONDS
        self.connection.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(
                    f"CDP command timeout after {CDP_COMMAND_TIMEOUT_SECONDS:.0f}s "
                    f"while waiting for {method}"
                )
            response = self._receive(
                timeout=remaining,
                timeout_message=(
                    f"CDP command timeout after {CDP_COMMAND_TIMEOUT_SECONDS:.0f}s "
                    f"while waiting for {method}"
                ),
            )
            if response.get("id") != message_id:
                if response.get("method"):
                    self.events.append(response)
                continue
            if "error" in response:
                raise RuntimeError(f"{method}: {response['error']}")
            return response.get("result", {})

    def discard_events(self, method: str) -> None:
        self.events = [event for event in self.events if event.get("method") != method]

    def wait_for_event(
        self,
        method: str,
        predicate,
        *,
        timeout: float,
        phase: str,
    ) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            for index, event in enumerate(self.events):
                if event.get("method") == method and predicate(event):
                    return self.events.pop(index)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"{phase} timeout after {timeout:.0f}s")

            event = self._receive(
                timeout=remaining,
                timeout_message=(
                    f"{phase} timeout after {timeout:.0f}s while waiting for {method}"
                ),
            )
            if event.get("method"):
                self.events.append(event)

    def close(self) -> None:
        self.connection.close()


def wait_for_debugger(port: int) -> None:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    deadline = time.monotonic() + CHROME_STARTUP_TIMEOUT_SECONDS
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(endpoint, timeout=0.4):
                return
        except OSError as error:
            last_error = error
            time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(
        f"Chrome startup timeout after {CHROME_STARTUP_TIMEOUT_SECONDS:.0f}s: "
        f"DevTools endpoint {endpoint} was unavailable; last_error={last_error!r}"
    )


def new_page(port: int) -> CDP:
    endpoint = f"http://127.0.0.1:{port}/json/new?{quote('about:blank', safe=':/')}"
    request = Request(endpoint, method="PUT")
    try:
        with urlopen(request, timeout=PAGE_CREATION_TIMEOUT_SECONDS) as response:
            page = json.load(response)
    except OSError as error:
        reason = getattr(error, "reason", None)
        if isinstance(error, TimeoutError) or isinstance(reason, TimeoutError):
            raise RuntimeError(
                f"Chrome page creation timeout after {PAGE_CREATION_TIMEOUT_SECONDS:.0f}s "
                f"for {endpoint}"
            ) from error
        raise RuntimeError(
            f"Chrome page creation request failed for {endpoint}: {error!r}"
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Chrome page creation returned invalid JSON from {endpoint}: {error}"
        ) from error

    if not isinstance(page, dict):
        raise RuntimeError(
            f"Chrome page creation response from {endpoint} must be a JSON object"
        )
    websocket_url = page.get("webSocketDebuggerUrl")
    if not websocket_url:
        raise RuntimeError(
            f"Chrome page creation response from {endpoint} omitted webSocketDebuggerUrl"
        )
    return CDP(websocket_url)


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
    cdp.call("Page.setLifecycleEventsEnabled", {"enabled": True})
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
    cdp.discard_events("Page.lifecycleEvent")
    navigation = cdp.call("Page.navigate", {"url": target})
    if navigation.get("errorText"):
        raise RuntimeError(f"Navigation failed for {target}: {navigation['errorText']}")

    frame_id = navigation.get("frameId")
    loader_id = navigation.get("loaderId")

    def is_target_load(event: dict) -> bool:
        params = event.get("params", {})
        return (
            params.get("name") == "load"
            and (not frame_id or params.get("frameId") == frame_id)
            and (not loader_id or params.get("loaderId") == loader_id)
        )

    cdp.wait_for_event(
        "Page.lifecycleEvent",
        is_target_load,
        timeout=NAVIGATION_TIMEOUT_SECONDS,
        phase=f"Navigation load event for {target}",
    )

    expected_url = target.rstrip("/")
    selectors = json.dumps(CRITICAL_DOM_SELECTORS)
    deadline = time.monotonic() + DOM_READY_TIMEOUT_SECONDS
    last_state = None
    while time.monotonic() < deadline:
        last_state = evaluate(
            cdp,
            f"""
            (() => {{
              const selectors = {selectors};
              return {{
                href: window.location.href,
                readyState: document.readyState,
                missing: selectors.filter((selector) => !document.querySelector(selector)),
              }};
            }})()
            """,
        )
        if (
            isinstance(last_state, dict)
            and str(last_state.get("href", "")).rstrip("/") == expected_url
            and last_state.get("readyState") == "complete"
            and not last_state.get("missing")
        ):
            return
        time.sleep(POLL_INTERVAL_SECONDS)

    raise RuntimeError(
        f"DOM readiness timeout after {DOM_READY_TIMEOUT_SECONDS:.0f}s for {target}: "
        f"last_state={last_state!r}"
    )


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
