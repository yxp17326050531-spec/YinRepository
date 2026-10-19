"""Synthetic equipment updates and filter behavior; no user traffic is committed."""
import copy
import io
import tempfile
import unittest
from unittest.mock import patch
from core import Engine, Inventory, load_mappings
from capture import CaptureJob
from storage import Archive
from equipment import project_gear, matches_gear, UNKNOWN
from test_core import scalar, blob, vi, frame, pcapng, tcp


def attr(tag,value,count=0):return (value << 12) | (tag << 4) | count


def gear(uid=42,level=3,attrs=None,matrix=1,points=3):
    return {'uid':uid,'config_id':99999,'level':level,
            'attributes_raw':attrs or [attr(8,9000),attr(22,32),attr(4,19200),attr(16,300),attr(19,23)],
            'matrix':{'id':matrix,'points':points},'flag_raw':1}


def delta(uid,values,flag=None):
    item=scalar(1,uid)+scalar(2,99999)+blob(4,b''.join(vi(v) for v in values))
    if flag is not None:item+=scalar(6,flag)
    return blob(3,item)


def upgraded(uid,level):return scalar(2,level)+blob(3,vi(uid))


class EquipmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.archive=Archive(self.temp.name)
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close(); self.archive.logger.removeHandler(h)
        self.temp.cleanup()
    def test_patch_preserves_matrix_flag_zero_and_other_items(self):
        inv=Inventory(load_mappings()); baseline={'gear':[gear(),gear(43)]}; inv.restore(baseline)
        values=[attr(8,15000),attr(22,64,1),attr(4,19200),attr(16,300),attr(19,23)]
        inv.update(0x1132,delta(42,values,0)); inv.update(0x1134,upgraded(42,6))
        snap=inv.snapshot(100,[]); a,b=snap['gear']
        self.assertEqual(a['matrix'],baseline['gear'][0]['matrix']); self.assertEqual(a['flag_raw'],0)
        self.assertEqual(a['level'],6); self.assertEqual(a['attributes_raw'],values); self.assertEqual(b,baseline['gear'][1])
        inv.update(0x1134,scalar(1,7)+upgraded(42,15))
        self.assertEqual(inv.gear[42][3],6)
        self.assertEqual(baseline['gear'][0]['level'],3)
    def test_midstream_delta_unknowns_and_five_stages_are_saved(self):
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive); job.source='synthetic'
        body=b''
        for level in (3,6,9,12,15):
            values=[attr(8,level*2000+3000),attr(22,32+level),attr(16,300)]
            body+=frame(0x1132,delta(42,values))+frame(0x1134,upgraded(42,level))
        # Synchronize on 0x1132 without login; coalesced messages share a timestamp.
        job.engine.read(io.BytesIO(pcapng(tcp(body))))
        snap=self.archive.latest_inventory()['data']; g=snap['gear'][0]
        self.assertEqual(g['level'],15); self.assertEqual(g['matrix'],{'id':None,'points':None})
        self.assertEqual(g['attributes_raw'][0],attr(8,33000)); self.assertNotIn('initial_sub_count',g)
        with self.archive.connect() as db:
            self.assertGreaterEqual(db.execute('SELECT COUNT(*) FROM inventory_snapshots').fetchone()[0],5)
    def test_live_worker_seeds_existing_bag_before_delta(self):
        baseline={'capture_time':1,'gear':[gear(),gear(43)],'heroes':[],'shells':[]}
        self.archive.save_inventory(baseline,'initial')
        wire=frame(0x1132,delta(42,[attr(8,15000),attr(22,64,1)]))+frame(0x1134,upgraded(42,6))
        class Process:
            stdout=io.BytesIO(pcapng(tcp(wire))); stderr=io.BytesIO()
            def wait(self,timeout=None):return 0
            def poll(self):return 0
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive)
        with patch('capture.subprocess.Popen',return_value=Process()):job.run(None,'fake-dumpcap','test-interface')
        bag=self.archive.latest_inventory()['data']['gear']
        self.assertEqual(len(bag),2); self.assertEqual(bag[0]['matrix'],gear()['matrix']); self.assertEqual(bag[0]['level'],6)
    def test_filter_or_within_groups_and_subattributes_all_required(self):
        g=gear(); original=copy.deepcopy(g)
        filters={'matrix':['1','15'],'points':['2','3'],'main':['8','7'],'subs':['16','22']}
        self.assertTrue(matches_gear(g,filters))
        self.assertFalse(matches_gear(g,dict(filters,subs=['16','25'])))
        self.assertFalse(matches_gear(g,dict(filters,matrix=['15'])))
        self.assertFalse(matches_gear(g,{'subs':['8']})) # Main attack cannot satisfy subattribute attack.
        self.assertEqual(g,original)
    def test_offline_delta_uses_earlier_baseline_and_not_future_inventory(self):
        import os
        self.archive.save_inventory({'capture_time':1,'gear':[gear(),gear(43)]},'earlier')
        self.archive.save_inventory({'capture_time':9999999999,'gear':[gear(99)]},'future')
        path=os.path.join(self.temp.name,'synthetic.pcapng')
        with open(path,'wb') as f:
            f.write(pcapng(tcp(frame(0x1132,delta(42,[attr(8,15000)]))+frame(0x1134,upgraded(42,6)))))
        job=CaptureJob(lambda *a:None,20001,load_mappings(),self.archive); job.run(path,None,None)
        snap=job.engine.inventory.snapshot(1,[])['gear']
        self.assertEqual([g['uid'] for g in snap],[42,43]); self.assertEqual(snap[0]['level'],6)
        self.assertEqual(snap[0]['matrix'],gear()['matrix'])
        self.assertEqual(self.archive.latest_inventory()['data']['gear'][0]['uid'],99)
    def test_unknown_rarity_and_initial_are_not_guessed_and_metadata_survives(self):
        g=gear(); p=project_gear(g)
        self.assertEqual(p['rarity'],UNKNOWN); self.assertEqual(p['initial'],UNKNOWN)
        self.assertTrue(matches_gear(g,{'rarity':[UNKNOWN],'initial':[UNKNOWN]}))
        self.assertFalse(matches_gear(g,{'initial':['4']}))
        self.archive.set_gear_metadata(42,{'rarity':'传说','initial_sub_count':3})
        self.archive.save_inventory({'capture_time':100,'gear':[gear(level=15)]},'update')
        meta=self.archive.gear_metadata()[42]
        self.assertTrue(matches_gear(g,{'rarity':['传说'],'initial':['3']},meta))
        self.assertNotIn('rarity',g)
        self.assertEqual(project_gear(dict(g,attributes_raw=[attr(99,123)]))['main']['value'],None)
    def test_only_explicit_zero_level_observation_records_initial_count(self):
        inv=Inventory(load_mappings())
        initial=scalar(1,42)+scalar(2,99999)+scalar(3,0)+blob(4,vi(attr(8,3000))+vi(attr(22,32)))
        inv.update(0x1133,blob(1,initial)); inv.update(0x1134,upgraded(42,15))
        g=inv.snapshot(1,[])['gear'][0]
        self.assertEqual(g['initial_sub_count'],1); self.assertEqual(g['level'],15)


if __name__=='__main__':unittest.main()
