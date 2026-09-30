"""Route the current user's placement; no component moves or old Rev A geometry."""
from pathlib import Path
import argparse,json,os,subprocess
import pcbnew as p
ROOT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2')
OUT=ROOT/'artwork-current';PCB=OUT/'IR_ESP32H2.kicad_pcb'
ROUTER=ROOT.parent/'KeyRing/tmp/route_tools'
os.environ['KIPRJMOD']=str(OUT)
def v(x,y):return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def xy(i):return (p.ToMM(i.GetPosition().x),p.ToMM(i.GetPosition().y))
b=p.LoadBoard(str(PCB));fps={f.GetReference():f for f in b.GetFootprints()}
def pad(ref,n):return next(i for i in fps[ref].Pads() if i.GetNumber()==str(n))
def trace(net,points,width=.22,layer=p.F_Cu):
    for a,c in zip(points,points[1:]):
        if a==c:continue
        t=p.PCB_TRACK(b);t.SetStart(v(*a));t.SetEnd(v(*c));t.SetWidth(p.FromMM(width));t.SetLayer(layer)
        t.SetNet(b.FindNet(net));t.SetLocked(True);b.Add(t)
def via(net,x,y,diam=.6,drill=.3):
    t=p.PCB_VIA(b);t.SetPosition(v(x,y));t.SetWidth(p.FromMM(diam));t.SetDrill(p.FromMM(drill))
    t.SetViaType(p.VIATYPE_THROUGH);t.SetLayerPair(p.F_Cu,p.B_Cu);t.SetNet(b.FindNet(net));t.SetLocked(True)
    t.SetFrontTentingMode(p.TENTING_MODE_TENTED);t.SetBackTentingMode(p.TENTING_MODE_TENTED);b.Add(t)

