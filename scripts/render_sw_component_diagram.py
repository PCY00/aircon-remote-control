"""Render the current smart-home software component diagram as one portable SVG.

Every component names the code it stands for; the run stops when a source path is
missing or a label would overflow its box. The SVG has no scripts, external fonts
or raster images. Layout coordinates are hand-placed so arrows avoid boxes.
"""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture" / "smart-home-sw-components.svg"
WIDTH, HEIGHT = 1800, 1690
FONT = "'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif"
INK, MUTED = "#0f172a", "#475569"
FLOW = {
    "local": "#2563eb",   # ① 집 안 에어컨 제어
    "remote": "#9333ea",  # ② 가족 앱 원격 제어
    "sensor": "#16a34a",  # ③ 센서
    "notify": "#ea580c",  # ④ 가족 알림
    "auth": "#0891b2",    # ⑤ 로그인·인증
    "shared": "#334155",  # 여러 흐름이 함께 지나가는 공통 경로
    "inner": "#94a3b8",   # 내부 호출·데이터 사용
}

# (x, y, w, h, title, title_x) — 실행 장치·네트워크 경계
NODES = [
    (30, 100, 1080, 200, "가족 휴대폰 · 가족 앱 com.aircon.family 0.5.1 (Android)", 46),
    (1130, 100, 640, 200, "웹 화면 클라이언트", 1146),
    (30, 326, 1740, 120, "인터넷·외부 서비스", 900),
    (30, 472, 1076, 340, "Galaxy A50 · Android 11 · Termux runit 서비스", 262),
    (1520, 472, 250, 340, "개발 PC (Windows) · 관리 경로", 1534),
    (30, 848, 1740, 432, "각 집 Raspberry Pi · Raspberry Pi OS · systemd 사용자 서비스", 46),
    (606, 1296, 682, 376, "IR 송수신 하드웨어 · 에어컨", 622),
    (1304, 1296, 466, 376, "Zigbee 망 장치", 1320),
]
# (x, y, w, h, label, label_x, label_y, anchor) — 프로세스·서비스 경계
PROCESSES = [
    (258, 506, 832, 290, "central-server · Flask + waitress · 127.0.0.1:8001", 1076, 524, "end"),
    (46, 882, 270, 380, "aircon-central-agent (systemd)", 60, 900, "start"),
    (332, 882, 956, 308, "aircon-controller · FastAPI/uvicorn :8001 · systemd", 1274, 1182, "end"),
    (1304, 882, 450, 196, "Docker compose (deploy/zigbee)", 1318, 900, "start"),
    (1316, 1390, 442, 266, "ESP32-H2 SuperMini 펌웨어 · ESP-IDF 5.5 (요청→큐→인코더→RMT)", 1328, 1408, "start"),
]

