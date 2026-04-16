# Admin Panel Documentation

## Overview

The Admin Panel is a comprehensive management interface for LodyLand game administrators. It provides complete control over game content, players, and game mechanics through a professional web interface.

**Access**: Game menu → "🔐 Admin Panel" (or `/admin/` route)

---

## Role-Based Access Control

The admin system uses three permission levels:

### Super Admin (`super_admin`)
- **Full access** to all admin features
- Can **manage user roles** (assign/revoke admin access)
- Can **delete players** or sensitive data
- Can **seed/reset** admin accounts
- **Recommended for**: Game owners, lead developers

**Initial setup**: Use `seed_super_admin.py` script to grant super_admin to an email:
```bash
python seed_super_admin.py lloyd.malfliet@gmail.com
```

### Admin (`admin`)
- Access to all management features **except role management**
- Can CRUD resources, lands, crafts, cards
- Can manage player data (view, edit basics)
- **Cannot** change user roles or access role management
- **Recommended for**: Content managers, game designers

### Artist (`artist`)
- **Limited access**: Image uploads only
- Can upload images for:
  - Resource icons
  - Land logos  
  - Card images
- **Cannot** modify game mechanics or create new content
- **Recommended for**: Artists, designers working on specific assets

---

## Role Assignment

Only **Super Admin** can assign roles to other players.

### To grant a role:
1. Go to **Admin Panel** → **Roles Management**
2. Search for a player by name or email
3. Select the role: `super_admin`, `admin`, `artist`, or `None` (player)
4. Click "Update Role"

### To remove admin access:
Set the player's role to `None` (removes `admin_role` and `is_admin` flags)

---

## Core Features

### 1. Dashboard
**Route**: `/admin/`

Overview of game statistics:
- Total players
- Total resources collected
- Total crafts completed
- Daily active players count

---

### 2. Player Management
**Route**: `/admin/users/`

#### List View
- Search players by name
- View player stats (level, coins, essence, XP)
- Quick role indicator
- Click player name for details

#### Player Details (`/admin/users/<id>`)
View complete player information:
- **Profile**: Name, email, creation date
- **Progress**: Level, XP, coins, essence
- **Inventory**: Resource stocks, items owned
- **Cards**: All cards player owns with quantities
- **Craft Jobs**: Active and completed crafts
- **Admin Controls**: Edit role, view story flags

---

### 3. Resources Management
**Routes**: `/admin/resources/`

Manage in-game resources (wood, stone, water, etc.)

#### List View
- View all defined resources
- See icon preview, sell price, enabled status
- Search and filter

#### Add/Edit Resource (`/admin/resources/new` or `/admin/resources/<key>/edit`)
- **Key**: Unique identifier (e.g., "wood", "stone")
- **Label**: Display name (French + English support)
- **Icon**: Image path or upload new icon
- **Sell Price**: Base price in coins
- **Enabled**: Toggle resource availability
- **Description**: Game text shown to players

#### Image Upload
- Accepts PNG/JPG images
- Auto-saves to `/static/assets/img/items/resources/`
- Preview before upload
- Supported by: `admin`, `artist` roles

---

### 4. Lands Management
**Routes**: `/admin/lands/`

Manage land/region definitions (forest, beach, cave, etc.)

#### List View
- All lands with slot count, starting land flag
- Logo preview
- Edit button for each land

#### Edit Land (`/admin/lands/<key>/edit`)

Two editing modes:

**A) Structured Form** (quick edits)
- Land name (FR/EN)
- Number of slots
- XP per collect
- Additional slot costs (essence + multiplier)
- Slot icon / Logo upload

**B) Raw YAML** (advanced)
For complex changes:
```yaml
forest:
  key: land_forest
  label_fr: Forêt
  label_en: Forest
  starting_land: true
  slots: 5
  tools:
    hands:
      cooldown_seconds: 10
      xp_multiplier: 1.0
      base_loot:
        - resource: wood
          min: 1
          max: 2
          chance: 1.0
```

