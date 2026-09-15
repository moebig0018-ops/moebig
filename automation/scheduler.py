#!/usr/bin/env python3
"""Image-based click automation with scheduling.

Generic desktop automation tool: finds a reference image on screen and
clicks it, either continuously ("watch"), on a fixed daily time ("cron"),
or on a repeating interval ("interval"). Intended for repetitive
business/QA tasks on your own machine (confirm dialogs, refresh buttons,
check-in forms, etc.) — not for automating third-party applications
against their terms of service.

Usage:
    pip install -r requirements.txt
    cp config.example.yaml config.yaml   # edit tasks + image paths
    python scheduler.py --config config.yaml
    python scheduler.py --config config.yaml --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

try:
    import pyautogui
except Exception as exc:  # pragma: no cover - depends on a display being present
    pyautogui = None
    _PYAUTOGUI_IMPORT_ERROR = exc
else:
    _PYAUTOGUI_IMPORT_ERROR = None

try:
    import schedule
except Exception as exc:  # pragma: no cover
    schedule = None
    _SCHEDULE_IMPORT_ERROR = exc
else:
    _SCHEDULE_IMPORT_ERROR = None


log = logging.getLogger("click_scheduler")


@dataclass
class Settings:
    confidence: float = 0.85
    dry_run: bool = False
    screenshot_on_click: bool = True
    log_file: Optional[str] = "automation.log"


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(settings: Settings) -> None:
    handlers = [logging.StreamHandler(sys.stdout)]
    if settings.log_file:
        handlers.append(logging.FileHandler(settings.log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def _require_pyautogui() -> None:
    if pyautogui is None:
        raise RuntimeError(
            "pyautogui를 불러올 수 없습니다 (디스플레이가 없는 환경일 수 있음): "
            f"{_PYAUTOGUI_IMPORT_ERROR}"
        )


def locate_and_click(
    image_path: str,
    confidence: float,
    click_offset: tuple[int, int],
    dry_run: bool,
    screenshot_on_click: bool,
) -> bool:
    """Find `image_path` on screen and click its center + offset.

    Returns True if the image was found (and clicked, unless dry_run).
    """
    _require_pyautogui()

    if not Path(image_path).is_file():
        log.warning("이미지 파일을 찾을 수 없습니다: %s", image_path)
        return False

    try:
        box = pyautogui.locateOnScreen(image_path, confidence=confidence)
    except Exception as exc:
        # locateOnScreen raises if opencv isn't installed and confidence != 1.0
        log.error("이미지 탐색 실패 (%s): %s", image_path, exc)
        return False

    if box is None:
        return False

    center_x, center_y = pyautogui.center(box)
    x, y = center_x + click_offset[0], center_y + click_offset[1]

    if dry_run:
        log.info("[DRY-RUN] %s 발견 → (%d, %d) 클릭 예정 (실제 클릭 안 함)", image_path, x, y)
        return True

    if screenshot_on_click:
        shot_dir = Path("click_log")
        shot_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        pyautogui.screenshot(str(shot_dir / f"{stamp}.png"))

    pyautogui.click(x, y)
    log.info("클릭: %s → (%d, %d)", image_path, x, y)
    return True


class WatchTask:
    """Polls for an image indefinitely and clicks it when found."""

    def __init__(self, cfg: dict, settings: Settings):
        self.name = cfg["name"]
        self.image = cfg["image"]
        self.poll_interval = cfg.get("poll_interval_sec", 2)
        self.click_offset = tuple(cfg.get("click_offset", [0, 0]))
        self.cooldown = cfg.get("cooldown_sec", 5)
        self.max_clicks = cfg.get("max_clicks", 0)  # 0 = unlimited
        self.settings = settings
        self._click_count = 0
        self._last_click_at = 0.0

    def tick(self) -> None:
        if self.max_clicks and self._click_count >= self.max_clicks:
            return
        now = time.time()
        if now - self._last_click_at < self.cooldown:
            return
        found = locate_and_click(
            self.image,
            self.settings.confidence,
            self.click_offset,
            self.settings.dry_run,
            self.settings.screenshot_on_click,
        )
        if found:
            self._click_count += 1
            self._last_click_at = now


def build_cron_job(cfg: dict, settings: Settings):
    image = cfg["image"]
    click_offset = tuple(cfg.get("click_offset", [0, 0]))
    retry = cfg.get("retry", {})
    attempts = retry.get("attempts", 1)
    interval = retry.get("interval_sec", 5)

    def job():
        for attempt in range(1, attempts + 1):
            if locate_and_click(
                image, settings.confidence, click_offset, settings.dry_run, settings.screenshot_on_click
            ):
                return
            log.info("[%s] %d/%d 시도 실패, %ds 후 재시도", cfg["name"], attempt, attempts, interval)
            time.sleep(interval)
        log.warning("[%s] 모든 재시도 실패: %s", cfg["name"], image)

    return job


def build_interval_job(cfg: dict, settings: Settings):
    image = cfg["image"]
    click_offset = tuple(cfg.get("click_offset", [0, 0]))

    def job():
        locate_and_click(
            image, settings.confidence, click_offset, settings.dry_run, settings.screenshot_on_click
        )

    return job


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--dry-run", action="store_true", help="설정값과 무관하게 강제로 dry-run")
    args = parser.parse_args()

    if not args.config.is_file():
        print(f"설정 파일을 찾을 수 없습니다: {args.config}", file=sys.stderr)
        return 1

    raw = load_config(args.config)
    raw_settings = raw.get("settings", {})
    settings = Settings(
        confidence=raw_settings.get("confidence", 0.85),
        dry_run=args.dry_run or raw_settings.get("dry_run", False),
        screenshot_on_click=raw_settings.get("screenshot_on_click", True),
        log_file=raw_settings.get("log_file", "automation.log"),
    )
    setup_logging(settings)

    if pyautogui is None:
        log.error("pyautogui 로드 실패: %s", _PYAUTOGUI_IMPORT_ERROR)
        return 1
    if schedule is None:
        log.error("schedule 로드 실패: %s", _SCHEDULE_IMPORT_ERROR)
        return 1

    # 실수로 화면 전체를 클릭 폭주하지 않도록 pyautogui의 안전장치를 켠다:
    # 마우스를 화면 좌상단 코너로 이동하면 즉시 실행을 중단시킬 수 있다.
    pyautogui.FAILSAFE = True

    watch_tasks: list[WatchTask] = []
    tasks = raw.get("tasks", [])
    if not tasks:
        log.warning("config에 tasks가 비어 있습니다.")

    for cfg in tasks:
        mode = cfg.get("mode")
        name = cfg.get("name", "<unnamed>")
        if mode == "watch":
            watch_tasks.append(WatchTask(cfg, settings))
            log.info("[watch] 등록: %s (%s, poll=%ss)", name, cfg["image"], cfg.get("poll_interval_sec", 2))
        elif mode == "cron":
            at = cfg["at"]
            schedule.every().day.at(at).do(build_cron_job(cfg, settings))
            log.info("[cron] 등록: %s → 매일 %s", name, at)
        elif mode == "interval":
            every_minutes = cfg.get("every_minutes", 30)
            schedule.every(every_minutes).minutes.do(build_interval_job(cfg, settings))
            log.info("[interval] 등록: %s → %d분마다", name, every_minutes)
        else:
            log.error("알 수 없는 mode '%s' (task: %s) — 무시합니다.", mode, name)

    log.info(
        "스케줄러 시작 (dry_run=%s). 마우스를 화면 좌상단 코너로 이동하면 즉시 중단됩니다.",
        settings.dry_run,
    )

    try:
        while True:
            schedule.run_pending()
            for wt in watch_tasks:
                wt.tick()
            # watch 폴링 주기 중 가장 짧은 값으로 루프를 돈다 (없으면 1초).
            time.sleep(min((wt.poll_interval for wt in watch_tasks), default=1))
    except KeyboardInterrupt:
        log.info("사용자 중단 (Ctrl+C)")
        return 0
    except pyautogui.FailSafeException:
        log.info("Fail-safe 발동 (마우스가 화면 코너로 이동됨) — 종료합니다.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
