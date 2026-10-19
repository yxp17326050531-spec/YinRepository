"""Synthetic component records; no personal inventory or capture bytes."""
import copy
import io
import tempfile
import unittest
from core import Inventory, Engine, decode_battle, load_mappings
from capture import CaptureJob, imprint_text
from storage import Archive, project_unit
from test_core import blob, scalar, vi, frame, tcp, pcapng, battle_body


def component_message(uids=(41,42,43)):
    body=blob(1,scalar(1,1)+scalar(2,0)+blob(3,b''.join(vi(v) for v in list(uids[:2])+[0,0])))
    for i,uid in enumerate(uids):
        item=scalar(1,uid)+scalar(2,90001+i)+blob(5,vi(12345678901)+vi(7654321))
        if i==1:item+=scalar(3,0)+scalar(6,0)
        if i==2:item+=scalar(3,4)+scalar(6,1)
        body+=blob(2,item)
    return body


class ComponentTests(unittest.TestCase):
    def test_raw_records_keep_missing_distinct_from_zero_and_restore(self):
        inventory=Inventory(load_mappings());inventory.update(0x2961,component_message())
        snapshot=inventory.snapshot(100,[0x2961]);before=copy.deepcopy(snapshot)
        self.assertEqual(len(snapshot['components']),3)
        a,b,c=snapshot['components']
        self.assertIsNone(a['field3_raw']);self.assertIsNone(a['field6_raw'])
        self.assertEqual((b['field3_raw'],b['field6_raw']),(0,0))
        self.assertEqual((c['field3_raw'],c['field6_raw']),(4,1))
        self.assertEqual(a['attributes_raw'],[12345678901,7654321])
        self.assertEqual(snapshot['component_groups'][0]['component_uids_raw'],[41,42,0,0])
        restored=Inventory(load_mappings());restored.restore(snapshot)
        self.assertEqual(restored.snapshot(100,[0x2961]),snapshot)
        inventory.components[41]['attributes_raw'].append(9)
        self.assertEqual(snapshot,before)
    def test_snapshot_replaces_deleted_records_and_bad_message_preserves_existing(self):
        inventory=Inventory(load_mappings());inventory.update(0x2961,component_message())
        before=inventory.snapshot(100,[])
        with self.assertRaises(ValueError):inventory.update(0x2961,blob(2,scalar(1,9)))
        self.assertEqual(inventory.snapshot(100,[]),before)
        inventory.update(0x2961,component_message((41,)))
        self.assertEqual(list(inventory.components),[41])
        with self.assertRaises(ValueError):inventory.update(0x2961,b'')
        inventory.update(0x2961,blob(1,scalar(1,1)+blob(3,vi(0)*4)))
        self.assertEqual(inventory.snapshot(101,[])['components'],[])
    def test_absent_old_snapshot_does_not_claim_an_empty_component_bag(self):
        inventory=Inventory(load_mappings());inventory.restore({'gear':[]})
        self.assertNotIn('components',inventory.snapshot(100,[]))
    def test_component_snapshot_is_archived_before_ui_and_first_frame_is_recognized(self):
        with tempfile.TemporaryDirectory() as root:
            archive=Archive(root);events=[]
            def emit(kind,data):
                if kind=='inventory_snapshot':
                    self.assertEqual(archive.latest_inventory()['data']['components'],data['components'])
                events.append((kind,data))
            try:
                job=CaptureJob(emit,20001,load_mappings(),archive)
                job.engine.read(io.BytesIO(pcapng(tcp(frame(0x2961,component_message())))))
                self.assertEqual(job.engine.counts['messages'],1)
                self.assertEqual(job.engine.counts['warnings'],0)
                self.assertNotIn(0x2961,job.engine.unknown_opcodes)
                self.assertEqual(len(archive.latest_inventory()['data']['components']),3)
                reopened=Inventory(load_mappings());reopened.restore(archive.latest_inventory()['data'])
                self.assertEqual(len(reopened.components),3)
            finally:
                for handler in archive.logger.handlers[:]:handler.close();archive.logger.removeHandler(handler)
    def test_user_confirmed_imprint_is_separate_from_shell_and_matrix(self):
        unit=decode_battle(battle_body(),load_mappings())['teams']['A'][0]
        unit['effects_raw']=[83889586,83889586,1121,33,35];before=copy.deepcopy(unit)
        display=project_unit(unit,load_mappings())
        self.assertEqual(imprint_text(display),'刻影：屠夫')
        self.assertEqual(len(display['imprints']),1)
        self.assertEqual(display['imprints'][0]['confidence'],'用户确认')
        self.assertEqual([m['effect_id'] for m in display['matrix_effects_candidates']],[1121])
        self.assertEqual(display['shells'],[]);self.assertEqual(unit,before)
        unit['effects_raw']=[33,35]
        self.assertEqual(imprint_text(project_unit(unit,load_mappings())),'刻影：待识别')

    def test_old_login_backfills_missing_category_but_never_uses_future_or_overrides_empty(self):
        with tempfile.TemporaryDirectory() as root:
            archive=Archive(root)
            try:
                inventory=Inventory(load_mappings());inventory.update(0x2961,component_message())
                known=inventory.snapshot(100,[0x2961]);archive.save_inventory(known,'old login')
                archive.save_inventory({'capture_time':200,'gear':[]},'newer pre-feature cache')
                self.assertEqual(len(archive.latest_inventory()['data']['components']),3)
                self.assertEqual(archive.latest_inventory()['data']['components_capture_time'],100)
                self.assertIsNone(archive.latest_inventory(before=99))
                archive.save_inventory({'capture_time':50,'gear':[{'uid':1}]},'earlier')
                self.assertNotIn('components',archive.latest_inventory(before=50)['data'])
                archive.save_inventory({'capture_time':300,'gear':[],'components':[],'component_groups':[]},'known empty')
                self.assertEqual(archive.latest_inventory()['data']['components'],[])
            finally:
                for handler in archive.logger.handlers[:]:handler.close();archive.logger.removeHandler(handler)


if __name__=='__main__':unittest.main()
