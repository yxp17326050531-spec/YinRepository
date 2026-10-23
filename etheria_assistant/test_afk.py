import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from types import SimpleNamespace
from afk import Trial, Step, WindowInput
from afk_widgets import AfkDialog
from PySide6.QtWidgets import QApplication


TARGET = (123, (456,'synthetic-game',1,2), (1280,720))
STEPS = (Step('结算',(100,200),30), Step('再次挑战',(300,400),3))


class FakeInput:
    def __init__(self):
        self.clicks = []; self.invalid = False; self.user = SimpleNamespace(IsIconic=lambda hwnd:True)
    def validate(self,target):
        if self.invalid:raise RuntimeError('目标已变化')
    def click(self,target,point):
        self.validate(target); self.clicks.append((target,point))
    def windows(self):return [TARGET]
    def calibrate(self,target):self.validate(target); return target
    def point(self,target):self.validate(target); return 120,240


class AfkTests(unittest.TestCase):
    def setUp(self):
        self.now = 0; self.backend = FakeInput(); self.messages = []
        self.trial = Trial(self.backend,lambda:self.now,self.messages.append)
    def test_waits_and_stops_after_exact_number_of_message_rounds(self):
        self.trial.start(TARGET,STEPS,2,120)
        self.now = 29; self.trial.tick(); self.assertEqual(self.backend.clicks,[])
        for now in (30,33,63,66):self.now = now; self.trial.tick()
        self.assertEqual([point for _,point in self.backend.clicks],[(100,200),(300,400)]*2)
        self.assertEqual(self.trial.completed,2); self.assertFalse(self.trial.running)
        self.now = 100; self.trial.tick(); self.assertEqual(len(self.backend.clicks),4)
        sent = [message for message in self.messages if '：消息已发送，' in message]
        self.assertEqual(len(sent),4)
        self.assertTrue(all('待核实' in message for message in sent))
    def test_expired_limit_and_resume_delay_never_send_catch_up_clicks(self):
        for now,limit in [(31,30),(45,120),(10000,120)]:
            with self.subTest(now=now):
                self.now = 0; self.trial.start(TARGET,STEPS,2,limit)
                self.now = now; self.trial.tick()
                self.assertFalse(self.trial.running); self.assertEqual(self.backend.clicks,[])
    def test_changed_target_and_input_failure_stop_without_retry(self):
        self.trial.start(TARGET,STEPS,2,120); self.backend.invalid = True
        self.now = 30; self.trial.tick(); self.trial.tick()
        self.assertFalse(self.trial.running); self.assertEqual(self.backend.clicks,[])
        self.assertIn('目标已变化',self.messages[-1])
    def test_invalid_points_limits_or_waits_never_start(self):
        for steps,rounds,seconds in [((),1,60),(STEPS,0,60),(STEPS,21,60),(STEPS,1,9),
                (STEPS,1,7201),((Step('bad',(-1,0),1),),1,60),
                ((Step('bad',(1280,0),1),),1,60),((Step('bad',(0,720),1),),1,60),
                ((Step('bad',(0,0),0),),1,60)]:
            with self.subTest(steps=steps,rounds=rounds,seconds=seconds):
                with self.assertRaises(ValueError):self.trial.start(TARGET,steps,rounds,seconds)
                self.assertFalse(self.trial.running)
    def test_stop_during_wait_and_running_start_protection(self):
        self.trial.start(TARGET,STEPS,2,120)
        with self.assertRaises(RuntimeError):self.trial.start(TARGET,STEPS,2,120)
        self.trial.stop(); self.now = 30; self.trial.tick(); self.assertEqual(self.backend.clicks,[])


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        # Exercise the real setup/run geometry boundary without loading Windows DLLs.
        self.backend = WindowInput.__new__(WindowInput)
        self.backend.identity = lambda hwnd:TARGET[1]
        self.size = (1600,900); self.minimized = False
        self.backend.size = lambda hwnd:self.size
        self.backend.user = SimpleNamespace(IsIconic=lambda hwnd:self.minimized)
    def test_setup_can_recalibrate_but_running_validation_remains_strict(self):
        with self.assertRaisesRegex(RuntimeError,'1280×720 → 1600×900'):
            self.backend.validate(TARGET)
        calibrated = self.backend.calibrate(TARGET)
        self.assertEqual(calibrated,(TARGET[0],TARGET[1],(1600,900)))
        self.backend.validate(calibrated)
        self.size = (1920,1080)
        with self.assertRaisesRegex(RuntimeError,'尺寸已变化'):self.backend.validate(calibrated)
    def test_closed_or_replaced_process_and_minimized_invalid_geometry_are_not_accepted(self):
        self.backend.identity = lambda hwnd:('different',)
        with self.assertRaisesRegex(RuntimeError,'进程或窗口已变化'):self.backend.calibrate(TARGET)
        self.backend.identity = lambda hwnd:TARGET[1]; self.minimized = True
        with self.assertRaisesRegex(RuntimeError,'恢复游戏窗口'):self.backend.calibrate(TARGET)
        self.minimized = False; self.size = (0,0)
        with self.assertRaisesRegex(RuntimeError,'尺寸无效'):self.backend.calibrate(TARGET)


class AfkWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app = QApplication.instance() or QApplication([])
    def setUp(self):self.dialog = AfkDialog(backend=FakeInput())
    def tearDown(self):self.dialog.close(); self.app.processEvents()
    def set_points(self):
        for _,x,y,_ in self.dialog.steps:x.setValue(100); y.setValue(200)
    def test_target_refresh_resets_points_and_pick_can_be_cancelled(self):
        self.set_points(); self.dialog.refresh_windows()
        self.assertTrue(all(x.value() == y.value() == -1 for _,x,y,_ in self.dialog.steps))
        _,x,y,_ = self.dialog.steps[0]; self.dialog.pick(x,y)
        self.assertTrue(self.dialog.pick_timer.isActive())
        self.dialog.stop(); self.assertFalse(self.dialog.pick_timer.isActive())
        self.assertTrue(self.dialog.start.isEnabled())
    def test_minimized_window_is_attempted_and_close_stops_pending_work(self):
        self.set_points(); self.dialog.begin(); self.dialog.tick()
        self.assertTrue(self.dialog.trial.running)
        self.assertIn('已最小化',self.dialog.log.toPlainText())
        self.assertFalse(self.dialog.refresh.isEnabled())
        self.dialog.close()
        self.assertFalse(self.dialog.timer.isActive()); self.assertFalse(self.dialog.trial.running)
        self.assertEqual(self.dialog.backend.clicks,[])
    def test_position_pick_and_report_are_bounded(self):
        _,x,y,_ = self.dialog.steps[0]; self.dialog.pick(x,y); self.dialog.finish_pick()
        self.assertEqual((x.value(),y.value()),(120,240))
        for _ in range(600):self.dialog.report('synthetic')
        self.assertLessEqual(self.dialog.log.document().blockCount(),500)
    def test_escape_reject_also_stops_trial_and_delayed_pick(self):
        self.set_points(); self.dialog.begin(); self.dialog.reject()
        self.assertFalse(self.dialog.trial.running); self.assertFalse(self.dialog.timer.isActive())
        _,x,y,_ = self.dialog.steps[0]; self.dialog.pick(x,y); self.dialog.reject()
        self.assertFalse(self.dialog.pick_timer.isActive())
    def test_resize_during_pick_recalibrates_and_invalidates_the_other_position(self):
        self.set_points()
        resized = (TARGET[0],TARGET[1],(1600,900))
        self.dialog.backend.calibrate = lambda target:resized
        seen = []
        self.dialog.backend.point = lambda target:seen.append(target) or (120,240)
        _,x,y,_ = self.dialog.steps[0]; self.dialog.pick(x,y); self.dialog.finish_pick()
        self.assertEqual(seen,[resized]); self.assertEqual(self.dialog.windows.currentData(),resized)
        self.assertEqual((x.value(),y.value()),(120,240))
        _,other_x,other_y,_ = self.dialog.steps[1]
        self.assertEqual((other_x.value(),other_y.value()),(-1,-1))
        _,x,y,_ = self.dialog.steps[1]; self.dialog.pick(x,y); self.dialog.finish_pick()
        self.assertEqual(self.dialog.steps[0][1].value(),120)
        self.assertEqual((x.value(),y.value()),(120,240))
    def test_failed_pick_after_resize_still_discards_stale_positions(self):
        self.set_points()
        self.dialog.backend.calibrate = lambda target:(TARGET[0],TARGET[1],(1600,900))
        def fail(target):raise RuntimeError('鼠标不在游戏内')
        self.dialog.backend.point = fail
        _,x,y,_ = self.dialog.steps[0]; self.dialog.pick(x,y); self.dialog.finish_pick()
        self.assertTrue(all(x.value() == y.value() == -1 for _,x,y,_ in self.dialog.steps))


if __name__ == '__main__':unittest.main()