S = "server/"
AND = S + "android/family-app/app/src/main/java/com/aircon/family/"
CS = S + "services/central-server/central_server/"
AG = S + "services/pi-central-agent/agent.py"
FW = "firmware/esp32-h2-zigbee-ir-node/main/"
# id: (x, y, w, h, kind, title, lines, sources); kind: comp | ext | data | hw | tool | mgmt
COMPONENTS = {
    # 가족 휴대폰
    "P2": (46, 150, 196, 92, "comp", "ApiClient", ["EndpointPolicy · 오류 문구", "HTTPS /v1 요청 (ID 토큰)"],
           [AND + "ApiClient.java", AND + "EndpointPolicy.java", AND + "ApiErrorMessages.java"]),
    "P1": (258, 150, 196, 92, "comp", "FamilyActivity", ["홈·기록·설정·에어컨 조작", "AirconUi · HomeListState", "CommandPoll (결과 확인)"],
           [AND + "FamilyActivity.java", AND + "AirconUi.java", AND + "HomeListState.java", AND + "CommandPoll.java"]),
    "P3": (470, 150, 196, 92, "comp", "FirebaseSession", ["AuthSession", "Google 로그인 → Firebase", "ID 토큰 갱신"],
           [AND + "FirebaseSession.java", AND + "AuthSession.java"]),
    "P5": (682, 150, 196, 92, "comp", "FamilyMessagingService", ["PushPolicy", "계정·집·수신 선택 확인", "→ Android 알림 표시"],
           [AND + "FamilyMessagingService.java", AND + "PushPolicy.java"]),
    "P4": (894, 150, 196, 92, "comp", "PushManager", ["PushSyncWorker (WorkManager)", "FCM 토큰·알림 선택 등록"],
           [AND + "PushManager.java", AND + "PushSyncWorker.java"]),
    # 웹 화면 클라이언트
    "W1": (1146, 150, 196, 92, "ext", "휴대폰·PC 브라우저", ["Tailscale 앱으로 접속", "집 밖에서 대시보드 사용"], []),
    "W2": (1358, 150, 196, 92, "comp", "Pi 터치 화면 키오스크", ["Chromium 전체 화면", "aircon-kiosk.service", "127.0.0.1:8001"],
           ["deploy/systemd/aircon-kiosk.service", "scripts/run_kiosk.sh"]),
    "W3": (1570, 150, 184, 92, "comp", "웹 화면 (SPA)", ["index.html · sensors.js", "automations.js · SSE 구독", "Pi :8001이 내려줌"],
           ["app/static/index.html", "app/static/sensors.js", "app/static/automations.js"]),
    # 외부 서비스
    "E4": (46, 368, 196, 66, "ext", "Cloudflare Quick Tunnel", ["공개 HTTPS 엣지", "주소가 바뀌는 시험용"], []),
    "E2": (258, 368, 196, 66, "ext", "Google 공개 인증서", ["ID 토큰 서명 확인용 키", "max-age 캐시 · 만료 후 1시간 유예"], []),
    "E1": (470, 368, 196, 66, "ext", "Google 로그인", ["Firebase Authentication", "ID 토큰 발급"], []),
    "E3": (682, 368, 196, 66, "ext", "Firebase Cloud Messaging", ["FCM HTTP v1", "휴대폰으로 푸시 전달"], []),
    "E5": (1146, 368, 196, 66, "ext", "Tailscale 사설망", ["Pi :8001 접근 경로", "공용 인터넷 직접 노출 없음"], []),
    # Galaxy A50
    "A1": (46, 506, 196, 74, "comp", "central-tunnel", ["tunnel.py + cloudflared", "준비 확인 후 터널 시작"],
           [S + "services/central-tunnel/tunnel.py"]),
    "A8": (46, 596, 196, 80, "data", "central.sqlite3", ["DB 스키마 5", "집·가족·제어·알림 작업"],
           [CS + "schema.py", CS + "storage.py"]),
    "A9": (46, 692, 196, 104, "mgmt", "A50 관리 앱", ["com.aircon.a50manager", "부팅·Wi-Fi 승인", "무선 디버깅·SSH 복구"],
           [S + "android/a50-manager/src/com/aircon/a50manager/MainActivity.java"]),
    "A3": (274, 534, 188, 66, "comp", "FirebaseIdentity", ["Certificates (auth.py)", "ID 토큰 서명·만료 확인"], [CS + "auth.py"]),
    "A4": (478, 534, 188, 66, "comp", "Households", ["집·가족 역할·초대", "허브 연결·기록 저장"], [CS + "households.py"]),
    "A7": (682, 534, 188, 66, "comp", "PushWorker·FCMSender", ["전송 직전 권한 재확인", "만료·재시도 후 FCM 전송"],
           [CS + "push.py", CS + "fcm.py"]),
    "A5": (886, 534, 188, 66, "comp", "Controls (control.py)", ["제어 대기열 30초 만료", "Pi 온라인·결과 기록"], [CS + "control.py"]),
    "A6": (682, 612, 188, 64, "comp", "PushStore · Preferences", ["설치 토큰·알림 선택", "집별 전송 작업 만들기"],
           [CS + "push.py", CS + "preferences.py"]),
    "A2": (274, 704, 800, 78, "comp", "API /v1 (api.py · web.py)", [
        "사용자 경로: Bearer ID 토큰 → FirebaseIdentity → 현재 집 역할 확인 (owner·member만 제어, viewer는 조회만)",
        "허브 경로: 허브 키 해시 → 서버에 저장된 집 · /v1/hub/events · /v1/hub/control/status·next·result"],
           [CS + "api.py", CS + "web.py"]),
    # 개발 PC
    "T1": (1534, 506, 222, 52, "tool", "server/scripts/android", ["adb·ssh로 A50 서버·앱 배포"], [S + "scripts/android/a50_adb.py"]),
    "T2": (1534, 566, 222, 52, "tool", "server/scripts/pi", ["Pi 연결 서비스 배포·제어 설정"], [S + "scripts/pi/configure_control.py"]),
    "T3": (1534, 626, 222, 52, "tool", "scripts/deploy.ps1", ["Pi 앱 단방향 배포 (기본 미리보기)"], ["scripts/deploy.ps1"]),
    "T4": (1534, 686, 222, 52, "tool", "esp32_h2_firmware.ps1", ["ESP-IDF 빌드 · 굽기는 별도 승인"], ["scripts/esp32_h2_firmware.ps1"]),
    "T5": (1534, 746, 222, 52, "tool", "Gradle · 블로그 도구", ["APK 서명 빌드 · 사진 메타데이터 검사"],
           [S + "scripts/android/build_family_app.py", "scripts/sanitize_blog_images.py"]),
    # Pi 연결 서비스
    "R20": (60, 912, 242, 56, "comp", "LocalController", ["→ Pi API /api/v1/devices", "명령 대기 20초 · 4xx는 실패"], [AG]),
    "R19": (60, 980, 242, 56, "comp", "ControlChannel", ["상태·다음 명령·결과 보고", "/v1/hub/control/*"], [AG]),
    "R18": (60, 1048, 242, 56, "comp", "Sender", ["새 기록 전송", "POST /v1/hub/events"], [AG]),
    "R17": (60, 1116, 242, 56, "data", "outbox.sqlite3 (Store)", ["전송 대기·진행 위치", "제어 실행 기록"], [AG]),
    "R16": (60, 1184, 242, 56, "comp", "원본 기록 읽기", ["sensors·automations DB", "읽기 전용, 원본 수정 없음"], [AG]),
    # Pi FastAPI 앱
    "R11": (346, 918, 216, 70, "comp", "CaptureService", ["IrCtlReceiver · CaptureStore", "IR 학습 녹화 (/dev/lirc1)"],
            ["app/ir/service.py", "app/ir/backend.py", "app/ir/store.py"]),
    "R10": (582, 918, 216, 70, "comp", "EventHub", ["SSE 이벤트 방송", "기기·센서·자동화 변경"], ["app/events.py"]),
    "R3": (818, 918, 216, 70, "comp", "DeviceService", ["명령 실행 · 기기별 잠금", "H2 연결이면 Zigbee, 아니면 GPIO"],
           ["app/devices/service.py"]),
    "R2": (1054, 918, 216, 70, "comp", "REST·SSE API (main.py)", ["/api/v1/devices·sensors", "/zigbee · /ir · /events"], ["app/main.py"]),
    "R12": (346, 1002, 216, 70, "data", "device_profiles", ["Carrier CS-A061GS", "commands.json · Coolix 온도표"],
            ["device_profiles/air_conditioner/Carrier/CS-A061GS/commands.json"]),
    "R4": (582, 1002, 216, 70, "comp", "DeviceCommandResolver", ["DeviceProfileCatalog", "프레임 생성·경제운전 재구성"],
           ["app/devices/commands.py", "app/devices/catalog.py"]),
    "R6": (818, 1002, 216, 70, "data", "RegisteredDeviceStore", ["기기 JSON", "last_desired_state (요청값)"], ["app/devices/store.py"]),
    "R7": (1054, 1002, 216, 70, "comp", "PahoSensorBridge", ["MQTT 구독 · H2 요청/결과", "Zigbee 가입 허용 관리"],
           ["app/integrations/mqtt.py"]),
    "R9": (582, 1086, 216, 70, "comp", "AutomationService", ["문 열림 + 냉방 경고", "automations.sqlite3"],
           ["app/automations/service.py", "app/automations/store.py"]),
    "R5": (818, 1086, 216, 70, "comp", "IrCtlTransport", ["ir-ctl 원시 송신", "/dev/lirc0 (gpio-ir-tx)"], ["app/devices/transport.py"]),
    "R8": (1054, 1086, 216, 70, "comp", "SensorService", ["SensorStore", "sensors.sqlite3 · 문 기록"],
           ["app/sensors/service.py", "app/sensors/store.py"]),
    # Docker
    "R13": (1320, 912, 418, 56, "comp", "Mosquitto", ["로컬 MQTT 브로커 · zigbee2mqtt/# 주제"], ["deploy/zigbee/mosquitto/mosquitto.conf"]),
    "R14": (1320, 986, 418, 80, "comp", "Zigbee2MQTT 2.x", ["외부 변환기 aircon-h2-ir.mjs",
                                                         "airconIr 클러스터 0xFF00 · send/sendV2 → ir_result"],
            ["deploy/zigbee/compose.yaml", "deploy/zigbee/zigbee2mqtt/external_converters/aircon-h2-ir.mjs"]),
    "R15": (1320, 1100, 418, 50, "hw", "ZBDongle-P 코디네이터 (USB 하드웨어)", ["Zigbee2MQTT 컨테이너가 사용 · 망 관리·가입 허용"], []),
    # 하드웨어
    "D4": (622, 1336, 180, 74, "hw", "실제 리모컨", ["IR 학습 원본 신호", "remote 16214-15597"],
           ["signals/remote-16214-15597/metadata/economy-press-01-multiframe.json"]),
    "D3": (818, 1336, 216, 74, "hw", "Pi GPIO IR LED·수신기", ["송신 /dev/lirc0 (gpio-ir-tx)", "수신 /dev/lirc1 (GPIO17)"], []),
    "D1": (1054, 1336, 216, 74, "hw", "Carrier CS-A061GS 에어컨", ["IR 수신 (Coolix 48비트)", "실제 상태는 읽지 못함"],
           ["device_profiles/air_conditioner/Carrier/CS-A061GS/profile.json"]),
    "Z1": (1320, 1330, 434, 48, "ext", "Zigbee 문·온습도 센서", ["상태 보고 → Zigbee2MQTT"], []),
    "H1": (1328, 1418, 418, 40, "comp", "ZCL airconIr 0xFF00 · 엔드포인트 10", ["요청 확인 · 중복 요청 처리 · ir_result 응답"], [FW + "main.c"]),
    "H2": (1328, 1464, 418, 40, "comp", "IR 작업 큐", ["송신 태스크가 하나씩 처리 · RMT 오류 시 송신 중지"], [FW + "main.c"]),
    "H3": (1328, 1510, 418, 40, "comp", "Carrier 프레임 인코더 (carrier_profile.h)", ["Coolix 온도표 · 경제운전 신호 1회"],
           [FW + "carrier_profile.h", FW + "ir_protocol.h"]),
    "H4": (1328, 1556, 418, 40, "comp", "RMT IR 송신 (ir_tx.c)", ["38 kHz 반송파 · 캐시 안전 ISR"], [FW + "ir_tx.c"]),
    "H5": (1328, 1602, 418, 40, "comp", "접속 재시도 · capability 2", ["1→60초 재접속 · 로컬 빌드만, 보드에는 아직 굽지 않음"],
           [FW + "commissioning_retry.h"]),
}

