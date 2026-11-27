"""Build the PSF2 set: the game's own sound driver plays the original bank.

  psf2.irx     loader: loads libsd.irx, sndfi.irx and sr2006.irx, then
               sleeps (Highly Experimental stops once psf2.irx returns)
  sr2006.irx   does what the game's EE side does, with the game's values:
               driver init (heap 0x1F800, DMA channel 1), driver start,
               memory layout with the bank in slot 1, bank header to IOP
               memory, samples to SPU2 RAM, activate, then the song request
               word and the music volume command from song.cfg
  sndfi.irx    the game's SNDFI.IRX (SNDF driver v2.15g), with its two SIF
               RPC server threads not started (there is no EE in a PSF2)
  libsd.irx    the game's LIBSD.IRX
  Both game modules import sysclib 1.4 and sysmem 1.2; Highly Experimental
  provides 1.3 and 1.1, so the import versions are lowered (the functions
  they use are the same).
"""
import os
import struct
import zlib

from .archive import GameError, game_file, read_archive_file
from .bank import Bank, song_timeline
from .irxasm import Asm, build_irx

# SNDFI.IRX (SNDF Driver v2.15g, Jan 12 2005) offsets
SNDFI_INIT = 0xca04          # RPC 0x1300 handler (heap size, ?, sdinit, dma ch)
SNDFI_START = 0xcaf0         # RPC 0x0100 handler (alloc heap, thread, timer)
SNDFI_EXP4 = 0xf544          # export #4: memory layout (iop sizes[32], spu sizes[32])
SNDFI_WORK = 0x12390         # pointer to the driver work area
WORK_IOP_ADDR = 672          # + 4*slot
WORK_SPU_ADDR = 928          # + 4*slot
SLOT = 1                     # the game loads R2K5SNGS.DAT into slot 1
DMA_CH = 1
HEAP = 0x1f800


def emit_strcat(a):
    """strcat_path(a0=dst, a1=prefix, a2=name): dst = prefix + name"""
    a.label('strcat_path')
    a.label('_cp1')
    a.lbu('t0', 0, 'a1')
    a.beq('t0', 'zero', '_cp2')
    a.sb('t0', 0, 'a0')
    a.addiu('a0', 'a0', 1)
    a.addiu('a1', 'a1', 1)
    a.b('_cp1')
    a.label('_cp2')
    a.lbu('t0', 0, 'a2')
    a.sb('t0', 0, 'a0')
    a.beq('t0', 'zero', '_cp3')
    a.addiu('a0', 'a0', 1)
    a.addiu('a2', 'a2', 1)
    a.b('_cp2')
    a.label('_cp3')
    a.jr('ra')


def build_loader():
    a = Asm()
    a.imports('modload', 0x0101, {'LoadStartModule': 7})
    a.imports('thbase', 0x0101, {'SleepThread': 24})
    a.imports('stdio', 0x0101, {'printf': 4})

    a.label('_start')
    a.addiu('sp', 'sp', -32)
    a.sw('ra', 28, 'sp')
    a.sw('s0', 24, 'sp')
    a.lw('s0', 0, 'a1')                 # argv[0], e.g. "hefile:/psf2.irx"
    a.la('t0', 'prefix')
    a.move('t1', 't0')
    a.label('_pf')
    a.lbu('t2', 0, 's0')
    a.sb('t2', 0, 't0')
    a.beq('t2', 'zero', '_pfdone')
    a.addiu('t0', 't0', 1)
    a.addiu('s0', 's0', 1)
    a.li('t3', ord('/'))
    a.beq('t2', 't3', '_pfsep')
    a.li('t3', ord('\\'))
    a.beq('t2', 't3', '_pfsep')
    a.li('t3', ord(':'))
    a.beq('t2', 't3', '_pfsep')
    a.b('_pf')
    a.label('_pfsep')
    a.move('t1', 't0')
    a.b('_pf')
    a.label('_pfdone')
    a.sb('zero', 0, 't1')
    # Highly Experimental's boot thread shuts the player down as soon as
    # psf2.irx returns from its start routine, so load everything here and
    # then sleep forever while the driver plays.
    a.jal('load_all')
    a.label('_sleep')
    a.jal('SleepThread')
    a.b('_sleep')

    a.label('load_all')
    a.addiu('sp', 'sp', -32)
    a.sw('ra', 28, 'sp')
    for nm, args in (('n_libsd', False), ('n_sndfi', False), ('n_player', True)):
        a.la('a0', 'path')
        a.la('a1', 'prefix')
        a.la('a2', nm)
        a.jal('strcat_path')
        a.la('a0', 'path')
        if args:
            # argument = the device prefix (NUL terminated)
            a.la('t0', 'prefix')
            a.move('a1', 'zero')
            a.label('_al')
            a.lbu('t1', 0, 't0')
            a.addiu('t0', 't0', 1)
            a.addiu('a1', 'a1', 1)
            a.bne('t1', 'zero', '_al')
            a.la('a2', 'prefix')
        else:
            a.li('a1', 0)
            a.li('a2', 0)
        a.la('a3', 'result')
        a.jal('LoadStartModule')
        a.move('a1', 'v0')
        a.la('a0', 'msg_load')
        a.la('a2', 'path')
        a.jal('printf')
    a.lw('ra', 28, 'sp')
    a.addiu('sp', 'sp', 32)
    a.jr('ra')

    emit_strcat(a)

    a.align(4)
    a.label('result')
    a.word(0)
    a.label('n_libsd')
    a.asciz('libsd.irx')
    a.label('n_sndfi')
    a.asciz('sndfi.irx')
    a.label('n_player')
    a.asciz('sr2006.irx')
    a.label('msg_load')
    a.asciz('psf2.irx: load %d %s\n')
    a.align(4)
    a.label('prefix')
    a.space(256)
    a.label('path')
    a.space(256)
    return build_irx(a, '_start', 'psf2_loader')


