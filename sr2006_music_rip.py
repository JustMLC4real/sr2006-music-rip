#!/usr/bin/env python3
"""
sr2006-music-rip - rip the sequenced music of Sega Rally 2006 (PS2).

Run without arguments for the window, or use the command line:

  python sr2006_music_rip.py <game folder> -o <output folder> [--no-psf2] [--no-midi] [--no-samples]

The game folder is a copy of the game disc's files (with DATA.FAI,
DATA.FAB and the IOP folder). Output:
  psf2/     PSF2 set: the game's own sound driver with the original bank
  midi/     the sequences as MIDI files, with loop markers
  samples/  every instrument sample as WAV, with loop points
"""
import argparse
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sr2006rip import __version__  # noqa: E402
from sr2006rip.archive import GameError  # noqa: E402
from sr2006rip.bank import write_midi, write_sample_wav  # noqa: E402
from sr2006rip.psf2 import ORDER, TITLES, build_set, load_bank, track_number  # noqa: E402


def rip(game_dir, outdir, psf2=True, midi=True, samples=True, log=print, cancel=None):
    """Do the selected steps. Raises GameError on a problem with the input."""
    if not (psf2 or midi or samples):
        raise GameError('Nothing selected.')
    game_dir = os.path.abspath(game_dir)
    outdir = os.path.abspath(outdir)
    if psf2:
        log('PSF2 set ...')
        build_set(game_dir, os.path.join(outdir, 'psf2'), log)
    if midi or samples:
        _, bank = load_bank(game_dir)
    if midi:
        log('MIDI files ...')
        d = os.path.join(outdir, 'midi')
        os.makedirs(d, exist_ok=True)
        for n in ORDER:
            name = f'{track_number(n):02d} {TITLES[n]}.mid'
            write_midi(os.path.join(d, name), bank, bank.songs[n], TITLES[n])
            log(f'  {name}')
    if samples:
        d = os.path.join(outdir, 'samples')
        os.makedirs(d, exist_ok=True)
        count = bank.sample_count()
        log(f'Samples ({count}) ...')
        for i in range(count):
            if cancel and cancel():
                log('Stopped.')
                return
            write_sample_wav(os.path.join(d, f'r2k5sngs_smp{i:03d}.wav'), bank.sample(i))
            if (i + 1) % 10 == 0 or i + 1 == count:
                log(f'  {i + 1}/{count}')
    log(f'Done: {outdir}')


# ----------------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------------
def cli(argv):
    p = argparse.ArgumentParser(
        prog='sr2006_music_rip.py',
        description='Rip the sequenced music of Sega Rally 2006 (PS2) to a PSF2 set, MIDI files '
                    'and samples. Run without arguments to open the window.')
    p.add_argument('game', help='game folder (with DATA.FAI, DATA.FAB and the IOP folder)')
    p.add_argument('-o', '--output', required=True, help='output folder')
    p.add_argument('--no-psf2', action='store_true', help='skip the PSF2 set')
    p.add_argument('--no-midi', action='store_true', help='skip the MIDI files')
    p.add_argument('--no-samples', action='store_true', help='skip the samples')
    p.add_argument('--version', action='version', version=__version__)
    a = p.parse_args(argv)
    try:
        rip(a.game, a.output, not a.no_psf2, not a.no_midi, not a.no_samples,
            log=lambda line: print(line, flush=True))
        return 0
    except (GameError, OSError, ValueError) as err:
        print(f'error: {err}', file=sys.stderr)
        return 1


