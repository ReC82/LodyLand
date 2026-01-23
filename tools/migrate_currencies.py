#!/usr/bin/env python3
"""
Database migration script: Rename currency columns

Changes:
  - coins  → shards
  - diams  → essence

Usage:
  python tools/migrate_currencies.py

IMPORTANT: Make a backup of game.db before running!
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import engine
from sqlalchemy import text, inspect


def backup_database():
    """Create a backup of the database"""
    from datetime import datetime
    import shutil
    
    db_path = Path("game.db")
    if not db_path.exists():
        print("⚠️  No database file found (game.db)")
        return False
    
    backup_name = f"game.db.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(db_path, backup_name)
    print(f"✅ Backup created: {backup_name}")
    return True


def get_column_names(table_name: str) -> list:
    """Get list of column names for a table"""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return [col["name"] for col in columns]


def migrate():
    """Perform the migration"""
    print("=" * 60)
    print("DATABASE MIGRATION: coins → shards, diams → essence")
    print("=" * 60)
    
    # Step 1: Backup
    print("\n[1/4] Creating backup...")
    if not backup_database():
        print("❌ Backup failed, aborting migration")
        return False
    
    # Step 2: Check current schema
    print("\n[2/4] Checking current schema...")
    try:
        columns = get_column_names("players")
        print(f"   Current columns: {', '.join(columns)}")
        
        has_coins = "coins" in columns
        has_diams = "diams" in columns
        has_shards = "shards" in columns
        has_essence = "essence" in columns
        
        if not has_coins and not has_diams:
            print("✅ Migration already done (no coins/diams columns)")
            return True
        
        if has_shards or has_essence:
            print("⚠️  New columns already exist, migration may have been partially done")
            response = input("   Continue anyway? (y/N): ")
            if response.lower() != 'y':
                print("❌ Migration cancelled")
                return False
        
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        return False
    
    # Step 3: Rename columns
    print("\n[3/4] Renaming columns...")
    try:
        with engine.connect() as conn:
            # SQLite doesn't support RENAME COLUMN in old versions
            # We need to check SQLite version
            version = conn.execute(text("SELECT sqlite_version()")).scalar()
            print(f"   SQLite version: {version}")
            
            # Rename coins → shards
            if has_coins and not has_shards:
                try:
                    conn.execute(text("ALTER TABLE players RENAME COLUMN coins TO shards"))
                    print("   ✅ Renamed: coins → shards")
                except Exception as e:
                    print(f"   ❌ Error renaming coins: {e}")
                    print("   ℹ️  This might require SQLite 3.25.0+")
                    conn.rollback()
                    return False
            
            # Rename diams → essence
            if has_diams and not has_essence:
                try:
                    conn.execute(text("ALTER TABLE players RENAME COLUMN diams TO essence"))
                    print("   ✅ Renamed: diams → essence")
                except Exception as e:
                    print(f"   ❌ Error renaming diams: {e}")
                    conn.rollback()
                    return False
            
            conn.commit()
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False
    
    # Step 4: Verify
    print("\n[4/4] Verifying migration...")
    try:
        new_columns = get_column_names("players")
        print(f"   New columns: {', '.join(new_columns)}")
        
        if "shards" in new_columns and "essence" in new_columns:
            print("\n" + "=" * 60)
            print("✅ MIGRATION SUCCESSFUL!")
            print("=" * 60)
            print("\nNext steps:")
            print("  1. Test the application")
            print("  2. If everything works, you can delete the backup")
            print("  3. Commit the changes to git")
            return True
        else:
            print("❌ Verification failed: columns not renamed properly")
            return False
        
    except Exception as e:
        print(f"❌ Verification error: {e}")
        return False


def main():
    """Main entry point"""
    print("\n⚠️  WARNING: This will modify your database!")
    print("   A backup will be created automatically.\n")
    
    response = input("Continue with migration? (y/N): ")
    if response.lower() != 'y':
        print("❌ Migration cancelled")
        return 1
    
    success = migrate()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())