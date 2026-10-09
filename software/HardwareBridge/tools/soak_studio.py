"""Real-board Studio recovery check; drops only zero-output servo packets."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from cyobot import Fleet, FRAME, OWNED
from studio import Studio


class DroppingFleet(Fleet):
    drop_until = 0
    dropped = 0

    def _send(self, robot, kind, body=b''):
        if kind == FRAME and time.perf_counter() < self.drop_until:
            robot.sequence = (robot.sequence+1)&0xffffffff
            self.dropped += 1
            return robot.sequence
        return super()._send(robot,kind,body)


def main():
    ip='192.168.1.8';client='recovery-hardware-check'
    with Fleet() as probe:
        robot,=probe.discover([ip],timeout=.4)
        if robot.flags & OWNED:raise RuntimeError('Board already owned')
        probe.claim(robot)
        if any(robot.telemetry['ticks']):raise RuntimeError('Refusing powered servos')
    studio=Studio(fleet_factory=DroppingFleet,auto_scan=False,connection_log_path=None)
    records=[]
    try:
        studio.action(dict(action='found',robots=[robot]))
        studio.action(dict(action='connect',mac=robot.mac,client=client))
        def observe(seconds, heartbeat=True):
            end=time.perf_counter()+seconds
            while time.perf_counter()<end:
                if heartbeat:studio.action(dict(action='heartbeat',client=client))
                s=studio.state()
                if s['telemetry']:assert not any(s['telemetry']['ticks'])
                records.append(dict(t=time.perf_counter(),connected=s['connected'],reconnecting=s['reconnecting'],
                    stale=s['link_stale'],mode=s['mode'],session=s['control_session'],stats=s['connection_stats']))
                time.sleep(.04)
        observe(.3)
        initial=studio.robot.session
        studio.fleet.drop_until=time.perf_counter()+.4
        observe(.65)
        assert studio.robot.session==initial and studio.reconnections==0
        assert any(s['stale'] for s in records)
        assert studio.mode=='hold'
        print('PASS 400 ms uplink blackout: HOLD, same session',flush=True)
        studio.fleet.drop_until=time.perf_counter()+1.3
        observe(2.3)
        assert studio.robot and studio.robot.session!=initial and studio.reconnections>=1
        assert studio.targets==[0]*16 and studio.mode=='hold' and studio.led_pending is None
        print('PASS 1300 ms uplink blackout: fresh session, read board pose, no replay',flush=True)
        count=studio.fleet.dropped
        observe(1.1,heartbeat=False)
        assert studio.robot and studio.browser_paused
        observe(.2)
        assert studio.mode=='hold' and studio.robot
        print('PASS browser heartbeat stall: board remains connected',flush=True)
        result=dict(records=records, dropped_frames=count, reconnections=studio.reconnections,
            final=studio.state())
        Path('reports/studio-recovery-hardware.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    finally:
        studio.close()


if __name__=='__main__':main()
