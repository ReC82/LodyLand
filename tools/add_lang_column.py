#!/usr/bin/env python3
"""
Add lang column to players table

Usage:
  python tools/add_lang_column.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import engine
from sqlalchemy import text


def add_lang_column():
    """Add lang column to players table"""
    print("=" * 60)
    print("ADD LANG COLUMN TO PLAYERS TABLE")
    print("=" * 60)
    
    with engine.connect() as conn:
        try:
            # Check if column exists
            result = conn.execute(text("PRAGMA table_info(players)"))
            columns = [row[1] for row in result.fetchall()]
            
            if "lang" in columns:
                print("✅ Column 'lang' already exists, nothing to do.")
                return True
            
            # Add column
            print("\n[1/2] Adding 'lang' column...")
            conn.execute(text("ALTER TABLE players ADD COLUMN lang VARCHAR(5) DEFAULT 'fr' NOT NULL"))
            
            print("   ✅ Column added")
            
            # Verify
            print("\n[2/2] Verifying...")
            result = conn.execute(text("PRAGMA table_info(players)"))
            columns = [row[1] for row in result.fetchall()]
            
            if "lang" in columns:
                print("   ✅ Verification successful")
                conn.commit()
                print("\n" + "=" * 60)
                print("✅ MIGRATION COMPLETE!")
                print("=" * 60)
                return True
            else:
                print("   ❌ Verification failed")
                conn.rollback()
                return False
                
        except Exception as e:
            print(f"❌ Error: {e}")
            conn.rollback()
            return False


if __name__ == "__main__":
    success = add_lang_column()
    sys.exit(0 if success else 1)