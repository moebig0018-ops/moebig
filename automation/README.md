# 이미지 기반 클릭 자동화 스케줄러

화면에서 특정 이미지를 찾아 클릭하는 범용 데스크톱 자동화 도구입니다.
반복 업무·QA 테스트 자동화(확인 대화상자 처리, 정기 새로고침, 정해진
시각의 체크인 클릭 등)를 목적으로 하며, **서드파티 프로그램/게임의
이용약관을 우회하는 매크로 용도로는 사용하지 마세요.**

## 설치

```bash
pip install -r requirements.txt
```

Linux에서 GUI 자동화를 쓰려면 `scrot` 또는 `python3-xlib`이 필요할 수
있습니다 (배포판에 따라 다름). macOS는 손쉬운 사용(Accessibility) 및
화면 기록 권한을 터미널/파이썬에 부여해야 합니다.

## 사용법

```bash
cp config.example.yaml config.yaml
# config.yaml을 열어 tasks의 image 경로와 스케줄을 실제 환경에 맞게 수정

python scheduler.py --config config.yaml
python scheduler.py --config config.yaml --dry-run   # 실제 클릭 없이 로그만 확인
```

### 이미지 준비

각 task의 `image`는 화면에서 찾을 대상의 스크린샷 조각(PNG)입니다.
버튼/아이콘만 딱 잘라서 저장하세요 — 배경이 많이 포함되면 매칭 정확도가
떨어집니다. `pyautogui.screenshot()`으로 캡처 후 잘라내는 것을 권장합니다.

### 실행 모드

| 모드 | 동작 |
|---|---|
| `watch` | 이미지가 나타날 때까지 계속 폴링, 발견 즉시 클릭 (쿨다운/최대횟수 설정 가능) |
| `cron` | 매일 정해진 시각(`at: "HH:MM"`)에 1회 시도, 실패 시 재시도 |
| `interval` | N분마다 반복 탐색 |

## 안전장치

- **Fail-safe**: 마우스를 화면 좌상단 코너로 이동하면 즉시 중단됩니다
  (`pyautogui.FAILSAFE = True`).
- **dry-run**: `--dry-run` 또는 `config.yaml`의 `settings.dry_run: true`로
  실제 클릭 없이 동작을 미리 확인할 수 있습니다.
- **클릭 로그**: `settings.screenshot_on_click: true`면 클릭 직전
  화면을 `click_log/`에 저장해 사후 확인이 가능합니다.
- **cooldown / max_clicks**: `watch` 모드에서 같은 이미지에 대한
  연속·과도한 클릭을 막습니다.

## 한계

- `locateOnScreen`은 해상도/배율(DPI)·테마·언어 변경에 취약합니다.
  이미지가 안 잡히면 신뢰도(`confidence`)를 낮추거나 이미지를 다시
  캡처하세요.
- 원격 데스크톱·가상 디스플레이 없는 서버(CI 등)에서는 화면 자체가
  없어 동작하지 않습니다. 로컬 데스크톱 환경에서 실행하세요.
