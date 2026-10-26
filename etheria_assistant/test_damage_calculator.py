"""Synthetic formula and native snapshot regressions; no real roster fixtures."""
import copy
import math
import os
import tempfile
import unittest
from dataclasses import replace
from damage_calculator import Fighter, Scenario, calculate, defense_terms, import_unit


class DamageTests(unittest.TestCase):
    def test_models_use_distinct_denominators_and_conditional_floors(self):
        self.assertEqual(defense_terms(3000, .2, 0, 'template'), (600, 1.65))
        self.assertEqual(defense_terms(3000, .2, 0, 'kzone'), (900, 1.575))
        self.assertEqual(defense_terms(400, .2, 0, 'kzone'), (400, .7))
        self.assertEqual(defense_terms(3000, 1, 2900, 'kzone'), (400, .7))
        self.assertEqual(defense_terms(1500, 1, 0, 'kzone'), (1500, 2.625))
        self.assertEqual(defense_terms(2500, 1, 0, 'kzone'), (2500, 3.5))
        self.assertEqual(defense_terms(1000, 0, 100, 'template'), (0, 1.05))

    def test_hp_threshold_and_death_stop_subsequent_shell_and_hits(self):
        a = Fighter(attack=10000, crit_damage=200)
        d = Fighter(hp=1000, defense=0)
        s = Scenario(a, d, pvp=False, ratios=(1, 1, 1), harvest=True, shell='启示录')
        r = calculate(s)
        self.assertTrue(r['killed']); self.assertEqual(r['damage'], 1000)
        self.assertEqual(len(r['rows']), 1); self.assertEqual(r['rows'][0]['shell'], 0)
        self.assertTrue(r['rows'][0]['harvest'])
        self.assertFalse(calculate(replace(s, remaining_hp=500))['rows'][0]['harvest'])

    def test_shell_kill_and_shell_damage_changes_next_harvest_threshold(self):
        s = Scenario(Fighter(attack=100, crit_damage=100), Fighter(hp=1000),
                     pvp=False, ratios=(0, 0), remaining_hp=550, shell='启示录', harvest=True)
        r = calculate(s)
        self.assertEqual([x['harvest'] for x in r['rows']], [True, False])
        self.assertAlmostEqual(r['remaining'], 310)
        r = calculate(replace(s, remaining_hp=100))
        self.assertEqual(r['rows'][0]['killed_by'], '启示录'); self.assertEqual(len(r['rows']), 1)

    def test_bloodbath_threshold_crossing_and_prior_turn_damage(self):
        s = Scenario(Fighter(attack=315, crit_damage=100), Fighter(hp=1000), pvp=False, bloodbath=True)
        self.assertAlmostEqual(calculate(s)['damage'], 245)
        self.assertAlmostEqual(calculate(replace(s, bloodbath_spent=200))['damage'], 135)

    def test_manual_loadout_beats_candidates_missing_is_not_zero(self):
        unit = {'hero_id': 1, 'stats': {'attack': 123},
                'matrix_effects_candidates': [{'name': '收割', 'threshold': 8, 'confidence': '已对照样本'},
                    {'name': '狂怒', 'threshold': 8, 'confidence': '候选关联'},
                    {'name': '沸腾打击', 'threshold': None, 'confidence': '已对照样本'}]}
        x = import_unit(unit)
        self.assertEqual(x['active_effects'], {'收割'})
        self.assertIsNone(x['values']['ignore_defense'])
        unit['manual'] = {'matrices': []}
        self.assertFalse(import_unit(unit)['active_effects'])
        unit['manual']['matrices'] = [{'name': '狂怒', 'points': 8}]
        self.assertEqual(import_unit(unit)['active_effects'], {'狂怒'})
        unit['attributes_raw'] = [58, (1 << 63) | ((123 << 8) | 171)]
        self.assertEqual(import_unit(unit)['values']['ignore_defense'], 0)
        self.assertEqual(import_unit(unit)['values']['pvp_damage_bonus'], 12.3)
        unit['attributes_raw'].append(58)
        self.assertIsNone(import_unit(unit)['values']['ignore_defense'])

    def test_noncrit_skips_fury_revelation_and_crit_damage_buff(self):
        s = Scenario(Fighter(attack=100, crit_damage=300), Fighter(hp=10000), pvp=False,
                     critical=False, shell='启示录', fury=True, crit_damage_up=50)
        self.assertAlmostEqual(calculate(s)['damage'], 100 / 1.05)

    def test_count_variants_use_original_panel_and_attack_buff_is_additive(self):
        s = Scenario(Fighter(attack=1000), Fighter(hp=100000), shell='伯爵', attack_up=54)
        self.assertEqual(calculate(s)['combat_attack'], 2740)
        self.assertEqual(calculate(replace(s, count_attack_percent=10))['combat_attack'], 2840)

    def test_multihit_study_tracks_thresholds_without_floor_injection(self):
        # Synthetic round-number panels, independent hand-calculated golden total.
        s = Scenario(Fighter(attack=4400, crit_damage=320, pvp_damage_bonus=10, ignore_defense=10),
                     Fighter(attack=2400, hp=64000, defense=2500, pvp_damage_reduction=20,
                             extra_damage_reduction=15), ratios=(1.1, 1.1, 1.1), target_multiplier=1.75,
                     quilo_passive=True, harvest=True, boiling=True, bloodbath=True, shell='启示录')
        r = calculate(s)
        self.assertAlmostEqual(r['damage'], 34028.89328993103, places=5)
        self.assertEqual([row['harvest'] for row in r['rows']], [True, True, True])
        enhanced = replace(s, attack_up=54, crit_damage_up=50, damage_multiplier=1.3, defense_down=60)
        r = calculate(enhanced)
        self.assertEqual([row['harvest'] for row in r['rows']], [True, True, False])
        self.assertAlmostEqual(r['rows'][0]['effective_defense'], 450)
        self.assertEqual(r['kill_hit'], 3); self.assertEqual(r['rows'][2]['shell'], 0)
        self.assertEqual(calculate(replace(enhanced, model='kzone'))['rows'][0]['effective_defense'], 900)

    def test_shield_break_and_dynamic_matrix_thresholds(self):
        s=Scenario(Fighter(attack=105,crit_damage=100),Fighter(hp=1000),pvp=False,ratios=(1,1),shield_hp=100,shield_bonus=True)
        r=calculate(s)
        self.assertAlmostEqual(r['rows'][0]['actual'],40)
        self.assertEqual(r['rows'][0]['shield_remaining'],0)
        self.assertAlmostEqual(r['rows'][1]['actual'],100)
        r=calculate(replace(s,shield_hp=0,shield_bonus=False,unyielding=True,remaining_hp=600))
        self.assertAlmostEqual(r['rows'][0]['actual'],80)
        self.assertAlmostEqual(r['rows'][1]['actual'],60)
        r=calculate(replace(s,shield_hp=0,shield_bonus=False,insight=True,ratios=(1,1,1,1)))
        self.assertEqual([round(x['actual']) for x in r['rows']],[125,115,105,100])
        with self.assertRaises(ValueError):calculate(replace(s,bloodbath=True))

    def test_seven_sleep_only_boosts_first_segment(self):
        s=Scenario(Fighter(attack=105,crit_damage=100),Fighter(hp=1000),pvp=False,ratios=(1,1),shell='宝剑七',sleeping=True)
        r=calculate(s)
        self.assertEqual([round(x['actual']) for x in r['rows']],[150,100])

    def test_butcher_tiers_require_hp_and_strict_ninety_percent(self):
        s=Scenario(Fighter(attack=105,crit_damage=100),Fighter(hp=10000),pvp=False)
        for tier in (6.4,8.8,11.2,13.6,16):
            self.assertAlmostEqual(calculate(replace(s,butcher_bonus=tier,attacker_hp_percent=90))['damage'],100)
            self.assertAlmostEqual(calculate(replace(s,butcher_bonus=tier,attacker_hp_percent=90.01))['damage'],100+tier)
        with self.assertRaises(ValueError):calculate(replace(s,butcher_bonus=16))
        with self.assertRaises(ValueError):calculate(replace(s,butcher_bonus=10,attacker_hp_percent=100))

    def test_fury_multiplies_result_bonus_and_affinity_is_separate(self):
        s=Scenario(Fighter(attack=105,crit_damage=100,damage_result_bonus=20),Fighter(hp=100000),pvp=False,fury=True,affinity='advantage')
        self.assertAlmostEqual(calculate(s)['damage'],100*1.2*1.12*1.15)
        self.assertAlmostEqual(calculate(replace(s,affinity='disadvantage'))['damage'],100*1.2*1.12*.85)

    def test_whitefang_borne_followups_each_add_sixty_percent_hp(self):
        from character_presets import apply_character
        s=Scenario(Fighter(attack=1000,hp=10000),Fighter(hp=1000000),shell='白獠武者',pvp=False)
        r=calculate(apply_character(s,'borne_s3',alive=5,hp_mode=2,entry_attack=1000,hp_damage_mode=2,passive_checked=True))
        self.assertEqual([x['phase'] for x in r['rows']],['技能','白獠追击','白獠追击'])
        self.assertAlmostEqual(r['rows'][1]['direct'],(1100+18000*.6)/1.05)
        self.assertAlmostEqual(r['rows'][2]['direct'],r['rows'][1]['direct'])
        s=replace(s,defender=Fighter(hp=1))
        r=calculate(apply_character(s,'borne_s3',alive=5,hp_mode=2,entry_attack=1000,hp_damage_mode=1,passive_checked=True))
        self.assertEqual(len(r['rows']),1)

    def test_rejects_nonfinite_and_unsupported_reductions_without_clamping(self):
        for s in (Scenario(Fighter(attack=math.nan)), Scenario(defender=Fighter(extra_damage_reduction=101)),
                  Scenario(ratios=(math.inf,)), Scenario(remaining_hp=0)):
            with self.assertRaises(ValueError): calculate(s)


