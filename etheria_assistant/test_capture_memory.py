"""Long-running capture handoff and transient reclamation regressions."""
import tempfile
import threading
import unittest
from pathlib import Path
from queue import Empty
from capture_events import CaptureEvents
from capture import CaptureJob
from core import Engine,load_mappings
from storage import Archive
from test_core import scalar,frame,tcp,pcapng,battle_body


class CaptureMemory(unittest.TestCase):
    def test_latest_states_coalesce_but_records_and_errors_remain_ordered(self):
        q=CaptureEvents(8)
        q.put((1,'battle',{'archive_id':'one'}));q.put((1,'counts',{'packets':1}))
        q.put((1,'warning','keep warning'))
        for i in range(1000):
            q.put((1,'counts',{'packets':i}));q.put((1,'inventory_snapshot',{'version':i}))
        q.put((1,'battle',{'archive_id':'two'}));q.put((1,'done',{}))
        self.assertEqual(q.qsize(),6)
        items=[]
        while not q.empty():items.append(q.get_nowait())
        self.assertEqual([k for _,k,_ in items],['battle','warning','counts','inventory_snapshot','battle','done'])
        self.assertEqual(items[2][2]['packets'],999);self.assertEqual(items[3][2]['version'],999)
        with self.assertRaises(Empty):q.get_nowait()
    def test_full_queue_applies_backpressure_without_discarding_durable_events(self):
        q=CaptureEvents(1);q.put((1,'battle','one'));started=threading.Event();done=threading.Event()
        def producer():
            started.set();q.put((1,'storage_error','keep'));done.set()
        worker=threading.Thread(target=producer,daemon=True);worker.start()
        self.assertTrue(started.wait(1));self.assertFalse(done.wait(0.02))
        self.assertEqual(q.get_nowait(),(1,'battle','one'));self.assertTrue(done.wait(1));worker.join(1)
        self.assertEqual(q.get_nowait(),(1,'storage_error','keep'));self.assertFalse(worker.is_alive())
    def test_aliases_are_bounded_and_stopped_capture_releases_buffers_after_saving(self):
        engine=Engine(lambda *a:None);aliases=[]
        for i in range(1200):aliases.append(engine.draft_observation(scalar(4,100000+i),i)['actor_alias'])
        self.assertLessEqual(len(engine.actor_aliases),512);self.assertEqual(len(set(aliases)),1200)
        self.assertNotIn(100000,engine.actor_aliases)
        with tempfile.TemporaryDirectory() as tmp:
            archive=Archive(tmp);events=[]
            try:
                path=Path(tmp)/'synthetic.pcapng';path.write_bytes(pcapng(tcp(frame(0x6003,battle_body())+frame(0x6004,scalar(1,382)))))
                job=CaptureJob(lambda k,d:events.append((k,d)),20001,load_mappings(),archive)
                job.run(str(path),None,None)
                self.assertEqual(archive.history()[0],1)
                self.assertEqual(job.engine.counts['settlements'],1)
                self.assertFalse(job.engine.flows);self.assertFalse(job.engine.sessions)
                self.assertFalse(job.engine.replay_records);self.assertFalse(job.engine.player_evidence)
                self.assertIsNone(job.engine.latest)
                self.assertEqual(job.engine.inventory.snapshot(1,[])['gear'],[])
                self.assertEqual(archive.settings()['last_capture_diagnostics']['counts']['settlements'],1)
                self.assertEqual(events[-1][0],'done');self.assertFalse(events[-1][1]['failed'])
            finally:
                for h in archive.logger.handlers[:]:h.close();archive.logger.removeHandler(h)


if __name__=='__main__':unittest.main()