def build_player():
    a = Asm()
    a.imports('sndfi', 0x0101, {'sndfi_layout': 4, 'sndfi_activate': 8, 'sndfi_request': 9})
    a.imports('libsd', 0x0101, {'sceSdVoiceTrans': 17, 'sceSdVoiceTransStatus': 19})
    a.imports('ioman', 0x0101, {'open': 4, 'close': 5, 'read': 6, 'lseek': 8})
    a.imports('sysmem', 0x0101, {'AllocSysMemory': 4, 'FreeSysMemory': 5})
    a.imports('stdio', 0x0101, {'printf': 4})

    a.label('_start')
    a.addiu('sp', 'sp', -64)
    a.sw('ra', 60, 'sp')
    for i, s in enumerate(['s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7']):
        a.sw(s, 24 + 4 * i, 'sp')
    a.lw('s7', 4, 'a1')                       # argv[1] = device prefix

    # driver base from the linked import stub ("j target")
    a.la('t0', 'sndfi_layout')
    a.lw('t1', 0, 't0')
    a.sll('t1', 't1', 6)
    a.srl('t1', 't1', 4)
    a.li('t2', SNDFI_EXP4)
    a.subu('s6', 't1', 't2')

    # song.cfg -> request word
    a.la('a0', 'path')
    a.move('a1', 's7')
    a.la('a2', 'n_cfg')
    a.jal('strcat_path')
    a.la('a0', 'path')
    a.li('a1', 1)                             # O_RDONLY
    a.jal('open')
    a.move('s0', 'v0')
    a.move('a0', 's0')
    a.la('a1', 'cfg')
    a.li('a2', 12)
    a.jal('read')
    a.move('a0', 's0')
    a.jal('close')

    # driver init (as RPC 0x1300 with the game's values; libsd init by driver)
    a.li('a0', HEAP)
    a.li('a1', 0)
    a.li('a2', 1)
    a.li('a3', DMA_CH)
    a.li('t9', SNDFI_INIT)
    a.addu('t9', 't9', 's6')
    a.jalr('t9')
    # driver start (as RPC 0x0100)
    a.la('a0', 'scratch')
    a.li('t9', SNDFI_START)
    a.addu('t9', 't9', 's6')
    a.jalr('t9')

    # open bank, read its header fields
    a.la('a0', 'path')
    a.move('a1', 's7')
    a.la('a2', 'n_bank')
    a.jal('strcat_path')
    a.la('a0', 'path')
    a.li('a1', 1)
    a.jal('open')
    a.move('s0', 'v0')
    a.move('a0', 's0')
    a.la('a1', 'hdr')
    a.li('a2', 32)
    a.jal('read')
    a.la('t0', 'hdr')
    a.lw('s1', 0x10, 't0')                    # header (IOP part) size
    a.lw('s2', 0x18, 't0')                    # sample data size
    a.lw('s3', 0x1c, 't0')                    # sample data offset

    # memory layout: slot sizes, 64-byte aligned (as the game does)
    a.la('t0', 'iopsz')
    a.addiu('t1', 's1', 63)
    a.li('t2', 0xffffffc0)
    a.and_('t1', 't1', 't2')
    a.sw('t1', 4 * SLOT, 't0')
    a.la('t0', 'spusz')
    a.addiu('t1', 's2', 63)
    a.and_('t1', 't1', 't2')
    a.sw('t1', 4 * SLOT, 't0')
    a.la('a0', 'iopsz')
    a.la('a1', 'spusz')
    a.jal('sndfi_layout')
    a.move('a1', 'v0')
    a.la('a0', 'msg_layout')
    a.jal('printf')

    # driver work area -> slot addresses
    a.li('t0', SNDFI_WORK)
    a.addu('t0', 't0', 's6')
    a.lw('t0', 0, 't0')
    a.lw('s4', WORK_IOP_ADDR + 4 * SLOT, 't0')
    a.lw('s5', WORK_SPU_ADDR + 4 * SLOT, 't0')

    # header -> IOP slot area
    a.move('a0', 's0')
    a.li('a1', 0)
    a.li('a2', 0)
    a.jal('lseek')
    a.move('a0', 's0')
    a.move('a1', 's4')
    a.move('a2', 's1')
    a.jal('read')

    # samples -> SPU2 RAM in 64 KiB pieces
    a.li('a0', 0)
    a.li('a1', 0x10000)
    a.li('a2', 0)
    a.jal('AllocSysMemory')
    a.move('s4', 'v0')                        # transfer buffer
    a.move('a0', 's0')
    a.move('a1', 's3')
    a.li('a2', 0)
    a.jal('lseek')
    a.label('_xfer')
    a.blez('s2', '_xdone')
    a.li('s1', 0x10000)
    a.slt('t0', 's2', 's1')
    a.beq('t0', 'zero', '_xn')
    a.move('s1', 's2')
    a.label('_xn')
    a.move('a0', 's0')
    a.move('a1', 's4')
    a.move('a2', 's1')
    a.jal('read')
    a.li('t0', 0)
    a.sw('s1', 16, 'sp')                      # 5th arg: size
    a.li('a0', DMA_CH)
    a.li('a1', 0)                             # write, DMA
    a.move('a2', 's4')
    a.move('a3', 's5')
    a.jal('sceSdVoiceTrans')
    a.li('a0', DMA_CH)
    a.li('a1', 1)                             # wait
    a.jal('sceSdVoiceTransStatus')
    a.addu('s5', 's5', 's1')
    a.subu('s2', 's2', 's1')
    a.b('_xfer')
    a.label('_xdone')
    a.move('a0', 's0')
    a.jal('close')
    a.move('a0', 's4')
    a.jal('FreeSysMemory')

    # activate bank in slot (RPC 0x0A00), then the game's song request
    a.li('a0', SLOT)
    a.jal('sndfi_activate')
    a.move('a1', 'v0')
    a.la('a0', 'msg_act')
    a.jal('printf')
    a.la('t0', 'cfg')
    a.lw('a0', 0, 't0')
    a.li('a1', 0)
    a.li('a2', 255)
    a.li('a3', 0)
    a.li('t0', 0xff)
    a.sw('t0', 16, 'sp')
    a.jal('sndfi_request')
    a.move('a1', 'v0')
    a.la('t0', 'cfg')
    a.lw('a2', 0, 't0')
    a.la('a0', 'msg_req')
    a.jal('printf')
    # optional second request (the game's music volume command, 0xA004VV00,
    # sent with group byte cfg[2]); skipped when cfg[1] == 0
    a.la('t0', 'cfg')
    a.lw('a0', 4, 't0')
    a.beq('a0', 'zero', '_novol')
    a.lw('t1', 8, 't0')
    a.sw('t1', 16, 'sp')
    a.li('a1', 0)
    a.li('a2', 255)
    a.li('a3', 0)
    a.jal('sndfi_request')
    a.move('a1', 'v0')
    a.la('t0', 'cfg')
    a.lw('a2', 4, 't0')
    a.la('a0', 'msg_req')
    a.jal('printf')
    a.label('_novol')

    for i, s in enumerate(['s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7']):
        a.lw(s, 24 + 4 * i, 'sp')
    a.lw('ra', 60, 'sp')
    a.addiu('sp', 'sp', 64)
    a.li('v0', 0)                             # RESIDENT_END
    a.jr('ra')

    emit_strcat(a)

    a.align(4)
    a.label('cfg')
    a.space(16)
    a.label('scratch')
    a.space(64)
    a.label('hdr')
    a.space(32)
    a.label('iopsz')
    a.space(128)
    a.label('spusz')
    a.space(128)
    a.label('n_cfg')
    a.asciz('song.cfg')
    a.label('n_bank')
    a.asciz('r2k5sngs.dat')
    a.label('msg_layout')
    a.asciz('sr2006: layout %d\n')
    a.label('msg_act')
    a.asciz('sr2006: bank activate %d\n')
    a.label('msg_req')
    a.asciz('sr2006: request %d word %08x\n')
    a.align(4)
    a.label('path')
    a.space(256)
    return build_irx(a, '_start', 'sr2006_player')


