"""Measure duplex PCM and servo continuity on an idle board; optional quiet tone."""
import argparse
import json
import math
from pathlib import Path
import struct
import sys
import time
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from cyobot import Fleet, OWNED
from studio import Studio

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--tone',action='store_true');a=p.parse_args()
    with Fleet() as f:
        r,=f.discover(['192.168.1.8'],timeout=.5)
        if r.flags&OWNED:raise RuntimeError('Robot is already controlled')
        f.claim(r)
        if any(r.telemetry['ticks']):raise RuntimeError('Refusing powered servos')
    studio=Studio(auto_scan=False,connection_log_path=None);records=[];pcm=bytearray();client='media-smoke'
    try:
        studio.action(dict(action='found',robots=[r]));studio.action(dict(action='connect',mac=r.mac,client=client))
        audio=studio.media.start_audio();audio.set_volume(15 if a.tone else 0)
        info=studio.media.info();start=next_pcm=heartbeat=time.perf_counter();index=0
        while time.perf_counter()-start<a.seconds:
            now=time.perf_counter();elapsed=now-start
            if now>=heartbeat:studio.action(dict(action='heartbeat',client=client));heartbeat=now+.2
            if now>=next_pcm:
                sound=a.tone and 2<=elapsed<3
                block=struct.pack('<320h',*(round(4096*math.sin(2*math.pi*500*(index*320+i)/16000)) if sound else 0 for i in range(320)))
                audio.write_pcm(block);index+=1;next_pcm=now+.02 if now-next_pcm>.04 else next_pcm+.02
            while True:
                block=audio.read_pcm(timeout=0)
                if not block:break
                pcm.extend(block)
            s=studio.state()
            if not s['connected'] or not audio.alive:raise RuntimeError('Media lost connection: '+str(s))
            if any(s['telemetry']['ticks']):raise RuntimeError('Unexpected servo output')
            if not records or elapsed-records[-1]['t']>.2:records.append(dict(t=elapsed,audio=audio.state(),connection=s['connection_stats']))
            time.sleep(.002)
        result=dict(seconds=a.seconds,tone=a.tone,initial=info,final=studio.media.info(),audio=audio.state(),records=records,pcm_bytes=len(pcm))
        Path('reports/media-duplex-final.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        if a.tone:
            with wave.open('reports/media-loopback.wav','wb') as out:out.setnchannels(2);out.setsampwidth(2);out.setframerate(16000);out.writeframes(pcm)
        print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2),flush=True)
    finally:studio.close()
if __name__=='__main__':main()
