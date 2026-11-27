# sr2006-music-rip

Rips the **sequenced music** of **Sega Rally 2006** (PlayStation 2) from your own copy of the game.

Most of the game's music is streamed audio (ADX files in `BGM0` and `BGM1`). Eleven tracks are different: the menu, Career and results music and two jingles are sequenced. They are played note by note by Sega's sound driver from one sound bank, `se/r2k5sngs.dat` in `DATA.FAB`. This tool turns them into:

| Folder | What |
|---|---|
| `psf2/` | A **PSF2 set**: the game's own sound driver plays the original bank in a PS2 sound emulator. This is the most faithful version, and it loops exactly like the game. |
| `midi/` | The sequences as MIDI files (1 tick = 1 ms), with `loopStart` / `loopEnd` markers. Program changes are the bank's instrument numbers, not General MIDI. |
| `samples/` | The 98 instrument samples as WAV files at their own sample rate, with their loop points. |

It has a simple window and a command line, and needs nothing but Python.

> This repository contains no game data. You need your own copy of the game.

## Requirements

- Python 3.8 or newer ([python.org](https://www.python.org/downloads/)). The window uses tkinter, which comes with the standard Python installer on Windows and macOS. On Linux you may need to install `python3-tk`.
- The files from your game disc in one folder: `DATA.FAI`, `DATA.FAB` and the `IOP` folder (with `SNDFI.IRX` and `LIBSD.IRX`).

Tested with the Japanese release (SLPM-66212). The tool checks the sound driver version and stops with a message if it is different.

## Using the window

1. Double-click `sr2006_music_rip.py`, or run `python sr2006_music_rip.py` without arguments.
2. Press **Browse...** next to *Game folder* and choose the folder with the game files.
3. Choose an output folder. It defaults to `sr2006_music` inside the game folder.
4. Tick what you want (PSF2 set, MIDI files, samples) and press **Start**.

## Using the command line

```
python sr2006_music_rip.py "path/to/game" -o "path/to/output"
python sr2006_music_rip.py "path/to/game" -o "path/to/output" --no-midi --no-samples
```

Options: `--no-psf2`, `--no-midi`, `--no-samples`, `--version`, `--help`.

## Playing the PSF2 set

Use [foobar2000](https://www.foobar2000.org/) with the [PSF Decoder component (foo_input_psf)](https://wiki.hydrogenaudio.org/index.php?title=Foobar2000:Components/PSF_Decoder_(foo_input_psf)), or another player based on the Highly Experimental emulator. Open the `.minipsf2` files; `sr2006.psf2lib` must stay in the same folder.

- **Normal playback:** each looping track plays the intro, the loop twice and a 10-second fade, then stops.
- **Endless, like in the game:** in foobar2000 go to *Preferences → Playback → Decoding → PSF Decoder* and tick **Force all songs to play indefinitely**, then stop playback and start the track again. The driver then keeps jumping back to the loop point by itself. foobar2000 still shows the tagged length as the duration; the time just keeps counting past it.
- The two jingles play once. With the endless setting on, they keep playing silence afterwards.

To get FLAC or WAV files, convert the PSF2 files with your player, for example foobar2000's *Convert* function.

## Track list

The game has no track titles; these names describe where each track plays. They were worked out from the game code and the in-game texts.

The tracks are numbered from the title screen into Career, with the amateur and pro version of a screen side by side. *Bank* is the song's number in the game's sound bank; it is also in the `comment` tag of each `.minipsf2`.

| # | Bank | Name | Where it plays | Intro | Loop |
|---|---|---|---|---|---|
| 01 | 00 | Title Screen | Right after the title movie | none | 57.313 s |
| 02 | 01 | Main Menu | After you leave the title screen; the front-end menus | 0.849 s | 39.735 s |
| 03 | 04 | Career Mode Start | The Career opening screen | 26.666 s | 42.666 s |
| 04 | 05 | Career Menu (Amateur) | Career main menu on practice days and free days | 17.767 s | 35.554 s |
| 05 | 03 | Career Menu (Pro) * | Career main menu while you have a pro contract (replaces 04) | 19.800 s | 38.400 s |
| 06 | 08 | Race Entry (Amateur) | Race entry screen without a pro contract | 2.665 s | 21.331 s |
| 07 | 06 | Race Entry (Pro) * | Race entry screen while you have a pro contract (replaces 06) | 17.453 s | 17.454 s |
| 08 | 07 | Race Day | Career main menu on a race day ("今日はレース参戦の日です") | none | 59.600 s |
| 09 | 02 | Results | The results screens; also the trophy / prize / CD room in Career | 9.600 s | 19.200 s |
| 10 | 09 | Jingle - Pro Contract Signed | With the message that you signed a pro contract with Subaru, Mitsubishi, Ford, Citroën or Peugeot | 9.850 s, once | - |
| 11 | 10 | Jingle - Sponsor Contract Signed | With the message that you signed a main or sub sponsor; probably also on the Career results screen for 2nd or 3rd place | 5.066 s, once | - |

\* The game plays 05 and 07 instead of 04 and 06 when a flag in the Career data is set. The same flag switches on the "XL" Career logo and replaces "buy parts" with "free run and tyre change" on free days, which fits a factory driver with a pro contract. That the flag means the pro contract is derived; the game never names it.

Intro and loop are the lengths in the sequence data.

### Composer

Unknown. The game's staff roll only lists the sound team of the whole game, most of whose music is streamed, and does not say who wrote which track. So it is not known who composed these eleven sequenced tracks.

## How it works

### The PSF2 set

A PSF2 file contains PS2 sound-processor (IOP) programs plus their data, and a player emulates the IOP and the SPU2 sound chip. This set runs the game's own sound driver instead of an imitation of it:

| Module | What it is |
|---|---|
| `psf2.irx` | Loader, built by this tool. Loads the other three modules and then sleeps, because Highly Experimental stops once `psf2.irx` returns. |
| `sr2006.irx` | Built by this tool. Does what the game's main program does, with the values from the game code (`SLPM_662.12`): driver init (heap `0x1F800`, DMA channel 1), driver start, memory layout with the bank in slot 1, bank header to IOP memory, samples to SPU2 RAM, activate the bank, then the song request (`0xA8000N00`, table at `0x35B930`) and the music volume command (`0xA004VV00`, volumes at `0x3727B0`). |
| `sndfi.irx` | The game's `SNDFI.IRX` (Sega SNDF driver v2.15g). Its two SIF RPC server threads are not started, because there is no EE in a PSF2. |
| `libsd.irx` | The game's `LIBSD.IRX`. |

Both game modules import `sysclib` 1.4 and `sysmem` 1.2, while Highly Experimental provides 1.3 and 1.1. The import versions are lowered; the functions they use are the same in both versions.

The SPU2 master volume is `0x3FFF`, as the game sets it. The game's BGM volume option is assumed to be at maximum. The jingles are started by the game through another path and get the driver's default volume here.

The `sr2006.irx` module is assembled by a small MIPS assembler in this repository (`sr2006rip/irxasm.py`).

### Timing and loops

The driver runs on an IOP hardware timer of exactly 5 ms. Each tick, the sequencer advances 5 ms and plays every event that is due, so notes always start on a 5 ms grid. Its time counter runs on across the end of a sequence, so there is no drift: on average a loop lasts exactly as long as in the data.

When the loop length is not a multiple of 5 ms (tracks 01, 03, 04, 06 and 07), each pass falls on the grid a little differently. Single notes can then be up to 5 ms earlier or later from pass to pass, and the pattern repeats after 5 passes. This is how the game plays them too.

The length tag of each looping track ends on the driver tick that starts the third pass, so the fade begins right after two full loops.

### The sound bank

`r2k5sngs.dat` starts with `ps2_DTPK`. Key header fields: `0x10` header size, `0x18` sample data size, `0x1C` sample data offset, `0x98` program table, `0xA4` song scripts, `0xB8` sample table. Table counts are stored as the highest index.

- A **song script** has three header words; the third holds the song number. Sequence pointers follow. A word with top byte `0x90` jumps back to the loop sequence, and a pointer with top byte `0x91` marks the last sequence of a song that plays once. Looping songs start with a 250 ms silent pre-roll sequence.
- **Sequences** are MIDI-like with running status. The last data byte of an event has bit 7 set when no delta time follows; otherwise a MIDI variable-length delta in milliseconds follows. Note-off carries only the key, pitch bend a single 7-bit value, and `FF 2F 00` ends the track.
- **Samples** are PS-ADPCM, the SPU2's own format.

## License and legal

The code in this repository is released under the [MIT License](LICENSE).

This tool only reads files you already have. Everything it writes contains Sega's music, samples and sound driver, and Sony's `LIBSD.IRX`. Keep it for your own use; do not redistribute it. Sega Rally is a trademark of Sega; this project is not affiliated with Sega.
