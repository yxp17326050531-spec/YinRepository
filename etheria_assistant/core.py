"""Etheria companion v0.1. Offline and live input share the same parser.

Protocol observations come from the supplied captures, not an official schema.
Only inbound battle and local inventory messages are decoded. Nothing is uploaded.
"""
from __future__ import annotations

import collections
import hashlib
import ipaddress
import json
import struct
import time
from pathlib import Path
from battle_session import BattleSession, battle_identity
from battle_attributes import decode_extra_attributes
from battle_metadata import mode_info

MAX_BODY = 2 * 1024 * 1024
MAX_BLOCK = 16 * 1024 * 1024


def varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            raise ValueError("不完整的 varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            if value >= 1 << 64:
                raise ValueError("varint 溢出")
            return value, pos
    raise ValueError("varint 过长")


def fields(data):
    pos = 0
    out = []
    while pos < len(data):
        tag, pos = varint(data, pos)
        field, wire = tag >> 3, tag & 7
        if not 0 < field < (1 << 29):
            raise ValueError("无效字段")
        if wire == 0:
            value, pos = varint(data, pos)
        elif wire in (1, 2, 5):
            if wire == 2:
                size, pos = varint(data, pos)
            else:
                size = 8 if wire == 1 else 4
            if pos + size > len(data):
                raise ValueError("字段被截断")
            value = data[pos:pos + size]
            pos += size
        else:
            raise ValueError("未支持的 protobuf wire type")
        out.append((field, wire, value))
    return out


def packed(data):
    if not isinstance(data, bytes):
        raise ValueError("预期 packed 字段")
    pos, out = 0, []
    while pos < len(data):
        value, pos = varint(data, pos)
        out.append(value)
    return out


def record(data):
    return {f: v for f, w, v in fields(data)}


def read_exact(stream, size, eof_ok=False):
    buf = bytearray()
    while len(buf) < size:
        part = stream.read(size - len(buf))
        if not part:
            if not buf and eof_ok:
                return None
            raise ValueError("抓包文件被截断；请先停止抓包再导入")
        buf.extend(part)
    return bytes(buf)


def packets(stream):
    """Yield (timestamp, linktype, packet) from pcapng or classic pcap."""
    magic = read_exact(stream, 4, True)
    if magic is None:
        return
    pcap = {b'\xd4\xc3\xb2\xa1': ('<', 1e-6), b'\xa1\xb2\xc3\xd4': ('>', 1e-6),
            b'\x4d\x3c\xb2\xa1': ('<', 1e-9), b'\xa1\xb2\x3c\x4d': ('>', 1e-9)}
    if magic in pcap:
        endian, resolution = pcap[magic]
        header = read_exact(stream, 20)
        link = struct.unpack_from(endian + 'I', header, 16)[0] & 0xffff
        while True:
            header = read_exact(stream, 16, True)
            if header is None:
                return
            sec, frac, cap, orig = struct.unpack(endian + 'IIII', header)
            if cap > MAX_BLOCK:
                raise ValueError("抓包分组过大")
            yield sec + frac * resolution, link, read_exact(stream, cap)
    if magic != b'\x0a\x0d\x0d\x0a':
        raise ValueError("请选择 .pcapng 或 .pcap 文件（不是文本导出）")
    endian, interfaces = '<', []
    while magic is not None:
        length_bytes = read_exact(stream, 4)
        if magic == b'\x0a\x0d\x0d\x0a':
            bom = read_exact(stream, 4)
            if bom not in (b'\x4d\x3c\x2b\x1a', b'\x1a\x2b\x3c\x4d'):
                raise ValueError("pcapng 字节序无效")
            endian = '<' if bom[0] == 0x4d else '>'
            length = struct.unpack(endian + 'I', length_bytes)[0]
            if not 28 <= length <= MAX_BLOCK or length % 4:
                raise ValueError("pcapng 段头无效")
            rest = read_exact(stream, length - 12)
            interfaces = []
            if struct.unpack(endian + 'I', rest[-4:])[0] != length:
                raise ValueError("pcapng 块尾长度不匹配")
        else:
            length = struct.unpack(endian + 'I', length_bytes)[0]
            if not 12 <= length <= MAX_BLOCK or length % 4:
                raise ValueError("pcapng 块长度无效")
            rest = read_exact(stream, length - 8)
            if struct.unpack(endian + 'I', rest[-4:])[0] != length:
                raise ValueError("pcapng 块尾长度不匹配")
            body = rest[:-4]
            kind = struct.unpack(endian + 'I', magic)[0]
            if kind == 1:
                if len(body) < 8:
                    raise ValueError("pcapng 接口块不完整")
                link = struct.unpack_from(endian + 'H', body)[0]
                resolution, offset, pos = 1e-6, 0, 8
                while pos + 4 <= len(body):
                    code, size = struct.unpack_from(endian + 'HH', body, pos)
                    value = body[pos + 4:pos + 4 + size]
                    if len(value) != size:
                        raise ValueError("pcapng 接口选项被截断")
                    pos += 4 + (size + 3) // 4 * 4
                    if code == 0:
                        break
                    if code == 9 and value:
                        resolution = 2 ** -(value[0] & 127) if value[0] & 128 else 10 ** -value[0]
                    if code == 14 and size == 8:
                        offset = struct.unpack(endian + 'q', value)[0]
                interfaces.append((link, resolution, offset))
            elif kind == 6:
                if len(body) < 20:
                    raise ValueError("pcapng 分组头不完整")
                iid, hi, lo, cap, orig = struct.unpack_from(endian + 'IIIII', body)
                if iid >= len(interfaces) or cap > len(body) - 20:
                    raise ValueError("pcapng 分组接口或长度无效")
                link, resolution, offset = interfaces[iid]
                yield (hi << 32 | lo) * resolution + offset, link, body[20:20 + cap]
        magic = read_exact(stream, 4, True)


def tcp_packet(link, data):
    if link == 1:  # Ethernet, including VLAN tags
        if len(data) < 14:
            return None
        kind, pos = struct.unpack_from('!H', data, 12)[0], 14
        while kind in (0x8100, 0x88a8):
            if len(data) < pos + 4:
                return None
            kind = struct.unpack_from('!H', data, pos + 2)[0]
            pos += 4
        if kind not in (0x0800, 0x86dd):
            return None
        data = data[pos:]
    elif link in (0, 108):  # NULL/loopback
        data = data[4:]
    elif link == 113:
        data = data[16:]
    elif link == 276:
        data = data[20:]
    elif link not in (101, 228, 229):
        return None
    if not data:
        return None
    if data[0] >> 4 == 4:
        if len(data) < 20 or data[9] != 6:
            return None
        size, fragment = struct.unpack_from('!HH', data, 2)[0], struct.unpack_from('!H', data, 6)[0]
        ihl = (data[0] & 15) * 4
        if fragment & 0x3fff or ihl < 20 or not ihl <= size <= len(data):
            return None
        src, dst = str(ipaddress.ip_address(data[12:16])), str(ipaddress.ip_address(data[16:20]))
        seg = data[ihl:size]
    elif data[0] >> 4 == 6:
        if len(data) < 40 or data[6] != 6:  # extension headers not supported
            return None
        size = 40 + struct.unpack_from('!H', data, 4)[0]
        if size > len(data):
            return None
        src, dst = str(ipaddress.ip_address(data[8:24])), str(ipaddress.ip_address(data[24:40]))
        seg = data[40:size]
    else:
        return None
    if len(seg) < 20:
        return None
    sp, dp, seq = struct.unpack_from('!HHI', seg)
    off, flags = (seg[12] >> 4) * 4, seg[13]
    if not 20 <= off <= len(seg):
        return None
    return (src, sp, dst, dp), seq, flags, seg[off:]


class Framer:
    ANCHORS = {1, 3, 4, 0x5fc1, 0x6001, 0x6002, 0x6003, 0x6004, 0x8421, 0x1122, 0x1129, 0x1132, 0x1133, 0x1134, 0x2961, 0x8100}

    def __init__(self, emit, warn):
        self.buffer = bytearray()
        self.synced = False
        self.emit, self.warn = emit, warn
        self.discarded_bytes = 0

    @staticmethod
    def lineup_anchor(body, complete):
        # A different opcode may carry the same roster schema. Only a fully
        # validated two-team payload can establish this unknown-message boundary.
        if complete:
            try:
                decode_battle(body,{'heroes':{},'shell_effects':{},'shell_families':{},'matrix_effects':{}})
                return True
            except (ValueError,TypeError,KeyError,OverflowError):return False
        if len(body)<3:return True  # Retain a short prefix until the next read.
        if body[0]!=10:return False
        try:_,pos=varint(body,1)
        except ValueError:return len(body)<11
        return pos==len(body) or body[pos] in (18,26)

    def feed(self, data, timestamp):
        self.buffer.extend(data)
        pos = 0
        while len(self.buffer) - pos >= 12:
            seq, op, size = struct.unpack_from('<III', self.buffer, pos)
            valid = op > 0 and size <= MAX_BODY
            if not self.synced:
                if valid and op not in self.ANCHORS:
                    available=len(self.buffer)-pos-12
                    valid = 0<size<=128*1024 and self.lineup_anchor(
                        bytes(self.buffer[pos+12:pos+12+size]),available>=size)
                # Heartbeats have a zero sequence in all observed samples.
                if op in (1, 4):
                    valid = valid and seq == 0 and size == 0
                elif op == 3:
                    valid = valid and seq == 0 and size <= 16
            if not valid:
                self.synced = False
                pos += 1
                self.discarded_bytes += 1
                continue
            if len(self.buffer) - pos < 12 + size:
                break
            body = bytes(self.buffer[pos + 12:pos + 12 + size])
            if not self.synced:
                try:
                    fields(body)
                except ValueError:
                    pos += 1
                    self.discarded_bytes += 1
                    continue
            self.synced = True
            self.emit(op, body, timestamp)
            pos += 12 + size
        if pos:
            del self.buffer[:pos]
        if len(self.buffer) > MAX_BODY + 12:
            self.buffer.clear()
            self.synced = False
            self.warn("消息缓存超限，正在重新定位消息边界")


class TCPStream:
    def __init__(self, emit, warn):
        self.framer = Framer(emit, warn)
        self.warn = warn
        self.next_seq = None
        self.pending = []
        self.gap_since = None

    def feed(self, seq, flags, data, timestamp):
        if flags & 2:  # SYN consumes one sequence number
            seq = (seq + 1) & 0xffffffff
        if self.next_seq is None:
            self.next_seq = seq
        # Unwrap modulo 2^32 relative to the contiguous stream head.
        start = self.next_seq + ((seq - self.next_seq + (1 << 31)) % (1 << 32) - (1 << 31))
        if start < self.next_seq:
            data = data[self.next_seq - start:]
            start = self.next_seq
        if data:
            self.pending.append((start, data))
        self.pending.sort(key=lambda item: item[0])
        if self.pending and self.pending[0][0] > self.next_seq:
            if self.gap_since is None:
                self.gap_since = timestamp
            if timestamp - self.gap_since > 10 or sum(len(d) for _, d in self.pending) > MAX_BODY:
                self.warn("TCP 数据有缺口，已跳过缺口；本场数据可能不完整")
                self.next_seq = self.pending[0][0]
                self.framer = Framer(self.framer.emit, self.warn)
                self.gap_since = None
        while self.pending and self.pending[0][0] <= self.next_seq:
            start, payload = self.pending.pop(0)
            payload = payload[max(0, self.next_seq - start):]
            if payload:
                self.next_seq += len(payload)
                self.framer.feed(payload, timestamp)
        if not self.pending:
            self.gap_since = None


def load_mappings(path=None):
    return json.loads(Path(path or Path(__file__).with_name('mappings.json')).read_text(encoding='utf-8'))


def shell_config_name(mappings, config):
    if not config:
        return '待接收'
    exact = mappings['shell_configs'].get(str(config))
    if exact:
        return exact
    family = mappings.get('shell_families', {}).get(str(config // 10))
    return family['name'] + ' [同类推定]' if family else f'智壳 #{config}'


def matrix_name(mappings, identifier):
    exact = mappings['matrices'].get(str(identifier))
    if exact:
        confidence = mappings.get('matrix_confidence', {}).get(str(identifier), '')
        return exact + (' [顺序推定]' if confidence else '')
    candidates = mappings.get('matrix_name_candidates', {}).get(str(identifier))
    if candidates:
        return f'矩阵 #{identifier}（待区分：' + '/'.join(candidates) + '）'
    return f'矩阵 #{identifier}'


def shell_effect_mapping(mappings, effect):
    exact = mappings['shell_effects'].get(str(effect))
    if exact:
        return exact
    if 38_000_000 <= effect < 40_000_000:
        family, variant = divmod(effect - 33_554_432, 1000)
        label = mappings.get('shell_families', {}).get(str(family))
        if label and 101 <= variant <= 109:
            return {'name': label['name'], 'family_id': family, 'confidence': '编号规律推定'}
    return None


def mapped_imprints(effects, mappings):
    found=[]
    for effect in dict.fromkeys(effects):
        item=mappings.get('imprint_effects',{}).get(str(effect))
        if item:found.append(dict(item,effect_id=effect))
    return found


def decode_battle(body, mappings):
    outer = record(body)
    inner = outer.get(1)
    if not isinstance(inner, bytes):
        raise ValueError("对局缺少阵容字段")
    battle=decode_roster(inner,mappings)
    candidates=[]
    for prefix,payload,excluded in [('outer',body,{1}),('roster',inner,{2,3})]:
        for field,wire,value in fields(payload):
            if wire==0 and field<=32 and type(value) is int and 0<=value<=255 and field not in excluded:
                item={'opcode':'0x6003','path':f'{prefix}.{field}','value':value}
                if item not in candidates:candidates.append(item)
    battle.update(source_opcode='0x6003',mode_candidates=candidates,
                  protocol_shape=[{'field':f,'wire':w,'size':len(v) if isinstance(v,bytes) else None} for f,w,v in fields(body)])
    battle['mode_detection']=mode_info(battle,mappings)
    return battle


def decode_roster(inner, mappings):
    teams = {'A': [], 'B': []}
    keys = {1: 'hp', 5: 'attack', 9: 'defense', 13: 'speed'}
    for group, wire, unit in fields(inner):
        if group not in (2, 3) or wire != 2:
            continue
        f = record(unit)
        hero = f.get(1)
        if not isinstance(hero, int) or not hero:
            raise ValueError("角色编号无效")
        attrs = packed(f.get(4, b''))
        stats, percents = {}, {}
        for raw in attrs:
            tag = raw & 255
            if tag in keys:
                stats[keys[tag]] = (raw >> 8) / 100
            if tag in (17, 20, 23, 26):
                percents[{17: 'crit', 20: 'crit_damage', 23: 'effect_hit', 26: 'effect_resist'}[tag]] = (raw >> 8) / 10
        if set(stats) != set(keys.values()) or any(not 0 <= v < 1e9 for v in stats.values()):
            raise ValueError("基础属性结构与已知样本不符")
        effects = packed(f.get(6, b''))
        shells = []
        for effect in effects:
            item = shell_effect_mapping(mappings, effect)
            if item and item not in shells:
                shells.append(item)
        candidates = []
        for effect in effects:
            item = mappings['matrix_effects'].get(str(effect))
            if item:
                candidates.append(dict(item, effect_id=effect))
        teams['A' if group == 2 else 'B'].append({
            'hero_id': hero, 'hero_name': mappings['heroes'].get(str(hero), f'角色 #{hero}'),
            'slot': f.get(2), 'stats': stats, 'percent_attributes_tentative': percents,
            'attributes_raw': attrs,
            'extra_attributes': decode_extra_attributes(attrs),
            'shells': shells, 'matrix_effects_candidates': candidates,
            'imprints': mapped_imprints(effects,mappings),
            'effects_raw': effects, 'unknown_shell_effects': [e for e in effects if 38_000_000 <= e < 40_000_000 and not shell_effect_mapping(mappings,e)],
            'matrix_loadout_complete': False,
        })
    if not teams['A'] or not teams['B']:
        raise ValueError("对局缺少一方阵容")
    return {'teams': teams, 'status': '对局数据已到达', 'schema': 'etheria-observed-v0.1'}


def decode_replay(body, mappings):
    """Observed 0x8421 envelope: field 2 -> field 2 -> the usual roster.

    Only the observed nickname path is copied; account metadata is excluded.
    Extra fields are retained as uninterpreted values, never a winner or log.
    """
    envelopes=[v for f,w,v in fields(body) if f==2 and w==2]
    if len(envelopes)!=1:raise ValueError('回放缺少唯一的数据封装')
    payload=fields(envelopes[0])
    rosters=[v for f,w,v in payload if f==2 and w==2]
    if len(rosters)!=1:raise ValueError('回放缺少唯一的阵容字段')
    battle=decode_roster(rosters[0],mappings)
    extras=[{'field':f,'wire':w,'value':v.hex() if isinstance(v,bytes) else v}
            for f,w,v in payload if f in (3,4,5)]
    # Allowlist only the observed nickname path; never copy player/account blobs.
    names=[]
    try:
        for field,wire,header in payload:
            if field!=1 or wire!=2:continue
            for f,w,participant in fields(header):
                if f!=8 or w!=2:continue
                profiles=[v for f,w,v in fields(participant) if f==1 and w==2]
                for profile in profiles:
                    for f,w,value in fields(profile):
                        if f==3 and w==2 and len(value)<=256:
                            name=value.decode('utf-8')
                            if 1<=len(name)<=64 and all(c.isprintable() for c in name) and name not in names:names.append(name)
    except (ValueError,UnicodeDecodeError):
        pass
    battle.update(participants=[{'nickname':name,'team':None,'source_path':'2.1.8.1.3'} for name in names[:2]],
                  participant_status='昵称已读取；对应A/B关系待对照' if names else '昵称未读取',
                  capture_context='replay',source_opcode='0x8421',
                  status='回放阵容已读取 · 不计本人战绩 · 胜负与回合过程未确认',
                  replay_evidence={'roster_path':'2.2','extra_fields_raw':extras,
                                   'semantics':'额外字段保留原值；未确认动作、随机种子或胜负含义'},
                  payload_fingerprint=hashlib.sha256(envelopes[0]).hexdigest())
    return battle


class Inventory:
    """Only local equipment information, never used as an opponent loadout."""
    def __init__(self, mappings):
        self.mappings = mappings
        self.heroes, self.shells, self.gear = {}, {}, {}
        self.components, self.component_groups = {}, {}
        self.components_observed = False
        self.components_capture_time = None
        self.initial_sub_counts = {}

    def restore(self, snapshot):
        """Restore a saved inventory selected for the current capture time."""
        def pack(values):
            out = bytearray()
            for value in values:
                while value >= 128:
                    out.append((value & 127) | 128); value >>= 7
                out.append(value)
            return bytes(out)
        def matrices(values):
            return pack([(m['points'] << 16) | m['id'] for m in values
                         if isinstance(m.get('id'), int) and isinstance(m.get('points'), int)])
        if 'components' in snapshot:
            self.components_observed=True
            self.components_capture_time=snapshot.get('components_capture_time',snapshot.get('capture_time'))
            self.components={r['uid']:dict(r,attributes_raw=list(r.get('attributes_raw',[]))) for r in snapshot['components']}
            self.component_groups={r['id_raw']:dict(r,component_uids_raw=list(r.get('component_uids_raw',[]))) for r in snapshot.get('component_groups',[])}
        for g in snapshot.get('gear', []):
            item = {1:g['uid'], 4:pack(g.get('attributes_raw', []))}
            for field, key in [(2,'config_id'), (3,'level'), (6,'flag_raw')]:
                if isinstance(g.get(key), int): item[field] = g[key]
            matrix = g.get('matrix') or {}
            if isinstance(matrix.get('id'), int) and isinstance(matrix.get('points'), int):
                item[5] = (matrix['points'] << 16) | matrix['id']
            self.gear[g['uid']] = item
            if g.get('initial_sub_count') is not None:
                self.initial_sub_counts[g['uid']] = g['initial_sub_count']
        for s in snapshot.get('shells', []):
            item = {1:s['uid'], 8:matrices(s.get('matrices', [])), 9:pack(s.get('passives_raw', []))}
            for field, key in [(2,'config_id'), (4,'level'), (6,'awakened_config_id')]:
                if isinstance(s.get(key), int): item[field] = s[key]
            self.shells[s['uid']] = item
        for h in snapshot.get('heroes', []):
            item = {1:h['base_id'], 10:pack(h.get('normal_gear_uids', [])), 12:pack(h.get('arena_gear_uids', []))}
            for field,key in [(9,'hero_id'), (7,'normal_shell_uid'), (11,'arena_shell_uid')]:
                if isinstance(h.get(key), int): item[field] = h[key]
            self.heroes[h['base_id']] = item

    def update(self, op, body):
        if op == 0x2961:
            components,groups={},{}
            for f,w,data in fields(body):
                if f not in (1,2) or w!=2:continue
                item=record(data);uid=item.get(1)
                if not isinstance(uid,int) or uid<=0:raise ValueError('元件记录缺少有效编号')
                if f==2:
                    if not isinstance(item.get(2),int) or not isinstance(item.get(5),bytes):
                        raise ValueError('元件结构与登录样本不符')
                    if uid in components:raise ValueError('元件编号重复')
                    components[uid]={'uid':uid,'config_id_raw':item[2],'field3_raw':item.get(3),
                                     'attributes_raw':packed(item[5]),'field6_raw':item.get(6)}
                else:
                    if not isinstance(item.get(3),bytes):raise ValueError('元件装配结构与登录样本不符')
                    if uid in groups:raise ValueError('元件装配分组重复')
                    groups[uid]={'id_raw':uid,'field2_raw':item.get(2),'component_uids_raw':packed(item[3])}
            if not groups and not components:raise ValueError('未收到元件快照结构，保留已有记录')
            # This is the observed login snapshot, not an inferred incremental patch.
            self.components,self.component_groups=components,groups
            self.components_observed=True
            self.components_capture_time=None
            return
        if op == 0x1134:
            response = record(body)
            level = response.get(2)
            if response.get(1, 0) != 0 or not isinstance(level, int) or not 0 <= level <= 15:
                return
            for uid in packed(response.get(3, b'')):
                if uid > 0:
                    self.gear.setdefault(uid, {1:uid})[3] = level
            return
        target, number = {0x1122: (self.heroes, 2), 0x1129: (self.shells, 1),
                          0x1133: (self.gear, 1), 0x1132: (self.gear, 3)}[op]
        for f, w, data in fields(body):
            if f == number and w == 2:
                item = record(data)
                if isinstance(item.get(1), int) and item[1] > 0:
                    uid = item[1]
                    if op == 0x1132:
                        # Omitted fields mean unchanged; explicit zero must be retained.
                        target.setdefault(uid, {1:uid}).update(item)
                    else:
                        target[uid] = item
                    if target is self.gear and item.get(3) == 0 and isinstance(item.get(4), bytes):
                        self.initial_sub_counts[uid] = max(0, len(packed(item[4])) - 1)

    def rows(self):
        out = []
        for hero in self.heroes.values():
            for mode, shell_field, gear_field in [('普通', 7, 10), ('竞技候选', 11, 12)]:
                sid = hero.get(shell_field)
                gids = packed(hero.get(gear_field, b''))
                if not sid and not gids:
                    continue
                shell = self.shells.get(sid, {})
                contributions = packed(shell.get(8, b''))
                missing = sum(gid not in self.gear for gid in gids)
                contributions += [self.gear[g][5] for g in gids if g in self.gear and isinstance(self.gear[g].get(5), int)]
                counts = collections.Counter()
                for v in contributions:
                    counts[v & 65535] += v >> 16
                hero_id = hero.get(9) or hero[1]
                config = shell.get(2)
                out.append({'hero_id': hero_id, 'hero_name': self.mappings['heroes'].get(str(hero_id), f'角色 #{hero_id}'),
                            'mode': mode, 'shell_config_id': config,
                            'shell_name': shell_config_name(self.mappings, config),
                            'matrices': [{'id': mid, 'name': matrix_name(self.mappings, mid), 'points': points} for mid, points in sorted(counts.items())],
                            'incomplete': bool(missing or (sid and not shell))})
        return out

    def snapshot(self, timestamp, observed):
        """Selected local inventory fields; raw attributes stay uninterpreted."""
        def matrix(value):
            return {'id': value & 65535, 'points': value >> 16} if isinstance(value, int) else {'id':None, 'points':None}
        gear = [{'uid': uid, 'config_id': r.get(2), 'level': r.get(3),
                 'attributes_raw': packed(r.get(4, b'')),
                 'matrix': matrix(r.get(5)), 'flag_raw': r.get(6),
                 **({'initial_sub_count':self.initial_sub_counts[uid]} if uid in self.initial_sub_counts else {})}
                for uid, r in sorted(self.gear.items())]
        shells = [{'uid': uid, 'config_id': r.get(2), 'level': r.get(4),
                   'awakened_config_id': r.get(6),
                   'matrices': [matrix(x) for x in packed(r.get(8, b''))],
                   'passives_raw': packed(r.get(9, b''))}
                  for uid, r in sorted(self.shells.items())]
        heroes = [{'base_id': uid, 'hero_id': r.get(9) or uid,
                   'normal_shell_uid': r.get(7), 'arena_shell_uid': r.get(11),
                   'normal_gear_uids': packed(r.get(10, b'')),
                   'arena_gear_uids': packed(r.get(12, b''))}
                  for uid, r in sorted(self.heroes.items())]
        extra={}
        if self.components_observed:
            extra={'components':[dict(v,attributes_raw=list(v['attributes_raw'])) for k,v in sorted(self.components.items())],
                   'component_groups':[dict(v,component_uids_raw=list(v['component_uids_raw'])) for k,v in sorted(self.component_groups.items())],
                   'components_capture_time':self.components_capture_time if self.components_capture_time is not None else timestamp,
                   'component_status':'0x2961登录快照；属性、专属与锁定按已对照样本投影，未知编号保留原值，未接入实时变更'}
        return {'schema': 'etheria-local-inventory-v1', 'capture_time': timestamp,
                'observed_opcodes': sorted(observed), 'heroes': heroes,
                'shells': shells, 'gear': gear, 'loadout_rows': self.rows(),
                **extra,
                'notes': ['仅本地已观测库存，不保证完整或最新；会沿用时间允许的已保存资料。',
                          '原始属性保留，界面按已对照规则解码；未知属性不猜测。']}


class Engine:
    def __init__(self, emit, port=20001, mappings=None, capture_context='live'):
        self.emit, self.port = emit, port
        self.mappings = mappings or load_mappings()
        self.flows = collections.OrderedDict()
        self.counts = collections.Counter()
        self.inventory = Inventory(self.mappings)
        self.latest = None
        self.last_warning = None
        self.inventory_observed = set()
        self.actor_aliases = {}
        self.active_battle = False
        self.capture_context = 'replay' if capture_context=='replay' else 'live'
        self.sessions = collections.OrderedDict()
        self.connection_serial = 0
        self.flow_connections = {}
        self.opcodes, self.unknown_opcodes = collections.Counter(), collections.Counter()
        self.candidates = []
        self.replay_records = collections.OrderedDict()
        self.last_timestamp = None

    def session(self, connection):
        if connection not in self.sessions:
            self.sessions[connection] = BattleSession(connection,self.capture_context,self.session_event)
            while len(self.sessions)>64:
                _,old = self.sessions.popitem(last=False)
                old.finish(self.last_timestamp,'连接记录超限，已结束旧会话')
        return self.sessions[connection]

    def session_event(self, kind, data):
        if kind=='battle':
            self.latest = data
            self.active_battle = data['tracking']['association_eligible']
        self.emit(kind,data)

    def replay_message(self, body, timestamp, connection):
        battle=decode_replay(body,self.mappings)
        fingerprint=battle['payload_fingerprint']
        self.counts['replay_messages']+=1
        if fingerprint in self.replay_records:
            self.counts['duplicate_replays']+=1
            battle=self.replay_records[fingerprint]
            self.replay_records.move_to_end(fingerprint)
        else:
            battle.update(capture_time=timestamp,connection_id=connection)
            battle['record_id']=battle_identity(battle)
            battle['tracking']={'state':'replay_loaded','reason':'0x8421 回放响应，已解析双方阵容',
                                'connection_id':connection,'capture_context':'replay',
                                'roster_received':True,'settlement_received':False,'result_code':None,
                                'updated_at':timestamp,'association_eligible':False,'protocol_match_id':None}
            self.replay_records[fingerprint]=battle
            while len(self.replay_records)>64:self.replay_records.popitem(last=False)
            self.counts['replays']+=1
        # A replay response never replaces a live session's settlement target.
        self.session_event('battle',battle)

    def diagnostics(self):
        return {'schema':'etheria-capture-diagnostics-v1','capture_context':self.capture_context,
                'configured_port':self.port,'counts':dict(self.counts),
                'inbound_opcodes':{hex(k):v for k,v in self.opcodes.items()},
                'unhandled_opcodes':{hex(k):v for k,v in self.unknown_opcodes.items()},
                'latest_record_id':(self.latest or {}).get('record_id'),
                'latest_tracking':self.latest.get('tracking') if self.latest else None,
                'mode_detection':mode_info(self.latest or {},self.mappings),
                'mode_candidates':(self.latest or {}).get('mode_candidates',[]),
                'protocol_shape':(self.latest or {}).get('protocol_shape',[]),
                'identity':{'status':'A/B为协议方向，己方由本场确认或本地完整阵容指纹识别',
                            'nickname_count':len((self.latest or {}).get('participants',[])),
                            'nickname_side_status':(self.latest or {}).get('participant_status','当前消息未提供已确认昵称路径')},
                'draft_messages':self.counts.get('draft_messages',0),
                'lineup_candidates':self.candidates,
                'notes':['只统计指定TCP端口的游戏下行消息；端口改变、UDP或其他封装不在已知解析范围。',
                         '未知消息仅统计编号和数量，不导出原始载荷、IP、MAC或账号凭据。',
                         '未收到已知开场不等于服务器没有下发阵容；候选阵容不计入战绩。']}

    def finish_capture(self, reason='采集结束，尚未收到结算'):
        for session in list(self.sessions.values()):session.finish(self.last_timestamp,reason)
        self.emit('diagnostics',self.diagnostics())

    def draft_observation(self, body, timestamp):
        r = record(body)
        def alias(identifier):
            if not isinstance(identifier, int):
                return None
            return self.actor_aliases.setdefault(identifier, f'参与者{len(self.actor_aliases)+1}')
        heroes = []
        for f, w, value in fields(body):
            if f == 9 and w == 2:
                unit = record(value)
                if isinstance(unit.get(1), int):
                    heroes.append({'hero_id': unit[1], 'shell_config_id': unit.get(4)})
        return {'schema': 'etheria-draft-observation-v1', 'kind': 'draft',
                'capture_time': timestamp, 'phase_raw': r.get(1), 'step_raw': r.get(8),
                'flag_raw': r.get(5), 'server_time': r.get(6),
                'observer_alias': alias(r.get(2)), 'actor_alias': alias(r.get(4)),
                'heroes': heroes, 'semantic_status': '预选、确认及禁用含义待验证；未关联具体对局'}

    def warn(self, message):
        self.counts['warnings'] += 1
        if message != self.last_warning:
            self.last_warning = message
            self.emit('warning', message)

    def message(self, op, body, timestamp, connection='direct'):
        self.counts['messages'] += 1
        self.last_timestamp = timestamp
        if op in self.opcodes or len(self.opcodes)<512:self.opcodes[op] += 1
        try:
            if op == 0x6003:
                session = self.session(connection)
                battle = decode_battle(body, self.mappings)
                if session.start(battle,body,timestamp):self.counts['battles'] += 1
                else:self.counts['duplicate_openings'] += 1
            elif op == 0x8421:
                self.replay_message(body,timestamp,connection)
            elif op in (0x1122, 0x1129, 0x1132, 0x1133, 0x1134, 0x2961):
                self.inventory.update(op, body)
                if op==0x2961:self.inventory.components_capture_time=timestamp
                self.emit('inventory', self.inventory.rows())
                self.inventory_observed.add(op)
                self.emit('inventory_snapshot', self.inventory.snapshot(timestamp, self.inventory_observed))
            elif op == 0x5fc1:
                self.counts['draft_messages']+=1
                self.emit('observation', self.draft_observation(body, timestamp))
            elif op in (0x6001, 0x6002):
                self.session(connection).boundary(timestamp)
            elif op == 0x6004:
                association = self.session(connection).settle(record(body).get(1),body,timestamp)
                self.counts['settlements'] += 1
                self.counts[association+'_settlements'] += 1
            elif op not in (1,3,4):
                if op in self.unknown_opcodes or len(self.unknown_opcodes)<512:self.unknown_opcodes[op] += 1
                if len(self.candidates)<8 and len(body)<=128*1024:
                    try:
                        candidate = decode_battle(body,self.mappings)
                    except (ValueError,TypeError,KeyError,OverflowError):
                        candidate = None
                    if candidate is not None:
                        item = {'capture_time':timestamp,'opcode':hex(op),'connection_id':connection,
                                'teams':candidate['teams'],'status':'结构符合开场，但消息含义未确认；不计入战绩'}
                        self.candidates.append(item)
                        self.emit('observation',{'kind':'lineup_candidate',**item})
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            if op==0x6003:
                self.counts['invalid_openings'] += 1
                self.session(connection).invalidate(timestamp,'收到新开场但解析失败，停止关联旧场结算')
            elif op==0x8421:
                self.counts['invalid_replays']+=1
            self.warn(f'消息 {op:#x} 未能解析：{exc}')

    def packet(self, timestamp, link, data):
        self.counts['packets'] += 1
        packet = tcp_packet(link, data)
        if packet is None:
            return
        key, seq, flags, payload = packet
        if key[3]==self.port and payload:self.counts['outbound_payload_packets'] += 1
        if key[1] != self.port:
            return
        self.last_timestamp = timestamp
        self.counts['game_packets'] += 1
        if key not in self.flows or flags & 2:
            if key in self.flow_connections:
                self.session(self.flow_connections[key]).finish(timestamp,'连接重新建立，旧会话未闭合')
            self.connection_serial += 1
            connection = f'连接{self.connection_serial}'
            self.flow_connections[key] = connection
            self.flows[key] = TCPStream(lambda op,body,t,c=connection:self.message(op,body,t,c),
                                       lambda message,c=connection:(self.session(c).invalidate(self.last_timestamp,'TCP数据缺口影响本场完整性'),self.warn(message)))
        self.flows.move_to_end(key)
        while len(self.flows) > 64:
            oldkey,_ = self.flows.popitem(last=False)
            oldconnection = self.flow_connections.pop(oldkey,None)
            if oldconnection in self.sessions:self.sessions[oldconnection].finish(timestamp,'连接缓存超限')
        framer=self.flows[key].framer; discarded=framer.discarded_bytes
        self.flows[key].feed(seq, flags, payload, timestamp)
        current=self.flows[key].framer
        self.counts['framing_discarded_bytes'] += current.discarded_bytes-discarded if current is framer else current.discarded_bytes
        if flags & 5:  # FIN/RST
            self.session(self.flow_connections[key]).finish(timestamp,'连接关闭，尚未收到本场结算')
            self.flows.pop(key, None)
            self.flow_connections.pop(key,None)

    def read(self, stream, stop=None):
        last_update = 0
        for timestamp, link, data in packets(stream):
            if stop and stop.is_set():
                break
            self.packet(timestamp, link, data)
            now = time.monotonic()
            if now - last_update > 0.5:
                self.emit('counts', dict(self.counts))
                self.emit('diagnostics',self.diagnostics())
                last_update = now
        if not stop or not stop.is_set():
            if any(flow.pending or flow.framer.buffer for flow in self.flows.values()):
                self.warn('抓包结尾有未完成的 TCP 数据或消息；已解析的完整消息保留')
        self.emit('counts', dict(self.counts))
        self.finish_capture('采集已停止，尚未收到结算' if stop and stop.is_set() else '文件结束，尚未收到结算')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='伊瑟抓包离线检查，仅输出已筛选的对局/装备信息')
    parser.add_argument('capture')
    parser.add_argument('--port', type=int, default=20001)
    parser.add_argument('--output', help='将已解析结果写入 JSON')
    args = parser.parse_args()
    events = []
    engine = Engine(lambda kind, data: events.append(data) if kind == 'warning' else None, args.port)
    with open(args.capture, 'rb') as stream:
        engine.read(stream)
    result = {'counts': dict(engine.counts), 'warnings': events, 'battle': engine.latest,
              'local_inventory': engine.inventory.rows()}
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(content, encoding='utf-8')
        print(args.output)
    else:
        print(content)
