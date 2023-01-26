"""
Sequencing backup helper
=========================
This provides a nice interface to do two things:
    1. Compute the SHA256 hash of files on a hard drive, and...
    2. Compare file hashes to the stored hashes.
    3. Run `par2` on the files to generate and/or verify parity data.

You can do all of these things manually!

This also only requires standard library packages, so you don't need
a virtual environment.
"""
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import argparse
from typing import Any, BinaryIO, Dict, List, Optional, Tuple
import hashlib
import math
import shutil
import sys
import subprocess
import re

VERSION = (1,0,0)



@dataclass
class JSONDataManifest:
    """
    Stores the raw loaded manifest data
    """
    version: str
    repo_name: str
    pair_name: str
    files: dict[str, str]

@dataclass
class DataManifest:
    """
    Stores the post-processed data manifest file
    """
    # Store the version as a triple int string.
    # This doesn't handle the edge cases with weird version number (1.2.3pre-alpha-1234),
    # but is the most resilient far into the future
    version: Tuple[int, int, int]
    repo_name: str
    pair_name: str
    files: dict[Path, str]

@dataclass
class FileStatus:
    """
    Stores the basic file information needed for comparisons
    when iterating over the data subdir tree
    """
    filename: Path
    rel_filename: Path
    has_hash: bool
    has_par2_files: bool
    has_file: bool

# ----- Pretty-printing helper functions --------
def version_string(version: Tuple[int,int,int]) -> str:
    return ".".join([str(x) for x in version])

def format_bytes(n_bytes: int) -> str:
    """
    Pretty-formats a given number of bytes
    """
    if n_bytes == 0:
        return '0 B'

    negative = False
    if n_bytes < 0:
        negative = True
        n_bytes = -n_bytes 
    
    unit_idx = math.floor(math.log(n_bytes, 1024))
    unit = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB'][unit_idx]
    return f'{round(n_bytes / 1024 ** unit_idx, 2)} {unit}'
    
def hash_file_with_progress(
        filename: Path, *,
        bufsize: int = 1024 * 1024 * 4,
        display_freq: int = 10,
        progress_width: int = 50,
        ) -> str:
    """
    SHA256-hashes a given file by filename,
    showing a progress bar as hashing proceeds
    """

    hash = hashlib.sha256()
    # Read in 4MB chunks. Actual size doesn't matter too much...
    
    filesize = filename.stat().st_size
    processed_size = 0

    print('\n', flush=True)
    with filename.open('rb') as f:
        i = display_freq
        done = False
        while True:
            data = f.read(bufsize)
            if not data:
                # Do done trick so we output the final output tick
                done = True
            else:
                processed_size += len(data)
                hash.update(data)

            i -= 1
            if i == 0 or done:
                i = display_freq
                n_hashes = int(progress_width * processed_size / filesize)
                print("{}: [{}{}] {} / {}".format(
                    filename.name,
                    '#' * n_hashes,
                    '.' * (progress_width - n_hashes),
                    format_bytes(processed_size),
                    format_bytes(filesize)
                ), end='\r', flush=True)
            if done:
                break
    print('\n', flush=True)
    
    return hash.hexdigest()

# ----- Actual helper implementation functions --------
def load_manifest(root: Path) -> Optional[DataManifest]:
    """
    Attempts to load a JSON manifest from the root path.
    """
    manifest_filename = root / 'manifest.json'
    if not manifest_filename.exists():
        print(f'Manifest file {manifest_filename} does not exist! You may need to `init`')
        return None
    
    try:
        with manifest_filename.open('r') as file:
            raw_manifest = JSONDataManifest(**json.load(file))
        manifest = DataManifest(
            version=tuple(map(int, (raw_manifest.version.split('.')))),
            repo_name=raw_manifest.repo_name,
            pair_name=raw_manifest.pair_name,
            files={Path(k): v for k,v in raw_manifest.files.items()}
        )

        if manifest.version > VERSION:
            raise RuntimeError(f'Backup helper version listed in manifest ({version_string(manifest.version)}) is newer than this software version ({version_string(VERSION)})!'
                " You probably need to `git pull` to get the latest version.")
        return manifest

    except Exception as e:
        print(e)
        return None

def save_manifest(root: Path, manifest: DataManifest) -> None:
    """
    Saves the given manifest back to the current root, using the current version
    """
    towrite = JSONDataManifest(
        version=version_string(manifest.version),
        repo_name=manifest.repo_name,
        pair_name=manifest.pair_name,
        files={str(k): v for k,v in manifest.files.items()}
    )
    with (root / 'manifest.json').open('w') as f:
        json.dump(asdict(towrite), f, indent=2, sort_keys=True)

