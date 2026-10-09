"""Exercise protocol on a real idle robot. Refuses to run if any servo is enabled."""
import argparse
from dataclasses import replace
from pathlib import Path
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from cyobot import *


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ip", required=True)
    args = p.parse_args()
    with Fleet() as f:
        r, = f.discover([args.ip], timeout=.25)
        f.claim(r)
        assert r.flags & PWM_OK and r.flags & IMU_OK and not r.flags & FAULT
        if any(r.telemetry["ticks"]):
            raise RuntimeError("Servo enabled: run this test on an idle/off robot")
        zeros = FRAME_BODY.pack(*([0]*16))

        def await_status(predicate, timeout=.15):
            end = time.perf_counter()+timeout
            while time.perf_counter()<end:
                f.poll(.005)
                if predicate(r.telemetry):
                    return
            raise AssertionError("Expected status not received: " + str(r.telemetry))

        first = f.send_ticks(r,[0]*16)
        await_status(lambda s: s["applied_seq"]==first)
        count, rejected = r.telemetry["received"], r.telemetry["rejected"]
        # Duplicate, out-of-order and malformed packets must not advance the counter.
        f.socket.sendto(packet(FRAME,r.session,first,zeros),r.address)
        f.socket.sendto(packet(FRAME,r.session,first-1,zeros),r.address)
        f.socket.sendto(packet(FRAME,r.session,first+1,zeros[:-1]),r.address)
        await_status(lambda s: s["rejected"]>=rejected+3)
        assert r.telemetry["received"]==count
        print("PASS duplicate/reordered/malformed frames")

        with Fleet() as stranger:
            wrong = replace(r, session=0, telemetry=None)
            stranger.robots[wrong.mac]=wrong
            stranger._addresses[wrong.address]=wrong
            # Correct session token from the wrong source port is also rejected.
            stranger.socket.sendto(packet(FRAME,r.session,first+100,zeros),r.address)
            f.send_ticks(r,[0]*16)
            try:
                stranger.claim(wrong,timeout=.06)
                raise AssertionError("A second client stole the active lease")
            except TimeoutError:
                pass
        assert r.telemetry["received"]<=count+1
        print("PASS controller ownership")

        seq=f.send_ticks(r,[0]*16)
        await_status(lambda s:s["applied_seq"]==seq)
        old_sid, old_challenge = r.session, r.challenge
        expiry=time.perf_counter()+r.lease_ms/1000+.05
        while time.perf_counter()<expiry:
            f.query_diagnostics(r)
            f.poll(.02)
        f.query_diagnostics(r);f.poll(.03)
        assert r.diagnostics and r.diagnostics['session']==0 and r.diagnostics['release_reason']==1
        print('PASS read-only diagnostics do not renew the command lease')
        fresh, = f.discover([args.ip], timeout=.08)
        assert not fresh.flags & OWNED and fresh.challenge!=old_challenge
        f.socket.sendto(packet(FRAME,old_sid,seq+1,zeros),r.address)
        f.socket.sendto(packet(CLAIM,old_sid,1,struct.pack('<II',r.boot,old_challenge)),r.address)
        f.claim(fresh)
        r=fresh
        assert r.telemetry["ticks"]==[0]*16 and r.telemetry["applied_seq"]==0
        print("PASS lease expiry, preserved outputs, stale-session rejection, explicit reclaim")
        f.off(r)
        print("PASS OFF acknowledgement")
    print("Hardware protocol checks passed; no movement requested.")


if __name__=="__main__":
    main()
