"""Preview a routine in the terminal, or explicitly run it with --ip ROBOT_IP."""
import argparse
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from cyobot import Fleet,JointMap
from routines import Routine,CATALOG

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name',choices=CATALOG,nargs='?',default='bow')
    parser.add_argument('--ip',help='Send to this robot; omitted = terminal preview only')
    parser.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[2]/'MicroPython/sd/config/robot-config.json')
    parser.add_argument('--speed',type=float,default=1)
    parser.add_argument('--repeats',type=int,default=1)
    args=parser.parse_args()
    mapping=JointMap.load(args.config)
    demo=Routine(args.name,[0]*8,args.speed,args.repeats)
    for frame in demo.frames:mapping.ticks(frame['angles'])
    if not args.ip:
        print(f'PREVIEW ONLY: {args.name}, {demo.duration:.2f} seconds')
        for i in range(6):
            t=i*demo.duration/5
            print(f'{t:5.2f}s: '+str([round(a,2) for a in demo.angles(t)]))
        return
    with Fleet() as fleet:
        robots=fleet.discover([args.ip])
        if len(robots)!=1:raise RuntimeError('Expected exactly one robot at the supplied IP')
        robot=robots[0];fleet.claim(robot)
        routine=Routine(args.name,mapping.angles(robot.telemetry['ticks'],robot.minimum,robot.maximum),args.speed,args.repeats)
        start=time.perf_counter()
        def step(observations):
            frame=mapping.ticks(routine.angles(time.perf_counter()-start),robot.minimum,robot.maximum)
            ticks=list(observations[robot.mac]['ticks'])
            for joint in mapping.joints:ticks[joint['pin']]=frame[joint['pin']]
            return {robot.mac:ticks}
        fleet.run([robot],step,hz=50,seconds=routine.duration+.1)
    print('Routine finished. Last angles are held.')

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Stopped. Last commanded angles are held.')
