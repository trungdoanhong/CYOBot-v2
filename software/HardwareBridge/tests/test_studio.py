"""Controller/HTTP checks with a fake board: never move real hardware."""
from pathlib import Path
import http.client
import json
import re
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from cyobot import Robot, OWNED, PWM_OK, IMU_OK, LED_READY, FAULT
from studio import Studio, create_server

MAC = "00:00:00:00:00:01"
CLIENT = "test-window-001"


class FakeFleet:
    def __init__(self):
        self.robot = Robot(MAC, ("127.0.0.1", 4242), 1, 2, PWM_OK|IMU_OK, 112, 120, 600, 1000)
        self.robot.telemetry = dict(ticks=[0]*16, flags=PWM_OK|IMU_OK, accel_g=[0,0,1], gyro_dps=[0]*3, battery_v=7.4, buttons=0)
        self.sent = []
        self.released = 0
        self.off_calls = 0
        self.respond = True
        self.led_sent = []
        self.led_respond = True
        self.claims = 0

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def discover(self, *_, **__): return [self.robot]
    def claim(self, robot):
        if not self.respond: raise TimeoutError('Unreachable')
        self.claims += 1
        robot.session = 122+self.claims
        robot.flags |= OWNED
        robot.seen_at = time.perf_counter()
    def poll(self):
        if self.respond: self.robot.seen_at = time.perf_counter()
    def send_ticks(self, robot, ticks):
        self.sent.append(list(ticks))
        if self.respond:
            robot.telemetry["ticks"] = list(ticks)
            robot.telemetry["flags"] = robot.flags
            robot.telemetry['applied_seq'] = len(self.sent)
    def send_leds(self,robot,matrix,ring):
        self.led_sent.append(dict(matrix=matrix,ring=ring))
        if self.led_respond:robot.leds=dict(applied_seq=len(self.led_sent),matrix=matrix,ring=ring)
    def release(self, robot):
        self.released += 1
        robot.session = 0
        robot.flags &= ~OWNED
    def off(self, robot):
        self.off_calls += 1
        robot.telemetry["ticks"] = [0]*16
        self.release(robot)
    def close(self):
        if self.robot.session: self.release(self.robot)


