"""Compatibility entry point for the complete source check."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_source import check
if __name__=='__main__':check()