# ----------------------------------------------------------------------------
# Window
# ----------------------------------------------------------------------------
def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(f'sr2006-music-rip {__version__} - Sega Rally 2006 sequenced music')
    root.geometry('760x560')
    root.minsize(600, 420)

    game_var = tk.StringVar()
    out_var = tk.StringVar()
    opt = {k: tk.BooleanVar(value=True) for k in ('psf2', 'midi', 'samples')}
    state = {'busy': False, 'cancel': False}

    frm = ttk.Frame(root, padding=10)
    frm.pack(fill='both', expand=True)
    frm.columnconfigure(1, weight=1)

    def browse_game():
        d = filedialog.askdirectory(title='Game folder (with DATA.FAI, DATA.FAB and IOP)')
        if d:
            game_var.set(d)
            if not out_var.get():
                out_var.set(os.path.join(d, 'sr2006_music'))

    def browse_out():
        d = filedialog.askdirectory(title='Output folder')
        if d:
            out_var.set(d)

    ttk.Label(frm, text='Game folder').grid(row=0, column=0, sticky='w')
    ttk.Entry(frm, textvariable=game_var).grid(row=0, column=1, sticky='ew', padx=6)
    ttk.Button(frm, text='Browse...', command=browse_game).grid(row=0, column=2)
    ttk.Label(frm, text='Output folder').grid(row=1, column=0, sticky='w', pady=(6, 0))
    ttk.Entry(frm, textvariable=out_var).grid(row=1, column=1, sticky='ew', padx=6, pady=(6, 0))
    ttk.Button(frm, text='Browse...', command=browse_out).grid(row=1, column=2, pady=(6, 0))

    box = ttk.LabelFrame(frm, text='Make', padding=8)
    box.grid(row=2, column=0, columnspan=3, sticky='ew', pady=10)
    ttk.Checkbutton(box, text='PSF2 set  (play in foobar2000 with foo_input_psf; loops like the game)',
                    variable=opt['psf2']).pack(anchor='w')
    ttk.Checkbutton(box, text='MIDI files  (sequences with loopStart / loopEnd markers)',
                    variable=opt['midi']).pack(anchor='w')
    ttk.Checkbutton(box, text='Samples  (98 instrument samples as WAV, with loop points)',
                    variable=opt['samples']).pack(anchor='w')

    log_frame = ttk.Frame(frm)
    log_frame.grid(row=3, column=0, columnspan=3, sticky='nsew')
    frm.rowconfigure(3, weight=1)
    text = tk.Text(log_frame, height=12, wrap='none', state='disabled')
    sb = ttk.Scrollbar(log_frame, orient='vertical', command=text.yview)
    text.configure(yscrollcommand=sb.set)
    text.pack(side='left', fill='both', expand=True)
    sb.pack(side='right', fill='y')

    bar = ttk.Progressbar(frm, mode='indeterminate')
    bar.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(8, 0))
    btns = ttk.Frame(frm)
    btns.grid(row=5, column=0, columnspan=3, sticky='e', pady=(8, 0))
    b_open = ttk.Button(btns, text='Open output folder')
    b_stop = ttk.Button(btns, text='Stop')
    b_start = ttk.Button(btns, text='Start')
    for b in (b_open, b_stop, b_start):
        b.pack(side='left', padx=(6, 0))

    def write(line):
        text.configure(state='normal')
        text.insert('end', line + '\n')
        text.see('end')
        text.configure(state='disabled')

    def log(line):
        root.after(0, write, line)

    def set_busy(busy):
        state['busy'] = busy
        b_start.state(['disabled'] if busy else ['!disabled'])
        b_stop.state(['!disabled'] if busy else ['disabled'])
        if busy:
            bar.start(12)
        else:
            bar.stop()

    def start():
        if state['busy']:
            return
        game = game_var.get().strip()
        out = out_var.get().strip()
        if not game or not out:
            messagebox.showwarning('Folders', 'Choose the game folder and an output folder first.')
            return
        state['cancel'] = False
        set_busy(True)
        text.configure(state='normal')
        text.delete('1.0', 'end')
        text.configure(state='disabled')

        def work():
            try:
                rip(game, out, opt['psf2'].get(), opt['midi'].get(), opt['samples'].get(),
                    log, lambda: state['cancel'])
            except (GameError, OSError, ValueError) as err:
                log(f'Error: {err}')
            root.after(0, set_busy, False)

        threading.Thread(target=work, daemon=True).start()

    def open_out():
        out = out_var.get().strip()
        if out and os.path.isdir(out):
            if sys.platform.startswith('win'):
                os.startfile(out)
            else:
                import subprocess
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', out])
        else:
            messagebox.showinfo('Output folder', 'The output folder does not exist yet.')

    b_start.configure(command=start)
    b_stop.configure(command=lambda: state.update(cancel=True))
    b_open.configure(command=open_out)
    set_busy(False)
    write('Choose the game folder (a copy of the disc: DATA.FAI, DATA.FAB, IOP) and press Start.')
    root.mainloop()
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        try:
            return gui()
        except ImportError:
            print('tkinter is not available; use the command line (see --help).', file=sys.stderr)
            return 1
    return cli(argv)


if __name__ == '__main__':
    sys.exit(main())
