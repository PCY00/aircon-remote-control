"""Render the current component model as portable SVGs and an A0 vector PDF.

Run with Python + reportlab. SVGs contain editable text and shapes, no scripts,
external resources or raster images. The same measured primitives drive PDF.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from html import escape
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture"
COLORS = {
    "ink": "#172a3a",
    "muted": "#526779",
    "line": "#ccd8e1",
    "blue": "#2664ad",
    "blue_bg": "#edf5fd",
    "teal": "#087e83",
    "teal_bg": "#eaf7f5",
    "purple": "#7650a6",
    "purple_bg": "#f4effb",
    "amber": "#98620a",
    "amber_bg": "#fff8e8",
    "slate": "#617184",
    "slate_bg": "#f2f5f8",
    "white": "#ffffff",
    "background": "#f8fafc",
}


class Diagram:
    def __init__(self, width, height, *, base_size=12):
        self.width, self.height, self.base_size = width, height, base_size
        self.items, self.components, self.links = [], [], []

    def rect(self, x, y, w, h, *, fill="white", stroke="line", radius=8, dash=False):
        self.items.append(
            dict(
                type="rect",
                x=x,
                y=y,
                w=w,
                h=h,
                fill=COLORS.get(fill, fill),
                stroke=COLORS.get(stroke, stroke),
                radius=radius,
                dash=dash,
            )
        )

    def text(self, x, y, value, *, size=None, color="ink", bold=False, max_width=None):
        size = size or self.base_size
        font = "ArchitectureBold" if bold else "ArchitectureRegular"
        measured = pdfmetrics.stringWidth(value, font, size)
        if max_width is not None and measured > max_width + 0.5:
            raise ValueError(f"Text exceeds its box: {value} ({measured:.1f} > {max_width})")
        if x < 0 or x + measured > self.width + 0.5 or y - size < 0 or y > self.height:
            raise ValueError(f"Text outside canvas: {value}")
        self.items.append(
            dict(
                type="text",
                x=x,
                y=y,
                value=value,
                size=size,
                fill=COLORS.get(color, color),
                bold=bold,
                measured_width=measured,
            )
        )

    def wrapped(self, x, y, value, width, *, size=None, color="muted", bold=False, leading=None):
        size = size or self.base_size
        leading = leading or size * 1.5
        font = "ArchitectureBold" if bold else "ArchitectureRegular"
        lines = []
        for paragraph in value.split("\n"):
            line = ""
            for word in re.findall(r"\S+\s*", paragraph):
                if pdfmetrics.stringWidth(word.rstrip(), font, size) > width:
                    words = list(word)
                else:
                    words = [word]
                for character in words:
                    if line and pdfmetrics.stringWidth(line + character, font, size) > width:
                        lines.append(line.rstrip())
                        line = character.lstrip()
                    else:
                        line += character
            lines.append(line.rstrip())
        for line in lines:
            self.text(x, y, line, size=size, color=color, bold=bold, max_width=width)
            y += leading
        return y

    def panel(self, x, y, w, h, title, subtitle, color="blue"):
        self.rect(x, y, w, h, fill=f"{color}_bg", stroke=color, radius=10)
        self.text(x + 16, y + 29, title, size=19, color=color, bold=True, max_width=w - 32)
        self.text(x + 16, y + 51, subtitle, size=12, color="muted", max_width=w - 32)

    def node(
        self,
        identity,
        x,
        y,
        w,
        h,
        title,
        lines,
        *,
        color="blue",
        sources=(),
        title_size=14,
        external=False,
    ):
        self.rect(x, y, w, h, stroke=color, radius=6, dash=external)
        self.rect(x, y, 4, h, fill=color, stroke=color, radius=0)
        end = self.wrapped(
            x + 13,
            y + 23,
            title,
            w - 26,
            size=title_size,
            color=color,
            bold=True,
            leading=title_size * 1.25,
        )
        end += 2
        body_leading = max(17, self.base_size * 1.4)
        for line in lines:
            end = self.wrapped(x + 13, end, line, w - 26, size=self.base_size, leading=body_leading)
        if end - body_leading > y + h - 9:
            raise ValueError(f"Node text clipped: {identity}: {end - body_leading} > {y + h - 9}")
        self.components.append(
            dict(
                id=identity,
                title=title,
                bounds=[x, y, w, h],
                sources=list(sources),
                description=list(lines),
                external=external,
                category=color,
            )
        )

    def arrow(self, points, *, color="blue", dashed=False, reverse=False, source=None, target=None):
        self.items.append(
            dict(type="arrow", points=points, color=COLORS[color], dashed=dashed, reverse=reverse)
        )
        if source or target:
            self.links.append(
                dict(source=source, target=target, color=color, dashed=dashed, points=points)
            )

    def label(self, x, y, value, *, color="muted", size=None):
        size = size or self.base_size
        w = pdfmetrics.stringWidth(value, "ArchitectureRegular", size)
        self.rect(
            x - 4, y - size - 1, w + 8, size + 6, fill="background", stroke="background", radius=2
        )
        self.text(x, y, value, size=size, color=color)

    def save_svg(self, path, *, a0=False, title="Smart home component architecture"):
        width, height = ("1189mm", "841mm") if a0 else (str(self.width), str(self.height))
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" '
            'aria-labelledby="diagram-title diagram-desc">',
            f'<title id="diagram-title">{escape(title)}</title>',
            '<desc id="diagram-desc">현재 코드의 Pi 제어, 집별 A50 알림 서버, '
            "Firebase 로그인 및 휴대폰별 FCM 전달 구조.</desc>",
            '<style>text{font-family:"Malgun Gothic","Noto Sans KR",sans-serif;'
            f"font-size:{self.base_size}px}}</style>",
        ]
        for item in self.items:
            if item["type"] == "rect":
                dash = ' stroke-dasharray="6 4"' if item["dash"] else ""
                parts.append(
                    f'<rect x="{item["x"]}" y="{item["y"]}" '
                    f'width="{item["w"]}" height="{item["h"]}" '
                    f'rx="{item["radius"]}" fill="{item["fill"]}" '
                    f'stroke="{item["stroke"]}" stroke-width="1"{dash}/>'
                )
            elif item["type"] == "text":
                weight = "700" if item["bold"] else "400"
                parts.append(
                    f'<text x="{item["x"]}" y="{item["y"]}" font-size="{item["size"]}px" '
                    f'style="font-size:{item["size"]}px" fill="{item["fill"]}" '
                    f'font-weight="{weight}">{escape(item["value"])}</text>'
                )
            else:
                dash = ' stroke-dasharray="6 4"' if item["dashed"] else ""
                coords = " ".join(f"{x},{y}" for x, y in item["points"])
                parts.append(
                    f'<polyline points="{coords}" fill="none" '
                    f'stroke="{item["color"]}" stroke-width="1.6" '
                    f'stroke-linejoin="round"{dash}/>'
                )
                arrow_points = [item["points"][-2:]]
                if item["reverse"]:
                    arrow_points.append(list(reversed(item["points"][:2])))
                for pair in arrow_points:
                    polygon = arrow_head(*pair)
                    points = " ".join(f"{x:.2f},{y:.2f}" for x, y in polygon)
                    parts.append(f'<polygon points="{points}" fill="{item["color"]}"/>')
        parts.append("</svg>\n")
        path.write_text("\n".join(parts), encoding="utf-8")

    def save_pdf(self, path):
        c = canvas.Canvas(str(path), pagesize=(1189 * mm, 841 * mm), pageCompression=1, invariant=1)
        c.setTitle("Smart home software component architecture - A0")
        c.setAuthor("Smart home project")
        c.scale(1189 * mm / self.width, 841 * mm / self.height)
        for item in self.items:
            if item["type"] == "rect":
                c.setFillColor(item["fill"])
                c.setStrokeColor(item["stroke"])
                c.setLineWidth(1)
                c.setDash([6, 4] if item["dash"] else [])
                c.roundRect(
                    item["x"],
                    self.height - item["y"] - item["h"],
                    item["w"],
                    item["h"],
                    item["radius"],
                    stroke=1,
                    fill=1,
                )
            elif item["type"] == "text":
                c.setFont(
                    "ArchitectureBold" if item["bold"] else "ArchitectureRegular", item["size"]
                )
                c.setFillColor(item["fill"])
                c.drawString(item["x"], self.height - item["y"], item["value"])
            else:
                c.setStrokeColor(item["color"])
                c.setFillColor(item["color"])
                c.setLineWidth(1.6)
                c.setDash([6, 4] if item["dashed"] else [])
                p = c.beginPath()
                for i, (x, y) in enumerate(item["points"]):
                    (p.moveTo if i == 0 else p.lineTo)(x, self.height - y)
                c.drawPath(p)
                heads = [item["points"][-2:]]
                if item["reverse"]:
                    heads.append(list(reversed(item["points"][:2])))
                for pair in heads:
                    p = c.beginPath()
                    for i, (x, y) in enumerate(arrow_head(*pair)):
                        (p.moveTo if i == 0 else p.lineTo)(x, self.height - y)
                    p.close()
                    c.drawPath(p, stroke=0, fill=1)
        c.showPage()
        c.save()


def arrow_head(start, end):
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    return [
        end,
        (
            end[0] - 8 * math.cos(angle) + 3.5 * math.sin(angle),
            end[1] - 8 * math.sin(angle) - 3.5 * math.cos(angle),
        ),
        (
            end[0] - 8 * math.cos(angle) - 3.5 * math.sin(angle),
            end[1] - 8 * math.sin(angle) + 3.5 * math.cos(angle),
        ),
    ]


def poster():
    d = Diagram(1682, 1189)
    d.rect(0, 0, 1682, 1189, fill="background", stroke="background", radius=0)
    d.text(36, 54, "스마트홈 소프트웨어 컴포넌트 아키텍처", size=30, bold=True)
    d.text(
        36,
        82,
        "집 안의 센서·에어컨 제어와 집별 가족 알림을 연결한 현재 구현",
        size=15,
        color="muted",
    )
    d.text(1230, 49, "A0 / 1189 × 841 mm / SVG + PDF", size=13, color="muted")
    d.text(1230, 74, "Pi 앱 0.7.0 · 중앙/가족 앱 0.4.0 · 2026-10-05", size=12, color="muted")
    for x, color, label in [
        (36, "blue", "센서·제어"),
        (211, "teal", "API·알림"),
        (386, "purple", "계정·권한"),
        (561, "slate", "저장·운영"),
    ]:
        d.arrow([(x, 111), (x + 30, 111)], color=color)
        d.text(x + 41, 115, label, color=color)
    d.text(
        776,
        115,
        "실선: 데이터/호출 방향 · 점선 상자: 외부 의존성 · 내부 호출은 핵심 흐름만 표시",
        color="muted",
    )

    d.panel(
        36,
        142,
        1610,
        223,
        "전체 연결",
        "각 집의 Pi는 기록을 보내고, A50은 해당 집 가족의 등록된 휴대폰만 선택한다.",
        "teal",
    )
    d.node(
        "home-container",
        52,
        212,
        268,
        88,
        "집 A / 집 B / … · 각 Raspberry Pi",
        ["센서·자동화 기록 + 독립 연결 서비스", "Pi마다 전용 허브 키 · 원본 DB는 읽기 전용"],
        color="blue",
        sources=["server/services/pi-central-agent/agent.py", "app/main.py"],
    )
    d.node(
        "https-edge",
        370,
        212,
        188,
        88,
        "Cloudflare HTTPS",
        ["Quick Tunnel (시험용)", "HTTPS 종료·요청 중계"],
        color="teal",
        sources=["server/services/central-tunnel/tunnel.py"],
    )
    d.node(
        "central-container",
        608,
        212,
        316,
        88,
        "Galaxy A50 · Termux 중앙 서버",
        ["Flask + Waitress / SQLite / 전송 작업", "집·가족·허브 연결과 휴대폰별 수신 선택"],
        color="teal",
        sources=["server/services/central-server/central_server/__main__.py"],
    )
    d.node(
        "fcm-provider",
        974,
        212,
        252,
        88,
        "Google FCM · 외부 서비스",
        ["HTTP v1 전송 요청 → 설치 토큰별 전달", "집 권한과 알림 대상은 A50이 결정"],
        color="teal",
        sources=["server/services/central-server/central_server/fcm.py"],
    )
    d.node(
        "android-container",
        1276,
        212,
        354,
        88,
        "가족 Android 앱 · 여러 휴대폰",
        ["같은 계정의 다른 폰도 각자 알림 선택", "문·온습도·경고 기록 조회와 알림 표시"],
        color="teal",
        sources=["server/android/family-app/app/src/main/java/com/aircon/family/FamilyActivity.java"],
    )
    for a, b, x, y, label in [
        ("home-container", "https-edge", 320, 370, "HTTPS"),
        ("https-edge", "central-container", 558, 608, "터널"),
        ("central-container", "fcm-provider", 924, 974, "FCM"),
        ("fcm-provider", "android-container", 1226, 1276, "Push"),
    ]:
        d.arrow([(x, 254), (y, 254)], color="teal", source=a, target=b)
        d.text(x + 2, 244, label, size=11, color="teal")
    d.arrow(
        [(1453, 300), (1453, 326), (464, 326), (464, 300)],
        color="purple",
        source="android-container",
        target="https-edge",
    )
    d.label(
        694,
        330,
        "HTTPS + Firebase ID 토큰 / 집·기록 조회, 초대, 휴대폰 등록·알림 선택",
        color="purple",
    )
    d.text(
        52,
        351,
        "Pi 업로드: POST /v1/hub/events + 전용 허브 키 · "
        "A50 내부 API: 127.0.0.1:8001 · 노트북은 운영 중계가 아니다.",
        color="muted",
    )

    d.text(36, 399, "컴포넌트 내부", size=21, bold=True)
    d.text(
        234,
        399,
        "상자는 책임 단위다. 같은 실행 프로세스 안의 클래스도 나누어 그렸다.",
        color="muted",
    )
    d.panel(
        36,
        415,
        470,
        480,
        "집마다 한 세트 · Raspberry Pi",
        "FastAPI / MQTT / 센서·자동화 DB / 사용자 systemd",
        "blue",
    )
    d.panel(
        530,
        415,
        600,
        480,
        "중앙 한 곳 · Galaxy A50",
        "Flask / Waitress 2 threads / 전송 worker / DB 스키마 4",
        "teal",
    )
    d.panel(
        1154,
        415,
        492,
        480,
        "가족마다 여러 대 · Android APK",
        "Google 로그인 + 기록 화면 + 설치별 FCM · Android 8 이상",
        "purple",
    )

    d.node(
        "sensors",
        52,
        484,
        119,
        77,
        "Zigbee 센서",
        ["문 / 온습도", "무선 보고"],
        title_size=13,
        sources=["app/sensors/service.py"],
    )
    d.node(
        "z2m",
        191,
        484,
        153,
        77,
        "Zigbee2MQTT",
        ["USB ZBDongle-P", "장치 메시지 변환"],
        title_size=13,
        sources=["deploy/zigbee/zigbee2mqtt/external_converters/aircon-h2-ir.mjs"],
    )
    d.node(
        "mqtt",
        364,
        484,
        126,
        77,
        "Mosquitto",
        ["MQTT 1883", "Pi 내부 연결"],
        title_size=13,
        sources=["deploy/zigbee/compose.yaml"],
    )
    d.arrow([(171, 522), (191, 522)], source="sensors", target="z2m")
    d.arrow([(344, 522), (364, 522)], source="z2m", target="mqtt")
    d.node(
        "sensor-service",
        52,
        596,
        218,
        89,
        "SensorService / MQTT",
        ["값 확인 → 상태·문 변화 저장", "app/integrations/mqtt.py", "app/sensors/service.py"],
        title_size=13,
        sources=["app/integrations/mqtt.py", "app/sensors/service.py"],
    )
    d.node(
        "pi-api",
        292,
        596,
        198,
        89,
        "FastAPI + DeviceService",
        ["/api/v1 · 웹 화면 · SSE", "기기 JSON / 명령 프로필", "H2 또는 Pi IR 송신 선택"],
        title_size=13,
        sources=["app/main.py", "app/devices/service.py", "app/devices/store.py"],
    )
    d.arrow(
        [(427, 561), (427, 578), (161, 578), (161, 596)], source="mqtt", target="sensor-service"
    )
    d.label(209, 582, "센서 수신", color="blue")
    d.arrow([(270, 633), (292, 633)], source="sensor-service", target="pi-api")
    d.node(
        "pi-db",
        52,
        722,
        218,
        74,
        "센서·자동화 SQLite",
        ["sensor_states / door_events", "automation_events"],
        color="slate",
        sources=["app/sensors/store.py", "app/automations/store.py"],
    )
    d.node(
        "automation",
        292,
        722,
        198,
        74,
        "Automation + EventHub",
        ["문 열림 경고 발생·해제", "웹 화면 갱신은 메모리 SSE"],
        title_size=13,
        sources=["app/automations/service.py", "app/events.py"],
    )
    d.arrow([(161, 685), (161, 722)], source="sensor-service", target="pi-db")
    d.arrow(
        [(250, 685), (250, 703), (391, 703), (391, 722)],
        source="sensor-service",
        target="automation",
    )
    d.arrow([(391, 722), (391, 685)], source="automation", target="pi-api")
    d.arrow([(292, 759), (270, 759)], source="automation", target="pi-db")
    d.node(
        "pi-agent",
        52,
        825,
        438,
        60,
        "Pi 연결 서비스 · agent.py",
        ["5초마다 새 기록 조회 / 자체 cursor + outbox.sqlite3 / HTTPS 전송"],
        title_size=13,
        sources=["server/services/pi-central-agent/agent.py"],
    )
    d.arrow([(161, 796), (161, 825)], source="pi-db", target="pi-agent", color="slate")
    d.label(174, 821, "읽기 전용", color="slate")

    d.node(
        "user-api",
        546,
        484,
        268,
        81,
        "사용자 API + FirebaseIdentity",
        ["Firebase ID 토큰 서명·만료·프로젝트 확인", "Google 공개 인증서 캐시 / auth.py"],
        color="purple",
        sources=[
            "server/services/central-server/central_server/auth.py",
            "server/services/central-server/central_server/api.py",
        ],
    )
    d.node(
        "hub-api",
        836,
        484,
        278,
        81,
        "허브 API · 기기 인증",
        ["허브 키의 해시 → 활성 hub → 소속 집", "앱 사용자 토큰과 다른 인증 경로"],
        color="teal",
        sources=[
            "server/services/central-server/central_server/api.py",
            "server/services/central-server/central_server/households.py",
        ],
    )
    d.node(
        "households",
        546,
        600,
        268,
        81,
        "Households · 집·가족 권한",
        ["현재 memberships / owner·member·viewer", "초대 수락 / 허브 연결 / 집 비활성화"],
        color="purple",
        sources=["server/services/central-server/central_server/households.py"],
    )
    d.node(
        "ingestion",
        836,
        600,
        278,
        81,
        "이벤트 수집 · 중복 처리",
        ["UNIQUE(hub_id, sender_event_id)", "이벤트와 알림 대기를 한 DB 트랜잭션으로"],
        color="teal",
        sources=[
            "server/services/central-server/central_server/households.py",
            "server/services/central-server/central_server/schema.py",
        ],
    )
    d.arrow([(680, 565), (680, 600)], color="purple", source="user-api", target="households")
    d.arrow([(975, 565), (975, 600)], color="teal", source="hub-api", target="ingestion")
    d.node(
        "push-store",
        546,
        721,
        268,
        80,
        "PushStore + Preferences",
        ["활성 가족·설치·binding + 종류별 선택", "온습도: 새 보고 + 1/5/15/60분 최소 간격"],
        color="teal",
        sources=[
            "server/services/central-server/central_server/push.py",
            "server/services/central-server/central_server/preferences.py",
        ],
    )
    d.node(
        "central-db",
        836,
        721,
        278,
        80,
        "SQLite · central.sqlite3",
        [
            "users / homes / memberships / hubs / events",
            "installations / preferences / push_jobs / audit",
        ],
        color="slate",
        sources=[
            "server/services/central-server/central_server/storage.py",
            "server/services/central-server/central_server/schema.py",
            "server/services/central-server/central_server/push_schema.py",
        ],
    )
    d.arrow([(680, 681), (680, 721)], color="purple", source="households", target="push-store")
    d.arrow(
        [(814, 640), (825, 640), (825, 702), (900, 702), (900, 721)],
        color="slate",
        source="households",
        target="central-db",
    )
    d.arrow([(975, 681), (975, 721)], color="teal", source="ingestion", target="central-db")
    d.arrow(
        [(814, 761), (836, 761)],
        color="slate",
        reverse=True,
        source="push-store",
        target="central-db",
    )
    d.node(
        "push-worker",
        546,
        825,
        568,
        60,
        "PushWorker → FCMSender",
        ["전송 직전 권한·선택 재확인 / 만료·재시도 / 서버 전용 키로 HTTP v1 요청"],
        color="teal",
        title_size=13,
        sources=[
            "server/services/central-server/central_server/push.py",
            "server/services/central-server/central_server/fcm.py",
        ],
    )
    d.arrow([(680, 801), (680, 825)], color="teal", source="push-store", target="push-worker")
    d.arrow([(975, 801), (975, 825)], color="slate", source="central-db", target="push-worker")

    java = "server/android/family-app/app/src/main/java/com/aircon/family/"
    d.node(
        "firebase-auth",
        1170,
        484,
        218,
        81,
        "Google / Firebase Auth",
        ["APK 밖의 외부 로그인 서비스", "Google 계정 → Firebase ID 토큰"],
        color="purple",
        sources=[java + "FirebaseSession.java"],
        external=True,
    )
    d.node(
        "firebase-session",
        1406,
        484,
        224,
        81,
        "FirebaseSession",
        ["Credential Manager 로그인", "Firebase 사용자·세션 유지"],
        color="purple",
        sources=[java + "FirebaseSession.java"],
    )
    d.arrow(
        [(1388, 524), (1406, 524)],
        color="purple",
        reverse=True,
        source="firebase-auth",
        target="firebase-session",
    )
    d.node(
        "family-ui",
        1170,
        600,
        218,
        81,
        "FamilyActivity · 화면",
        ["홈 / 기록 / 설정 / 가족 관리", "알림 선택·오류 안내·스크롤 유지"],
        color="purple",
        sources=[java + "FamilyActivity.java", java + "ApiErrorMessages.java"],
    )
    d.node(
        "api-client",
        1406,
        600,
        224,
        81,
        "ApiClient + EndpointPolicy",
        ["HTTPS / Bearer Firebase ID 토큰", "집·기록·설치·선택 API 호출"],
        color="purple",
        title_size=13,
        sources=[java + "ApiClient.java", java + "EndpointPolicy.java"],
    )
    d.arrow(
        [(1518, 565), (1518, 600)], color="purple", source="firebase-session", target="api-client"
    )
    d.arrow([(1388, 640), (1406, 640)], color="purple", source="family-ui", target="api-client")
    d.node(
        "push-sync",
        1170,
        721,
        218,
        80,
        "PushManager + SyncWorker",
        ["설치 증명·FCM 토큰 등록", "WorkManager / 선택 동기화"],
        color="teal",
        title_size=13,
        sources=[java + "PushManager.java", java + "PushSyncWorker.java"],
    )
    d.node(
        "fcm-receiver",
        1406,
        721,
        224,
        80,
        "FamilyMessagingService",
        ["FCM data 메시지 수신", "계정·binding·중복·선택 재확인"],
        color="teal",
        title_size=13,
        sources=[java + "FamilyMessagingService.java", java + "PushPolicy.java"],
    )
    d.arrow(
        [(1279, 721), (1279, 701), (1518, 701), (1518, 681)],
        color="purple",
        source="push-sync",
        target="api-client",
    )
    d.node(
        "app-prefs",
        1170,
        825,
        218,
        60,
        "SharedPreferences",
        ["설치 증명 / binding / 선택 / 중복"],
        color="slate",
        title_size=13,
        sources=[java + "PushManager.java"],
    )
    d.node(
        "android-notifications",
        1406,
        825,
        224,
        60,
        "Android NotificationManager",
        ["알림 권한 / 일반·온습도 채널"],
        color="teal",
        title_size=12,
        sources=[java + "FamilyMessagingService.java"],
    )
    d.arrow([(1279, 801), (1279, 825)], color="slate", source="push-sync", target="app-prefs")
    d.arrow(
        [(1518, 801), (1518, 825)],
        color="teal",
        source="fcm-receiver",
        target="android-notifications",
    )

    d.panel(
        36,
        919,
        470,
        222,
        "에어컨 제어 · 별도 경로",
        "가족 APK는 기록·알림용이다. 에어컨 명령은 Pi 웹 화면에서 보낸다.",
        "blue",
    )
    for identity, x, w, title, lines, sources in [
        ("private-web", 52, 128, "웹 / 터치 화면", ["Tailscale :8001"], ["app/static/index.html"]),
        (
            "h2-transport",
            200,
            126,
            "Pi → MQTT",
            ["DeviceService"],
            ["app/devices/service.py", "app/integrations/mqtt.py"],
        ),
        (
            "h2-firmware",
            346,
            144,
            "H2 → IR LED",
            ["Zigbee 펌웨어"],
            [
                "firmware/esp32-h2-zigbee-ir-node/main/main.c",
                "firmware/esp32-h2-zigbee-ir-node/main/ir_tx.c",
            ],
        ),
    ]:
        d.node(identity, x, 988, w, 56, title, lines, title_size=13, sources=sources)
    d.arrow([(180, 1016), (200, 1016)], source="private-web", target="h2-transport")
    d.arrow([(326, 1016), (346, 1016)], source="h2-transport", target="h2-firmware")
    d.wrapped(52, 1069, "H2 경로: MQTT → Zigbee2MQTT 변환기 → Zigbee → H2 → IR → 에어컨", 438)
    d.wrapped(
        52,
        1103,
        "선택: Pi GPIO IR / ir-ctl. 화면 상태는 마지막 명령의 추정값이다. "
        "H2의 sent는 에어컨의 실제 상태 응답이 아니다.",
        438,
    )

    d.panel(
        530,
        919,
        600,
        222,
        "집별 격리 · 서버에서 결정",
        "로그인은 계정 확인이고, 집에 들어갈 권한은 중앙 DB에서 확인한다.",
        "purple",
    )
    d.text(546, 995, "Pi A → 집 A → 집 A 가족의 활성 설치", size=14, color="purple", bold=True)
    d.text(546, 1024, "Pi B → 집 B → 집 B 가족의 활성 설치", size=14, color="purple", bold=True)
    d.text(890, 995, "같은 사용자가 여러 집에 소속될 수 있다.", size=12, color="muted")
    d.text(890, 1024, "현재: 집마다 활성 허브 1대", size=12, color="muted")
    d.wrapped(
        546,
        1055,
        "소유자만 초대·가족 변경·허브 연결·집 삭제·시험 알림을 요청한다. "
        "초대는 지정 Google 계정, 1회 사용·24시간. 허브 연결 코드는 10분이다.",
        568,
    )
    d.wrapped(
        546,
        1102,
        "수신 대상을 고를 때와 전송 직전에 가족 소속을 읽는다. "
        "FCM에는 식별·분류만 보내고 상세 기록은 인증된 API에서 읽는다.",
        568,
    )

    d.panel(
        1154,
        919,
        492,
        222,
        "실행·복구와 현재 확인 범위",
        "현재 코드 구조다. 대규모 서비스나 새 시험 성공을 뜻하지 않는다.",
        "slate",
    )
    d.wrapped(
        1170,
        991,
        "A50: Termux:Boot + wake-lock + runit / Pi: 사용자 systemd. "
        "PC는 코드·배포·SSH/ADB 관리용이다.",
        460,
    )
    d.wrapped(
        1170,
        1039,
        "Pi outbox: 만료 240초·최대 8회 시도. 중앙 push: 최대 300초·최대 6회 시도. "
        "로그 제한과 반복 실패 중단이 있다.",
        460,
    )
    d.wrapped(
        1170,
        1087,
        "Quick Tunnel 주소는 바뀔 수 있다. FCM 전송 접수 ≠ 휴대폰 표시. "
        "물리 센서→폰 전체 시험·다른 가족 계정·장시간 운영은 남아 있다.",
        460,
    )
    d.text(
        36,
        1171,
        "공개용 모델 · 실제 이메일·서버 주소·기기 고유값·인증키 제외 · "
        "코드 근거와 재생성 방법: docs/architecture/README.md",
        color="muted",
    )
    return d


def overview():
    d = Diagram(1260, 680, base_size=16)
    d.rect(0, 0, 1260, 680, fill="background", stroke="background", radius=0)
    d.text(28, 42, "스마트홈 · 제어와 가족 알림의 두 경로", size=26, bold=True)
    d.text(
        28,
        72,
        "각 집의 Pi → A50의 집별 권한·수신 선택 → 해당 가족의 휴대폰",
        size=17,
        color="muted",
    )
    d.node(
        "pi",
        28,
        162,
        245,
        123,
        "각 집의 Raspberry Pi",
        ["Zigbee 센서·웹 화면·기록 DB", "연결 서비스: 새 기록만 읽음", "Pi마다 전용 허브 키"],
        title_size=19,
        sources=["app/main.py", "server/services/pi-central-agent/agent.py"],
    )
    d.node(
        "tunnel",
        325,
        162,
        197,
        123,
        "Cloudflare HTTPS",
        ["시험용 Quick Tunnel", "요청을 A50으로 중계", "주소는 바뀔 수 있음"],
        color="teal",
        title_size=18,
        sources=["server/services/central-tunnel/tunnel.py"],
    )
    d.node(
        "central",
        574,
        162,
        313,
        123,
        "A50 · 가족 중앙 서버",
        ["계정 + 집·가족 권한 확인", "휴대폰별 알림 선택·전송 대기", "Flask / SQLite / FCM sender"],
        color="teal",
        title_size=19,
        sources=["server/services/central-server/central_server/__main__.py"],
    )
    d.node(
        "app",
        1010,
        162,
        222,
        123,
        "가족 Android 앱",
        ["Google 로그인", "집·기록·가족·알림 선택", "여러 폰, 각각 알림 설정"],
        color="purple",
        title_size=19,
        sources=["server/android/family-app/app/src/main/java/com/aircon/family/FamilyActivity.java"],
    )
    d.arrow([(273, 222), (325, 222)], source="pi", target="tunnel", color="teal")
    d.text(279, 210, "HTTPS", size=13, color="teal")
    d.arrow([(522, 222), (574, 222)], source="tunnel", target="central", color="teal")
    d.text(530, 210, "터널", size=13, color="teal")
    d.node(
        "auth",
        950,
        94,
        282,
        56,
        "Google / Firebase Auth",
        ["계정 로그인·ID 토큰 발급"],
        color="purple",
        title_size=16,
        external=True,
        sources=["server/android/family-app/app/src/main/java/com/aircon/family/FirebaseSession.java"],
    )
    d.arrow([(1121, 150), (1121, 162)], color="purple", reverse=True, source="auth", target="app")
    d.arrow(
        [(1121, 285), (1121, 331), (424, 331), (424, 285)],
        color="purple",
        source="app",
        target="tunnel",
    )
    d.label(589, 337, "HTTPS + Firebase ID 토큰 / 집·기록·설정 API", color="purple", size=16)
    d.node(
        "fcm",
        911,
        210,
        79,
        69,
        "FCM",
        ["외부"],
        color="teal",
        title_size=17,
        sources=["server/services/central-server/central_server/fcm.py"],
    )
    d.arrow([(887, 247), (911, 247)], color="teal", source="central", target="fcm")
    d.arrow([(990, 247), (1010, 247)], color="teal", source="fcm", target="app")
    d.text(899, 191, "알림 전달", size=15, color="teal")
    d.rect(28, 389, 1204, 116, fill="blue_bg", stroke="blue")
    d.text(44, 420, "에어컨 제어는 Pi 웹 대시보드에서", size=20, bold=True, color="blue")
    d.text(
        44,
        453,
        "휴대폰·PC·터치 화면 → Tailscale :8001 → Pi FastAPI → "
        "MQTT → Zigbee2MQTT → H2 → IR → 에어컨",
        size=16,
        color="blue",
    )
    d.text(
        44,
        483,
        "가족 APK는 현재 기록·알림용이다. Pi GPIO IR은 선택 경로이며, "
        "화면의 에어컨 상태는 마지막 명령의 추정값이다.",
        size=16,
        color="muted",
    )
    d.rect(28, 531, 588, 106, fill="purple_bg", stroke="purple")
    d.text(44, 561, "다른 집의 알림을 받지 않게", size=19, bold=True, color="purple")
    d.text(44, 592, "서버가 집 소속·현재 역할·활성 설치를 확인한다.", size=16, color="muted")
    d.text(
        44, 620, "알림 전송 직전에도 가족 권한과 휴대폰 선택을 다시 읽는다.", size=16, color="muted"
    )
    d.rect(644, 531, 588, 106, fill="teal_bg", stroke="teal")
    d.text(660, 561, "휴대폰마다 받고 싶은 소식만", size=19, bold=True, color="teal")
    d.text(660, 592, "문 / 경고 / 온습도 · 온습도 최소 간격 1·5·15·60분", size=16, color="muted")
    d.text(
        660,
        620,
        "FCM에는 식별·분류만, 자세한 기록은 인증된 API에서 읽는다.",
        size=16,
        color="muted",
    )
    d.text(
        28,
        666,
        "현재 구현 · Pi 0.7.0 / 중앙·앱 0.4.0 · 전체 컴포넌트·저장·복구 구조는 A0 원본 참고",
        size=14,
        color="muted",
    )
    return d


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/malgun.ttf"))
    parser.add_argument("--bold-font", type=Path, default=Path("C:/Windows/Fonts/malgunbd.ttf"))
    args = parser.parse_args()
    pdfmetrics.registerFont(TTFont("ArchitectureRegular", str(args.font)))
    pdfmetrics.registerFont(TTFont("ArchitectureBold", str(args.bold_font)))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    large, small = poster(), overview()
    for name, diagram in [("smart-home-components-a0", large), ("smart-home-overview", small)]:
        for component in diagram.components:
            for source in component["sources"]:
                if not (ROOT / source).is_file():
                    raise ValueError(f"Missing architecture source: {source}")
        diagram.save_svg(OUTPUT / f"{name}.svg", a0=diagram is large)
    large.save_pdf(OUTPUT / "smart-home-components-a0.pdf")
    model = {
        "version": 1,
        "scope": "current implementation",
        "snapshot_date": "2026-10-05",
        "paper_mm": [1189, 841],
        "view_box": [0, 0, large.width, large.height],
        "body_font_px": 12,
        "components": large.components,
        "connections": large.links,
    }
    (OUTPUT / "component-model.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"ARCHITECTURE_SVGS=2 A0_PDF=1 COMPONENTS={len(large.components)}")
    print(
        f"CODE_SOURCE_REFERENCES={sum(len(c['sources']) for c in large.components)} ALL_EXIST=TRUE"
    )
    print("A0_MM=1189x841 BODY_FONT_PX=12 TEXT_BOUNDS=PASS NO_RASTER_IMAGES=TRUE")


if __name__ == "__main__":
    main()