trace('/SW_L1',[xy(pad('U5',9)),(100.38,82.5),(100.68,82.1265)])
trace('/SW_L1',[(100.68,82.1265),xy(pad('L1',1))],.5)
trace('/SW_L2',[xy(pad('U5',7)),(100.38,83.5),(100.68,83.8735)])
trace('/SW_L2',[(100.68,83.8735),xy(pad('L1',2))],.5)
trace('/VSYS',[xy(pad('U5',10)),(99.75,81.2)])
trace('/VSYS',[(99.75,81.2),(99.95,81),xy(pad('C10',1))],.5)
trace('/VSYS',[xy(pad('U5',1)),(97.4,82),(97.4,81.2),(99.75,81.2)])
trace('/3V3_REG',[xy(pad('U5',6)),(99.75,84.8)])
trace('/3V3_REG',[(99.75,84.8),(100.475,85.525),xy(pad('C8',2))],.5)
trace('GND',[xy(pad('U5',8)),(100.8,83)]);via('GND',100.8,83)
trace('GND',[xy(pad('C10',2)),(96.9,80)],.5);via('GND',96.9,80)
trace('GND',[xy(pad('C8',1)),(96.4,86)],.5);via('GND',96.4,86)
trace('GND',[xy(pad('U5',2)),(97.4,82.5),(96.6,82.5)])
trace('GND',[xy(pad('U5',3)),(97.4,83),(97.4,82.5)]);via('GND',96.6,82.5)
trace('GND',[xy(pad('R14',2)),(95.7,81.99),(96.21,82.5),(96.6,82.5)])
trace('/FB',[xy(pad('R14',1)),(94.8,83.5),xy(pad('R15',2))],.2)
trace('/FB',[(94.8,83.5),xy(pad('U5',4))],.2)
trace('/3V3_REG',[xy(pad('R15',1)),(94.8,88),(100.475,88),xy(pad('C8',2))],.2)
# Strong regulator supply paths on the back, not back-mounted components.
trace('/VSYS',[(95.68,65.69),(95.68,63.8)],.3);via('/VSYS',95.68,63.8)
via('/VSYS',101.1,79.7)
trace('/VSYS',[(95.68,63.8),(100.5,68.62),(100.5,79.1),(101.1,79.7)],.6,p.B_Cu)
trace('/VSYS',[(101.1,79.7),(100.8,80),xy(pad('C10',1))],.5)
trace('/VSYS',[xy(pad('C9',1)),(101.1,78.42),(101.1,79.7)],.3)
via('/3V3_REG',101.5,86)
trace('/3V3_REG',[xy(pad('C8',2)),(101.5,86)],.6)
via('/3V3_REG',75.5,89)
trace('/3V3_REG',[(101.5,86),(100.5,87),(74,87),(74,88.5),(74.5,89),(75.5,89)],.6,p.B_Cu)
trace('/3V3_REG',[(75.5,89),xy(pad('R16',1))],.6)
trace('/+3V3',[xy(pad('U2',3)),(73.2,81.2),(72.72,81.68),xy(pad('C2',1))],.3)
trace('/+3V3',[xy(pad('C2',1)),(72.72,82.8),(73.35,83.43),xy(pad('C3',1))],.5)
trace('/+3V3',[xy(pad('C3',1)),(73.35,85.5),(75.15,87.3),(77.9125,87.3),xy(pad('R16',2))],.6)
via('/+3V3',79,89)
trace('/+3V3',[xy(pad('R16',2)),(79,89)],.6)
via('/+3V3',136.5,84)
trace('/+3V3',[(79,89),(82.5,92.5),(128,92.5),(136.5,84)],.6,p.B_Cu)
trace('/+3V3',[(136.5,84),(136.5,79.975),xy(pad('C5',2))],.6)
trace('/+3V3',[xy(pad('C5',2)),(136.475,79.995),xy(pad('C6',1))],.3)
trace('/+3V3',[(136.5,84),(139.5,87),xy(pad('R12',2))],.5)
trace('Net-(D1-A)',[xy(pad('R12',1)),(146.14,87),(148,85.14),(148,77.6),xy(pad('D1',2))],.5)
trace('/IR_K',[xy(pad('Q1',3)),xy(pad('D1',1))],.5)
trace('GND',[xy(pad('Q1',2)),(139.5625,76.4)],.6);via('GND',139.5625,76.4)
# Very short device-side full-speed USB traces. Connector reversal is routed separately.
trace('/USB_DP',[xy(pad('U2',27)),(78,67.1),(77.9,67),xy(pad('R5',1))],.2)
trace('/USB_DM',[xy(pad('U2',26)),(78.8,67.8),(80,66.6),xy(pad('R1',1))],.2)
b.BuildConnectivity();assert p.SaveBoard(str(PCB),b)
assert p.ExportSpecctraDSN(b,str(OUT/'checks/user-route-input.dsn'))
print('Manual critical route items:',len(list(b.GetTracks())),flush=True)
parser=argparse.ArgumentParser();parser.add_argument('--autoroute',action='store_true');args=parser.parse_args()
if args.autoroute:
    cmd=[str(ROUTER/'jre25/jdk-25.0.4.1+1-jre/bin/java.exe'),'-jar',str(ROUTER/'freerouting-2.4.1.jar'),
         '-de',str(OUT/'checks/user-route-input.dsn'),'-do',str(OUT/'checks/user-route-output.ses'),'-da',
         '--gui.enabled=false','--api_server.enabled=false',f'--user_data_path={OUT/"checks/router-data"}',
         '--router.max_passes=30','--router.optimizer.max_passes=2']
    with (OUT/'checks/router-log.txt').open('w',encoding='utf8') as log:
        result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=900)
    assert result.returncode==0,result.returncode
    assert p.ImportSpecctraSES(b,str(OUT/'checks/user-route-output.ses'))
    b.BuildConnectivity();assert p.SaveBoard(str(PCB),b)
    print('Routing imported:',len(list(b.GetTracks())),flush=True)
