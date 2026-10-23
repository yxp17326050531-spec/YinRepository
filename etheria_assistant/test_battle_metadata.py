"""Synthetic regressions for protocol sides, mode evidence and nickname allowlist."""
import copy
import json
import tempfile
import unittest
from analytics import analyse
from battle_metadata import infer_side, mode_info, result_text
from capture import CaptureJob
from core import decode_battle, decode_replay, load_mappings, record
from storage import Archive
from test_core import battle_body, blob, scalar
from test_replay import replay_body


def unique_battle(stamp=100):
    b=decode_battle(battle_body(),load_mappings());b['capture_time']=stamp
    unit=b['teams']['A'][0]
    b['teams']={t:[dict(copy.deepcopy(unit),hero_id=i) for i in ids]
                for t,ids in [('A',[11,12,13,14]),('B',[21,22,23,24])]}
    return b


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.archive=Archive(self.tmp.name)
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close();self.archive.logger.removeHandler(h)
        self.tmp.cleanup()
    def test_b_side_loss_and_unknown_identity_do_not_change_original_or_protocol_result(self):
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive);job.source='test'
        job.engine.message(0x6003,battle_body(),100);job.engine.message(0x6004,scalar(1,382),110)
        bid=self.archive.history()[1][0]['id'];original=copy.deepcopy(self.archive.get(bid)['original'])
        ctx=self.archive.context(bid)
        self.assertEqual(result_text(ctx),'结算 382 · 胜方待确认')
        self.archive.set_review(bid,'A')
        self.archive.set_perspective(bid,'B')
        self.assertEqual(result_text(self.archive.context(bid)),'失败')
        self.assertEqual(self.archive.context(bid)['winner'],'A')
        self.archive.set_perspective(bid,'A');self.assertEqual(result_text(self.archive.context(bid)),'胜利')
        self.archive.set_perspective(bid,None);self.assertIsNone(self.archive.context(bid)['own_team'])
        self.assertEqual(self.archive.get(bid)['original'],original)
    def test_auto_side_requires_multiple_exact_units_and_ignores_slot_and_order(self):
        ref=unique_battle();bid=self.archive.save_battle(ref,'test');self.archive.set_perspective(bid,'A')
        reverse=copy.deepcopy(ref);reverse['capture_time']=200
        reverse['teams']={'A':ref['teams']['B'],'B':list(reversed(ref['teams']['A']))}
        second=self.archive.save_battle(reverse,'test')
        self.assertEqual(self.archive.context(second)['own_team'],'B')
        self.assertEqual(self.archive.context(second)['side_origin'],'fingerprint')
        changed=copy.deepcopy(reverse)
        for units in changed['teams'].values():
            for u in units:u['stats']['attack']+=1
        self.assertIsNone(infer_side(changed,[(ref,'A')])['own_team'])
        partial=copy.deepcopy(reverse);partial['teams']['B']=partial['teams']['B'][:1]
        self.assertIsNone(infer_side(partial,[(ref,'A')])['own_team'])
        old=copy.deepcopy(reverse);old['capture_time']+=86401
        self.assertIsNone(infer_side(old,[(ref,'A')])['own_team'])
        ambiguous=copy.deepcopy(reverse);ambiguous['teams']['A']=ref['teams']['A']
        self.assertIsNone(infer_side(ambiguous,[(ref,'A')])['own_team'])
    def test_replay_auto_type_overrides_legacy_classification_and_never_waits_for_personal_result(self):
        b=decode_replay(replay_body(),load_mappings());b['capture_time']=100
        bid=self.archive.save_battle(b,'test');self.archive.set_classification(bid,'竞技场')
        self.archive.set_perspective(bid,'A')
        ctx=self.archive.context(bid)
        self.assertEqual(ctx['sample_kind'],'回放/观战');self.assertIsNone(ctx['own_team'])
        self.assertEqual(result_text(ctx),'回放 · 结果未确认 · 不计战绩')
        self.assertEqual(self.archive.history(sample_kind='竞技场')[0],0)
        self.assertEqual(self.archive.history(sample_kind='回放/观战')[0],1)
        self.assertEqual(analyse(self.archive.dataset(),load_mappings(),('回放/观战',))['eligible_matches'],0)
    def test_mode_candidates_need_explicit_mapping_manual_priority_conflict_and_undo(self):
        body=battle_body()+scalar(7,2)+scalar(8,3)+scalar(9,123456789)
        b=decode_battle(body,load_mappings());b['capture_time']=100
        b['teams']=unique_battle()['teams']
        self.assertEqual(len(b['mode_candidates']),2)
        bid=self.archive.save_battle(b,'test');candidate=b['mode_candidates'][0]
        self.assertEqual(self.archive.context(bid)['sample_kind'],'未分类')
        self.archive.set_mode_mapping(candidate,'竞技场')
        self.assertEqual(self.archive.context(bid)['sample_kind'],'竞技场')
        self.assertEqual(self.archive.history(sample_kind='竞技场')[0],1)
        self.archive.set_mode_mapping(b['mode_candidates'][1],'BP排位')
        self.assertEqual(self.archive.context(bid)['sample_kind'],'未分类')
        self.archive.set_classification(bid,'BP排位');self.assertEqual(self.archive.context(bid)['mode_origin'],'manual')
        self.archive.set_classification(bid,'未分类')
        self.archive.remove_mode_mapping(b['mode_candidates'][1]);self.assertEqual(self.archive.context(bid)['sample_kind'],'竞技场')
        self.archive.remove_mode_mapping(candidate);self.assertEqual(self.archive.context(bid)['sample_kind'],'未分类')
        self.assertNotIn('123456789',json.dumps(b['mode_candidates']))
        self.assertEqual(self.archive.get(bid)['original'],b)
    def test_draft_is_diagnostic_evidence_not_a_mode_or_identity(self):
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive)
        job.engine.message(0x5fc1,scalar(2,123456789)+scalar(4,987654321),10)
        job.engine.message(0x6003,battle_body()+scalar(6,3),20)
        d=job.engine.diagnostics();self.assertEqual(d['draft_messages'],1)
        self.assertEqual(d['mode_detection']['kind'],'PVE')  # This fixture is 1v1.
        self.assertEqual(d['mode_candidates'][0]['value'],3)
        text=json.dumps(d);self.assertNotIn('123456789',text);self.assertNotIn('987654321',text)
    def test_nicknames_are_allowlisted_unassigned_and_optional(self):
        payload=record(replay_body())[2]
        profile=lambda name:blob(8,blob(1,scalar(1,999999999)+blob(3,name)))
        header=profile('测试玩家#1234'.encode())+profile(b'Synthetic#5678')
        b=decode_replay(blob(2,blob(1,header)+payload),load_mappings())
        self.assertEqual([p['nickname'] for p in b['participants']],['测试玩家#1234','Synthetic#5678'])
        self.assertTrue(all(p['team'] is None for p in b['participants']))
        self.assertNotIn('999999999',str(b))
        bad=decode_replay(blob(2,blob(1,profile(b'bad\nname'))+payload),load_mappings())
        self.assertEqual(bad['participants'],[])
        malformed=decode_replay(blob(2,blob(1,profile(b'\xff'))+payload),load_mappings())
        self.assertEqual(len(malformed['teams']['A']),4)
    def test_unknown_identity_is_excluded_from_own_statistics(self):
        b=unique_battle();bid=self.archive.save_battle(b,'test');self.archive.set_context(bid,'A','竞技场')
        self.assertEqual(analyse(self.archive.dataset(),load_mappings(),('竞技场',),perspective='own')['eligible_matches'],0)
        self.archive.set_perspective(bid,'B')
        result=analyse(self.archive.dataset(),load_mappings(),('竞技场',),perspective='own')
        self.assertTrue(all(r['losses']==1 for r in result['heroes']))
    def test_filtered_directory_pagination_delete_restore(self):
        for i in range(6):
            b=unique_battle(100+i);bid=self.archive.save_battle(b,'test')
            self.archive.set_classification(bid,'BP排位' if i%2 else '竞技场')
        total,rows=self.archive.history(2,1,'竞技场');self.assertEqual(total,3)
        self.assertEqual([r['capture_time'] for r in rows],[102,100])
        self.archive.trash_battles([rows[0]['id']]);self.assertEqual(self.archive.history(sample_kind='竞技场')[0],2)
        self.archive.restore_last_trash();self.assertEqual(self.archive.history(sample_kind='竞技场')[0],3)

