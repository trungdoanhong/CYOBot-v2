"""Run a PC policy: predict(observations) returns {MAC: eight logical angles in degrees}."""
import argparse
import importlib.util
from pathlib import Path
from cyobot import Fleet, JointMap, IMU_OK


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path, help="Python file exporting predict(observations)")
    parser.add_argument("--robot", action="append", required=True, help="MAC=calibration.json; repeat per robot")
    parser.add_argument("--ip", action="append", help="Discovery addresses; default LAN broadcast")
    parser.add_argument("--hz", type=float, default=100)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("cyobot_user_policy", args.policy.resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    predict = module.predict
    maps = {}
    for value in args.robot:
        mac, config = value.split("=", 1)
        maps[mac.lower()] = JointMap.load(config)
    with Fleet() as fleet:
        found = {r.mac: r for r in fleet.discover(args.ip or ("255.255.255.255",))}
        missing = set(maps) - set(found)
        if missing:
            raise SystemExit("Robots not found: " + ", ".join(sorted(missing)))
        robots = [found[mac] for mac in maps]
        fleet.claim_all(robots)

        def policy(observations):
            for mac, observation in observations.items():
                if not observation["flags"] & IMU_OK or ((observation["uptime_us"] - observation["imu_us"]) & 0xFFFFFFFF) > 50000:
                    raise RuntimeError("IMU unavailable/stale for " + mac)
                observation["commanded_angles_deg"] = maps[mac].angles(observation["ticks"], found[mac].minimum, found[mac].maximum)
            actions = predict(observations)
            unknown = set(actions) - set(maps)
            if unknown:
                raise ValueError("Policy returned unknown robots: " + str(unknown))
            return {mac: maps[mac].ticks(angles, found[mac].minimum, found[mac].maximum)
                    for mac, angles in actions.items()}

        fleet.run(robots, policy, hz=args.hz)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Policy stopped; robots hold their last commanded pose.")