class StatusTests(unittest.TestCase):
    def test_flower_conversion_and_heart_are_additive_not_compounded(self):
        from calculator_statuses import apply_statuses
        s=Scenario(Fighter(attack=1000,defense=1000),Fighter(attack=1000,hp=10000,defense=1000))
        r=apply_statuses(s,{'flower':3,'heart':2},{'flower':1,'defense':1,'heart':1})
        self.assertEqual(r.attack_up,80);self.assertEqual(r.crit_damage_up,30)
        self.assertEqual(r.defense_up,66);self.assertEqual(r.attacker.defense,1300)
        self.assertEqual(r.defender.attack,1310)
        self.assertAlmostEqual(r.damage_multiplier,.82)

    def test_damage_states_and_critical_lastwords(self):
        from calculator_statuses import apply_statuses
        s=Scenario(Fighter(attack=100),Fighter(hp=10000))
        r=apply_statuses(s,{'frost':1},{'vulnerable':1,'nightmare':1,'guard':1,'lastwords':4,'jade':5})
        self.assertAlmostEqual(r.damage_multiplier,1.25*1.3*1.15*.7*1.28*.6)
        r=apply_statuses(replace(s,critical=False),{}, {'lastwords':4})
        self.assertEqual(r.damage_multiplier,1)
        self.assertEqual(apply_statuses(s,{'speed_up':1},{'speed_down':1}).damage_multiplier,1)

    def test_new_states_and_sleep_only_affects_first_hit(self):
        from calculator_statuses import apply_statuses
        s=Scenario(Fighter(attack=100,crit_damage=100),Fighter(hp=10000),pvp=False,ratios=(1,1))
        r=apply_statuses(s,{'dataflow':12,'sun':6},{'sleep':1,'scales':1,'sun':1})
        self.assertAlmostEqual(r.damage_multiplier,1.42*1.5*.7*.8)
        rows=calculate(r)['rows']
        self.assertAlmostEqual(rows[0]['direct']/rows[1]['direct'],1.25)
        r=apply_statuses(replace(s,critical=False),{}, {'scales':1})
        self.assertEqual(r.damage_multiplier,1)

    def test_sharing_is_final_reduction_including_revelation(self):
        from calculator_statuses import apply_statuses
        s=Scenario(Fighter(attack=105,crit_damage=100),Fighter(hp=10000),pvp=False,shell='启示录',bloodbath=True,bloodbath_spent=2000)
        a=calculate(s);b=calculate(apply_statuses(s,{}, {'tiamat':1}))
        self.assertAlmostEqual(b['damage'],a['damage']*.75)
        self.assertAlmostEqual(b['rows'][0]['shell'],a['rows'][0]['shell']*.75)

    def test_newly_confirmed_statuses_use_layers_and_skill_wide_paper(self):
        from calculator_statuses import apply_statuses
        s=Scenario(Fighter(attack=105,crit_damage=100),Fighter(hp=10000),pvp=False,ratios=(1,1))
        r=apply_statuses(s,{'execution':4,'weak':1},{'execution':4,'color':5,'feather':10,'paper':5})
        self.assertAlmostEqual(r.damage_multiplier,1.32*.75*.76*.5*1.6*.65)
        rows=calculate(r)['rows'];self.assertAlmostEqual(rows[0]['actual'],rows[1]['actual'])
        with self.assertRaises(ValueError):apply_statuses(s,{}, {'execution':17})

    def test_unknown_and_complex_states_cannot_silently_predict_kill(self):
        from calculator_statuses import apply_statuses,STATUSES
        self.assertEqual(len(STATUSES),26)
        for key,_,_,maximum,supported in STATUSES:
            if not supported:
                with self.assertRaises(ValueError):apply_statuses(Scenario(),{}, {key:1})
            with self.assertRaises(ValueError):apply_statuses(Scenario(),{}, {key:maximum+1})


