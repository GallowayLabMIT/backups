# Cold backup helpers
This script requires Python to run! It only requires standard-library packages,
so can be run outside of a virtual environment.

Backups can be managed, checked, and restored manually, without Python if needed. See the ending section for details.

## Nomenclature
- These backups are "cold backups", e.g. backups that are not actively plugged into a computer. Hard drives live for
  roughly 8 years when plugged in, so cold backups can last pretty much indefinitely.
- Even with good storage conditions, you need to regularly check for corruption coming from e.g. cosmic rays or X-rays hitting the disk.
- This software lets you maintain **backup sets**, e.g. pairs, triplets, or larger sets of (nearly) identical drives.
- Each **backup set** has a **base name**. For the purpose of this readme, the base name will be "apple".
- The `cold_backups` repo should be cloned into a subfolder (probably named `cold_backups`). You run this script from inside that directory.
- Whenever you run it, you specify drive roots for the entire backup set to work on. If you specify multiple roots,
  then a _single_ add/list/verify command is sufficient to do the action on each drive. You don't need to repeat the add per-drive
  if you are specifying multiple roots.
- It is possible to run commands on less than the full backup set (e.g. run a verify on a single drive in a two-drive backup set) by only specifying
  some of the roots, but this is not advised.
- All backup metadata is stored in the `manifest.json` file. This is openable and examinable by a normal text editor (e.g. VS Code).
  Data corruption may cause you to need to manually edit this file.

## Starting a new pair of drives checklist
- [ ] Buy a pair of hard drives. It is highly recommended to buy a Conventional Magnetic Recording (CMR)-type hard drive, as opposed to [Shingled Magnetic Recording](https://en.wikipedia.org/wiki/Shingled_magnetic_recording) which has higher data density but lower rates. As of 2023, Western Digital Blue or Red drives are generally reliable; Seagate are less so. Western Digital sells both CMR and SMR drives in both the Blue and Red lineups.
- [ ] Create a partition table. On Windows, this involves [going to "Disk Management"](https://learn.microsoft.com/en-us/windows-server/storage/disk-management/initialize-new-disks), finding the drive, right clicking and hitting "Initialize Disk", and choosing the GPT partition table type.
- [ ] Create a hard drive partition spanning the whole drive. Use the NTFS file system. You can do this in the same Disk Management view.
- [ ] Start a terminal (Powershell on Windows) and `cd` or otherwise move to the root of
  one of the backup drives.
- [ ] Clone this repository into the root of each drive. It is a public repository so
  can be cloned with `git clone https://github.com/GallowayLabMIT/cold_backups.git`. This will create a subfolder called `cold_backups` with the relevant code inside.
- [ ] Initialize the pair of drives:
    - Locate the path to the drive to be paired. On Windows this path probably looks like `H:\`.
    - Decide and document a base name for these drives. If you set a base name of "apple", the generated names will be "apple_1" and "apple_2".
    - Run `python -m backup_helper --root "PATH_TO_FIRST_DRIVE_ROOT" --root "PATH_TO_SECOND_DRIVE_ROOT" init --base-name "BASE_NAME"`

## Adding new items checklist
- [ ] Copy new items into the `data` subfolder on *all* drives in the backup set.
- [ ] Run `python -m backup_helper --root "FIRST_DRIVE" --root "SECOND_DRIVE" list`, and confirm that your new files are listed.
- [ ] Decide on the amount of recovery data you want for each new file. A good default is 5%, from which you would write `--parity-percent 5`
  Then, for each new file run `python -m backup_helper --root "FIRST_DRIVE" --root "SECOND_DRIVE" add --parity-percent N data/path/to/file`
- [ ] Run `python -m backup_helper --root "FIRST_DRIVE" --root "SECOND_DRIVE" list` again once finished to check.

## Verification checklist (Yearly run)
- [ ] Check for a newer version of [par2](https://github.com/Parchive/par2cmdline/releases),
  and update the binary in `bin` if necessary. You want the `par2cmdline-x.y.z-win-x64.zip` file.
  - Update the binary `in the git repo`, while bumping the minor version number in `backup_helper.py` script (e.g. the second integer in the tuple).
  - Once you push, on each drive, do a `git pull` before running the various scripts.
  - The version number bump ensures that we won't accidentally use an older version of `par2`.
- [ ] Perform the automated backup verification on each pair of drives, with
  `python -m backup_helper --root "FIRST_DRIVE" --root "SECOND_DRIVE" verify`, run from the root of one of the drives.
  The drive paths are likely something like `F:\` on Windows.
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
