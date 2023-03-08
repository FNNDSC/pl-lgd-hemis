#!/usr/bin/env python
import os
import subprocess as sp
import sys
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from chris_plugin import chris_plugin, PathMapper
from loguru import logger

__version__ = '1.0.0'

DISPLAY_TITLE = r"""
       _        _           _        _                    _     
      | |      | |         | |      | |                  (_)    
 _ __ | |______| | __ _  __| |______| |__   ___ _ __ ___  _ ___ 
| '_ \| |______| |/ _` |/ _` |______| '_ \ / _ \ '_ ` _ \| / __|
| |_) | |      | | (_| | (_| |      | | | |  __/ | | | | | \__ \
| .__/|_|      |_|\__, |\__,_|      |_| |_|\___|_| |_| |_|_|___/
| |                __/ |                                        
|_|               |___/                                         
"""


parser = ArgumentParser(description='WM mask extraction for LGD project data',
                        formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument('-p', '--pattern', default='**/*seg*.mnc', type=str,
                    help='input segmentation files glob')


@chris_plugin(
    parser=parser,
    title='LGD WM Hemispheres',
    category='Surfaces',
    min_memory_limit='500Mi',
    min_cpu_limit='1000m',
    min_gpu_limit=0
)
def main(options: Namespace, inputdir: Path, outputdir: Path):
    print(DISPLAY_TITLE, flush=True)

    mapper = PathMapper.file_mapper(inputdir, outputdir, glob=options.pattern)
    input_files, output_files = zip(*mapper)

    proc = len(os.sched_getaffinity(0))
    logger.debug('Using {} threads', proc)

    with ThreadPoolExecutor(max_workers=proc) as pool:
        results = pool.map(lgd_hemis_wrapper, input_files, output_files)

    if not all(results):
        sys.exit(1)


def lgd_hemis_wrapper(seg: Path, output_path: Path) -> bool:
    """
    :returns: True if successful
    """
    t2 = find_t2(seg)

    if t2 is None:
        return False

    wm_left = output_path.with_stem('wm_left')
    wm_right = output_path.with_stem('wm_right')
    logger.info(f'{seg.parent} (segmentation={seg.name} t2={t2.name}) -> {output_path.with_stem("wm_{left,right}")}')

    try:
        lgd_hemis(seg, t2, wm_left, wm_right)
        return True
    except sp.CalledProcessError as e:
        logger.error(f'{e.cmd} exited with code: {e.returncode}')
        return False


def lgd_hemis(seg: Path, t2: Path, wm_left: Path, wm_right: Path) -> None:
    """
    Prepares intermediate input files for and then runs ``extract_wm_hemispheres``
    """
    with TemporaryDirectory(prefix=seg.parent.name) as tmpdir:
        brain_mask = os.path.join(tmpdir, 'brain_mask.mnc')
        classified = os.path.join(tmpdir, 'classified.mnc')
        create_brain_mask(seg, brain_mask)
        regions2classified(seg, classified)
        extract_wm_hemispheres(classified, t2, brain_mask, wm_left, wm_right)


def create_brain_mask(seg, output) -> None:
    """
    Create whole brain mask.
    """
    cmd = ('minccalc', '-quiet', '-unsigned', '-byte', '-expr', 'A[0]>0.5', seg, output)
    sp.run(cmd, check=True)


def regions2classified(seg, output) -> None:
    """
    Convert Lana's fetal brain region segmentations to the
    classified labeled expected by ``extract_wm_hemispheres``

    -  WM = 3
    -  GM = 2
    - CSF = 1
    -  BG = 0
    """

    cp = 'if(A[0]>111.5&&A[0]<113.5){out=2}'
    csf = 'if(A[0]>123.5&&A[0]<124.5){out=1}'
    cerebellum = 'if(A[0]>99.5&&A[0]<101.5){out=1}'
    midbrain = 'if(A[0]>93.5&&A[0]<95.5){out=1}'
    bg = 'if(A[0]<0.5){out=0}'
    wm = '{out=3}'
    regions = (bg, csf, cerebellum, midbrain, cp, wm)
    expr = ' else '.join(regions)

    cmd = ('minccalc', '-quiet', '-unsigned', '-byte', '-expr', expr, seg, output)
    sp.run(cmd, check=True)


def extract_wm_hemispheres(classified, t1, brain_mask, wm_left, wm_right):
    """
    Create white matter masks for left and right hemispheres.

    Using t2 as t1 seems to work just fine.
    """
    # modified extract_wm_hemispheres script, see base/Dockerfile for details
    cmd = ('extract_wm_hemispheres_fetus', classified, t1, brain_mask, 'none', 'none', wm_left, wm_right)
    sp.run(cmd, stdout=sp.DEVNULL, stderr=sp.STDOUT, check=True)


def find_t2(seg: Path) -> Optional[Path]:
    """
    Every subject directory is assumed to contain exactly two files.
    The file which is not the segmentations, is the t2.
    """
    glob = seg.parent.glob(f'*{seg.suffix}')
    others = filter(lambda p: p.name != seg.name, glob)
    first = next(others, None)
    second = next(others, None)

    if second is not None:
        logger.error(f'Too many files in {seg.parent}')
        return None
    if first is None:
        logger.error(f't2 image not found in {seg.parent}')
        return None
    return first


if __name__ == '__main__':
    main()
