"""Real-board LED protocol check, low brightness; refuses enabled servos."""
import argparse
from pathlib import Path
import struct
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from cyobot import *


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ip',required=True);args=p.parse_args()
    black_matrix=[[0,0,0] for _ in range(33)];black_ring=[[0,0,0] for _ in range(12)]
    with Fleet() as f:
        r,=f.discover([args.ip],timeout=.3);f.claim(r)
        assert r.flags & LED_READY and not r.flags & FAULT
        if any(r.telemetry['ticks']):raise RuntimeError('Servo enabled; use an idle/off robot')
        def wait(predicate,timeout=.18,retry=None):
            end=time.perf_counter()+timeout;send_at=0;retry_at=time.perf_counter()
            while time.perf_counter()<end:
                now=time.perf_counter()
                if now-send_at>.01:f.send_ticks(r,[0]*16);send_at=now
                if retry and now-retry_at>.08:retry();retry_at=now
                f.poll(.003)
                assert not any(r.telemetry['ticks']) and not r.flags & FAULT
                if predicate():return
            raise AssertionError('LED confirmation not received: '+str(dict(leds=r.leds,telemetry=r.telemetry)))
        wait(lambda:r.leds is not None)
        for i in range(45):
            m=[list(x) for x in black_matrix];ring=[list(x) for x in black_ring]
            (m if i<33 else ring)[i if i<33 else i-33]=[6,3,1]
            seq=f.send_leds(r,m,ring)
            wait(lambda:(r.leds['applied_seq']==seq or is_newer(r.leds['applied_seq'],seq)) and r.leds['matrix']==m and r.leds['ring']==ring,
                 timeout=.55,retry=lambda:f.send_leds(r,m,ring))
        print('PASS all 33 matrix + 12 ring indices confirmed; PWM remains off')
        m=[[i%7,(i+2)%7,(i+4)%7] for i in range(33)]
        ring=[[i%5,(i+1)%5,(i+3)%5] for i in range(12)]
        frame_seq=f.send_ticks(r,[0]*16);led_seq=f.send_leds(r,m,ring)
        end=time.perf_counter()+.18
        while time.perf_counter()<end:
            f.poll(.002)
            if r.telemetry['applied_seq']==frame_seq and r.leds['applied_seq']==led_seq:break
        assert r.telemetry['applied_seq']==frame_seq and r.leds['applied_seq']==led_seq
        print('PASS interleaved LED/PWM acknowledgements use separate applied sequences')
        r.sequence=(r.sequence+1)&0xffffffff;delayed_seq=r.sequence
        delayed=packet(LED_FRAME,r.session,delayed_seq,led_bytes(m,ring))
        f.send_ticks(r,[0]*16)
        f.socket.sendto(delayed,r.address)
        wait(lambda:r.leds['applied_seq']==delayed_seq)
        rejected=r.telemetry['rejected']
        f.socket.sendto(delayed,r.address)
        wait(lambda:r.telemetry['rejected']>rejected)
        assert r.leds['matrix']==m and r.leds['ring']==ring
        print('PASS delayed LED after newer PWM is accepted; duplicate LED is rejected')
        rejected=r.telemetry['rejected'];previous=dict(r.leds)
        seq=f._send(r,LED_FRAME,b'bad')
        wait(lambda:r.telemetry['rejected']>rejected)
        assert r.leds==previous
        print('PASS malformed LED packet cannot alter lights')
        time.sleep(r.lease_ms/1000+.05)
        fresh,=f.discover([args.ip],timeout=.08)
        assert not fresh.flags & OWNED
        f.claim(fresh);r=fresh
        wait(lambda:r.leds is not None)
        assert r.leds['matrix']==m and r.leds['ring']==ring and not any(r.telemetry['ticks'])
        print('PASS lease loss preserves LED colors and PWM')
        seq=f.send_leds(r,black_matrix,black_ring)
        wait(lambda:r.leds['applied_seq']==seq and r.leds['matrix']==black_matrix and r.leds['ring']==black_ring)
        print('PASS both LED groups off; no servo movement requested')


if __name__=='__main__':main()
