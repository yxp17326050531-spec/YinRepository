from dataclasses import replace
import unittest
from damage_calculator import Fighter,Scenario,calculate
from gear_scoring import default_rules,score_gear
from test_equipment import gear,attr

class IterationTests(unittest.TestCase):
    def test_tiger_order_and_target(self):
        s=Scenario(Fighter(attack=105,crit_damage=100),Fighter(hp=5000),pvp=False,
                   ratios=(1,1),target_multiplier=2,shell='寅虎',tiger_target=True)
        r=calculate(s);self.assertEqual([round(v['direct']) for v in r['rows']],[180,300,200])
        r=calculate(replace(s,tiger_target=False));self.assertEqual([round(v['direct']) for v in r['rows']],[200,200])
        with self.assertRaises(ValueError):calculate(replace(s,tiger_target=None))
        r=calculate(replace(s,defender=Fighter(hp=140)))
        self.assertEqual(len(r['rows']),1);self.assertEqual(r['rows'][0]['killed_by'],'寅虎先手')
    def test_tiger_changes_target_state_before_first_skill(self):
        s=Scenario(Fighter(attack=105),Fighter(hp=220),ratios=(.1,),pvp=False,shell='寅虎',tiger_target=True,harvest=True,shield_hp=20)
        a,b=calculate(s)['rows'];self.assertEqual(a['direct_trace']['absorbed'],20)
        self.assertTrue(a['harvest']);self.assertFalse(b['harvest']);self.assertAlmostEqual(b['before'],60)
    def test_borne_tiger_applies_passive_once_before_mark(self):
        from character_presets import apply_character
        from calculator_formula import formula_text

        base = Scenario(Fighter(attack=1000, hp=10000), Fighter(hp=1000000),
                        shell='寅虎', tiger_target=True, pvp=False)
        # Entry attack 1000 adds 8000 HP. 牧夜行 contributes 10800 per trigger.
        for mode, second_base in ((1, 13300), (2, 2500)):
            with self.subTest(mode=mode):
                s = apply_character(base, 'borne_s3', alive=4, hp_mode=2, entry_attack=1000,
                                    hp_damage_mode=mode, passive_checked=True)
                result = calculate(s)
                opener, first, second = result['rows']
                self.assertAlmostEqual(opener['direct'], (1800 + 10800) / 1.05)
                self.assertAlmostEqual(first['direct'], (6000 + 10800) * 1.5 / 1.05)
                self.assertAlmostEqual(second['direct'], second_base / 1.05)
                self.assertIn('牧夜行随寅虎先手触发一次', formula_text(s, result))
                other = calculate(replace(s, tiger_target=False))['rows']
                self.assertEqual([row['phase'] for row in other], ['技能', '技能'])
                self.assertAlmostEqual(other[0]['direct'], (6000 + 10800) / 1.05)
                lethal = calculate(replace(s, remaining_hp=10000))
                self.assertEqual([row['killed_by'] for row in lethal['rows']], ['寅虎先手'])

    def test_main_stat_gate_and_speed_exception(self):
        for main,role in [(7,'attack'),(3,'hp'),(11,'defense'),(25,'accuracy'),(28,'resistance')]:
            g=gear(attrs=[attr(main,100),attr(16,1800),attr(11,130),attr(22,150),attr(19,100)],matrix=4)
            rows={r['key']:r for r in score_gear(g,{'matrices':{'4':'疾驰'}},default_rules())['roles']}
            self.assertTrue(rows[role]['eligible']);self.assertTrue(rows['speed']['eligible'])
            for k in {'hp','defense','attack'}-{role}:self.assertFalse(rows[k]['eligible'])
            if main==25:self.assertIsNone(rows['attack']['score'])
