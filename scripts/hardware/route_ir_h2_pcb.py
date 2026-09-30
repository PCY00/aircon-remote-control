"""Critical explicit routing followed by local offline autorouting of residual nets."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import pcbnew as p

OUT=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\IR_ESP32H2\codex-revA')
NAME='IR_ESP32H2_RevA'
PCB=OUT/(NAME+'.kicad_pcb')
KICAD=Path(r'C:\Users\kksp1\AppData\Local\Programs\KiCad\10.0')
ROUTER=Path(r'C:\Users\kksp1\OneDrive\Desktop\설계-하드웨어\kicad\KeyRing\tmp\route_tools')
os.environ['KIPRJMOD']=str(OUT)

def v(x,y): return p.VECTOR2I(p.FromMM(x),p.FromMM(y))
def xy(pad): return (p.ToMM(pad.GetPosition().x),p.ToMM(pad.GetPosition().y))

board=p.LoadBoard(str(PCB))
fps={f.GetReference():f for f in board.GetFootprints()}

def pad(ref,n):
    return next(pad for pad in fps[ref].Pads() if pad.GetNumber()==str(n))

def trace(net,points,width=.22,layer=p.F_Cu):
    for a,b in zip(points,points[1:]):
        if a==b: continue
        t=p.PCB_TRACK(board)
        t.SetStart(v(*a));t.SetEnd(v(*b));t.SetWidth(p.FromMM(width));t.SetLayer(layer)
        t.SetNet(board.FindNet('/'+net));t.SetLocked(True);board.Add(t)

def via(net,x,y,diam=.6,drill=.3):
    t=p.PCB_VIA(board);t.SetPosition(v(x,y));t.SetWidth(p.FromMM(diam));t.SetDrill(p.FromMM(drill))
    t.SetViaType(p.VIATYPE_THROUGH);t.SetLayerPair(p.F_Cu,p.B_Cu)
    t.SetNet(board.FindNet('/'+net));t.SetLocked(True);board.Add(t)

# Tight switching loops on top. No switch-node vias and no tracks beneath coil.
trace('SW_L1',[xy(pad('U3',9)),(120.38,123.5),(120.68,123.2)])
trace('SW_L1',[(120.68,123.2),xy(pad('L1',1))],.5)
trace('SW_L2',[xy(pad('U3',7)),(120.38,124.5),(120.68,124.8)])
trace('SW_L2',[(120.68,124.8),xy(pad('L1',2))],.5)
trace('VSYS',[xy(pad('U3',10)),(119.75,122.2)],.22)
trace('VSYS',[(119.75,122.2),(120.475,121.475),xy(pad('C3',1))],.5)
trace('VSYS',[xy(pad('U3',1)),(117.4,123),(117.4,122.2),(119.75,122.2)],.22)
trace('3V3_REG',[xy(pad('U3',6)),(119.75,125.8)],.22)
trace('3V3_REG',[(119.75,125.8),(120.475,126.525),xy(pad('C4',1))],.5)

# A short local power-ground via and a quiet FB/AGND branch into the ground plane.
trace('GND',[xy(pad('U3',8)),(120.8,124)],.22);via('GND',120.8,124)
trace('GND',[xy(pad('C3',2)),(116.5,121)],.6);via('GND',116.5,121)
trace('GND',[xy(pad('C4',2)),(116.5,127)],.6);via('GND',116.5,127)
trace('GND',[xy(pad('U3',2)),(117.4,123.5),(116.6,123.5)],.22)
trace('GND',[xy(pad('U3',3)),(117.4,124),(117.4,123.5)],.22)
via('GND',116.6,123.5)
trace('GND',[xy(pad('R11',2)),(116.1,122.175),(116.6,122.675),(116.6,123.5)],.22)
trace('FB',[xy(pad('R11',1)),(114.5,124.5),xy(pad('R10',2))],.2)
trace('FB',[(114.5,124.5),xy(pad('U3',4))],.2)
trace('3V3_REG',[xy(pad('R10',1)),(114.5,129.2),(120.475,129.2),xy(pad('C4',1))],.2)

# Native USB differential pins to their series resistors: direct, no vias.
trace('USB_DP',[xy(pad('U1',27)),(147.3,108.2),(147.6,107.9),xy(pad('R4',2))],.2)
trace('USB_DM',[xy(pad('U1',26)),(147.3,109),(147.6,109.3),xy(pad('R3',2))],.2)

# Mux input bypass capacitors are within a couple millimeters of their pins.
trace('USB_5V',[xy(pad('C1',1)),xy(pad('U2',3))],.22)
trace('BAT_PROTECTED',[xy(pad('U2',6)),xy(pad('C2',1))],.22)
trace('VSYS',[xy(pad('U2',2)),xy(pad('U2',7)),(110,120.75),(110,119.4)],.22)
via('VSYS',110,119.4)
via('VSYS',122,121)
trace('VSYS',[(110,119.4),(110.8,118.6),(114.9,118.6),(117.3,116.2),(122.8,116.2),(124,117.4),(124,119),(122,121)],.5,p.B_Cu)
trace('VSYS',[(122,121),xy(pad('C3',1))],.5)

board.BuildConnectivity()
assert p.SaveBoard(str(PCB),board)
assert p.ExportSpecctraDSN(board,str(OUT/'checks/route-input.dsn'))
print('Critical routing written:',len(list(board.GetTracks())),'track/via items',flush=True)

parser=argparse.ArgumentParser()
parser.add_argument('--autoroute',action='store_true')
args=parser.parse_args()
if args.autoroute:
    cmd=[str(ROUTER/'jre25/jdk-25.0.4.1+1-jre/bin/java.exe'),'-jar',str(ROUTER/'freerouting-2.4.1.jar'),
         '-de',str(OUT/'checks/route-input.dsn'),'-do',str(OUT/'checks/route-output.ses'),'-da',
         '--gui.enabled=false','--api_server.enabled=false',f'--user_data_path={OUT/"checks/router-data"}',
         '--router.max_passes=20','--router.optimizer.max_passes=3']
    with (OUT/'checks/router-log.txt').open('w',encoding='utf-8') as log:
        run=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    assert run.returncode==0,run.returncode
    assert p.ImportSpecctraSES(board,str(OUT/'checks/route-output.ses'))
    board.BuildConnectivity()
    assert p.SaveBoard(str(PCB),board)
    print('Imported routing:',len(list(board.GetTracks())),'track/via items',flush=True)
