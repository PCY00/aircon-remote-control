"""Create matching, portable SVG and PNG explanations of the actual network paths."""

from __future__ import annotations

import argparse
import math
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
WIDTH, HEIGHT = 1600, 1400
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
                    '<desc id="desc">파란 선은 앱의 에어컨 제어, 보라 점선은 장치가 먼저 만드는 연결, 주황 선은 FCM 알림, 초록 선은 집 안 센서 기록이다. 도메인 고정 설정 상태는 상단에 별도로 표시한다.</desc>',
                    '<rect width="1600" height="1400" fill="white"/>']

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
    d.text(60,76,'2026-10-15 코드 기준 · 고정 주소 연결 후의 구조 · 로그인·제어·알림을 서로 구분해서 읽는다.',18,MUTED)
    d.rect(1100,68,440,39,'#eef6ef' if status=='connected' else '#fff6e7','#cbd5e1',8)
    d.text(1120,76,'고정 주소 연결 확인 완료' if status=='connected' else '도메인 구매 완료 · 고정 연결 설정 중',17,GREEN if status=='connected' else '#946017',True)
    d.card(60,140,340,105,'Google / Firebase 로그인',['앱에 로그인 증명(ID 토큰) 발급'],PURPLE,'#faf7ff',17)
    d.card(570,140,400,105,'도메인과 DNS',['roomrelay.top의 목적지를 안내'],MUTED,'#f8fafc',18)
    d.card(1100,140,440,105,'Spaceship · 구매와 갱신',['도메인을 빌려 쓰는 기간을 관리'],MUTED,'#f8fafc',18)
    d.card(60,320,340,310,'내 휴대폰 · 가족 앱',[
        '집·에어컨·알림 선택 화면',
        'HTTPS 요청에 로그인 증명 포함',
        '',
        '명령 결과와 집 기록 조회',
        'FCM 수신 후 Android 알림 표시',
        '화면이 꺼져도 알림 수신 가능'],BLUE,'#f5f8ff',17)
    d.card(570,320,400,310,'Cloudflare · 외부 연결 입구',[
        '고정 도메인의 HTTPS 요청 수신',
        '',
        '기존 암호화 통로로 A50에 전달',
        '집·가족 권한은 A50에서 판단',
        '',
        '실제 서버 프로그램은 A50에 있음'],BLUE,'#f5f8ff',18)
    d.card(1100,320,440,310,'Galaxy A50 · 중앙 서버',[
        'cloudflared가 외부 통로를 유지',
        '로그인 증명·집·가족 역할 확인',
        '제어할 명령을 대기열에 보관',
        'Pi에서 받은 결과·센서 기록 저장',
        '휴대폰별 알림 선택·주기 적용',
        '집·가족·기록은 저장 파일에 유지'],BLUE,'#f5f8ff',18)
    d.rect(570,785,970,425,'#f4faf7','#9ebcaa')
    d.text(920,800,'각 가족의 집 · Raspberry Pi와 Zigbee 기기',22,GREEN,True)
    d.card(590,850,260,165,'Pi 연결 서비스',[
        '중앙 서버에 먼저 접속',
        '명령 조회·결과 보고',
        '새 센서 기록 전송'],PURPLE,'#faf7ff',18)
    d.card(900,850,260,165,'Pi 제어 프로그램',[
        '기기·센서·자동화 관리',
        '에어컨 명령 처리',
        '로컬 웹 화면도 제공'],BLUE,'#f5f8ff',17)
    d.card(1210,850,300,165,'MQTT / Zigbee 연결',[
        'MQTT: 집 안 메시지 전달',
        'Zigbee2MQTT + USB 동글',
        '센서·H2 기기와 통신'],GREEN,'#f4faf7',17)
    d.card(590,1090,260,100,'문·온습도 센서',['측정값과 문 열림 전송'],GREEN,'#f4faf7',17)
    d.card(900,1090,260,100,'실제 에어컨',['IR 신호를 받아 동작'],BLUE,'#f5f8ff',17)
    d.card(1210,1090,300,100,'ESP32-H2 + IR LED',['Zigbee 명령 → 적외선 송신'],BLUE,'#f5f8ff',17)
    d.card(60,845,340,175,'Firebase Cloud Messaging',[
        'FCM · 휴대폰 알림 배달',
        'A50이 고른 수신 기기로 전달',
        'Google 로그인과는 다른 기능'],ORANGE,'#fff8f0',17)
    d.arrow([(230,245),(230,320)],PURPLE,True)
    d.text(250,272,'로그인 증명',16,PURPLE)
    d.arrow([(1100,192),(970,192)],MUTED,True)
    d.text(1035,163,'주소 관리 위임',15,MUTED,anchor='middle')
    d.arrow([(370,320),(370,280),(540,280),(540,220),(570,220)],MUTED,True)
    d.text(455,254,'주소 조회',15,MUTED,anchor='middle')
    d.arrow([(770,245),(770,320)],MUTED,True)
    d.text(790,272,'목적지 안내',16,MUTED)
    d.arrow([(400,410),(570,410)],BLUE)
    d.text(485,377,'제어·조회 요청',17,BLUE,True,'middle')
    d.arrow([(970,410),(1100,410)],BLUE)
    d.text(1035,377,'암호화 통로',17,BLUE,True,'middle')
    d.arrow([(1100,510),(970,510)],MUTED)
    d.text(1035,522,'응답',17,MUTED,anchor='middle')
    d.arrow([(570,510),(400,510)],MUTED)
    d.text(485,522,'결과·집 기록',17,MUTED,anchor='middle')
    d.arrow([(1100,590),(970,590)],PURPLE,True)
    d.text(1035,605,'A50이 연결 유지',14,PURPLE,anchor='middle')
    d.arrow([(680,850),(680,630)],PURPLE,True)
    d.text(660,735,'Pi가 먼저 HTTPS로 접속',17,PURPLE,True,'end')
    d.text(660,764,'명령 조회·새 기록 전송',16,PURPLE,anchor='end')
    d.arrow([(850,630),(850,850)],BLUE)
    d.text(875,735,'조회 응답으로',17,BLUE)
    d.text(875,764,'대기 중인 명령 수신',17,BLUE)
    d.arrow([(850,905),(900,905)],BLUE)
    d.text(875,877,'명령',15,BLUE,anchor='middle')
    d.arrow([(1160,905),(1210,905)],BLUE)
    d.text(1185,877,'명령',15,BLUE,anchor='middle')
    d.arrow([(1210,975),(1160,975)],GREEN)
    d.arrow([(900,975),(850,975)],GREEN)
    d.text(875,986,'기록',15,GREEN,anchor='middle')
    d.arrow([(1360,1015),(1360,1090)],BLUE)
    d.text(1380,1039,'Zigbee',16,BLUE)
    d.arrow([(1210,1140),(1160,1140)],BLUE)
    d.text(1185,1113,'IR',16,BLUE,anchor='middle')
    d.arrow([(720,1090),(720,1050),(1280,1050),(1280,1015)],GREEN)
    d.text(1000,1023,'문 열림·온습도 기록 (Zigbee)',17,GREEN,anchor='middle')
    d.arrow([(1320,630),(1320,695),(455,695),(455,930),(400,930)],ORANGE)
    d.text(1090,665,'A50 → 선택한 휴대폰으로 알림 발송',18,ORANGE,True,'middle')
    d.arrow([(230,845),(230,630)],ORANGE)
    d.text(250,731,'푸시 알림',18,ORANGE,True)
    d.text(60,1240,'읽는 법',22,bold=True)
    notes=[
        '도메인·DNS는 목적지를 찾는 안내다. Spaceship은 구매·갱신을 맡고 앱의 제어 요청을 중계하지 않는다.',
        'Pi는 중앙 서버에 명령이 있는지 물어보고 응답으로 가져간다. 공유기의 내부 포트를 밖에 직접 열지 않는다.',
        'FCM은 알림을 배달한다. 에어컨 제어는 앱 → HTTPS → A50 → Pi의 조회 응답 → H2 → IR 순서다.',
        '명령 전송 결과와 실제 에어컨 반응은 구분한다. Tailscale·SSH는 별도의 관리와 기존 Pi 웹 화면에 사용한다.',
    ]
    for i,note in enumerate(notes):
        d.text(60,1280+i*27,'• '+note,17,MUTED)
    return d


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status',choices=['preparing','connected'],default='preparing')
    args=parser.parse_args()
    render(args.status).save(ROOT/'docs/architecture/connection-flow')
    print('CONNECTION_FLOW_SVG_AND_PNG_CREATED status='+args.status)