#### Tool Configuration
Each tool has:
- **Cooldown** (seconds between uses)
- **XP Multiplier** (1.0 = normal, 1.5 = 50% bonus)
- **Base Loot**: Guaranteed drops
- **Extra Loot**: Chance-based drops

#### Loot Table Format
```yaml
- resource: wood          # Item to drop
  min: 1                  # Minimum quantity
  max: 2                  # Maximum quantity
  chance: 1.0             # 0.0 to 1.0 (1.0 = guaranteed)
```

#### Logo Upload
- Upload new land logo (replaces existing)
- Auto-saves to `/static/assets/img/lands/`
- Shows current logo preview

---

### 5. Crafts Management
**Routes**: `/admin/crafts/`

Manage crafting recipes and craft stations.

#### List View
- View all crafts with output item name
- Craft station, recipe type
- Enabled/disabled toggle
- Edit/delete buttons

#### Add/Edit Craft (`/admin/crafts/new` or `/admin/crafts/<key>/edit`)

Configure a craft recipe:

**Basic Info**
- **Key**: Unique identifier
- **Station**: craft_table_basic, craft_table_advanced, forge, etc.
- **Enabled**: Toggle availability

**Recipe**
- **Output**: Item produced (name + quantity)
- **Ingredients**: Resources/items needed (pattern-based or flat list)
- **Required Table Level**: Minimum craft station level needed
- **Craft Time**: Duration in seconds

**Progression**
- **Unlock Card**: Recipe card required to unlock
- **Min Level**: Minimum player level
- **XP Reward**: XP gained on craft

#### Recipe Format (Advanced)
Grid-based pattern:
```yaml
recipe:
  pattern:
    - VVV
    - VVV
    - VVV
  legend:
    V:
      kind: resource
      key: vine
      quantity: 1
```

---

### 6. Cards Management
**Routes**: `/admin/cards/`

Manage card definitions (loot cards, boost cards, land access, etc.)

#### List View
- All cards with type, rarity, image preview
- Enabled status
- Edit/delete buttons

#### Add/Edit Card (`/admin/cards/new` or `/admin/cards/<key>/edit`)

**Card Info**
- **Key**: Unique identifier
- **Label**: Display name (FR/EN)
- **Description**: Card effect explanation
- **Type**: land_access, boost, building, item, etc.
- **Rarity**: common, uncommon, rare, epic, legendary
- **Category**: Grouping for UI organization

**Game Effects**
- **Card Gameplay**: JSON object defining card effects
  ```json
  {
    "target_land": "forest",
    "boost_type": "resource_boost",
    "amount": 1.5
  }
  ```

**Shop / Availability**
- **Prices**: Coins, essence, or resource costs
- **Quantity Available**: How many exist in the game world
- **Purchase Limit**: Max copies per player
- **Max Owned**: How many a player can hold
- **Tradable**: Can be traded between players
- **Giftable**: Can be gifted to other players

**Image Upload**
- Card artwork (PNG/JPG)
- Auto-saves to `/static/assets/img/cards/`
- Preview in edit form

#### Unlock Rules (Advanced)
```yaml
unlock_rules:
  required_level: 5
  required_cards:
    - land_forest
  required_items:
    - rope: 5
```

---

### 7. Configuration Files

Admin panel manages these YAML files in `/app/data/`:

#### `resources.yml`
Game resources directory. Format:
```yaml
resources:
  - key: wood
    label: Bois
    icon: wood.png
    base_sell_price: 5
    enabled: true
```

#### `lands.yml`
Land/region definitions with tools and loot tables.

#### `crafts.yml`
Recipe definitions. Generated from `/app/data/crafts/` fragments.

#### `cards.yml`
Card definitions with mechanics and shop data.

#### `levels.yml`
Player progression thresholds.

---

## Typical Admin Workflows

### ✅ Add a New Resource
1. Go to **Resources** → **Add Resource**
2. Enter: key, label (FR/EN), base_sell_price
3. Upload icon image
4. Click "Create"
5. Resource appears in game immediately

