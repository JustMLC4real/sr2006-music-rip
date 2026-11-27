"""Tiny MIPS R3000 assembler that emits PS2 IOP modules (IRX ELF files).

Everything (code, import stubs, data) lives in .text; relocations are
emitted for absolute addresses (R_MIPS_26 / HI16 / LO16 / 32) so the IOP
loader can place the module anywhere.
"""
import struct

REG = {n: i for i, n in enumerate(
    ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
     's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra'])}

R_MIPS_32, R_MIPS_26, R_MIPS_HI16, R_MIPS_LO16 = 2, 4, 5, 6


def r(x):
    return REG[x] if isinstance(x, str) else x


class Asm:
    def __init__(self):
        self.items = []      # (kind, payload)
        self.labels = {}
        self.pc = 0

    # --- layout helpers -------------------------------------------------
    def label(self, name):
        assert name not in self.labels, name
        self.labels[name] = self.pc

    def _emit(self, kind, payload, size=4):
        self.items.append((self.pc, kind, payload))
        self.pc += size

    def word(self, v):
        self._emit('word', v)

    def addr_word(self, lbl):
        self._emit('addrword', lbl)

    def bytes_(self, b):
        self._emit('bytes', bytes(b), len(b))

    def align(self, n):
        pad = (-self.pc) % n
        if pad:
            self.bytes_(b'\0' * pad)

    def asciz(self, s):
        self.bytes_(s.encode() + b'\0')

    def space(self, n):
        self.bytes_(b'\0' * n)

    # --- raw instruction encoders -------------------------------------------
    def R(self, fn, rd=0, rs=0, rt=0, sa=0):
        self.word((r(rs) << 21) | (r(rt) << 16) | (r(rd) << 11) | (sa << 6) | fn)

    def I(self, op, rt, rs, imm):
        self.word((op << 26) | (r(rs) << 21) | (r(rt) << 16) | (imm & 0xffff))

    def nop(self): self.word(0)
    def addu(self, d, s, t): self.R(0x21, d, s, t)
    def subu(self, d, s, t): self.R(0x23, d, s, t)
    def and_(self, d, s, t): self.R(0x24, d, s, t)
    def or_(self, d, s, t): self.R(0x25, d, s, t)
    def slt(self, d, s, t): self.R(0x2a, d, s, t)
    def sltu(self, d, s, t): self.R(0x2b, d, s, t)
    def sll(self, d, t, sa): self.R(0x00, d, 0, t, sa)
    def srl(self, d, t, sa): self.R(0x02, d, 0, t, sa)
    def move(self, d, s): self.addu(d, s, 'zero')

    def jr(self, s):
        self.R(0x08, 0, s)
        self.nop()

    def jalr(self, s):
        self.R(0x09, 'ra', s)
        self.nop()

    def addiu(self, t, s, imm): self.I(9, t, s, imm)
    def andi(self, t, s, imm): self.I(12, t, s, imm)
    def ori(self, t, s, imm): self.I(13, t, s, imm)
    def lui(self, t, imm): self.I(15, t, 0, imm)
    def lw(self, t, off, s): self.I(35, t, s, off)
    def sw(self, t, off, s): self.I(43, t, s, off)
    def lbu(self, t, off, s): self.I(36, t, s, off)
    def sb(self, t, off, s): self.I(40, t, s, off)

    def li(self, t, v):
        v &= 0xffffffff
        if v < 0x8000 or v >= 0xffff8000:
            self.addiu(t, 'zero', v & 0xffff)
        elif v <= 0xffff:
            self.ori(t, 'zero', v)
        else:
            self.lui(t, v >> 16)
            if v & 0xffff:
                self.ori(t, t, v & 0xffff)

    def la(self, t, lbl):
        self._emit('hi16', (r(t), lbl))
        self._emit('lo16', (r(t), lbl))

    def _branch(self, op, rs, rt, lbl):
        self._emit('branch', (op, r(rs), r(rt), lbl))
        self.nop()

    def beq(self, s, t, lbl): self._branch(4, s, t, lbl)
    def bne(self, s, t, lbl): self._branch(5, s, t, lbl)
    def b(self, lbl): self._branch(4, 0, 0, lbl)
    def blez(self, s, lbl): self._branch(6, s, 0, lbl)
    def bgtz(self, s, lbl): self._branch(7, s, 0, lbl)

    def jal(self, lbl):
        self._emit('jal', lbl)
        self.nop()

    # --- imports --------------------------------------------------------
    def imports(self, libname, version, funcs):
        """funcs: {stub_label: index}"""
        self.align(4)
        self.word(0x41e00000)
        self.word(0)
        self.word(version)
        self.bytes_(libname.encode().ljust(8, b'\0'))
        for lbl, idx in funcs.items():
            self.label(lbl)
            self.word(0x03e00008)
            self.word(0x24000000 | idx)
        self.word(0)
        self.word(0)

    # --- assemble ---------------------------------------------------------
    def assemble(self):
        out = bytearray(self.pc)
        rel = []
        for pc, kind, p in self.items:
            if kind == 'word':
                struct.pack_into('<I', out, pc, p & 0xffffffff)
            elif kind == 'bytes':
                out[pc:pc + len(p)] = p
            elif kind == 'addrword':
                struct.pack_into('<I', out, pc, self.labels[p])
                rel.append((pc, R_MIPS_32))
            elif kind == 'hi16':
                t, lbl = p
                a = self.labels[lbl]
                struct.pack_into('<I', out, pc, (15 << 26) | (t << 16) | (((a + 0x8000) >> 16) & 0xffff))
                rel.append((pc, R_MIPS_HI16))
            elif kind == 'lo16':
                t, lbl = p
                a = self.labels[lbl]
                struct.pack_into('<I', out, pc, (9 << 26) | (t << 21) | (t << 16) | (a & 0xffff))
                rel.append((pc, R_MIPS_LO16))
            elif kind == 'branch':
                op, rs, rt, lbl = p
                off = (self.labels[lbl] - (pc + 4)) >> 2
                assert -0x8000 <= off < 0x8000
                struct.pack_into('<I', out, pc, (op << 26) | (rs << 21) | (rt << 16) | (off & 0xffff))
            elif kind == 'jal':
                a = self.labels[p]
                struct.pack_into('<I', out, pc, (3 << 26) | (a >> 2))
                rel.append((pc, R_MIPS_26))
        return bytes(out), rel


