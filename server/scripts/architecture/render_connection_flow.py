"""Create matching, portable SVG and PNG explanations of the actual network paths."""

from __future__ import annotations

import argparse
import math
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
WIDTH, HEIGHT = 1600, 1660
INK, MUTED = '#12233c', '#536479'
BLUE, PURPLE, ORANGE, GREEN = '#2463d7', '#7755bb', '#c66819', '#15805b'
FONT_PATH = Path('C:/Windows/Fonts/malgun.ttf')
BOLD_PATH = Path('C:/Windows/Fonts/malgunbd.ttf')


class Drawing:
    def __init__(self):
        self.image = Image.new('RGB', (WIDTH * 2, HEIGHT * 2), '#ffffff')
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
                    '<title id="title">스마트홈 앱·도메인·A50·라즈베리파이 연결 구조</title>',
                    '<desc id="desc">Android APK와 iPhone 홈 화면 웹앱은 같은 도메인과 A50 API를 쓴다. 웹앱 파일도 A50이 제공한다. 파란 선은 제어와 조회, 보라 점선은 먼저 만드는 연결, 주황 선은 Android와 웹 푸시, 초록 선은 센서 기록이다. 웹앱의 방해 금지 시간은 A50이 적용한다. 실제 iPhone 로그인과 수신 확인은 남아 있다.</desc>',
                    f'<rect width="{WIDTH}" height="{HEIGHT}" fill="white"/>']

    def text(self, x, y, value, size=18, color=INK, bold=False, anchor='start'):
        font = ImageFont.truetype(str(BOLD_PATH if bold else FONT_PATH), size * 2)
        width = self.draw.textlength(value, font=font) / 2
        xx = x - width / 2 if anchor == 'middle' else x - width if anchor == 'end' else x
        if xx < 0 or xx + width > WIDTH:
            raise ValueError('Text would leave canvas: ' + value)
        self.draw.text((xx * 2, y * 2), value, fill=color, font=font, anchor='lt')
        self.svg.append(f'<text x="{x}" y="{y + size}" font-size="{size}" font-weight="{"700" if bold else "400"}" fill="{color}" text-anchor="{anchor}" font-family="Malgun Gothic,Apple SD Gothic Neo,Noto Sans KR,sans-serif">{escape(value)}</text>')

    def rect(self, x, y, w, h, fill='#f8fafc', stroke='#cbd5e1', radius=14):
        self.draw.rounded_rectangle((x*2,y*2,(x+w)*2,(y+h)*2),radius=radius*2,fill=fill,outline=stroke,width=2)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>')

    def card(self, x, y, w, h, title, lines, color=BLUE, fill='#f6f9ff', size=18):
        if lines and 58 + (len(lines)-1)*29 + size > h-14:
            raise ValueError('Card text exceeds height: '+title)
        self.rect(x,y,w,h,fill,color)
        self.text(x+18,y+18,title,22,color,True)
        for i, line in enumerate(lines):
            font = ImageFont.truetype(str(FONT_PATH),size*2)
            if self.draw.textlength(line,font=font)/2 > w-36:
                raise ValueError('Card label overflows: '+line)
            self.text(x+18,y+58+i*29,line,size)

    def arrow(self, points, color=BLUE, dashed=False):
        # White underlay makes crossings visibly separate, rather than junctions.
        coords=[(x*2,y*2) for x,y in points]
        self.draw.line(coords,fill='white',width=13,joint='curve')
        if dashed:
            for (x1,y1),(x2,y2) in zip(coords,coords[1:]):
                length=math.hypot(x2-x1,y2-y1)
                for a in range(0,int(length),20):
                    b=min(a+12,length)
                    self.draw.line((x1+(x2-x1)*a/length,y1+(y2-y1)*a/length,x1+(x2-x1)*b/length,y1+(y2-y1)*b/length),fill=color,width=5)
        else:
            self.draw.line(coords,fill=color,width=5,joint='curve')
        (px,py),(x,y)=points[-2:]
        length=math.hypot(x-px,y-py)
        ux,uy=(x-px)/length,(y-py)/length
        tip=[(x,y),(x-ux*12-uy*6,y-uy*12+ux*6),(x-ux*12+uy*6,y-uy*12-ux*6)]
        self.draw.polygon([(a*2,b*2) for a,b in tip],fill=color)
        path='M '+' L '.join(f'{a} {b}' for a,b in points)
        self.svg.append(f'<path d="{path}" fill="none" stroke="white" stroke-width="7" stroke-linejoin="round"/>')
        self.svg.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round"'+(' stroke-dasharray="6 4"' if dashed else '')+'/>')
        self.svg.append(f'<polygon points="{" ".join(f"{a},{b}" for a,b in tip)}" fill="{color}"/>')

    def save(self, stem):
        stem.parent.mkdir(parents=True,exist_ok=True)
        stem.with_suffix('.svg').write_text('\n'.join(self.svg+['</svg>'])+'\n',encoding='utf-8')
        self.image.save(stem.with_suffix('.png'))


