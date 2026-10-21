import copy
import unittest

import json
from pathlib import Path

from core import decode_battle, load_mappings, shell_config_name, matrix_name, shell_effect_mapping
from storage import project_unit
from base_ui import shell_text, matrix_text
from test_core import battle_body


class MappingBoundaries(unittest.TestCase):
    def setUp(self):
        self.mappings = load_mappings()
        self.unit = decode_battle(battle_body(), self.mappings)['teams']['A'][0]

    def test_inferred_variants_deduplicate_and_keep_label(self):
        self.unit['effects_raw'] = [39010533,39010534,39010535,39010536]
        rendered = project_unit(self.unit, self.mappings)
        self.assertEqual(len(rendered['shells']),1)
        self.assertEqual(shell_text(rendered),'天才球手 [推定]')
        rendered = project_unit(self.unit, self.mappings, {'shell':'本场手动','matrices':None})
        self.assertEqual(shell_text(rendered),'本场手动 [手动]')
        self.unit['effects_raw'] = [39008533]
        self.assertEqual(project_unit(self.unit,self.mappings)['shells'],[])

    def test_configuration_fallback_and_exact_override(self):
        self.assertEqual(shell_config_name(self.mappings,54245),'万魔法典')
        self.assertEqual(shell_config_name(self.mappings,54244),'万魔法典 [同类推定]')
        custom = copy.deepcopy(self.mappings)
        custom['shell_configs']['54244'] = '用户精确命名'
        self.assertEqual(shell_config_name(custom,54244),'用户精确命名')
        self.assertEqual(shell_config_name(custom,54542),'智壳 #54542')

    def test_corrected_matrix_names_and_inferred_order(self):
        self.assertEqual(len(self.mappings['matrices']),27)
        self.assertEqual(matrix_name(self.mappings,19),'亵渎')
        self.assertEqual(matrix_name(self.mappings,40),'沸腾打击')
        self.assertEqual(matrix_name(self.mappings,66),'进化荫庇')
        for identifier in (3,21):
            self.assertIn('顺序推定',matrix_name(self.mappings,identifier))
        self.assertEqual(matrix_name(self.mappings,61),'暴烈利刃')
        self.assertEqual(matrix_name(self.mappings,64),'疾影强袭')

    def test_new_family_can_infer_unseen_battle_variant_with_bounds(self):
        effect=33_554_432+5456*1000+101
        self.assertNotIn(str(effect),self.mappings['shell_effects'])
        self.assertEqual(shell_effect_mapping(self.mappings,effect)['name'],'天才球手')
        self.assertIn('推定',shell_effect_mapping(self.mappings,effect)['confidence'])
        self.assertIsNone(shell_effect_mapping(self.mappings,effect-2))
        self.assertIsNone(shell_effect_mapping(self.mappings,39008533))
        custom=copy.deepcopy(self.mappings)
        custom['shell_effects'][str(effect)]={'name':'用户确认名称','confidence':'用户映射'}
        self.assertEqual(shell_effect_mapping(custom,effect)['name'],'用户确认名称')

    def test_controlled_pair_effects_and_no_absence_or_point_inference(self):
        evidence = json.loads(Path(__file__).with_name('mapping_evidence.json').read_text(encoding='utf-8'))
        observed = evidence['controlled_matrix_pair']['observations']
        expected = {33101:'荆棘',31951:'不屈之誓',32102:'时光驾驭'}
        for row in observed:
            snapshots = []
            for key in ('before_effects','after_effects'):
                raw = copy.deepcopy(self.unit)
                raw.update(hero_id=row['hero_id'], effects_raw=row[key])
                untouched = copy.deepcopy(raw)
                projected = project_unit(raw,self.mappings)
                self.assertEqual(raw,untouched)
                self.assertEqual(projected['effects_raw'],row[key])
                self.assertFalse(projected['matrix_loadout_complete'])
                self.assertNotIn('matrices',projected)
                self.assertEqual(shell_text(projected),row['shell_name'])
                snapshots.append(projected)
            if row['hero_id'] in expected:
                name = expected[row['hero_id']]
                before_text,after_text = map(matrix_text,snapshots)
                self.assertEqual(before_text.count(name),1)
                self.assertIn('已对照',before_text)
                self.assertNotIn(name,after_text)
                self.assertEqual(after_text,'完整矩阵未知')
            else:
                # The third capture now resolves the former simultaneous changes.
                self.assertEqual(matrix_text(snapshots[0]),'涌泉 12点效果（已对照）、浴血之躯 12点效果（已对照）')
                self.assertEqual(matrix_text(snapshots[1]),'涌泉 8点效果（已对照）')
        guard = copy.deepcopy(self.unit)
        guard['effects_raw'] = [1081,1081,1421,1422,1423,1331,1021,1391,1192]
        result = project_unit(guard,self.mappings)
        self.assertEqual(matrix_text(result).count('荆棘'),1)
        self.assertEqual(matrix_text(result).count('不屈之誓'),1)
        self.assertEqual(len(result['matrix_effects_candidates']),6)
        self.assertTrue(all(m['effect_id'] not in (1021,1391,1192) for m in result['matrix_effects_candidates']))

    def test_three_battle_observations_resolve_threshold_replacement(self):
        evidence = json.loads(Path(__file__).with_name('mapping_evidence.json').read_text(encoding='utf-8'))
        observations = evidence['controlled_matrix_triple']['observations']
        expected = [ [('涌泉',12),('浴血之躯',12)], [('涌泉',8)], [('涌泉',12)] ]
        for row, wanted in zip(observations,expected):
            raw = copy.deepcopy(self.unit)
            raw.update(hero_id=row['hero_id'], effects_raw=row['effects_raw'])
            original = copy.deepcopy(raw)
            result = project_unit(raw,self.mappings)
            actual = [(x['name'],x['threshold']) for x in result['matrix_effects_candidates']]
            self.assertEqual(actual,wanted)
            self.assertTrue(all(x['confidence']=='已对照样本' for x in result['matrix_effects_candidates']))
            self.assertEqual(raw,original)
            self.assertEqual(result['effects_raw'],row['effects_raw'])
            self.assertFalse(result['matrix_loadout_complete'])
            self.assertNotIn('matrices',result)
            self.assertEqual(result['hero_name'],'瑞玛丽')
            self.assertEqual(shell_text(result),'冠军巨鳄')
        before,lower,isolated=[set(row['effects_raw']) for row in observations]
        self.assertEqual(before-isolated,{1321})
        self.assertEqual(isolated-before,set())
        self.assertEqual(lower-isolated,{1191})
        self.assertEqual(isolated-lower,{1401})

    def test_confirmed_display_keeps_candidate_and_manual_sources_separate(self):
        self.unit['effects_raw'] = [1081,1171,1421,1422,1423]
        projected = project_unit(self.unit,self.mappings)
        self.assertIn('荆棘 8点效果（已对照）',matrix_text(projected))
        self.assertIn('狂怒 8点效果（候选）',matrix_text(projected))
        manual = project_unit(self.unit,self.mappings,{'matrices':[{'name':'用户记录','points':9}]})
        self.assertEqual(matrix_text(manual),'用户记录 +9 [手动]')

    def test_confirmed_matrix_threshold_preserves_raw_positions(self):
        from capture import matrix_text as desktop_matrix_text
        before=copy.deepcopy(self.unit)
        before['effects_raw']=[33,1121,39001533,83889586,35]
        original=copy.deepcopy(before)
        mapped=project_unit(before,self.mappings)
        effect=mapped['matrix_effects_candidates'][0]
        self.assertEqual((effect['name'],effect['matrix_id'],effect['effect_id']),('奋进',12,1121))
        self.assertEqual(effect['threshold'],8)
        self.assertEqual(desktop_matrix_text(mapped),'奋进 8点效果（已对照）')
        self.assertEqual(matrix_text(mapped),desktop_matrix_text(mapped))
        self.assertEqual(before,original)
        after=copy.deepcopy(before);after['effects_raw'].remove(1121)
        self.assertEqual(project_unit(after,self.mappings)['matrix_effects_candidates'],[])
        for identifier in (33,35,83889586,3275101,3275102,3275103,38978533,39001533):
            self.assertNotIn(str(identifier),self.mappings['matrix_effects'])

    def test_four_user_confirmed_matrix_effects_keep_shell_namespace(self):
        cases=[(1051,'戍卫',8,5),(1121,'奋进',8,12),(1151,'收割',8,15),(1431,'沸腾打击',12,40)]
        for identifier,name,threshold,matrix_id in cases:
            unit=copy.deepcopy(self.unit);unit['effects_raw']=[identifier]
            effect=project_unit(unit,self.mappings)['matrix_effects_candidates'][0]
            self.assertEqual((effect['name'],effect['threshold'],effect['matrix_id']),(name,threshold,matrix_id))
        self.assertEqual(self.mappings['shell_effects']['38978533']['name'],'万魔法典')
        self.assertEqual(self.mappings['shell_effects']['39001533']['name'],'琥珀')

    def test_healing_matrix_effect_is_separate_from_potential_and_received_bonuses(self):
        from capture import matrix_text as desktop_matrix_text
        from battle_attributes import decode_extra_attributes,extra_text
        unit=copy.deepcopy(self.unit)
        unit['effects_raw']=[1401,1101]
        unit['attributes_raw']=[(1<<63)|(110<<8)|41,(130<<8)|47,(130<<8)|94,80]
        before=copy.deepcopy(unit)
        display=project_unit(unit,self.mappings)
        healing=next(m for m in display['matrix_effects_candidates'] if m['effect_id']==1101)
        self.assertEqual((healing['name'],healing['matrix_id'],healing['threshold']),('治愈',10,8))
        self.assertIn('治愈 8点效果（已对照）',desktop_matrix_text(display))
        self.assertIn('涌泉 12点效果（已对照）',desktop_matrix_text(display))
        changed=copy.deepcopy(unit);changed['effects_raw']=[1191]
        changed_display=project_unit(changed,self.mappings)
        self.assertEqual(desktop_matrix_text(changed_display),'涌泉 8点效果（已对照）')
        self.assertEqual(display['extra_attributes'],changed_display['extra_attributes'])
        self.assertEqual(decode_extra_attributes(unit['attributes_raw'])['extra_damage_reduction'],11)
        self.assertIn('潜能提供的额外减伤与涌泉矩阵效果分开',extra_text(unit))
        self.assertEqual(decode_extra_attributes(unit['attributes_raw'])['damage_result_bonus'],0)
        self.assertIn('条件值未下发时不补入',extra_text(unit))
        self.assertEqual(unit,before)
        custom=copy.deepcopy(self.mappings)
        custom['matrix_effects']['1101']={'name':'用户治愈名称','threshold':8,'confidence':'用户映射'}
        self.assertIn('用户治愈名称',desktop_matrix_text(project_unit(unit,custom)))


if __name__=='__main__':
    unittest.main()