def locate_par2(root: Path) -> Path:
    """
    Locates the par2 executable, either globally installed
    or located within the repo (inside `bin`).
    """
    par2_in_path = shutil.which('par2')
    par2 = Path(par2_in_path) if par2_in_path is not None else None
    if par2 is None:
        # Try to locate within the bin path if on Windows
        if sys.platform == 'win32':
            winpath = root / 'bin' / 'par2.exe'
            if winpath.exists():
                par2 = winpath
    # Exit if par2 is still none
    if par2 is None:
        raise RuntimeError("Could not locate the par2 executable! "
            "Check that you are in the root of a backup drive and "
            "have par2 installed (if not on Windows)"
        )
    return par2

# ------ Subfunction implementation functions --------
def init_paired_backups(root: Path, name: str, paired_name: str) -> None:
    """
    Initializes the paired backup system, given a root path, name, and paired name.
    """
    # Abort if a manifest already exists
    if (root / 'manifest.json').exists():
        raise RuntimeError(f"Backup repository already exists on root {root}")
    # Create the data folder if it does not exist
    if not (root / 'data').exists():
        (root / 'data').mkdir()
    # Write an empty manifest 
    save_manifest(root, DataManifest(VERSION, name, paired_name, {}))

def add_file(root: Path, manifest: DataManifest, file: Path, parity_percent: int) -> None:
    """
    Adds a file to the (single) linked manifest, and uses Par2 to compute parity information
    """
    # Get the root-relative path
    try:
        rel_file = file.resolve().relative_to(root)
    except ValueError:
        raise RuntimeError(f"Requested file {str(file)} is not within the current backup drive root!")
    # Hash the file first:
    print(f'Computing hash for {str(rel_file)}:')
    filehash = hash_file_with_progress(file)

    # Launch par2
    launch_args = [str(locate_par2(root)), 'create', f'-r{parity_percent}', str(file.name)]
    wd = file.parent
    print(f'Running `{" ".join(launch_args)}` in directory {str(wd)}')
    subprocess.run(launch_args, check=True, cwd=wd)

    # Update the manifest
    if rel_file in manifest.files and manifest.files[rel_file] != filehash:
        raise RuntimeError(f"File hash mismatch when adding file! File {str(file)} "
                "likely differs between paired hard drives.\n"
                f"Expected hash: {manifest.files[rel_file]}\n"
                f"Actual hash: {filehash}"
        )
    manifest.files[rel_file] = filehash

def verify_file(root: Path, manifest: DataManifest, file: Path) -> bool:
    """
    Verifies that a given file has the correct hash and proper `par2` recovery data.
    """
    # Get the root-relative path
    try:
        rel_file = file.resolve().relative_to(root)
    except ValueError:
        raise RuntimeError(f"Requested file {str(file)} is not within the current backup drive root!")
    
    if rel_file not in manifest.files:
        print(f'File {str(rel_file)} is missing hash information!')
        return False
    # Hash the file first:
    print(f'Computing hash for {str(rel_file)}:')
    filehash = hash_file_with_progress(file)
    bad = False
    if filehash != manifest.files[rel_file]:
        print(f'File {str(rel_file)} appears to be corrupted!\nExpected hash:{manifest.files[rel_file]}\nActual hash:{filehash}')
        bad = True

    # Launch par2
    launch_args = [str(locate_par2(root)), 'verify', file.name + '.par2']
    wd = file.parent
    print(f'Running `{" ".join(launch_args)}` in directory {str(wd)}')
    run_result = subprocess.run(launch_args, check=False, cwd=wd, capture_output=True)
    if run_result.returncode != 0:
        print(run_result.stdout.decode('utf8'))
        print(run_result.stderr.decode('utf8'))
        print(f'File {str(rel_file)} appears to be corrupted or have corrupted recovery data! See recovery instructions.')
        bad = True
    
    return not bad

def list_files(root: Path, manifest:DataManifest) -> List[FileStatus]:
    """
    Finds all files in the data directory with their basic status
    """
    results: Dict[Path, FileStatus] = {}
    for file in (root / 'data').glob('**/*'):
        rel_filename = file.resolve().relative_to(root)
        if file.suffix == '.par2':
            # Try to locate the base filename
            basename_match = re.match(r"(.*?)(?:\.vol\d+\+\d+)?\.par2", file.name)
            if basename_match is None:
                raise RuntimeError(f"Unexpected par2 file: {str(rel_filename)}")
            
            basepath_rel = rel_filename.with_name(basename_match.group(1))
            basepath = file.with_name(basename_match.group(1))
            if basepath_rel not in results:
                results[basepath_rel] = FileStatus(filename=basepath, rel_filename=basepath_rel,
                                            has_hash=basepath_rel in manifest.files, has_par2_files=True, has_file=False)
            else:
                results[basepath_rel].has_par2_files = True
        else:
            if rel_filename not in results:
                results[rel_filename] = FileStatus(filename=file, rel_filename=rel_filename,
                                            has_hash=rel_filename in manifest.files, has_par2_files=False, has_file=True)
            else:
                results[rel_filename].has_file = True
    return sorted(results.values(), key=lambda v: (v.has_hash, v.has_file, v.has_par2_files, v.rel_filename))
            