# (flow, points, both_ends, dashed, label, label_xy, anchor)
EDGES = [
    # 휴대폰 안
    ("shared", [(258, 196), (244, 196)], False, False, None, None, None),
    ("auth", [(454, 196), (468, 196)], False, False, None, None, None),
    ("shared", [(992, 150), (992, 140), (144, 140), (144, 148)], False, False, "설치 등록·알림 선택", (700, 136), "middle"),
    # 휴대폰 ↔ 외부 서비스 ↔ A50
    ("shared", [(144, 242), (144, 366)], True, False, "HTTPS /v1 · ID 토큰", (150, 300), "start"),
    ("shared", [(144, 434), (144, 504)], True, False, "터널 (A50이 먼저 연결)", (150, 462), "start"),
    ("auth", [(568, 242), (568, 366)], True, False, "Google 로그인", (574, 300), "start"),
    ("notify", [(776, 366), (776, 244)], False, False, "푸시", (782, 300), "start"),
    ("auth", [(440, 532), (440, 436)], False, False, "공개 키 조회", (446, 462), "start"),
    ("notify", [(776, 532), (776, 436)], False, False, "FCM HTTP v1", (782, 462), "start"),
    # A50 안
    ("shared", [(244, 545), (250, 545), (250, 743), (272, 743)], False, False, None, None, None),
    ("auth", [(368, 702), (368, 602)], False, False, None, None, None),
    ("shared", [(572, 702), (572, 602)], False, False, None, None, None),
    ("notify", [(666, 585), (674, 585), (674, 644), (680, 644)], False, False, None, None, None),
    ("notify", [(776, 612), (776, 602)], False, False, None, None, None),
    ("shared", [(776, 702), (776, 678)], False, False, None, None, None),
    ("remote", [(980, 702), (980, 602)], False, False, "명령 등록·조회", (986, 662), "start"),
    # 웹 클라이언트 → Pi API
    ("local", [(1244, 242), (1244, 366)], False, False, "Tailscale", (1250, 300), "start"),
    ("local", [(1200, 434), (1200, 916)], False, False, "HTTP :8001", (1206, 462), "start"),
    ("local", [(1456, 242), (1456, 830), (1240, 830), (1240, 916)], False, False, "127.0.0.1:8001", (1462, 300), "start"),
    # Pi 연결 서비스 ↔ 엣지 (왼쪽 여백)
    ("remote", [(60, 1008), (22, 1008), (22, 412), (44, 412)], True, False, None, None, None),
    ("notify", [(60, 1076), (14, 1076), (14, 394), (44, 394)], False, False, None, None, None),
    # Pi 연결 서비스 안
    ("remote", [(280, 980), (280, 970)], False, False, None, None, None),
    ("notify", [(280, 1116), (280, 1106)], False, False, None, None, None),
    ("notify", [(280, 1184), (280, 1174)], False, False, None, None, None),
    ("remote", [(302, 940), (324, 940), (324, 902), (1150, 902), (1150, 916)], False, False,
     "POST /api/v1/devices/{id}/commands", (590, 897), "start"),
    ("notify", [(690, 1156), (690, 1212), (304, 1212)], False, True, "읽기 전용 SQLite", (430, 1207), "middle"),
    # Pi 앱 안
    ("local", [(1054, 953), (1036, 953)], False, False, None, None, None),
    ("inner", [(818, 973), (808, 973), (808, 1037), (800, 1037)], False, False, None, None, None),
    ("inner", [(582, 1037), (564, 1037)], False, False, None, None, None),
    ("inner", [(926, 988), (926, 1000)], False, False, None, None, None),
    ("local", [(1034, 968), (1044, 968), (1044, 1037), (1052, 1037)], False, False, None, None, None),
    ("local", [(1044, 1037), (1044, 1121), (1036, 1121)], False, False, None, None, None),
    ("sensor", [(1162, 1072), (1162, 1084)], False, False, None, None, None),
    ("shared", [(1270, 1022), (1294, 1022), (1294, 940), (1318, 940)], True, False, "MQTT", (1298, 984), "start"),
    ("shared", [(1529, 968), (1529, 984)], True, False, None, None, None),
    ("shared", [(1529, 1066), (1529, 1098)], True, False, None, None, None),
    # Pi → 현장 장치
    ("local", [(926, 1156), (926, 1334)], False, False, "ir-ctl", (932, 1290), "start"),
    ("sensor", [(1450, 1328), (1450, 1152)], False, False, "Zigbee 보고", (1456, 1290), "start"),
    ("local", [(1738, 1125), (1784, 1125), (1784, 1438), (1748, 1438)], True, False,
     "Zigbee sendV2 → ir_result", (1778, 1290), "end"),
    ("local", [(1034, 1373), (1052, 1373)], False, False, "적외선", (1043, 1328), "middle"),
    ("inner", [(802, 1373), (816, 1373)], False, True, None, None, None),
    ("local", [(1328, 1576), (1296, 1576), (1296, 1373), (1272, 1373)], False, False, "H2 적외선 38 kHz", (1286, 1500), "end"),
]