class StudioTests(unittest.TestCase):
    def test_routine_preserves_unmapped_channels_and_hold_freezes_pose(self):
        self.do('joint',channel=15,angle=30)
        self.wait(lambda:self.fleet.sent[-1][15]==440)
        self.do('routine',name='wave',speed=1,repeats=2)
        self.wait(lambda:self.studio.state()['routine'] is not None)
        time.sleep(.06)
        self.assertEqual(self.studio.targets[15],440)
        self.assertEqual(self.studio.state()['mode'],'routine')
        self.do('hold')
        frozen=list(self.studio.targets)
        time.sleep(.05)
        self.assertEqual(self.studio.targets,frozen)
        self.assertIsNone(self.studio.state()['routine'])

    def test_routine_and_effect_stop_on_browser_timeout_and_never_resume(self):
        self.fleet.robot.flags|=LED_READY
        self.do('routine',name='bounce',repeats=5)
        self.do('led_effect',effect='chase')
        self.wait(lambda:self.studio.state()['led_effect']=='chase')
        self.wait(lambda:self.studio.state()['mode']=='hold' and self.studio.state()['led_effect'] is None,timeout=1.2)
        self.do('heartbeat');time.sleep(.05)
        self.assertEqual(self.studio.state()['mode'],'hold')
        self.assertIsNone(self.studio.state()['led_effect'])

    def test_bad_routine_is_rejected_without_changing_output(self):
        before=list(self.studio.targets)
        for values in [dict(name='unknown'),dict(name={}),dict(name='bow',speed=9),dict(name='bow',repeats=True)]:
            with self.assertRaises(ValueError):self.do('routine',**values)
        self.assertEqual(self.studio.targets,before)
        self.assertEqual(self.studio.mode,'hold')

    def test_led_effect_ack_failure_stops_effect_without_stopping_servo_control(self):
        self.fleet.robot.flags|=LED_READY;self.fleet.led_respond=False
        self.do('led_effect',effect='heartbeat')
        deadline=time.perf_counter()+.9
        while time.perf_counter()<deadline and not self.studio.state().get('error','').startswith('LED'):
            self.do('heartbeat');time.sleep(.025)
        self.assertTrue(self.studio.state()['error'].startswith('LED'))
        self.assertIsNone(self.studio.state()['led_effect'])
        self.assertTrue(self.studio.state()['connected'])
        self.assertTrue(all(frame==[0]*16 for frame in self.fleet.sent))

    def test_manual_led_frame_replaces_effect_and_disconnect_clears_programs(self):
        self.fleet.robot.flags|=LED_READY
        self.do('led_effect',effect='rainbow')
        self.wait(lambda:bool(self.fleet.led_sent))
        self.do('leds',matrix=[[1,2,3]]*33,ring=[[0,0,0]]*12)
        self.wait(lambda:not self.studio.state()['leds_pending'])
        self.assertIsNone(self.studio.state()['led_effect'])
        self.assertEqual(self.fleet.robot.leds['matrix'],[[1,2,3]]*33)
        self.do('routine',name='bow');self.do('led_effect',effect='face');self.do('disconnect')
        self.do('connect',mac=MAC)
        self.assertEqual(self.studio.mode,'hold');self.assertIsNone(self.studio.led_effect)

    def test_missing_led_ack_reports_failure_without_altering_servo_outputs(self):
        self.fleet.robot.flags|=LED_READY;self.fleet.led_respond=False
        self.do('leds',matrix=[[1,2,3]]*33,ring=[[0,0,0]]*12)
        end=time.perf_counter()+.7
        while time.perf_counter()<end and not self.studio.state().get('error','').startswith('LED'):
            self.do('heartbeat');time.sleep(.03)
        self.assertTrue(self.studio.state()['error'].startswith('LED'))
        self.assertTrue(self.studio.state()['connected'])
        self.assertFalse(self.studio.state()['leds_pending'])
        self.assertEqual(self.studio.targets,[0]*16)
        self.fleet.led_respond=True
        self.do('leds',matrix=[[1,2,3]]*33,ring=[[0,0,0]]*12)
        self.wait(lambda:self.studio.state()['leds'] is not None and not self.studio.state()['leds_pending'])
        self.assertEqual(self.studio.state()['error'],'')

    def test_leds_preserve_servo_targets_and_confirm_without_repeated_writes(self):
        self.fleet.robot.flags|=LED_READY
        self.do('joint',channel=4,angle=30)
        self.wait(lambda:self.fleet.sent and self.fleet.sent[-1][4]==440)
        before=list(self.studio.targets)
        self.do('leds',matrix=[[20,0,10]]*33,ring=[[0,10,30]]*12)
        self.wait(lambda:self.studio.state().get('leds') and not self.studio.state()['leds_pending'])
        self.assertEqual(self.studio.targets,before)
        self.assertEqual(len(self.fleet.led_sent),1)
        self.assertEqual(self.studio.state()['leds']['ring'][11],[0,10,30])
        with self.assertRaises(ValueError):self.do('leds',matrix=[[256,0,0]]*33,ring=[[0,0,0]]*12)
        self.assertEqual(len(self.fleet.led_sent),1)

    def test_leds_require_support_and_owner(self):
        colors=dict(matrix=[[0,0,0]]*33,ring=[[0,0,0]]*12)
        with self.assertRaises(ValueError):self.do('leds',**colors)
        self.fleet.robot.flags|=LED_READY
        with self.assertRaises(ValueError):self.studio.action(dict(action='leds',client='other-window',**colors))
        self.assertFalse(self.fleet.led_sent)

    def setUp(self):
        self.fleet = FakeFleet()
        self.studio = Studio(fleet_factory=lambda:self.fleet, auto_scan=False,connection_log_path=None)
        self.studio.action(dict(action="found", robots=[self.fleet.robot]))
        self.do("connect", mac=MAC)

    def tearDown(self): self.studio.close()
    def do(self, action, **values): return self.studio.action(dict(action=action, client=CLIENT,
        control_session=self.fleet.robot.session, **values))
    def wait(self, predicate, timeout=.5):
        end = time.perf_counter()+timeout
        while time.perf_counter()<end:
            if predicate(): return
            time.sleep(.01)
        self.fail("Controller did not reach expected state")

    def test_connect_preserves_disabled_channels_and_sends_full_frames(self):
        self.wait(lambda:len(self.fleet.sent)>3)
        self.assertTrue(all(ticks == [0]*16 for ticks in self.fleet.sent))
        self.assertEqual(self.studio.state()["owner"], CLIENT)

    def test_invalid_commands_do_not_change_targets(self):
        for values in (dict(channel=16,angle=0),dict(channel=4,angle=91),dict(channel=True,angle=0),dict(channel=4,angle=float("nan"))):
            with self.assertRaises(ValueError): self.do("joint", **values)
        self.assertEqual(self.studio.targets, [0]*16)

    def test_each_of_16_channels_can_be_controlled(self):
        self.do("joint",channel=15,angle=30)
        self.wait(lambda:self.fleet.sent[-1][15]==440)
        self.assertEqual(self.fleet.sent[-1][:15], [0]*15)
        self.do("channel_off",channel=15)
        self.wait(lambda:self.fleet.sent[-1]==[0]*16)

    def test_browser_timeout_freezes_test_without_dropping_connection(self):
        self.do("test",channel=4,amplitude=10,period=1)
        self.wait(lambda:self.fleet.sent and self.fleet.sent[-1][4]>360)
        self.studio.client_at = time.perf_counter()-1
        self.wait(lambda:self.studio.state()['browser_paused'])
        frozen = list(self.fleet.robot.telemetry["ticks"])
        count = len(self.fleet.sent)
        time.sleep(.06)
        self.assertGreater(len(self.fleet.sent), count)
        self.assertEqual(self.fleet.robot.telemetry["ticks"], frozen)
        self.assertEqual(self.fleet.released,0)
        self.assertTrue(self.studio.state()['connected'])
        self.do('heartbeat')
        self.assertEqual(self.studio.mode,'hold')

    def test_missing_telemetry_reconnects_using_board_pose_without_resuming_motion(self):
        self.do('joint',channel=4,angle=30)
        self.wait(lambda:self.fleet.sent[-1][4]==440)
        old_session=self.fleet.robot.session
        self.fleet.respond = False
        self.fleet.robot.seen_at = time.perf_counter()-2
        self.wait(lambda:self.studio.state()['reconnecting'])
        self.assertEqual(self.studio.state()["mode"], "hold")
        self.fleet.robot.telemetry['ticks'][4]=400
        self.fleet.respond = True
        self.wait(lambda:self.studio.state()['connected'],timeout=1.5)
        self.assertEqual(self.studio.targets[4],400)
        self.assertEqual(self.studio.mode,'hold')
        self.assertEqual(self.studio.state()['reconnections'],1)
        with self.assertRaises(ValueError):
            self.studio.action(dict(action='walk',client=CLIENT,direction='forward',control_session=old_session))
        self.assertEqual(self.studio.mode,'hold')

    def test_short_uplink_loss_freezes_targets_even_when_telemetry_is_fresh(self):
        self.do('test',channel=4,amplitude=10,period=1)
        self.wait(lambda:self.studio.mode=='test')
        original=self.fleet.send_ticks
        self.fleet.send_ticks=lambda robot,ticks:self.fleet.sent.append(list(ticks))
        self.fleet.robot.telemetry['applied_seq']=self.studio.applied_sequence
        self.fleet.robot.telemetry['ticks'][4]=400
        self.studio.current[4]=500
        self.studio.progress_at=time.perf_counter()-.2
        self.wait(lambda:self.studio.state()['link_stale'])
        self.assertTrue(self.studio.state()['connected'])
        self.assertEqual(self.studio.mode,'hold')
        self.assertEqual(self.studio.targets,self.studio.current)
        self.assertEqual(self.studio.current[4],400)
        self.fleet.send_ticks=original
        self.wait(lambda:not self.studio.state()['link_stale'])
        self.assertEqual(self.studio.mode,'hold')

    def test_hardware_fault_does_not_attempt_automatic_reclaim(self):
        self.fleet.robot.flags |= FAULT
        self.wait(lambda:not self.studio.state()['connected'])
        self.assertFalse(self.studio.state()['reconnecting'])
        self.assertEqual(self.fleet.claims,1)

    def test_explicit_disconnect_cancels_recovery(self):
        self.fleet.respond=False
        self.fleet.robot.seen_at=time.perf_counter()-2
        self.wait(lambda:self.studio.state()['reconnecting'])
        self.do('disconnect')
        self.fleet.respond=True
        time.sleep(.65)
        self.assertFalse(self.studio.state()['connected'])
        self.assertFalse(self.studio.state()['reconnecting'])

    def test_second_window_cannot_take_control(self):
        with self.assertRaises(ValueError):
            self.studio.action(dict(action="connect",mac=MAC,client="other-window"))
        with self.assertRaises(ValueError):
            self.studio.action(dict(action="joint",channel=4,angle=30,client="other-window"))
        self.assertEqual(self.studio.client,CLIENT)

    def test_inactive_window_allows_explicit_handover_in_hold(self):
        self.studio.client_at=time.perf_counter()-1
        self.studio.action(dict(action='connect',mac=MAC,client='other-window'))
        self.assertEqual(self.studio.client,'other-window')
        self.assertEqual(self.studio.mode,'hold')

    def test_reboot_recovery_never_reenables_old_targets(self):
        self.do('joint',channel=4,angle=30)
        self.wait(lambda:self.fleet.sent[-1][4]==440)
        self.fleet.respond=False
        self.fleet.robot.seen_at=time.perf_counter()-2
        self.wait(lambda:self.studio.state()['reconnecting'])
        self.fleet.robot.boot+=1
        self.fleet.robot.telemetry['ticks']=[0]*16
        self.fleet.respond=True
        self.wait(lambda:self.studio.state()['connected'],timeout=1.5)
        self.assertEqual(self.studio.targets,[0]*16)
        self.assertEqual(self.studio.mode,'hold')

    def test_test_respects_bounds_and_off_confirms_new_session(self):
        self.do("joint",channel=4,angle=85)
        self.wait(lambda:self.fleet.sent[-1][4]>=586)
        with self.assertRaises(ValueError):self.do("test",channel=4,amplitude=10)
        self.do("off")
        self.wait(lambda:self.studio.state()["connected"] and self.fleet.sent[-1]==[0]*16)
        self.assertEqual(self.fleet.off_calls,1)
        self.assertEqual(self.studio.targets,[0]*16)
        self.assertEqual(self.studio.mode,"hold")

    def test_http_token_host_and_heartbeat(self):
        server = create_server(self.studio,0)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        connection=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=2)
        try:
            connection.request("GET","/")
            response=connection.getresponse(); html=response.read().decode()
            self.assertEqual(response.status,200)
            token=re.search(r'name="cyo-token" content="([^"]+)"',html)[1]
            body=json.dumps(dict(action="heartbeat",client=CLIENT))
            connection.request("POST","/api/action",body,{"Content-Type":"application/json"})
            response=connection.getresponse();response.read();self.assertEqual(response.status,403)
            connection.request("POST","/api/action",body,{"X-CYO-Token":token})
            response=connection.getresponse();response.read();self.assertEqual(response.status,200)
            connection.request("GET","/api/state",headers={"Host":"external.example"})
            response=connection.getresponse();response.read();self.assertEqual(response.status,403)
            connection.request("GET","/../studio.py")
            response=connection.getresponse();response.read();self.assertEqual(response.status,404)
        finally:
            connection.close();server.shutdown();server.server_close();thread.join()


if __name__ == "__main__": unittest.main()
