# -*- coding: utf-8 -*-
"""RetroWave 啟動器：python run.py（等同 cd src && python -m retrowave）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from retrowave.app import main

if __name__ == "__main__":
    main()