# Highly Experimental's IOP kernel exports sysclib 1.3 and sysmem 1.1; the game
# modules import 1.4 / 1.2 but only use functions present in the older ones
# (memcpy, memset, bzero, AllocSysMemory, FreeSysMemory).
IMPORT_VERSION_FIX = {b'sysclib': 0x103, b'sysmem': 0x101}


def fix_import_versions(data):
    d = bytearray(data)
    o = 0
    while True:
        o = d.find(bytes.fromhex('0000e041'), o)
        if o < 0:
            break
        name = bytes(d[o + 12:o + 20]).split(bytes(1))[0]
        if name in IMPORT_VERSION_FIX:
            ver = struct.unpack_from('<I', d, o + 8)[0]
            new = IMPORT_VERSION_FIX[name]
            if (ver >> 8) == (new >> 8) and ver > new:
                struct.pack_into('<I', d, o + 8, new)
        o += 4
    return bytes(d)


def patch_sndfi(data):
    """Skip StartThread for the two SIF RPC server threads (blez a0 -> b)."""
    d = bytearray(fix_import_versions(data))
    text_off = 0xa0
    for addr in (0xfaf0, 0xfb54):
        o = text_off + addr
        if o + 4 > len(d) or struct.unpack_from('<I', d, o)[0] != 0x18800003:
            raise GameError('IOP/SNDFI.IRX is not the expected driver version (SNDF v2.15g). '
                            'Only the Japanese release (SLPM-66212) has been tested.')
        struct.pack_into('<I', d, o, 0x10000003)
    return bytes(d)


