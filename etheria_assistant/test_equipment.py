"""Synthetic equipment updates and filter behavior; no user traffic is committed."""
import copy
import io
import tempfile
import unittest
from unittest.mock import patch
from core import Engine, Inventory, load_mappings
from capture import CaptureJob
from storage import Archive
from equipment import project_gear, matches_gear, UNKNOWN, sort_gear, gear_sort_value
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


def login_gear(uid, level=15):
    return blob(1, scalar(1, uid) + scalar(2, 99999) + scalar(3, level)
                + blob(4, vi(attr(8, 33000))) + scalar(5, (3 << 16) | 1) + scalar(6, 1))


def login_shell(uid):
    return blob(1, scalar(1, uid) + scalar(2, 54311) + scalar(4, 50) + scalar(5, 0)
                + scalar(6, 0) + scalar(7, 0) + blob(8, b''))


def login_hero(uid, gear_uid, shell_uid):
    return blob(2, scalar(1, uid) + scalar(7, shell_uid) + scalar(9, 101)
                + blob(10, vi(gear_uid)) + scalar(11, 0) + blob(12, b''))


class EquipmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.archive=Archive(self.temp.name)
    def tearDown(self):
        for h in self.archive.logger.handlers[:]:h.close(); self.archive.logger.removeHandler(h)
        self.temp.cleanup()

    def test_login_replaces_other_account_inventory_and_cache_survives_restart(self):
        job = CaptureJob(lambda *a: None, 20001, load_mappings(), self.archive)
        job.source = 'synthetic login'
        marker = scalar(4, 2)
        old_login = ((0x1133, login_gear(42, 0) + login_gear(43) + marker),
                     (0x1129, login_shell(101) + login_shell(102)),
                     (0x1122, login_hero(1001, 42, 101)))
        for op, body in old_login:
            job.engine.message(op, body, 100)
        saved = self.archive.latest_inventory()['data']
        new_job = CaptureJob(lambda *a: None, 20001, load_mappings(), self.archive)
        new_job.source = 'synthetic login'
        new_job.engine.inventory.restore(saved)
        new_login = ((0x1133, login_gear(51) + marker), (0x1129, login_shell(201)),
                     (0x1122, login_hero(2001, 51, 201)))
        for op, body in new_login:
            new_job.engine.message(op, body, 200)
        new_job.engine.message(0x1132, delta(51, [attr(8, 33000), attr(16, 1480)]), 201)
        latest = self.archive.latest_inventory()['data']
        self.assertEqual([item['uid'] for item in latest['gear']], [51])
        self.assertEqual([item['uid'] for item in latest['shells']], [201])
        self.assertEqual([item['base_id'] for item in latest['heroes']], [2001])
        self.assertEqual(latest['gear'][0]['level'], 15)
        self.assertEqual(latest['gear'][0]['attributes_raw'][-1], attr(16, 1480))
        self.assertEqual(new_job.engine.inventory.initial_sub_counts, {})
        self.assertFalse(latest['loadout_rows'][0]['incomplete'])
        self.assertEqual(self.archive.latest_inventory(before=100)['data'], saved)

    def test_partial_and_invalid_login_packets_do_not_replace_inventory(self):
        inv = Inventory(load_mappings())
        inv.restore({'gear': [gear()]})
        marker = scalar(4, 2)
        inv.update(0x1133, marker)
        self.assertEqual(set(inv.gear), {42})
        inv.update(0x1133, login_gear(43))
        self.assertEqual(set(inv.gear), {42, 43})
        for invalid in (login_gear(51) * 2, login_gear(51) + blob(1, scalar(1, 52))):
            with self.assertRaises(ValueError):
                inv.update(0x1133, invalid + marker)
            self.assertEqual(set(inv.gear), {42, 43})

    def test_manual_entry_requires_one_fresh_connection_and_waits_for_all_lists(self):
        from test_components import component_message
        old = {'capture_time': 1, 'gear': [gear(42)]}
        self.archive.save_inventory(old, 'old account')
        events = []
        job = CaptureJob(lambda kind, data: events.append((kind, data)), 20001,
                         load_mappings(), self.archive, inventory_workflow=True)
        login = frame(0x1133, login_gear(51) + scalar(4, 2))
        tail = (frame(0x1129, login_shell(201)) + frame(0x2961, component_message((301,)))
                + frame(0x1122, login_hero(1001, 51, 201)))
        job.engine.packet(2, 1, tcp(login + tail, flags=0x12))
        self.assertFalse(events)

        job.request_inventory_entry(('first', 3))
        job.before_packet()
        job.engine.packet(4, 1, tcp(login, seq=101+len(login+tail)))
        self.assertFalse(events)  # Already open before the latest request.
        job.engine.packet(5, 1, tcp(login, flags=0x12))
        self.assertEqual(events[-1], ('inventory_entry', {'id': 'first', 'counts': {'gear': 1}}))
        job.engine.message(0x1129, login_shell(999), 6, 'other connection')
        job.engine.message(0x1132, delta(99, [attr(8, 33000)]), 6, job.engine.inventory_connection)
        self.assertEqual(len(events), 1)

        job.request_inventory_entry(('second', 7))
        job.before_packet()
        job.engine.packet(8, 1, tcp(tail, seq=101+len(login)))
        self.assertEqual(len(events), 1)
        job.engine.packet(9, 1, tcp(login, flags=0x12))
        job.engine.packet(10, 1, tcp(tail, seq=101+len(login)))
        ready = events[-1][1]
        self.assertEqual(ready['id'], 'second')
        self.assertEqual(ready['counts'], {'gear': 1, 'shells': 1, 'components': 1, 'heroes': 1})
        self.assertEqual([g['uid'] for g in ready['snapshot']['gear']], [51])
        self.assertEqual([s['uid'] for s in ready['snapshot']['shells']], [201])
        self.assertFalse(ready['snapshot']['loadout_rows'][0]['incomplete'])
        self.assertEqual(self.archive.latest_inventory()['data'], old)

    def test_clear_inventory_survives_restart_and_rebuilds_only_from_fresh_login(self):
        old = {'capture_time': 100, 'gear': [gear(42)], 'components': [{'uid': 3}]}
        self.archive.save_inventory(old, 'old account')
        reset = self.archive.clear_current_inventory()
        cleared_at = reset['inventory_reset_time']
        # A worker may still finish persisting its last snapshot after a clear.
        self.archive.save_inventory(dict(old, gear=[gear(42), gear(43)], capture_time=cleared_at + 1), 'old worker')
        reopened = Archive(self.temp.name)
        self.assertEqual(reopened.latest_inventory()['data'], reset)
        self.assertEqual(reopened.latest_inventory(before=100)['data'], old)

        events = []
        job = CaptureJob(lambda kind, data: events.append((kind, data)), 20001, load_mappings(), reopened)
        job.restore_inventory(reopened.latest_inventory())
        events.clear()
        engine = job.engine
        engine.message(0x1132, delta(42, [attr(8, 33000)]), cleared_at + 2, 'previous')
        engine.message(0x1133, login_gear(42) + scalar(4, 2), cleared_at - 1, 'previous')
        engine.message(0x1133, login_gear(42), cleared_at + 3, 'previous')
        self.assertFalse(any(kind == 'inventory_snapshot' for kind, _ in events))
        self.assertEqual(reopened.latest_inventory()['data'], reset)
        engine.message(0x1133, login_gear(51) + scalar(4, 2), cleared_at + 4, 'current')
        engine.message(0x1129, login_shell(201), cleared_at + 5, 'current')
        engine.message(0x1132, delta(42, [attr(8, 33000)]), cleared_at + 6, 'previous')
        engine.message(0x1132, delta(51, [attr(8, 33000), attr(16, 1480)]), cleared_at + 7, 'current')
        snapshot = reopened.latest_inventory()['data']
        self.assertEqual([item['uid'] for item in snapshot['gear']], [51])
        self.assertEqual(snapshot['gear'][0]['attributes_raw'][-1], attr(16, 1480))
        self.assertEqual([item['uid'] for item in snapshot['shells']], [201])
        self.assertNotIn('components', snapshot)

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
        # Capture teardown frees parser buffers; the historical projection is durable.
        snap=self.archive.latest_inventory(before=2)['data']['gear']
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

    def test_sort_uses_decimal_values_and_keeps_missing_last_both_directions(self):
        bag=[gear(1,attrs=[attr(8,33000),attr(16,1560,4)]),
             gear(2,attrs=[attr(8,33000),attr(16,1620,4)]),
             gear(3,attrs=[attr(8,33000)]),
             gear(4,attrs=[attr(8,33000),attr(16,1590,4)])]
        original=copy.deepcopy(bag);spec={'key':'attr:16','scope':'subs','descending':True}
        self.assertEqual([g['uid'] for g in sort_gear(bag,spec)],[2,4,1,3])
        self.assertEqual([g['uid'] for g in sort_gear(bag,dict(spec,descending=False))],[1,4,2,3])
        self.assertEqual(gear_sort_value(bag[0],spec),15.6)
        self.assertIsNone(gear_sort_value(bag[0],dict(spec,scope='main')))
        duplicate=gear(5,attrs=[attr(8,33000),attr(8,1920)])
        self.assertEqual(gear_sort_value(duplicate,{'key':'attr:8','scope':'subs'}),19.2)
        self.assertEqual(gear_sort_value(duplicate,{'key':'attr:8','scope':'all'}),349.2)
        self.assertEqual(bag,original)


if __name__=='__main__':unittest.main()