parser = argparse.ArgumentParser(
    description="Handles data on pairs of PAR2-protected hard drives."
)
paired = parser.add_mutually_exclusive_group(required=True)
paired.add_argument('--orphan', action='store_true')
paired.add_argument('--paired-root')

subparsers = parser.add_subparsers(help='sub-command help', dest='subparser_type', required=True)
init_parser = subparsers.add_parser('init', help='Initialize a pair of backup drives')
init_parser.add_argument('--base-name', required=True)

list_parser = subparsers.add_parser('list', help='Lists the files and their current backup status')
list_parser.add_argument('--all', action='store_true')

add_parser = subparsers.add_parser('add', help='Adds files to the manifest, hashing it and creating parity recovery data')
add_parser.add_argument('--parity-percent', default=5, type=int)
add_parser.add_argument('file')

verify_parser = subparsers.add_parser('verify', help='Verifies all files in the manifest')

if __name__ == '__main__':
    root = Path(__file__).parent
    args = parser.parse_args()
    paired_root = Path('.')
    if not args.orphan:
        paired_root = Path(args.paired_root)

    if args.subparser_type == 'init':
        if args.orphan:
            init_paired_backups(root, args.base_name, '')
        if not args.orphan:
            init_paired_backups(root, args.base_name + '_1', args.base_name + '_2')
            init_paired_backups(paired_root, args.base_name + '_2', args.base_name + '_1')
    else:
        # Check that the manifests are equal
        manifest = load_manifest(root)
        if manifest is None:
            raise RuntimeError(f"Unable to locate manifest for drive {str(root)}!")
        if not args.orphan:
            paired_manifest = load_manifest(paired_root)
            if paired_manifest is None:
                raise RuntimeError(f"Unable to locate manifest for drive {str(paired_root)}")
            # Check that these are the same
            if manifest.version != paired_manifest.version:
                raise RuntimeError("Manifest versions differ! You should compare manifests to figure out what happened (with a diff tool like git diff)")
            if manifest.repo_name != paired_manifest.pair_name or manifest.pair_name != paired_manifest.repo_name:
                raise RuntimeError('Manifests do not appear to be paired based on their names! You should compare the manifests to figure out what happened (with a diff tool like git diff)')
            if manifest.files != paired_manifest.files:
                raise RuntimeError("Manifest files do not match! You should compare the manifests to figure out what happened (with a diff tool like git diff)")

        if args.subparser_type == 'list':
            to_list = [(root, manifest.repo_name, list_files(root, manifest))]
            if not args.orphan:
                to_list.append((paired_root, manifest.pair_name, list_files(paired_root, manifest)))
            for list_root, root_name, file_list in to_list:
                valid_count = 0
                print(f'{root_name} ({str(list_root)}) files:')
                for file in file_list:
                    valid = file.has_hash and file.has_par2_files and file.has_file
                    if valid:
                        valid_count += 1
                    if args.all or not valid:
                        print('{} {} {} {}'.format(
                            '[NO HASH]' if not file.has_hash else '',
                            '[NO PARITY]' if not file.has_par2_files else '',
                            '[MISSING]' if not file.has_file else '',
                            str(file.rel_filename)
                        ))
                if not args.all:
                    print(f'{valid_count} valid tracked files not shown. Use --all to list all.')

        elif args.subparser_type == 'add':
            # Compute relative path for file
            file_relpath = Path(args.file).resolve().relative_to(root)

            if not args.orphan:
                # Check that the file exists in both paths
                if not ((root / file_relpath).exists() and (paired_root / file_relpath).exists()):
                    raise RuntimeError("File to add does not exist on both paired drives!")

            add_file(root, manifest, root / file_relpath, args.parity_percent)

            if not args.orphan:
                add_file(paired_root, manifest, paired_root / file_relpath, args.parity_percent)
            
            save_manifest(root, manifest)
            if not args.orphan:
                pair_name = manifest.pair_name
                manifest.pair_name = manifest.repo_name
                manifest.repo_name = pair_name
                save_manifest(paired_root, manifest)

        elif args.subparser_type == 'verify':
            failed = False
            for file in manifest.files:
                if not verify_file(root, manifest, root / file):
                    failed = True
                if not args.orphan:
                    if not verify_file(paired_root, manifest, paired_root / file):
                        failed = True
            if failed:
                print('File verification failed!')
                sys.exit(1)
        else:
            raise RuntimeError('unknown subcommand')