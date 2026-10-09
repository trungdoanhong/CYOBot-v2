from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from routines import Routine,CATALOG
from led_effects import LedEffect,CHARACTER_PIXELS
from cyobot import JointMap
from studio import DEFAULT_CONFIG

class ProgramsTests(unittest.TestCase):
    def test_custom_routine_rejects_invalid_keyframes(self):
        for frames in [[],[{'seconds':0,'angles':[0]*8}],[{'seconds':1,'angles':[0]*7}],[{'seconds':1,'angles':[float('nan')]*8}]]:
            with patch.dict(CATALOG,{'custom':{'frames':frames}}):
                with self.assertRaises(ValueError):Routine('custom',[0]*8)

    def test_all_routines_interpolate_and_end_at_home_with_valid_calibration(self):
        mapping=JointMap.load(DEFAULT_CONFIG)
        for name in CATALOG:
            r=Routine(name,[5]*8,speed=1.5,repeats=3)
            self.assertEqual(r.angles(0),[5]*8)
            self.assertEqual(r.angles(r.duration+1),[0]*8)
            for i in range(101):
                angles=r.angles(r.duration*i/100)
                ticks=mapping.ticks(angles)
                self.assertTrue(all(t==0 or 120<=t<=600 for t in ticks))

    def test_text_maps_center_5x5_to_physical_led_indices(self):
        frame=LedEffect(text='I',color=[100,50,0],brightness=20).frame(5)
        lit=[i for i,p in enumerate(frame['matrix']) if any(p)]
        self.assertEqual(lit,[CHARACTER_PIXELS[i] for i in [0,1,2,3,4,7,12,17,20,21,22,23,24]])
        self.assertTrue(all(c in ([20,10,0],[0,0,0]) for c in frame['matrix']))
        self.assertEqual(len(frame['ring']),12)

    def test_effect_frames_loop_and_zero_brightness_is_black(self):
        for name in ['text','heartbeat','face','rainbow','chase']:
            effect=LedEffect(effect=name)
            self.assertEqual(effect.frame(0),effect.frame(effect.steps))
            for frame in effect.preview()['frames']:
                self.assertEqual(len(frame['matrix']),33)
                self.assertTrue(all(type(c)is int and 0<=c<=51 for group in frame.values() for rgb in group for c in rgb))
            off=LedEffect(effect=name,brightness=0).frame(12)
            self.assertFalse(any(c for group in off.values() for rgb in group for c in rgb))

    def test_effect_options_reject_invalid_input(self):
        for options in [dict(text=''),dict(text='x'*33),dict(text='☃'),dict(effect={}),dict(color=[256,0,0]),dict(brightness=float('nan')),dict(speed=0)]:
            with self.assertRaises(ValueError):LedEffect(**options)

if __name__=='__main__':unittest.main()
