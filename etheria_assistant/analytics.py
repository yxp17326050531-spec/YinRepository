"""Observed lineup statistics, never claims to be global pick/ban data."""
from collections import Counter, defaultdict
from itertools import combinations


def analyse(dataset, mappings, kinds=('BP排位',), dataset_group='', perspective='both'):
    if perspective not in ('both','own'):
        raise ValueError('未知统计视角')
    rows = defaultdict(Counter)
    pairs = defaultdict(Counter)
    opponents = defaultdict(Counter)
    matches, decided_matches, teams = 0, 0, 0
    for battle in dataset['battles']:
        if battle['original'].get('capture_context')=='replay' or battle.get('sample_kind')=='回放/观战':
            continue
        if battle['sample_kind'] not in kinds or (dataset_group and battle['dataset_group'] != dataset_group):
            continue
        own_team = battle.get('own_team')  # Never infer identity from protocol position.
        if perspective == 'own' and not own_team:
            continue
        matches += 1
        winner = battle['winner']
        decided_matches += winner in ('A','B')
        for team, units in battle['original']['teams'].items():
            if perspective == 'own' and team != own_team:
                continue
            teams += 1
            # Duplicate protocol slots must not multiply hero appearances in one team.
            heroes = sorted({unit['hero_id'] for unit in units})
            result = ('draws' if winner == 'draw' else 'unknown' if winner == 'unknown'
                      else 'wins' if winner == team else 'losses')
            for hero in heroes:
                rows[hero]['appearances'] += 1
                rows[hero][result] += 1
            for pair in combinations(heroes,2):
                pairs[pair]['appearances'] += 1
                pairs[pair][result] += 1
            other = 'B' if team == 'A' else 'A'
            enemies = {u['hero_id'] for u in battle['original']['teams'][other]}
            for hero in heroes:
                for enemy in enemies:
                    if hero != enemy:
                        opponents[(hero,enemy)]['appearances'] += 1
                        opponents[(hero,enemy)][result] += 1
    def stats(counts):
        counts = dict(counts)
        decided = counts.get('wins',0) + counts.get('losses',0)
        return {**{key:counts.get(key,0) for key in ('appearances','wins','losses','draws','unknown')},
                'decided':decided,
                'team_appearance_rate':counts['appearances']/teams if teams else None,
                'win_rate':counts.get('wins',0)/decided if decided else None}
    heroes = [{'hero_id':hero, 'hero_name':mappings['heroes'].get(str(hero),f'角色 #{hero}'),
               **stats(count)} for hero,count in sorted(rows.items(),key=lambda x:(-x[1]['appearances'],x[0]))]
    cooccurrences = [{'hero_ids':list(pair),**stats(count)} for pair,count in sorted(pairs.items())]
    matchups = [{'hero_id':hero,'opponent_id':enemy,**stats(count)} for (hero,enemy),count in sorted(opponents.items())]
    return {'eligible_matches':matches,'team_samples':teams,'decided_matches':decided_matches,
            'heroes':heroes,'cooccurrences':cooccurrences,'matchups':matchups,'perspective':perspective,
            'scope':'本地观测队伍出场率，不是选取率、禁用率或全服胜率'}


def rank_statistics(result, category, hero_id=None, min_decided=5):
    """Descriptive rankings: adverse matchups first, winning duos first."""
    if category not in ('matchups','cooccurrences') or type(min_decided) is not int or min_decided < 1:
        raise ValueError('榜单类型或最少样本数无效')
    rows=[]
    for row in result[category]:
        if row['decided'] < min_decided:
            continue
        if hero_id is not None:
            if category=='matchups' and row['hero_id']!=hero_id:
                continue
            if category=='cooccurrences' and hero_id not in row['hero_ids']:
                continue
        rows.append(row)
    if category=='matchups':
        return sorted(rows,key=lambda r:(r['win_rate'],-r['decided'],r['hero_id'],r['opponent_id']))
    return sorted(rows,key=lambda r:(-r['win_rate'],-r['decided'],r['hero_ids']))