def build_irx(asm, entry_label, name, version=0x0101, bss=0):
    text, rel = asm.assemble()
    entry = asm.labels[entry_label]
    modname = name.encode() + b'\0'
    iopmod = struct.pack('<IIIIIIH', 0xffffffff, entry, 0x7ff0, len(text), 0, bss, version) + modname
    shstr = b'\0.iopmod\0.text\0.rel.text\0.shstrtab\0.symtab\0.strtab\0'

    def sidx(s):
        return shstr.index(s.encode() + b'\0')

    off = 0x34 + 2 * 0x20
    iop_off = off
    off += len(iopmod)
    off = (off + 15) & ~15
    text_off = off
    off += len(text)
    off = (off + 3) & ~3
    rel_off = off
    relb = b''.join(struct.pack('<II', o, t) for o, t in rel)
    off += len(relb)
    shstr_off = off
    off += len(shstr)
    off = (off + 3) & ~3
    sym_off = off
    symb = b'\0' * 16
    off += len(symb)
    str_off = off
    strb = b'\0'
    off += 1
    off = (off + 3) & ~3
    sh_off = off
    # section headers: 0 null,1 .iopmod,2 .text,3 .rel.text,4 .shstrtab,5 .symtab,6 .strtab
    sh = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (sidx('.iopmod'), 0x70000080, 0, 0, iop_off, len(iopmod), 0, 0, 4, 0),
        (sidx('.text'), 1, 6, 0, text_off, len(text), 0, 0, 16, 0),
        (sidx('.rel.text'), 9, 0, 0, rel_off, len(relb), 5, 2, 4, 8),
        (sidx('.shstrtab'), 3, 0, 0, shstr_off, len(shstr), 0, 0, 1, 0),
        (sidx('.symtab'), 2, 0, 0, sym_off, len(symb), 6, 1, 4, 16),
        (sidx('.strtab'), 3, 0, 0, str_off, 1, 0, 0, 1, 0),
    ]
    ehdr = struct.pack('<16sHHIIIIIHHHHHH', b'\x7fELF\x01\x01\x01' + b'\0' * 9, 0xff80, 8, 1, entry,
                       0x34, sh_off, 1, 0x34, 0x20, 2, 0x28, len(sh), 4)
    ph = struct.pack('<8I', 0x70000080, iop_off, 0, 0, len(iopmod), 0, 4, 4)
    ph += struct.pack('<8I', 1, text_off, 0, 0, len(text), len(text) + bss, 7, 16)
    img = bytearray(off + 40 * len(sh))
    img[0:0x34] = ehdr
    img[0x34:0x74] = ph
    img[iop_off:iop_off + len(iopmod)] = iopmod
    img[text_off:text_off + len(text)] = text
    img[rel_off:rel_off + len(relb)] = relb
    img[shstr_off:shstr_off + len(shstr)] = shstr
    img[sym_off:sym_off + 16] = symb
    for i, s in enumerate(sh):
        img[sh_off + 40 * i:sh_off + 40 * i + 40] = struct.pack('<10I', *s)
    return bytes(img)
