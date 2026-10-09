"""Read/zero-output WLAN soak test. Refuses to run with any powered servo."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host'))
from cyobot import Fleet, OWNED


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--output', default='reports/connection-baseline.json')
    args = parser.parse_args()
    result = dict(samples=[], failures=[], max_send_gap_ms=0, max_rx_age_ms=0)
    with Fleet() as fleet:
        robots = fleet.discover(['192.168.1.8'], timeout=.5)
        if not robots or robots[0].flags & OWNED:
            raise RuntimeError('Board missing or already controlled; do not steal session')
        robot = robots[0]
        fleet.claim(robot)
        if any(robot.telemetry['ticks']):
            raise RuntimeError('Refusing test while any servo is powered')
        result.update(mac=robot.mac, boot=robot.boot, lease_ms=robot.lease_ms)
        start = previous = next_sample = time.perf_counter()
        sent = 0
        while time.perf_counter()-start < args.seconds:
            fleet.poll()
            now = time.perf_counter()
            gap = (now-previous)*1000
            age = (now-robot.seen_at)*1000
            result['max_send_gap_ms'] = max(result['max_send_gap_ms'], gap)
            result['max_rx_age_ms'] = max(result['max_rx_age_ms'], age)
            if now >= next_sample:
                result['samples'].append(dict(t=round(now-start,3), sent=sent, seq=robot.sequence,
                    gap_ms=round(gap,2), age_ms=round(age,2), **robot.telemetry))
                next_sample = now+.05
            if age > robot.lease_ms or not robot.flags & OWNED:
                result['failures'].append(dict(t=now-start, sent=sent, seq=robot.sequence,
                    age_ms=age, gap_ms=gap, telemetry=robot.telemetry))
                break
            fleet.send_ticks(robot, [0]*16)
            sent += 1
            previous = now
            time.sleep(max(0,.01-(time.perf_counter()-now)))
        result.update(duration_s=time.perf_counter()-start, sent=sent)
    with Fleet() as probe:
        result['after'] = [dict(boot=r.boot,flags=r.flags,challenge=r.challenge) for r in probe.discover(['192.168.1.8'],timeout=.5)]
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2),flush=True)


if __name__ == '__main__':
    main()
