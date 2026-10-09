"""PC controls. Discover/monitor/benchmark do not request servo movement."""
import argparse
import json
import statistics
import time
from cyobot import Fleet, JointMap
from gait import CrawlerGait, GAITS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["discover", "monitor", "benchmark", "off", "pose", "servo-test", "walk"])
    parser.add_argument("--ip", action="append", help="Repeat for multiple robots; default broadcast discovery")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--hz", type=float, default=100)
    parser.add_argument("--config", help="Robot calibration JSON, required for pose")
    parser.add_argument("--angles", type=float, nargs=8, help="Eight logical joint angles, in degrees")
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--amplitude", type=float, default=10, help="Servo-test degrees either side of center")
    parser.add_argument("--report", help="Write benchmark JSON")
    parser.add_argument("--motion", choices=list(GAITS), default="forward")
    parser.add_argument("--cycle", type=float, default=1.0, help="Seconds per gait cycle")
    args = parser.parse_args()
    if args.seconds <= 0 or not 1 <= args.hz <= 400:
        parser.error("seconds > 0 and 1 <= hz <= 400 required")
    if args.command == "pose" and (not args.config or args.angles is None):
        parser.error("pose requires --config and --angles")
    if args.command == "walk" and (not args.config or args.cycle <= 0):
        parser.error("walk requires --config and --cycle > 0")
    if args.command == "servo-test" and (not 0 <= args.channel <= 15 or not 0 < args.amplitude <= 90):
        parser.error("channel 0..15, amplitude 0..90 degrees")
    mapping = JointMap.load(args.config) if args.command in ("pose", "walk") else None
    poses = mapping.ticks(args.angles) if args.command == "pose" else None
    with Fleet() as fleet:
        robots = fleet.discover(args.ip or ("255.255.255.255",))
        if not robots:
            raise SystemExit("No robots found; try --ip or check the Wi-Fi")
        if args.command == "discover":
            for r in robots:
                print(f"{r.mac}  {r.address[0]}:{r.address[1]} flags={r.flags} boot={r.boot:08x}")
            return
        fleet.claim_all(robots)
        if args.command == "off":
            for robot in robots:
                fleet.off(robot)
                print(robot.mac, "all PWM off, confirmed")
            return
        held = {r.mac: list(r.telemetry["ticks"]) for r in robots}
        gaits = {r.mac: CrawlerGait(args.motion, mapping.angles(held[r.mac]), args.cycle)
                 for r in robots} if args.command == "walk" else {}
        initial = {r.mac: r.telemetry["received"] for r in robots}
        initial_applied = {r.mac: r.telemetry["applied"] for r in robots}
        sent = {r.mac: 0 for r in robots}
        start, display = time.perf_counter(), [0]

        def policy(observations):
            now = time.perf_counter()
            if args.command == "monitor" and now - display[0] >= 1:
                print(json.dumps(observations, ensure_ascii=False))
                display[0] = now
            actions = {mac: list(ticks) for mac, ticks in held.items()}
            if args.command == "pose":
                actions = {r.mac: list(poses) for r in robots}
            elif args.command == "walk":
                actions = {r.mac: mapping.ticks(gaits[r.mac].angles(now-start), r.minimum, r.maximum)
                           for r in robots}
            elif args.command == "servo-test":
                import math
                # Test is generated ONLY on the PC. Other channels retain their state.
                angle = args.amplitude * math.sin((now - start) * math.pi)
                for r in robots:
                    actions[r.mac][args.channel] = round(r.minimum + (angle + 90) * (r.maximum - r.minimum) / 180)
            for mac in actions:
                sent[mac] += 1
            return actions

        fleet.run(robots, policy, hz=args.hz, seconds=args.seconds)
        # Drain feedback without adding commands; still within the 250 ms lease.
        feedback_deadline = time.perf_counter() + .1
        while time.perf_counter() < feedback_deadline:
            fleet.poll(.005)
            if all(r.telemetry["applied_seq"] == r.sequence for r in robots):
                break
        report = {"requested_hz": args.hz, "seconds": args.seconds, "robots": {}}
        for r in robots:
            rtt = sorted(r.rtt_ms)
            item = dict(sent=sent[r.mac], received=r.telemetry["received"]-initial[r.mac],
                        applied=r.telemetry["applied"]-initial_applied[r.mac],
                        samples=len(rtt), rtt_median_ms=statistics.median(rtt) if rtt else None,
                        rtt_p95_ms=rtt[min(len(rtt)-1, int(len(rtt)*.95))] if rtt else None,
                        last_i2c_apply_us=r.telemetry["apply_us"], status=r.telemetry)
            report["robots"][r.mac] = item
        if args.command == "benchmark":
            print(json.dumps(report, indent=2))
        if args.report:
            from pathlib import Path
            target = Path(args.report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Controller stopped; robots hold their last commanded pose.")