LEGEND_FLOWS = [
    ("local", "① 집 안 에어컨 제어: 웹 화면 → Pi API → H2(Zigbee) 또는 Pi GPIO → 적외선"),
    ("remote", "② 가족 앱 원격 제어: 앱 → A50 Controls(30초) → Pi 연결 서비스가 가져가 실행"),
    ("sensor", "③ 센서: Zigbee 보고 → Zigbee2MQTT → MQTT → SensorService"),
    ("notify", "④ 가족 알림: Pi 기록 → 연결 서비스 → A50 → FCM → 앱 알림"),
    ("auth", "⑤ 로그인·인증: Google ID 토큰 발급 → A50이 공개 키로 확인"),
    ("shared", "공통 경로: HTTPS·MQTT처럼 여러 흐름이 함께 지나가는 연결"),
    ("inner", "내부 호출·데이터 사용 (점선은 읽기 전용·학습 신호)"),
]
LEGEND_NOTES = [
    "• 보냈는지 모르는 명령(시간 초과·연결 끊김)은 다시 보내지 않고 '알 수 없음'으로 남긴다.",
    "• IR은 단방향이라 에어컨의 실제 상태는 읽지 못하고 마지막 요청값만 저장한다.",
    "• 경제운전은 냉방 중일 때만 보낸다: 경제운전 신호 1회 + 현재 온도·자동풍 상태 2회.",
    "• 한 집에는 활성 Pi(허브) 한 대만 연결한다. Pi는 집 ID를 고르지 않고 허브 키로만 인증한다.",
]