# ----------------------------------------------------------------------------
# PSF2 container
# ----------------------------------------------------------------------------
def vfs(files, block=0x8000):
    """files: {name: bytes} (root directory only)."""
    names = sorted(files)
    hdr_size = 4 + 48 * len(names)
    body = bytearray()
    entries = []
    for nm in names:
        data = files[nm]
        off = hdr_size + len(body)
        if not data:
            entries.append((nm, 0, 0, 0))
            continue
        blocks = [zlib.compress(data[i:i + block], 9) for i in range(0, len(data), block)]
        body += b''.join(struct.pack('<I', len(b)) for b in blocks)
        body += b''.join(blocks)
        entries.append((nm, off, len(data), block))
    out = bytearray(struct.pack('<I', len(names)))
    for nm, off, size, blk in entries:
        out += nm.encode().ljust(36, b'\0') + struct.pack('<III', off, size, blk)
    return bytes(out + body)


def psf2(files, tags):
    res = vfs(files)
    out = b'PSF\x02' + struct.pack('<III', len(res), 0, zlib.crc32(b''))
    out += res
    if tags:
        out += b'[TAG]' + ''.join(f'{k}={v}\n' for k, v in tags.items()).encode('utf-8')
    return out


def fmt_time(ms):
    s = ms / 1000.0
    m = int(s // 60)
    return f'{m}:{s - 60 * m:06.3f}'


LEAD_MS = 300      # driver start-up + the 250 ms pre-roll sequence of the song script
TICK_MS = 5        # driver tick: IOP hard timer, compare 720 at sysclock / 256
FADE_S = 10
JINGLE_TAIL_MS = 2000

# Game song table (SLPM_662.12 @0x35B930): game index i -> request 0xA8000N00.
# Index 7 plays bank song 8 and index 8 plays bank song 7.
GAME_INDEX = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 8, 8: 7}   # bank song -> game index
# Music volume per game index in percent (@0x3727B0), sent as 127 * vol / 100
GAME_VOLUME = [90, 90, 63, 72, 90, 63, 90, 72, 81, 72]
MASTER = 127

