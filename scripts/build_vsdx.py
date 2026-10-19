#!/usr/bin/env python3
"""Write a new single-page native VSDX from a basic scene JSON."""
import argparse
import json
from pathlib import Path
from native_vsdx import build_scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    scene = json.loads(args.scene.read_text(encoding='utf-8'))
    mapping = build_scene(scene, args.output, overwrite=args.overwrite)
    print(json.dumps({'output': str(args.output.resolve()), 'native_ids': mapping}, ensure_ascii=False))


if __name__ == '__main__':
    main()