FONT_FILES = {"normal": Path("C:/Windows/Fonts/malgun.ttf"), "bold": Path("C:/Windows/Fonts/malgunbd.ttf")}
_MEASURE: dict = {}


def text_width(text: str, size: float, weight: str = "normal") -> float:
    """Measure with Malgun Gothic when available (the first font the SVG asks for)."""
    try:
        from PIL import ImageFont
        key = (weight, size)
        if key not in _MEASURE and FONT_FILES[weight].is_file():
            _MEASURE[key] = ImageFont.truetype(str(FONT_FILES[weight]), size=round(size * 4))
        if key in _MEASURE:
            return _MEASURE[key].getlength(text) / 4
    except ImportError:
        pass
    width = 0.0
    for char in text:
        if ord(char) >= 0x1100:
            width += size * 1.0
        elif char in " .,:·|/()[]'`-":
            width += size * 0.34
        elif char.isupper() or char in "→＋+=_%#@&":
            width += size * 0.66
        else:
            width += size * 0.56
    return width


def t(x, y, text, size, *, weight="normal", fill=INK, anchor="start"):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}">{escape(text)}</text>')


def component(x, y, w, h, kind, title, lines):
    compact = h <= 44
    title_size, line_size = (12, 10.5) if compact else (13, 11)
    for text, size, weight in [(title, title_size, "bold")] + [(line, line_size, "normal") for line in lines]:
        if text_width(text, size, weight) > w - (32 if text == title else 16):
            raise ValueError(f"Label overflows {title!r}: {text!r}")
    stroke, fill, dash = {
        "comp": ("#475569", "#ffffff", ""),
        "ext": ("#64748b", "#f8fafc", ' stroke-dasharray="6 4"'),
        "data": ("#475569", "#ffffff", ""),
        "hw": ("#64748b", "#e2e8f0", ""),
        "tool": ("#94a3b8", "#ffffff", ' stroke-dasharray="3 3"'),
        "mgmt": ("#94a3b8", "#ffffff", ' stroke-dasharray="3 3"'),
    }[kind]
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.4"{dash}/>']
    ix, iy = x + w - 20, y + 7
    if kind == "data":  # 데이터 저장소: 원통
        out.append(f'<path d="M{ix} {iy + 3}v8a6 3 0 0 0 12 0v-8" fill="none" stroke="{stroke}" stroke-width="1.1"/>'
                   f'<ellipse cx="{ix + 6}" cy="{iy + 3}" rx="6" ry="3" fill="none" stroke="{stroke}" stroke-width="1.1"/>')
    elif kind in ("comp", "mgmt"):  # UML 컴포넌트 기호
        out.append(f'<rect x="{ix + 2}" y="{iy}" width="11" height="13" fill="#fff" stroke="{stroke}" stroke-width="1.1"/>'
                   f'<rect x="{ix - 1}" y="{iy + 2.5}" width="6" height="3" fill="#fff" stroke="{stroke}" stroke-width="1"/>'
                   f'<rect x="{ix - 1}" y="{iy + 7.5}" width="6" height="3" fill="#fff" stroke="{stroke}" stroke-width="1"/>')
    tight = compact or h < 64
    top, step = y + (15 if compact else 18 if tight else 21), 15 if tight else 17
    if top + step * len(lines) > y + h - 4:
        raise ValueError(f"Too many lines for {title!r} at height {h}")
    out.append(t(x + 10, top, title, title_size, weight="bold"))
    for index, line in enumerate(lines):
        out.append(t(x + 10, top + step * (index + 1), line, line_size, fill=MUTED))
    return out