# Descriptive names per bank song (the game has no track titles); see the
# README for where each one plays.
TITLES = ['Title Screen', 'Main Menu', 'Results', 'Career Menu (Pro)', 'Career Mode Start',
          'Career Menu (Amateur)', 'Race Entry (Pro)', 'Race Day', 'Race Entry (Amateur)',
          'Jingle - Pro Contract Signed', 'Jingle - Sponsor Contract Signed']
# Track order of the output: from the title screen into Career, with the
# amateur and pro version of a screen side by side.
ORDER = [0, 1, 4, 5, 3, 8, 6, 7, 2, 9, 10]      # bank song of track 1, 2, ...


def track_number(n):
    """Track number (1-11) of bank song n."""
    return ORDER.index(n) + 1
BANK_PATH = 'se/r2k5sngs.dat'
LIB_NAME = 'sr2006.psf2lib'


def song_cfg(n):
    """song.cfg: request word, music volume command (0 = none), group byte."""
    word = 0xa8000000 | (n << 8)
    if n in GAME_INDEX:
        vol = (MASTER * GAME_VOLUME[GAME_INDEX[n]] // 100) & 0x7f
        return struct.pack('<III', word, 0xa0040000 | (vol << 8), 1)
    return struct.pack('<III', word, 0, 0)


def song_length(bank, song):
    """-> (length ms, fade s). Looping songs: intro + 2 loops, ending on the
    driver tick that starts pass 3 (an event at t ms after the intro start is
    played on tick ceil(t / 5)); jingles: once plus the release tail."""
    intro, loop, _ = song_timeline(bank, song)
    if loop is None:
        return LEAD_MS + intro + JINGLE_TAIL_MS, 0
    t = intro + 2 * loop
    return LEAD_MS + TICK_MS * -(-t // TICK_MS), FADE_S


def check_game(game_dir):
    """-> (sndfi bytes, libsd bytes); raises GameError with a clear message."""
    sndfi = game_file(game_dir, 'IOP', 'SNDFI.IRX')
    libsd = game_file(game_dir, 'IOP', 'LIBSD.IRX')
    missing = [n for n, p in (('IOP/SNDFI.IRX', sndfi), ('IOP/LIBSD.IRX', libsd),
                              ('DATA.FAI', game_file(game_dir, 'DATA.FAI')),
                              ('DATA.FAB', game_file(game_dir, 'DATA.FAB'))) if not p]
    if missing:
        raise GameError('Not a Sega Rally 2006 game folder, missing: ' + ', '.join(missing))
    with open(sndfi, 'rb') as f:
        sndfi_data = f.read()
    with open(libsd, 'rb') as f:
        libsd_data = f.read()
    patch_sndfi(sndfi_data)
    return sndfi_data, libsd_data


def load_bank(game_dir):
    data = read_archive_file(game_dir, BANK_PATH)
    bank = Bank(data)
    if len(bank.songs) != len(TITLES):
        raise GameError(f'{BANK_PATH} has {len(bank.songs)} songs, expected {len(TITLES)}.')
    return data, bank


def build_set(game_dir, outdir, log=print):
    """Write the PSF2 set to outdir. -> list of written paths."""
    sndfi, libsd = check_game(game_dir)
    bank_bytes, bank = load_bank(game_dir)
    os.makedirs(outdir, exist_ok=True)
    lib = {
        'psf2.irx': build_loader(),
        'sr2006.irx': build_player(),
        'sndfi.irx': patch_sndfi(sndfi),
        'libsd.irx': fix_import_versions(libsd),
        'r2k5sngs.dat': bank_bytes,
    }
    paths = [os.path.join(outdir, LIB_NAME)]
    with open(paths[0], 'wb') as f:
        f.write(psf2(lib, {}))
    log(f'  {LIB_NAME}')
    for n in ORDER:
        song = bank.songs[n]
        tn = track_number(n)
        length, fade = song_length(bank, song)
        tags = {'_lib': LIB_NAME, 'game': 'Sega Rally 2006', 'year': '2006',
                'copyright': 'Sega', 'title': TITLES[n], 'track': str(tn),
                'comment': f'Bank song {n:02d}, SNDF request 0x{0xa8000000 | (n << 8):08X}, bank r2k5sngs.dat',
                'length': fmt_time(length), 'fade': str(fade)}
        path = os.path.join(outdir, f'{tn:02d} {TITLES[n]}.minipsf2')
        with open(path, 'wb') as f:
            f.write(psf2({'song.cfg': song_cfg(n)}, tags))
        paths.append(path)
        log(f'  {os.path.basename(path)}  ({tags["length"]} + {fade} s fade)')
    return paths
