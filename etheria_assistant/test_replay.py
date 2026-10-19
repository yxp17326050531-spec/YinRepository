"""Synthetic 0x8421 replay responses; no uploaded player data or capture bytes."""
import copy
import io
import tempfile
import unittest
from analytics import analyse
from capture import CaptureJob
from core import decode_replay, load_mappings
from storage import Archive
from test_core import blob, scalar, vi, frame, tcp, pcapng, battle_body


def replay_body(request=7, roster=True):
    attrs=b''.join(vi(value<<8|tag) for tag,value in
                   [(1,1234500),(5,234500),(9,123400),(13,32100),
                    (17,512),(20,1500),(23,432),(26,222),(201,123)])
    teams=b''
    for group in (2,3):
        for i in range(4):
            unit=scalar(1,50000+group*100+i)+scalar(2,25000+i)+blob(4,attrs)+blob(6,vi(38997533))
            teams+=blob(group,unit)
    payload=blob(1,blob(8,b'private-account-metadata-not-to-save'))
    if roster:payload+=blob(2,teams)
    payload+=blob(3,vi(789)+vi(1234))+scalar(4,123456789)+scalar(5,98765)
    return scalar(1,request)+blob(2,payload)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.archive=Archive(self.temp.name);self.events=[]
        self.job=CaptureJob(lambda k,d:self.events.append((k,d)),20001,load_mappings(),self.archive)
        self.job.source='synthetic replay'
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close();self.archive.logger.removeHandler(h)
        self.temp.cleanup()
    def test_eight_units_reuse_attribute_rules_and_keep_unknown_values(self):
        b=decode_replay(replay_body(),load_mappings())
        self.assertEqual([len(b['teams'][t]) for t in ('A','B')],[4,4])
        u=b['teams']['A'][0]
        self.assertEqual(u['stats'],{'hp':12345,'attack':2345,'defense':1234,'speed':321})
        self.assertEqual(u['percent_attributes_tentative']['crit'],51.2)
        self.assertIn((123<<8)|201,u['attributes_raw'])
        self.assertEqual(b['capture_context'],'replay')
        self.assertNotIn('private-account',str(b))
        self.assertEqual(b['replay_evidence']['extra_fields_raw'][0]['value'],(vi(789)+vi(1234)).hex())
    def test_known_replay_is_automatic_even_in_default_live_capture(self):
        e=self.job.engine;e.message(0x8421,replay_body(),100)
        row=self.archive.history_directory()[0];record=self.archive.get(row['id'])
        self.assertEqual(record['original']['capture_context'],'replay')
        self.assertEqual(record['tracking']['state'],'replay_loaded')
        self.assertFalse(record['tracking']['association_eligible'])
        self.archive.set_classification(row['id'],'竞技场')
        self.assertEqual(analyse(self.archive.dataset(),load_mappings(),('竞技场',))['eligible_matches'],0)
        self.assertEqual(self.archive.context(row['id'])['winner'],'unknown')
        self.assertEqual(e.counts['replays'],1);self.assertEqual(e.counts['battles'],0)
        self.assertNotIn(0x8421,e.unknown_opcodes)
        self.assertNotIn('private-account',str(e.diagnostics()))
    def test_replay_and_live_settlement_do_not_share_targets(self):
        e=self.job.engine;e.message(0x6003,battle_body(),100,'one')
        live=self.archive.history_directory()[0]['id']
        e.message(0x8421,replay_body(),110,'one');replay=self.archive.history_directory()[0]['id']
        e.message(0x6004,scalar(1,382),120,'one');e.finish_capture()
        self.assertEqual(self.archive.context(live)['settlement_candidate'],'A')
        self.assertEqual(self.archive.context(replay)['winner'],'unknown')
        self.assertEqual(self.archive.get(replay)['tracking']['state'],'replay_loaded')
    def test_replay_only_does_not_accept_live_result(self):
        e=self.job.engine;e.message(0x8421,replay_body(),100)
        e.message(0x6004,scalar(1,383),110)
        row=self.archive.history_directory()[0]
        self.assertEqual(self.archive.context(row['id'])['winner'],'unknown')
        self.assertEqual(e.counts['unlinked_settlements'],1)
    def test_duplicate_requests_keep_one_record_and_first_capture_time(self):
        e=self.job.engine;e.message(0x8421,replay_body(request=7),100)
        e.message(0x8421,replay_body(request=8),101)
        rows=self.archive.history_directory()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['capture_time'],100)
        self.assertEqual(e.counts['replay_messages'],2);self.assertEqual(e.counts['duplicate_replays'],1)
    def test_malformed_replay_does_not_invalidate_live_opening(self):
        e=self.job.engine;e.message(0x6003,battle_body(),100)
        e.message(0x8421,replay_body(roster=False),110)
        e.message(0x6004,scalar(1,382),120)
        rows=self.archive.history_directory()
        self.assertEqual(len(rows),1);self.assertEqual(self.archive.context(rows[0]['id'])['settlement_candidate'],'A')
        self.assertEqual(e.counts['invalid_replays'],1)
        with self.assertRaises(ValueError):decode_replay(blob(2,b'')+blob(2,b''),load_mappings())
    def test_first_segmented_message_offline_import_and_repeat_import(self):
        wire=frame(0x8421,replay_body());split=23
        capture=pcapng(tcp(wire[:split],1000))+pcapng(tcp(wire[split:],1000+split))
        e=self.job.engine;e.read(io.BytesIO(capture))
        self.assertEqual(e.counts['messages'],1);self.assertEqual(e.counts['framing_discarded_bytes'],0)
        row=self.archive.history_directory()[0];original=copy.deepcopy(self.archive.get(row['id'])['original'])
        other=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive);other.source=self.job.source
        other.engine.read(io.BytesIO(capture))
        self.assertEqual(len(self.archive.history_directory()),1)
        self.assertEqual(self.archive.get(row['id'])['original'],original)
        self.assertEqual(self.archive.get(row['id'])['tracking']['state'],'replay_loaded')


if __name__=='__main__':unittest.main()
