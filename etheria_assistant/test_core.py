"""Synthetic protocol tests. No original traffic or account data included."""
import io
import struct
import unittest

from core import Engine, TCPStream, Framer, decode_battle, load_mappings, packets


def vi(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def scalar(field, value):
    return vi(field << 3) + vi(value)


def blob(field, value):
    return vi(field << 3 | 2) + vi(len(value)) + value


def battle_body():
    attrs = b''.join(vi(int(v * 100) << 8 | k) for k, v in [(1, 28696), (5, 4753), (9, 1883), (13, 291)])
    unit = scalar(1, 30153) + blob(4, attrs) + blob(6, b''.join(map(vi, [38997533, 1171, 1341])))
    return blob(1, blob(2, unit) + blob(3, unit))


def frame(op, body=b'', seq=0):
    return struct.pack('<III', seq, op, len(body)) + body


def tcp(payload, seq=100, flags=0x18):
    ip = bytes.fromhex('4500') + struct.pack('!H', 40 + len(payload)) + b'\0' * 4 + b'\x40\x06\0\0' + bytes([10, 0, 0, 1, 10, 0, 0, 2])
    seg = struct.pack('!HHII', 20001, 50000, seq, 0) + bytes([0x50, flags]) + b'\0' * 6 + payload
    return b'\0' * 12 + b'\x08\x00' + ip + seg


def block(kind, body, endian='<'):
    body += b'\0' * (-len(body) % 4)
    size = len(body) + 12
    return struct.pack(endian + 'II', kind, size) + body + struct.pack(endian + 'I', size)


def pcapng(packet, endian='<'):
    section = block(0x0a0d0d0a, struct.pack(endian + 'IHHq', 0x1a2b3c4d, 1, 0, -1), endian)
    iface = block(1, struct.pack(endian + 'HHI', 1, 0, 65535), endian)
    epb = block(6, struct.pack(endian + 'IIIII', 0, 0, 2000000, len(packet), len(packet)) + packet, endian)
    return section + iface + epb


class SlowReader(io.BytesIO):
    def read(self, size=-1):
        return super().read(min(size, 3))


class ProtocolTests(unittest.TestCase):
    def test_battle_values_and_honest_matrix_status(self):
        b = decode_battle(battle_body(), load_mappings())
        unit = b['teams']['A'][0]
        self.assertEqual(unit['stats'], dict(hp=28696, attack=4753, defense=1883, speed=291))
        self.assertEqual(unit['shells'][0]['name'], '伯爵')
        self.assertEqual(len(unit['matrix_effects_candidates']), 2)
        self.assertFalse(unit['matrix_loadout_complete'])

    def test_tcp_reorder_duplicates_segmentation_and_wraparound(self):
        out, warnings = [], []
        stream = TCPStream(lambda *args: out.append(args), warnings.append)
        payload = frame(1) + frame(0x6003, battle_body()) + frame(4)
        base = 0xfffffff0
        stream.feed(base, 0, payload[:18], 1)
        stream.feed((base + 40) & 0xffffffff, 0, payload[40:], 2)
        stream.feed((base + 40) & 0xffffffff, 0, payload[40:], 2.1)
        stream.feed((base + 18) & 0xffffffff, 0, payload[18:40], 3)
        stream.feed(base, 0, payload[:18], 4)
        self.assertEqual([x[0] for x in out], [1, 0x6003, 4])
        self.assertFalse(warnings)
        self.assertFalse(stream.pending)

    def test_stream_gap_warns_and_resynchronizes(self):
        out, warnings = [], []
        stream = TCPStream(lambda *args: out.append(args), warnings.append)
        stream.feed(100, 0, frame(1), 1)
        stream.feed(200, 0, frame(4), 2)
        stream.feed(212, 0, frame(0x6003, battle_body()), 13)
        self.assertTrue(warnings)
        self.assertEqual([x[0] for x in out], [1, 4, 0x6003])

    def test_attach_midstream_and_large_opcode(self):
        out = []
        framer = Framer(lambda *args: out.append(args), lambda x: None)
        framer.feed(b'junk\xff\xfe' + frame(1) + frame(0x101023, scalar(1, 300)) + frame(0x6003, battle_body()), 1)
        self.assertEqual([x[0] for x in out], [1, 0x101023, 0x6003])

    def test_pcapng_endian_sections_and_short_pipe_reads(self):
        packet = tcp(frame(0x6003, battle_body()))
        data = pcapng(packet) + pcapng(packet, '>')
        decoded = list(packets(SlowReader(data)))
        self.assertEqual(len(decoded), 2)
        self.assertEqual(decoded[0], (2.0, 1, packet))
        self.assertEqual(decoded[1], decoded[0])

    def test_classic_pcap(self):
        packet = tcp(frame(0x6003, battle_body()))
        data = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
        data += struct.pack('<IIII', 2, 100, len(packet), len(packet)) + packet
        self.assertEqual(len(list(packets(io.BytesIO(data)))), 1)

    def test_engine_and_no_battle_without_init(self):
        events = []
        engine = Engine(lambda *x: events.append(x))
        engine.read(io.BytesIO(pcapng(tcp(frame(1)))))
        self.assertIsNone(engine.latest)
        engine.packet(3, 1, tcp(frame(0x6003, battle_body()), 112))
        self.assertEqual(engine.counts['battles'], 1)

    def test_truncated_file_and_malformed_battle(self):
        with self.assertRaises(ValueError):
            list(packets(io.BytesIO(pcapng(tcp(frame(1)))[:-1])))
        with self.assertRaises(ValueError):
            decode_battle(blob(1, b''), load_mappings())


if __name__ == '__main__':
    unittest.main()
