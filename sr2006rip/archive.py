"""Read one file from the game's DATA.FAI / DATA.FAB archive.

DATA.FAI header (little endian): "FAH\\0", u32 file count at 0x10, u32
file-table offset at 0x14, u32 name-table size at 0x18, u32 name-table
offset at 0x1C (the suffix table follows the name table). File table: 16
bytes per file: u16 suffix index, u16 name index (both in 4-byte units),
u32 offset in DATA.FAB, u32 size, u32 hash. Path = name + suffix.
"""
import os
import struct


class GameError(Exception):
    pass


def game_file(game_dir, *parts):
    """Case-insensitive lookup of a file in the game folder."""
    cur = game_dir
    for part in parts:
        if not os.path.isdir(cur):
            return None
        names = {n.upper(): n for n in os.listdir(cur)}
        if part.upper() not in names:
            return None
        cur = os.path.join(cur, names[part.upper()])
    return cur


def read_archive_file(game_dir, wanted):
    """-> bytes of the archive file whose path is `wanted` (e.g. 'se/r2k5sngs.dat')."""
    fai_path = game_file(game_dir, 'DATA.FAI')
    fab_path = game_file(game_dir, 'DATA.FAB')
    if not fai_path or not fab_path:
        raise GameError('DATA.FAI and DATA.FAB were not found in the game folder.')
    with open(fai_path, 'rb') as f:
        d = f.read()
    if d[:4] != b'FAH\0':
        raise GameError('DATA.FAI is not a valid archive index.')
    count, table, name_size, name_base = struct.unpack_from('<IIII', d, 0x10)
    suffix_base = name_base + name_size

    def cstr(o):
        return d[o:d.index(b'\0', o)].decode('latin-1')

    for i in range(count):
        suffix, name, offset, size, _ = struct.unpack_from('<HHIII', d, table + 16 * i)
        if (cstr(name_base + 4 * name) + cstr(suffix_base + 4 * suffix)).lower() == wanted.lower():
            with open(fab_path, 'rb') as f:
                f.seek(offset)
                data = f.read(size)
            if len(data) != size:
                raise GameError(f'DATA.FAB is shorter than expected ({wanted}).')
            return data
    raise GameError(f'{wanted} was not found in DATA.FAI.')