### ✅ Adjust Land Difficulty
1. Go to **Lands** → Select land → **Edit**
2. Modify tool cooldom_seconds or XP multipliers
3. Adjust loot chances/quantities in YAML
4. Save → Changes live immediately

### ✅ Balance a Craft Recipe
1. Go to **Crafts** → Find recipe → **Edit**
2. Adjust craft_time_seconds or ingredient costs
3. Update XP reward
4. Save → Next craft uses new balance

### ✅ Grant Admin Access to Team Member
1. Team member creates game account
2. Go to **Roles Management**
3. Search for player name
4. Set role to `admin` or `artist` (as needed)
5. Save → They now see admin link in menu

### ✅ Manage Card Prices
1. Go to **Cards** → Find card → **Edit**
2. Modify `shop` section with new prices
3. Adjust `card_purchase_limit_quantity` or `card_max_owned`
4. Save → Shop prices update immediately

---

## Technical Details

### Permission System

Permissions are checked via decorators on routes:

```python
@admin.permission_required('manage_resources')
def resource_list():
    # Only admin/super_admin can access
```

Available permissions:
- `manage_users` - View and edit players
- `manage_resources` - CRUD resources
- `manage_lands` - CRUD lands
- `manage_crafts` - CRUD crafts  
- `manage_cards` - CRUD cards
- `manage_roles` - Change player roles (super_admin only)
- `upload_images` - Upload images

### File Upload

Images are uploaded via:
- **Endpoint**: `POST /admin/<section>/<key>/upload`
- **Destination**: `/app/static/assets/img/<section>/`
- **Formats**: PNG, JPG (max 5MB)
- **Security**: Filename validation, type checking

### Database Changes

When content is modified:
1. YAML files are updated in `/app/data/`
2. Database models are updated (ResourceDef, CardDef, etc.)
3. Changes are **instantly live** - no restart needed
4. All active players see new content next game load

---

## Troubleshooting

### "Access Denied" Error
- Your account doesn't have the required role
- Ask a super_admin to grant you the right role
- Check: Game Menu → Your account should show "🔐 Admin Panel" link

### Changes Not Taking Effect
- Clear browser cache (Ctrl+Shift+Delete)
- Refresh game page (F5)
- Check YAML file for syntax errors (use raw YAML editor to validate)

### Image Upload Fails
- File must be PNG or JPG
- File size must be under 5MB
- Filename should contain only letters, numbers, hyphens, underscores
- Check server logs: `tail -f app.log`

### Can't Find a Player
- Search is case-insensitive
- Try searching by partial name
- Check player actually exists in game

---

## Advanced Tips

### Bulk Editing (Advanced Users)
1. Go to section (lands, crafts)
2. Click "Edit Raw YAML"
3. Edit complete configuration directly
4. Syntax must be valid YAML
5. Back up original before making changes

### Setting XP Thresholds
Edit `/app/data/levels.yml`:
```yaml
levels:
  - level: 1
    xp_required: 100
  - level: 2
    xp_required: 250
```

### Creating Balanced Loot Tables
General formula: `rarity = probability × value`
- Common drops: 100% chance, low value (1-3 qty)
- Rare drops: 5-10% chance, high value (1-2 qty)

### Testing Changes
1. Create a test account
2. Modify game content in admin panel
3. Play as test account
4. Verify changes work as intended
5. Adjust and repeat

---

## Support & Maintenance

### Regular Maintenance Tasks
- **Weekly**: Review and archive old craft jobs
- **Monthly**: Balance-check resource drops
- **Quarterly**: Audit admin access (who has what role)

### Database Backup
Before major changes:
```bash
sqlite3 game.db ".backup game.db.backup"
```

### Logging
Admin actions are logged in `/app/debug.log`:
- Route accessed
- User who performed action
- Changes made
- Timestamp

---

## Security Notes

⚠️ **Important**
- Super admin role should only be granted to trusted team members
- Be cautious with artist role - verify before granting upload access
- All changes are permanent - no undo within the UI (restore from backup)
- Use unique passwords for admin accounts
- Enable 2FA if available

---

*Last updated: 2026-04-15*
*Admin Panel v1.0*