def edge(flow, points, both, dashed, label, label_xy, anchor):
    color = FLOW[flow]
    path = "M" + " L".join(f"{x} {y}" for x, y in points)
    marker = f' marker-end="url(#a-{flow})"' + (f' marker-start="url(#s-{flow})"' if both else "")
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    width = 1.4 if flow == "inner" else 2
    out = [f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width}"{dash}{marker}/>']
    if label:
        x, y = label_xy
        out.append(f'<text x="{x}" y="{y}" font-size="10.5" font-weight="bold" fill="{color}" text-anchor="{anchor}" '
                   f'stroke="#ffffff" stroke-width="4" paint-order="stroke">{escape(label)}</text>')
    return out


def render() -> str:
    missing = [path for *_, sources in COMPONENTS.values() for path in sources if not (ROOT / path).is_file()]
    if missing:
        raise FileNotFoundError("Diagram source paths missing: " + ", ".join(sorted(set(missing))))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" '
           f'font-family="{FONT}" role="img" aria-labelledby="title desc">',
           '<title id="title">스마트홈 소프트웨어 아키텍처 · 컴포넌트 다이어그램</title>',
           '<desc id="desc">가족 앱, A50 중앙 서버, Pi 게이트웨이, ESP32-H2 IR 노드와 외부 서비스의 컴포넌트와 연결</desc>',
           "<defs>"]
    for flow, color in FLOW.items():
        out.append(f'<marker id="a-{flow}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                   f'orient="auto"><path d="M0 0L10 5L0 10z" fill="{color}"/></marker>')
        out.append(f'<marker id="s-{flow}" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" '
                   f'orient="auto"><path d="M10 0L0 5L10 10z" fill="{color}"/></marker>')
    out.append("</defs>")
    out.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#ffffff"/>')
    out.append(t(32, 52, "스마트홈 소프트웨어 아키텍처 · 컴포넌트 다이어그램", 26, weight="bold"))
    out.append(t(32, 80, "2026-10-14 로컬 코드 기준 · Pi 앱 0.7.0 · 중앙 서버·가족 앱 0.5.1 (DB 스키마 5) · "
                 "H2 펌웨어 capability 2는 로컬 빌드만 하고 보드에는 아직 굽지 않음", 14, fill=MUTED))
    for x, y, w, h, title, title_x in NODES:
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.6"/>')
        out.append(t(title_x, y + 24, title, 15, weight="bold"))
    for x, y, w, h, label, lx, ly, anchor in PROCESSES:
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#eef2f7" stroke="#cbd5e1" stroke-width="1.2"/>')
        out.append(t(lx, ly, label, 11.5, weight="bold", fill=MUTED, anchor=anchor))
    for x, y, w, h, kind, title, lines, _ in COMPONENTS.values():
        out.extend(component(x, y, w, h, kind, title, lines))
    for spec in EDGES:
        out.extend(edge(*spec))
    # 노드 사이 여백에 둔 설명
    out.append(t(36, 836, "② ④ Pi 연결 서비스 → 엣지 → A50: 허브 키 HTTPS (Pi가 먼저 요청)", 10.5, weight="bold", fill=FLOW["remote"]))
    out.append(t(622, 1446, "• 학습: 리모컨 → IR 수신기 → CaptureService", 11, fill=MUTED))
    out.append(t(622, 1466, "• 송신: Pi GPIO 또는 H2 중 기기 등록에 따라 한 경로", 11, fill=MUTED))
    out.append(t(622, 1486, "• 결과 확인은 사람이 에어컨을 보고 한다", 11, fill=MUTED))
    # 범례
    out.append('<rect x="30" y="1296" width="560" height="376" rx="12" fill="#ffffff" stroke="#94a3b8" stroke-width="1.6"/>')
    out.append(t(46, 1320, "읽는 법", 15, weight="bold"))
    y = 1348
    for flow, text in LEGEND_FLOWS:
        if text_width(text, 11.5) > 470:
            raise ValueError("Legend line overflows: " + text)
        dash = ' stroke-dasharray="5 4"' if flow == "inner" else ""
        out.append(f'<path d="M46 {y - 4} L86 {y - 4}" stroke="{FLOW[flow]}" stroke-width="2.2"{dash} marker-end="url(#a-{flow})"/>')
        out.append(t(96, y, text, 11.5))
        y += 22
    y += 4
    samples = [("comp", "우리 코드"), ("ext", "외부 서비스"), ("data", "데이터 저장소"), ("hw", "하드웨어")]
    for index, (kind, label) in enumerate(samples):
        out.extend(component(46 + index * 134, y, 124, 34, kind, label, []))
    y += 58
    for note in LEGEND_NOTES:
        if text_width(note, 11) > 528:
            raise ValueError("Legend note overflows: " + note)
        out.append(t(46, y, note, 11, fill=MUTED))
        y += 20
    out.append(t(46, y + 6, "생성: scripts/render_sw_component_diagram.py", 10.5, fill="#94a3b8"))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.output.write_text(render(), encoding="utf-8", newline="\n")
    print(f"SW_COMPONENT_DIAGRAM={args.output.relative_to(ROOT).as_posix()} COMPONENTS={len(COMPONENTS)} EDGES={len(EDGES)}")


if __name__ == "__main__":
    main()