def render(status):
    d=Drawing()
    d.text(60,26,'내 휴대폰에서 집 안 기기까지, 요청은 어떻게 이어질까?',32,bold=True)
    d.text(60,76,'2026-10-16 · Android 0.6.2 · 중앙 서버 0.8.0 / DB 8 · iPhone 웹앱 추가',18,MUTED)
    d.rect(1100,68,440,39,'#eef6ef' if status=='connected' else '#fff6e7','#cbd5e1',8)
    d.text(1120,76,'고정 주소 연결 완료 · iPhone 수신 미확인' if status=='connected' else '고정 연결 설정 중 · iPhone 수신 미확인',17,GREEN if status=='connected' else '#946017',True)
    d.card(60,150,340,125,'Google / Firebase 로그인',[
        '두 앱에 로그인 증명(ID 토큰) 발급',
        '웹 로그인 보조 요청은 A50이 전달'],PURPLE,'#faf7ff',16)
    d.card(570,150,400,125,'도메인과 DNS',['roomrelay.top의 목적지를 안내'],MUTED,'#f8fafc',18)
    d.card(1100,150,440,125,'Spaceship · 구매와 갱신',['도메인을 빌려 쓰는 기간을 관리'],MUTED,'#f8fafc',18)

    d.rect(60,350,340,440,'#f5f8ff',BLUE)
    d.text(78,368,'가족 휴대폰',22,BLUE,True)
    d.text(78,402,'두 앱 모두 로그인 증명으로 조회·제어',15,MUTED)
    d.card(78,435,304,150,'Android · APK 0.6.2',[
        '집·기기·에어컨·알림 선택',
        'FCM → Android 알림',
        '가족·허브 관리는 Android에서'],BLUE,'#ffffff',16)
    d.card(78,600,304,175,'iPhone · 홈 화면 웹앱',[
        '/app/에서 화면 받기 · Google 로그인',
        '집·에어컨·기록·알림 설정',
        'iOS 16.4↑ · 홈 화면 추가·허용',
        'FCM 웹 푸시 → iOS 알림'],PURPLE,'#ffffff',15)

    d.card(570,350,400,440,'Cloudflare · 외부 연결 입구',[
        '고정 도메인의 HTTPS 요청 수신',
        '/app/ 웹 화면 · /v1/ API 전달',
        '/__/auth/ 로그인 보조 경로 전달',
        'A50이 유지하는 암호화 통로 사용',
        '집·가족 권한은 A50에서 판단',
        '',
        '실제 서버 프로그램은 A50에 있음'],BLUE,'#f5f8ff',18)
    d.card(1100,350,440,440,'Galaxy A50 · 중앙 서버 0.8.0',[
        'DB 스키마 8 · 집별 기록과 권한 유지',
        '/app/ 웹앱 파일·설정 제공',
        '웹 로그인 보조 요청 → Firebase',
        '로그인 증명·집·가족 역할 확인',
        '제어할 명령을 대기열에 보관',
        'Pi 기기 목록·공간·결과·기록 저장',
        '기기별 알림 종류·중요도·간격 적용',
        '웹앱 방해 금지 시간은 서버가 적용',
        'cloudflared가 외부 통로를 유지'],BLUE,'#f5f8ff',18)
    d.rect(570,970,970,425,'#f4faf7','#9ebcaa')
    d.text(920,985,'각 가족의 집 · Raspberry Pi와 Zigbee 기기',22,GREEN,True)
    d.card(590,1035,260,165,'Pi 연결 서비스',[
        '중앙 서버에 먼저 접속',
        '명령 조회·결과 보고',
        '기기 목록·공간·새 기록 전송'],PURPLE,'#faf7ff',16)
    d.card(900,1035,260,165,'Pi 제어 프로그램',[
        '기기·센서·자동화 관리',
        '에어컨 명령 처리',
        '로컬 웹 화면도 제공'],BLUE,'#f5f8ff',17)
    d.card(1210,1035,300,165,'MQTT / Zigbee 연결',[
        'MQTT: 집 안 메시지 전달',
        'Zigbee2MQTT + USB 동글',
        '센서·H2 기기와 통신'],GREEN,'#f4faf7',17)
    d.card(590,1275,260,100,'문·온습도 센서',['측정값과 문 열림 전송'],GREEN,'#f4faf7',17)
    d.card(900,1275,260,100,'실제 에어컨',['IR 신호를 받아 동작'],BLUE,'#f5f8ff',17)
    d.card(1210,1275,300,100,'ESP32-H2 + IR LED',['Zigbee 명령 → 적외선 송신'],BLUE,'#f5f8ff',17)
    d.card(60,1035,340,195,'Firebase Cloud Messaging',[
        'Android 알림과 웹 푸시 배달',
        'A50이 고른 수신 기기로 전달',
        'Google 로그인과는 다른 기능',
        '에어컨 명령을 보내는 통로가 아님'],ORANGE,'#fff8f0',16)

    d.arrow([(230,275),(230,350)],PURPLE,True)
    d.text(250,302,'로그인 증명',16,PURPLE)
    d.arrow([(1100,212),(970,212)],MUTED,True)
    d.text(1035,183,'주소 관리 위임',15,MUTED,anchor='middle')
    d.arrow([(370,350),(370,310),(540,310),(540,250),(570,250)],MUTED,True)
    d.text(455,284,'주소 조회',15,MUTED,anchor='middle')
    d.arrow([(770,275),(770,350)],MUTED,True)
    d.text(790,302,'목적지 안내',16,MUTED)
    d.arrow([(400,475),(570,475)],BLUE)
    d.text(485,442,'두 앱의 제어·조회',16,BLUE,True,'middle')
    d.arrow([(970,475),(1100,475)],BLUE)
    d.text(1035,442,'암호화 통로',17,BLUE,True,'middle')
    d.arrow([(1100,675),(970,675)],MUTED)
    d.text(1035,687,'응답',17,MUTED,anchor='middle')
    d.arrow([(570,675),(400,675)],MUTED)
    d.text(485,687,'화면·결과·기록',16,MUTED,anchor='middle')
    d.arrow([(1100,745),(970,745)],PURPLE,True)
    d.text(1035,760,'A50이 연결 유지',14,PURPLE,anchor='middle')
    d.arrow([(680,1035),(680,790)],PURPLE,True)
    d.text(660,916,'Pi가 먼저 HTTPS 조회',17,PURPLE,True,'end')
    d.text(660,945,'기기 목록·새 기록 전송',15,PURPLE,anchor='end')
    d.arrow([(850,790),(850,1035)],BLUE)
    d.text(875,916,'조회 응답으로',17,BLUE)
    d.text(875,945,'대기 중인 명령 수신',17,BLUE)
    d.arrow([(850,1090),(900,1090)],BLUE)
    d.text(875,1062,'명령',15,BLUE,anchor='middle')
    d.arrow([(1160,1090),(1210,1090)],BLUE)
    d.text(1185,1062,'명령',15,BLUE,anchor='middle')
    d.arrow([(1210,1160),(1160,1160)],GREEN)
    d.arrow([(900,1160),(850,1160)],GREEN)
    d.text(875,1171,'기록',15,GREEN,anchor='middle')
    d.arrow([(1360,1200),(1360,1275)],BLUE)
    d.text(1380,1224,'Zigbee',16,BLUE)
    d.arrow([(1210,1325),(1160,1325)],BLUE)
    d.text(1185,1298,'IR',16,BLUE,anchor='middle')
    d.arrow([(720,1275),(720,1235),(1280,1235),(1280,1200)],GREEN)
    d.text(1000,1208,'문 열림·온습도 기록 (Zigbee)',17,GREEN,anchor='middle')
    d.arrow([(1320,790),(1320,865),(455,865),(455,1120),(400,1120)],ORANGE)
    d.text(1090,835,'A50 → 선택한 기기로 알림 발송',18,ORANGE,True,'middle')
    d.arrow([(230,1035),(230,790)],ORANGE)
    d.text(250,894,'기기별 푸시 알림',17,ORANGE,True)
    d.text(60,1430,'읽는 법과 확인 범위',22,bold=True)
    notes=[
        '도메인·DNS는 목적지를 찾는 안내다. Spaceship은 구매·갱신을 맡고 앱의 제어 요청을 중계하지 않는다.',
        'Android와 iPhone은 같은 A50 API를 쓴다. iPhone 화면 파일도 A50이 제공하고 웹 로그인 보조 요청을 Firebase에 전달한다.',
        'Pi가 먼저 명령을 조회한다. 공유기 포트를 열지 않으며, Tailscale·SSH는 관리와 기존 Pi 웹 화면에 쓴다.',
        '웹앱의 일반 알림은 방해 금지 시간에 서버가 보내지 않는다. 긴급·시험 알림은 예외이고 Android는 폰에서 처리한다.',
        'FCM은 알림 경로다. 에어컨 제어는 앱 → HTTPS → A50 → Pi의 조회 응답 → H2 → IR 순서다.',
        '웹앱 화면·Google 로그인 페이지 진입은 확인했다. 실제 iPhone 로그인·푸시 수신과 에어컨의 물리 반응은 별도 확인이다.',
    ]
    for i,note in enumerate(notes):
        d.text(60,1470+i*27,'• '+note,16,MUTED)
    return d


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status',choices=['preparing','connected'],default='preparing')
    args=parser.parse_args()
    render(args.status).save(ROOT/'docs/architecture/connection-flow')
    print('CONNECTION_FLOW_SVG_AND_PNG_CREATED status='+args.status)
