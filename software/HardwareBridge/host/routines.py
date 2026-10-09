"""Finite, PC-side motion programs in logical crawler joint degrees."""
import json
import math
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent/'ui'/'routines.json').read_text())


class Routine:
    def __init__(self, name, initial, speed=1, repeats=1):
        if not isinstance(name,str) or name not in CATALOG:
            raise ValueError('Unknown routine')
        if type(speed) not in (int,float) or not math.isfinite(speed) or not .5 <= speed <= 1.5:
            raise ValueError('Routine speed must be 0.5–1.5')
        if type(repeats) is not int or not 1 <= repeats <= 5:
            raise ValueError('Repeat count must be 1–5')
        if len(initial)!=8 or not all(math.isfinite(x) for x in initial):
            raise ValueError('Eight finite starting angles required')
        self.name,self.speed,self.repeats=name,speed,repeats
        self.initial=list(initial)
        frames=CATALOG[name]['frames']
        if not frames or any(
            type(f.get('seconds')) not in (int,float) or not math.isfinite(f['seconds']) or f['seconds']<=0
            or not isinstance(f.get('angles'),list) or len(f['angles'])!=8
            or any(type(x) not in (int,float) or not math.isfinite(x) for x in f['angles'])
            for f in frames
        ):
            raise ValueError('Routine frames require a positive duration and eight finite angles')
        self.frames=frames*repeats
        self.duration=sum(frame['seconds'] for frame in self.frames)/speed

    def angles(self, elapsed):
        remaining=max(0,elapsed)*self.speed
        before=self.initial
        for frame in self.frames:
            after=frame['angles']
            if remaining < frame['seconds']:
                fraction=remaining/frame['seconds']
                blend=fraction*fraction*(3-2*fraction)
                return [a+(b-a)*blend for a,b in zip(before,after)]
            remaining-=frame['seconds']
            before=after
        return list(before)