class CharacterPresetTests(unittest.TestCase):
    def test_borne_uses_entry_attack_for_hp_and_cannot_crit(self):
        from character_presets import apply_character
        s=Scenario(Fighter(attack=1000,hp=10000),Fighter(hp=100000),attack_up=48)
        r=apply_character(s,'borne_s3',alive=4,hp_mode=2,entry_attack=1000,hp_damage_mode=1,passive_checked=True)
        self.assertEqual(r.attacker.hp,18000);self.assertEqual(r.extra_hit_damage,10800)
        self.assertEqual(r.ratios,(6,2.5));self.assertFalse(r.critical)
        with self.assertRaises(ValueError):apply_character(s,'borne_s3',alive=4,hp_mode=2,entry_attack=1000)

    def test_misaya_skills_keep_passive_confirmation_separate(self):
        from character_presets import apply_character
        s=Scenario()
        self.assertEqual(apply_character(s,'misaya_s1').other_ignore,70)
        with self.assertRaises(ValueError):apply_character(s,'misaya_s3')
        self.assertEqual(apply_character(s,'misaya_s3',passive_checked=True).other_ignore,70)
        with self.assertRaises(ValueError):apply_character(s,'misaya_s3',passive_checked=True,defense_states={'scales':1})

    def test_qianyu_speed_up_is_applied_once_and_does_not_leak(self):
        from character_presets import apply_character
        s=Scenario()
        r=apply_character(s,'qianyu_s3',attacker_speed=200,defender_speed=200,speed_up=True)
        self.assertAlmostEqual(r.damage_multiplier,1.36)
        self.assertEqual(apply_character(s,None),s)
        with self.assertRaises(ValueError):apply_character(s,'qianyu_s3')


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent
from damage_calculator_widgets import DamageCalculatorDialog


class CalculatorQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        def unit(name, attack, defense):
            return {'hero_name': name, 'stats': {'hp': 10000, 'attack': attack, 'defense': defense},
                    'percent_attributes_tentative': {'crit_damage': 250, 'crit': 80},
                    'attributes_raw': None}
        self.battle = {'teams': {'A': [unit('SyntheticA', 3000, 1500)], 'B': [unit('SyntheticB', 1000, 2500)]}}
        self.original = copy.deepcopy(self.battle)
        self.dialog = DamageCalculatorDialog(None, self.battle)

    def tearDown(self):
        self.dialog.close(); self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_select_import_swap_and_edits_do_not_mutate_battle(self):
        d = self.dialog
        self.assertEqual(d.defender_select.currentData(), 1)
        self.assertEqual(d.fields['attacker']['attack'].value(), 3000)
        self.assertEqual(d.fields['attacker']['ignore_defense'].value(), -1)
        self.assertEqual(d.preset.currentIndex(), 0)
        d.swap(); self.assertEqual(d.fields['attacker']['attack'].value(), 1000)
        d.fields['attacker']['attack'].setValue(5000)
        self.assertEqual(self.battle, self.original)
        self.battle['teams']['B'][0]['stats']['attack'] = 9999
        d.reload(); self.assertEqual(d.fields['attacker']['attack'].value(), 1000)

    def test_missing_extras_require_explicit_assumption_and_model_switch_invalidates(self):
        d = self.dialog
        d.run(); self.assertIsNone(d.last_result); self.assertIn('缺失', d.result_label.text())
        d.assume_zero.setChecked(True); d.run()
        self.assertIsNotNone(d.last_result); primary = d.last_result['damage']
        self.assertEqual(d.process_table.rowCount(), 1)
        d.model.setCurrentIndex(1)
        self.assertIsNone(d.last_result); self.assertEqual(d.process_table.rowCount(), 0)
        d.run(); self.assertNotEqual(d.last_result['damage'], primary)

    def test_same_team_guard_and_manual_zero_preservation(self):
        d = self.dialog; d.assume_zero.setChecked(True)
        d.defender_select.setCurrentIndex(1); d.run()
        self.assertIn('不同队伍', d.result_label.text())
        d.defender_select.setCurrentIndex(2)
        d.fields['attacker']['ignore_defense'].setValue(0)
        d.fields['attacker']['crit_damage'].setValue(-1); d.run()
        self.assertIn('必要面板', d.result_label.text())
        d.critical.setChecked(False); d.run(); self.assertIsNotNone(d.last_result)

    def test_character_switch_keeps_independent_skill_choices(self):
        d=self.dialog
        d.preset.setCurrentText('博尔涅')
        self.assertFalse(d.critical.isChecked());self.assertFalse(d.critical.isEnabled())
        self.assertEqual(d.borne_hp_mode.currentIndex(),2)
        self.assertEqual(d.borne_entry_attack.value(),3000)
        self.assertEqual(d.character_skill.currentData(),'borne_s3')
        d.preset.setCurrentText('弥瑟亚')
        self.assertTrue(d.critical.isEnabled());self.assertEqual(d.character_skill.count(),2)
        d.character_skill.setCurrentIndex(1);self.assertEqual(d.hits.value(),2)
        d.preset.setCurrentText('千羽');self.assertEqual(d.hits.value(),4)
        self.assertFalse(d.quilo_passive.isChecked());self.assertEqual(d.target_multiplier.value(),1)
        d.preset.setCurrentIndex(0);self.assertEqual(d.hits.value(),1)
        self.assertIsNone(d.character_skill.currentData())

    def test_conditional_ui_enforces_void_and_imported_shell_assumptions(self):
        d=self.dialog;d.assume_zero.setChecked(True)
        d.status_states['defender']['void'].setCurrentIndex(1);d.run()
        self.assertIn('虚无目标',d.result_label.text())
        d.aoe.setChecked(True);d.secondary.setChecked(True);d.target_multiplier.setValue(1.75);d.run()
        self.assertEqual(d.scenario().target_multiplier,1)
        self.assertIsNotNone(d.last_result)
        d.shell.setCurrentText('噬身之蛇');d.enable_shell.setChecked(True);d.serpent.setValue(7)
        d.run();self.assertIsNotNone(d.last_result)
        d.shell.setCurrentText('白獠武者（博尔涅联动）');d.run()
        self.assertIsNone(d.last_result);self.assertIn('尚未建模',d.result_label.text())
        d.preset.setCurrentText('博尔涅');d.secondary.setChecked(True);d.run()
        self.assertIn('白獠只追击主目标',d.result_label.text())

    def test_main_window_entry_uses_current_projection_and_reopens_after_close(self):
        from storage import Archive
        from qt_app import MainWindow
        with tempfile.TemporaryDirectory() as directory:
            archive = Archive(directory); window = MainWindow(archive)
            try:
                window.latest = copy.deepcopy(self.battle)
                window.show_damage_calculator(); self.app.processEvents()
                calc = window.calculator_dialog
                self.assertTrue(calc.isVisible())
                self.assertEqual(calc.fields['defender']['defense'].value(), 2500)
                window.latest = None  # capture/navigation cannot replace an open snapshot
                window.show_damage_calculator(); self.assertIs(window.calculator_dialog, calc)
                calc.close(); self.app.processEvents()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                window.show_damage_calculator(); self.app.processEvents()
                self.assertIsNot(window.calculator_dialog, calc)
                self.assertEqual(window.calculator_dialog.attacker_select.currentIndex(), 0)
            finally:
                window.calculator_dialog.close(); window.close(); window.deleteLater(); self.app.processEvents()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                for handler in archive.logger.handlers[:]:
                    handler.close(); archive.logger.removeHandler(handler)


if __name__ == '__main__': unittest.main()
