#!/usr/bin/env python3
"""
Convert YAML files: coins/diams → currency format

Converts old format:
  - type: coins
    amount: 100

To new format:
  - type: currency
    currency: primary
    amount: 100

Usage:
  python tools/convert_yaml_currencies.py
"""

import sys
from pathlib import Path
import yaml


def convert_rewards(rewards: list) -> list:
    """Convert rewards list from old to new format"""
    if not rewards:
        return rewards
    
    new_rewards = []
    
    for reward in rewards:
        r_type = reward.get("type")
        
        if r_type == "coins":
            # coins → currency:primary
            new_rewards.append({
                "type": "currency",
                "currency": "primary",
                "amount": reward.get("amount", 0)
            })
        
        elif r_type == "diams":
            # diams → currency:premium
            new_rewards.append({
                "type": "currency",
                "currency": "premium",
                "amount": reward.get("amount", 0)
            })
        
        else:
            # Keep other reward types unchanged
            new_rewards.append(reward)
    
    return new_rewards


def convert_level_file(filepath: Path) -> int:
    """Convert a single level YAML file. Returns number of changes."""
    try:
        with filepath.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        if "levels" not in data:
            return 0
        
        changes = 0
        
        for level in data["levels"]:
            if "rewards" in level:
                old_rewards = level["rewards"]
                new_rewards = convert_rewards(old_rewards)
                
                # Count changes
                if old_rewards != new_rewards:
                    changes += 1
                    level["rewards"] = new_rewards
        
        # Write back
        if changes > 0:
            with filepath.open("w", encoding="utf-8") as f:
                yaml.safe_dump(
                    data,
                    f,
                    sort_keys=False,
                    allow_unicode=True,
                    default_flow_style=False,
                    indent=2
                )
        
        return changes
    
    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}")
        return 0


def convert_quest_file(filepath: Path) -> int:
    """Convert a quest YAML file. Returns number of changes."""
    try:
        with filepath.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        if "quest_templates" not in data:
            return 0
        
        changes = 0
        
        for quest_key, quest_data in data["quest_templates"].items():
            # Check reward_templates
            if "reward_templates" in quest_data:
                rt = quest_data["reward_templates"]
                
                # Rename coins_min/max → shards_min/max
                if "coins_min" in rt:
                    rt["shards_min"] = rt.pop("coins_min")
                    changes += 1
                
                if "coins_max" in rt:
                    rt["shards_max"] = rt.pop("coins_max")
                    changes += 1
                
                # Rename diams_min/max → essence_min/max
                if "diams_min" in rt:
                    rt["essence_min"] = rt.pop("diams_min")
                    changes += 1
                
                if "diams_max" in rt:
                    rt["essence_max"] = rt.pop("diams_max")
                    changes += 1
        
        # Write back
        if changes > 0:
            with filepath.open("w", encoding="utf-8") as f:
                yaml.safe_dump(
                    data,
                    f,
                    sort_keys=False,
                    allow_unicode=True,
                    default_flow_style=False,
                    indent=2
                )
        
        return changes
    
    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}")
        return 0


def main():
    """Main conversion process"""
    print("=" * 60)
    print("YAML CURRENCY CONVERSION")
    print("=" * 60)
    
    total_changes = 0
    
    # Convert levels
    print("\n[1/2] Converting level files...")
    levels_dir = Path("app/data/levels")
    
    if levels_dir.exists():
        for level_file in levels_dir.glob("*.yml"):
            if level_file.name == "levels.yml":
                continue  # Skip generated file
            
            changes = convert_level_file(level_file)
            if changes > 0:
                print(f"  ✅ {level_file.name}: {changes} level(s) updated")
                total_changes += changes
    
    # Convert quests
    print("\n[2/2] Converting quest files...")
    quests_dir = Path("app/data/quests")
    
    if quests_dir.exists():
        for quest_file in quests_dir.rglob("*.yml"):
            changes = convert_quest_file(quest_file)
            if changes > 0:
                print(f"  ✅ {quest_file.relative_to('app/data')}: {changes} change(s)")
                total_changes += changes
    
    # Summary
    print("\n" + "=" * 60)
    if total_changes > 0:
        print(f"✅ CONVERSION COMPLETE: {total_changes} change(s) made")
        print("\nNext steps:")
        print("  1. Review changes: git diff app/data/")
        print("  2. Test the game")
        print("  3. Commit: git add app/data/ && git commit")
    else:
        print("✅ No changes needed (already converted)")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())