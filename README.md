# Cold backup helpers
This script requires Python to run! It only requires standard-library packages,
so can be run outside of a virtual environment.

Backups can be managed, checked, and restored manually, without Python if needed.

## Starting a new pair of drives checklist
- [ ] Start a terminal (Powershell on Windows) and `cd` or otherwise move to the root of
  one of the backup drives.
- [ ] Clone this repository into the root of each drive. It is a public repository so
  can be cloned with `git clone https://github.com/GallowayLabMIT/cold_backups.git`
- [ ] Initialize the pair of drives:
    - Locate the path to the drive to be paired. On Windows this path probably looks like `H:\`
    - Decide and document a base name for these drives. If you set a base name of "apple", the generated names will be "apple_1" and "apple_2"
    - Run `python -m backup_helper --paired-root "PATH_TO_ROOT" init --base-name "BASE_NAME"`

## Adding new items checklist
- [ ] Copy new items into the `data` subfolder on *both* drives.
- [ ] Run `python -m backup_helper --paired-root "PATH_TO_ROOT" list`, and confirm that your new files are listed.
- [ ] Decide on the amount of recovery data you want for each new file. A good default is 5%, from which you would write `--parity-percent 5`
  Then, for each new file run `python -m backup_helper --paired-root "PATH_TO_ROOT" add --parity-percent N data/path/to/file`
- [ ] Run `python -m backup_helper --paired-root "PATH_TO_ROOT list"` again once finished to check.

## Verification checklist (Yearly run)
- [ ] Check for a newer version of [par2](https://github.com/Parchive/par2cmdline/releases),
  and update the binary in `bin` if necessary. You want the `par2cmdline-x.y.z-win-x64.zip` file.
  - Update the binary `in the git repo`, while bumping the minor version number in `backup_helper.py` script (e.g. the second integer in the tuple).
  - Once you push, on each drive, do a `git pull` before running the various scripts.
  - The version number bump ensures that we won't accidentally use an older version of `par2`.
- [ ] Perform the automated backup verification on each pair of drives, with
  `python -m backup_helper --paired-root "PATH_TO_ROOT verify"`, run from the root of one of the drives.
  `PATH_TO_ROOT` is likely something like `F:\` on Windows.
- [ ] Do a manual spot-check to test manual changes. Open the `manifest.json` file and pick one of the files. Then:
  - [ ] In a terminal (Powershell), run `Get-FileHash FILE_NAME -Algorithm SHA256` and check that it matches the manifest list.
  - [ ] In a terminal (Powershell), find the path to `par2` (it should be in the bin folder) and run `path/to/par2.exe verify FILE_NAME`

## Recovery instructions
- Full instructions are at https://github.com/Parchive/par2cmdline
- In short, if you see a failure on the verify, you should see output that says "Repair is required", followed by information.
  Ideally, it should say "Repair is possible". If not, you may have to copy extra recovery blocks (the volNNN+YY.par2 files).
- In a terminal, find the path to `par2` (it should be in the bin folder) and run `path/to/par2.exe repair FILE_NAME`

## Full discussion of what is happening
The script is a nice wrapper around two key features:
1. **Hashing** tracked files with the SHA256 algorithm. This gives you a (reasonably) unique number/string that represents the file.
   Any change in the file should _dramatically_ change the hash, so this gives us a quick way of seeing if the file is corrupted or not.
2. Generating and verifying **parity** data using the program [par2](https://github.com/Parchive/par2cmdline). The hash tells us if the
   file is corrupted, but how do we recover? `par2` solves this by generating the backup data necessary for recovering information.

You can manually do these things! In Windows, you can generate and check the hash using `Get-FileHash`; there are other tools on other OS's,
just look up "SHA256 hash file". You can manually compute parity data using `par2 create <file name>`, manually verify it with `par2 verify <file name>`,
and manually repair with `par2 repair <file name>`.

What is the script doing? The script does a lot of nice features, like:
1. Automatically hash verifying a bunch of files, and automatically running `par2 verify`
2. Versioning the manifest file, so we ensure we are using the right script version.
3. Keeping data between two drives paired, e.g. easily mananaging hashes and recovery data even though it is on two separate hard drives.
