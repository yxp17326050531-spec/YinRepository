"""Synthetic lifecycle regressions, including observer isolation and cross-connection data."""
import copy
import io
import tempfile
import unittest
from core import Engine, Framer, load_mappings
from capture import CaptureJob
from storage import Archive
from analytics import analyse
from test_core import battle_body, blob, scalar, vi, frame, tcp, pcapng


def opening(hero=30153):
    attrs=b''.join(vi(int(value*100)<<8|tag) for tag,value in [(1,10000),(5,2000),(9,900),(13,300)])
    unit=scalar(1,hero)+blob(4,attrs)+blob(6,vi(38997533))
    return blob(1,blob(2,unit)+blob(3,unit))


class BattleSessions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.archive=Archive(self.temp.name);self.events=[]
        self.job=CaptureJob(lambda k,d:self.events.append((k,d)),20001,load_mappings(),self.archive);self.job.source='synthetic'
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close();self.archive.logger.removeHandler(h)
        self.temp.cleanup()
    def records(self):return self.archive.history_directory()
    def test_connections_never_share_the_latest_opening(self):
        e=self.job.engine;e.message(0x6003,opening(30153),100,'one');e.message(0x6003,opening(32101),101,'two')
        e.message(0x6004,scalar(1,382),110,'one');e.message(0x6004,scalar(1,383),111,'two')
        rows=self.records()
        self.assertEqual([self.archive.context(r['id'])['settlement_candidate'] for r in rows],['B','A'])
        self.assertTrue(all(self.archive.get(r['id'])['tracking']['state']=='settled' for r in rows))
    def test_malformed_new_opening_cannot_settle_previous_battle(self):
        e=self.job.engine;e.message(0x6003,opening(),100);bid=self.records()[0]['id']
        e.message(0x6003,blob(1,b''),110);e.message(0x6004,scalar(1,382),120)
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
        self.assertEqual(self.archive.get(bid)['tracking']['state'],'incomplete')
        self.assertEqual(e.diagnostics()['counts']['invalid_openings'],1)
    def test_boundary_before_settlement_preserves_current_association(self):
        e=self.job.engine;e.message(0x6003,opening(),100);bid=self.records()[0]['id']
        e.message(0x6002,b'',101)
        self.assertEqual(self.archive.get(bid)['tracking']['state'],'awaiting_settlement')
        e.message(0x6004,scalar(1,382),102)
        self.assertEqual(self.archive.context(bid)['settlement_candidate'],'A')
    def test_overlapping_openings_quarantine_ambiguous_result_then_recover(self):
        e=self.job.engine;e.message(0x6003,opening(),100);e.message(0x6003,opening(32101),200)
        e.message(0x6004,scalar(1,382),210)
        self.assertTrue(all(self.archive.context(r['id'])['winner']=='unknown' for r in self.records()))
        e.message(0x6003,opening(),300);e.message(0x6004,scalar(1,383),310)
        self.assertEqual(self.archive.context(self.records()[0]['id'])['settlement_candidate'],'B')
    def test_duplicate_opening_is_one_record_and_does_not_assume_identity(self):
        e=self.job.engine;e.message(0x6003,opening(),100);e.message(0x6003,opening(),101)
        self.assertEqual(len(self.records()),1);self.assertEqual(e.latest['capture_time'],100)
        self.assertEqual(e.diagnostics()['counts']['duplicate_openings'],1)
        e.message(0x6004,scalar(1,382),110)
        self.assertEqual(self.archive.context(self.records()[0]['id'])['winner'],'unknown')
    def test_clean_consecutive_identical_lineups_are_distinct(self):
        e=self.job.engine
        for t,code in [(100,382),(200,383)]:
            e.message(0x6003,opening(),t);e.message(0x6004,scalar(1,code),t+10)
        self.assertEqual(len(self.records()),2)
        self.assertEqual([self.archive.context(r['id'])['settlement_candidate'] for r in self.records()],['B','A'])
    def test_replay_is_saved_without_personal_result_or_statistics(self):
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive,capture_context='replay');job.source='replay'
        job.engine.message(0x6003,opening(),100);job.engine.message(0x6004,scalar(1,382),110)
        bid=self.records()[0]['id'];self.archive.set_classification(bid,'竞技场')
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
        result=analyse(self.archive.dataset(),load_mappings(),('竞技场',))
        self.assertEqual(result['eligible_matches'],0)
        original=self.archive.get(bid)['original']
        self.assertEqual(original['capture_context'],'replay')
    def test_unhandled_lineup_becomes_diagnostic_candidate_only(self):
        e=self.job.engine;e.message(0x7777,opening(),100);e.message(0x7778,b'secret-token-value',101)
        d=e.diagnostics();self.assertEqual(len(d['lineup_candidates']),1)
        self.assertEqual(d['unhandled_opcodes']['0x7777'],1);self.assertEqual(len(self.records()),0)
        self.assertNotIn('secret-token-value',str(d))
        self.assertNotIn('body_hex',str(d))
    def test_unknown_opcode_roster_can_sync_without_heartbeat_even_when_segmented(self):
        messages=[];framer=Framer(lambda *args:messages.append(args),lambda *a:None)
        wire=frame(0x7777,opening())
        for byte in wire:framer.feed(bytes([byte]),100)
        self.assertEqual([(m[0],m[1]) for m in messages],[(0x7777,opening())])
        self.assertEqual(framer.discarded_bytes,0)
    def test_eof_and_disconnect_mark_incomplete_without_changing_original(self):
        e=self.job.engine;e.read(io.BytesIO(pcapng(tcp(frame(0x6003,opening())))))
        bid=self.records()[0]['id'];row=self.archive.get(bid)
        self.assertEqual(row['tracking']['state'],'incomplete')
        self.assertEqual(row['original']['tracking']['state'],'active')
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
    def test_late_settlement_on_new_connection_remains_unlinked(self):
        e=self.job.engine;e.packet(100,1,tcp(frame(0x6003,opening()),1000))
        bid=self.records()[0]['id'];e.packet(101,1,tcp(b'',1000+len(frame(0x6003,opening())),flags=0x11))
        e.packet(110,1,tcp(frame(0x6004,scalar(1,382)),5000))
        self.assertEqual(self.archive.context(bid)['winner'],'unknown')
        self.assertEqual(e.counts['unlinked_settlements'],1)
    def test_reimport_incomplete_prefix_cannot_downgrade_known_result(self):
        e=self.job.engine;e.message(0x6003,opening(),100);e.message(0x6004,scalar(1,382),110)
        bid=self.records()[0]['id'];original=copy.deepcopy(self.archive.get(bid)['original'])
        other=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive);other.source='synthetic'
        other.engine.message(0x6003,opening(),100);other.engine.last_timestamp=120;other.engine.finish_capture()
        row=self.archive.get(bid)
        self.assertEqual(row['tracking']['state'],'settled');self.assertEqual(row['original'],original)
        self.assertEqual(self.archive.context(bid)['settlement_candidate'],'A')


if __name__=='__main__':unittest.main()
