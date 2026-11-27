"""The song bank r2k5sngs.dat ("ps2_DTPK", Sega SNDF driver v2.15g):
songs, sequences, MIDI export and sample export."""
import array
import struct
import sys


def u16(d, o): return struct.unpack_from('<H', d, o)[0]
def s16(d, o): return struct.unpack_from('<h', d, o)[0]
def u32(d, o): return struct.unpack_from('<I', d, o)[0]


# ----------------------------------------------------------------------------
# PS-ADPCM (SPU2 sample format)
# ----------------------------------------------------------------------------
ADPCM_COEF = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]


def decode_psadpcm(buf):
    """-> (array('h') of samples, loop start or None, loop end or None)."""
    out = array.array('h')
    s1 = s2 = 0
    loop_start = None
    loop_end = None
    for f in range(len(buf) // 16):
        b = buf[f * 16:(f + 1) * 16]
        shift = b[0] & 0xf
        filt = (b[0] >> 4) & 0xf
        flags = b[1]
        if filt > 4:
            filt = 0
        if shift > 12:
            shift = 9
        c0, c1 = ADPCM_COEF[filt]
        if flags & 4 and loop_start is None:
            loop_start = f * 28
        for i in range(14):
            byte = b[2 + i]
            for nib in (byte & 0xf, byte >> 4):
                v = nib << 12
                if v & 0x8000:
                    v -= 0x10000
                v = (v >> shift) + ((s1 * c0 + s2 * c1 + 32) >> 6)
                if v > 32767:
                    v = 32767
                elif v < -32768:
                    v = -32768
                out.append(v)
                s2, s1 = s1, v
        if flags & 1:
            if flags & 2:
                loop_end = (f + 1) * 28
            break
    if loop_end is None:
        loop_start = None
    elif loop_start is None:
        loop_start = 0
    return out, loop_start, loop_end


# ----------------------------------------------------------------------------
# Bank
# ----------------------------------------------------------------------------
class Bank:
    """Header fields: 0x10 header size, 0x18 sample data size, 0x1C sample
    data offset, 0x98 program table, 0xA4 song scripts, 0xB8 sample table.
    Table counts are stored as the highest index (count - 1)."""

    def __init__(self, data):
        d = self.d = bytes(data)
        if d[:8] != b'ps2_DTPK':
            raise ValueError('not a ps2_DTPK sound bank')
        self.smp_base = u32(d, 0x1c)
        self.prog_tbl = u32(d, 0x98)
        self.script_tbl = u32(d, 0xa4)
        self.smp_tbl = u32(d, 0xb8)
        self._parse_programs()
        self._parse_songs()

    def sample_count(self):
        return u32(self.d, self.smp_tbl) + 1

    def sample(self, i):
        """-> dict(pcm, rate, loop_start, loop_end) for sample i."""
        off, _, _flag, rate, size = struct.unpack_from('<IIHHI', self.d, self.smp_tbl + 4 + 16 * i)
        raw = self.d[self.smp_base + off:self.smp_base + off + size]
        pcm, ls, le = decode_psadpcm(raw)
        return dict(pcm=pcm, rate=rate, loop_start=ls, loop_end=le)

    def _parse_programs(self):
        """Program i+1 belongs to song i: channel -> tone number."""
        d = self.d
        P = self.prog_tbl
        self.programs = []
        for i in range(u16(d, P) + 1):
            p = P + u16(d, P + 2 + 2 * i)
            prog = {}
            for k in range(d[p] + 1):
                q = p + 8 + 16 * k
                prog[d[q + 1]] = d[q + 3]
            self.programs.append(prog)

    def _parse_songs(self):
        """Song script: three header words (the third holds the song number),
        then sequence pointers relative to the script; a word with top byte
        0x90 jumps back to byte offset (low 16 bits) - the loop -, a pointer
        with top byte 0x91 is the last sequence of a song that plays once."""
        d = self.d
        S = self.script_tbl
        self.songs = []
        for i in range(u32(d, S + 8) + 1):
            e = S + u32(d, S + 0xc + 4 * i)
            words = []
            for k in range(17):
                w = u32(d, e + 4 * k)
                words.append(w)
                if k >= 3 and (w >> 24) in (0x90, 0x91):
                    break
            seqs = []
            loop_to = None
            for w in words[3:]:
                top = w >> 24
                if top == 0x90:
                    loop_to = (w & 0xffff) // 4
                    break
                seqs.append(e + (w & 0xffffff))
                if top == 0x91:
                    break
            self.songs.append(dict(index=i, seqs=seqs,
                                   loop_seq=(loop_to - 3) if loop_to is not None else None,
                                   program=(words[2] & 0xff) + 1))


# ----------------------------------------------------------------------------
# Sequences
# ----------------------------------------------------------------------------
DATA_BYTES = {0x80: 1, 0x90: 2, 0xa0: 2, 0xb0: 2, 0xc0: 1, 0xd0: 1, 0xe0: 1}


def parse_seq(d, p):
    """SNDF sequence: MIDI-like with running status. The last data byte has
    bit 7 set when no delta time follows (delta 0); otherwise a MIDI varlen
    delta in milliseconds follows. Note-off (8x) carries only the key, pitch
    bend (Ex) a single 7-bit value. FF 2F 00 ends the track.
    -> (events [(ms, status, data)], length ms)"""
    ev = []
    t = 0
    st = None
    while True:
        b = d[p]
        if b >= 0x80:
            st = b
            p += 1
        if st == 0xff:
            typ, ln = d[p], d[p + 1]
            p += 2 + ln
            if typ == 0x2f:
                break
            continue
        nb = DATA_BYTES[st & 0xf0]
        data = list(d[p:p + nb])
        p += nb
        last = data[-1]
        data[-1] &= 0x7f
        ev.append((t, st, data))
        if not last & 0x80:
            v = 0
            while True:
                c = d[p]
                p += 1
                v = (v << 7) | (c & 0x7f)
                if not c & 0x80:
                    break
            t += v
    return ev, t


def song_timeline(bank, song):
    """-> (intro ms, loop ms or None, [(events, length ms)] without the
    250 ms silent pre-roll sequence that looping songs start with)."""
    parsed = [parse_seq(bank.d, p) for p in song['seqs']]
    loop_seq = song['loop_seq']
    start = 0
    if loop_seq is not None and len(parsed) > 1 and len(parsed[0][0]) <= 3:
        start = 1
    if loop_seq is None:
        return sum(ln for _, ln in parsed), None, parsed
    intro = sum(parsed[i][1] for i in range(start, loop_seq))
    loop = sum(parsed[i][1] for i in range(loop_seq, len(parsed)))
    return intro, loop, parsed[start:]


# ----------------------------------------------------------------------------
# Writers
# ----------------------------------------------------------------------------
def varlen(v):
    out = [v & 0x7f]
    v >>= 7
    while v:
        out.append(0x80 | (v & 0x7f))
        v >>= 7
    return bytes(reversed(out))


def write_midi(path, bank, song, title):
    """Standard MIDI File, 1 tick = 1 ms, with loopStart / loopEnd markers.
    Program changes are the bank's tone numbers, not General MIDI."""
    intro, loop, parsed = song_timeline(bank, song)
    looping = loop is not None
    prog = bank.programs[song['program']]
    trk = bytearray()
    trk += b'\x00\xff\x03' + varlen(len(title)) + title.encode('ascii', 'replace')
    trk += b'\x00\xff\x51\x03' + struct.pack('>I', 480000)[1:]      # 480 ticks per 480 ms
    for ch, tone in sorted(prog.items()):
        trk += bytes([0, 0xc0 | ch, tone & 0x7f])
    events = []
    t0 = 0
    loop_idx = (song['loop_seq'] - (len(song['seqs']) - len(parsed))) if looping else None
    for i, (ev, ln) in enumerate(parsed):
        if looping and i == loop_idx:
            events.append((t0, 'marker', 'loopStart'))
        for t, st, dt in ev:
            if st & 0xf0 == 0xe0:
                v = dt[0] << 7
                events.append((t0 + t, 'raw', bytes([st, v & 0x7f, v >> 7])))
            elif st & 0xf0 == 0x80:
                events.append((t0 + t, 'raw', bytes([st, dt[0], 0x40])))
            else:
                events.append((t0 + t, 'raw', bytes([st] + dt)))
        t0 += ln
    if looping:
        events.append((t0, 'marker', 'loopEnd'))
    last = 0
    for t, kind, val in events:
        trk += varlen(t - last)
        last = t
        if kind == 'raw':
            trk += val
        else:
            trk += b'\xff\x06' + varlen(len(val)) + val.encode()
    trk += b'\x00\xff\x2f\x00'
    with open(path, 'wb') as f:
        f.write(b'MThd' + struct.pack('>IHHH', 6, 0, 1, 480))
        f.write(b'MTrk' + struct.pack('>I', len(trk)) + trk)


def write_sample_wav(path, smp):
    """Mono 16-bit WAV at the sample's own rate, with a 'smpl' loop chunk."""
    pcm = array.array('h', smp['pcm'])
    if sys.byteorder == 'big':
        pcm.byteswap()
    pcm = pcm.tobytes()
    rate = smp['rate']
    fmt = struct.pack('<HHIIHH', 1, 1, rate, rate * 2, 2, 16)
    chunks = b'fmt ' + struct.pack('<I', len(fmt)) + fmt
    if smp['loop_end'] is not None:
        sm = struct.pack('<IIIIIIIII', 0, 0, int(1e9 / rate), 60, 0, 0, 0, 1, 0)
        sm += struct.pack('<IIIIII', 0, 0, smp['loop_start'], smp['loop_end'] - 1, 0, 0)
        chunks += b'smpl' + struct.pack('<I', len(sm)) + sm
    chunks += b'data' + struct.pack('<I', len(pcm)) + pcm
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 4 + len(chunks)) + b'WAVE' + chunks)
