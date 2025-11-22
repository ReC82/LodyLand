
# LodyLand — Cards Definition Guide
This folder (`app/data/cards/`) contains **all card definitions** used by the game.
Cards are stored in **multiple subfolders**, organized by theme (boosts, lands, packs, etc.).
Each file is a YAML document containing a single top-level key:

```yaml
cards:
  - key: ...
    ...
```

The game automatically **loads all `.yml` files recursively** when seeding the database.

---

# 📂 Folder Structure

```
cards/
│
├── boosts/
│   ├── resources.yml       # resource_boost cards
│   ├── xp.yml              # xp_boost cards
│   ├── cooldown.yml        # cooldown_boost cards
│   └── land_loot.yml       # land_loot_boost cards
│
├── lands/
│   ├── access.yml          # cards that unlock lands
│   ├── slots.yml           # extra land slots
│   └── specials.yml        # future special land cards
│
├── packs/
│   ├── starters.yml        # starter packs
│   └── events.yml          # limited-time event packs
│
├── debug/
│   └── test_cards.yml      # test cards (never in production)
│
└── _README.md              # this file
```

You may add new `.yml` files and new folders if needed.
The loader will pick them up automatically.

---

# ✨ How to Add a New Card

To create a card:

1. Choose the right folder  
2. Inside that file, add a new entry under:

```yaml
cards:
  - key: your_new_card_key
```

3. Follow the **standard card structure** below.

---

# 🧩 Standard Card Structure

Every card must follow this format:

```yaml
- key: my_card_key
  enabled: true
  label: "Human readable name"
  description: "Human readable description"
  icon: "/static/path/to/icon.png"
  type: resource_boost
  categorie: boost
  rarity: common

  gameplay:
    target_resource: branch
    boost:
      type: addition
      amount: 0.1

  prices:
    - coins: 100
      diams: 0
      resources: {}

  buy_rules: null

  shop:
    enabled: true
    tradable: false
    giftable: true
    quantity: 0
    purchase_limit: null
    max_owned: 5
    show_in_main_shop: false
    show_in_village_shop: true
```

---

# 🧠 Quick Reference: Allowed `type` values

| type               | description |
|--------------------|-------------|
| `resource_boost`   | increase amount collected from a resource |
| `cooldown_boost`   | reduce cooldown for a specific resource |
| `xp_boost`         | increase XP gains |
| `land_access`      | unlock an entire land (forest, lake…) |
| `land_slot`        | grant extra land slots |
| `land_loot_boost`  | boost loot quantity for a specific land |
| `pack`             | bundle of cards or items |
| *(extendable)*     | you may add new custom types |

---

# 🕹 Gameplay Field Examples

### **Resource Boost**
```yaml
gameplay:
  target_resource: wood
  boost:
    type: addition
    amount: 0.2
```

### **Cooldown Boost**
```yaml
gameplay:
  cooldown:
    resource_key: branch
    type: multiplier
    amount: 0.8
```

### **XP Boost**
```yaml
gameplay:
  xp:
    type: multiplier
    amount: 1.1
```

### **Land Access**
```yaml
gameplay:
  target_land: beach
```

### **Land Slot**
```yaml
gameplay:
  land: forest
  slots: 1
```

### **Land Loot Boost**
```yaml
gameplay:
  target_land: forest
  loot:
    type: addition
    amount: 0.2
```

---

# 🛍 Prices Rules

You may define **one or several pricing options**:

```yaml
prices:
  - coins: 100
    diams: 0
    resources: {}
  - coins: 0
    diams: 5
    resources:
      branch: 50
```

The player can buy using **any** of the listed options.

---

# 🛒 Shop Behavior

```yaml
shop:
  enabled: true
  tradable: false
  giftable: true
  quantity: 0
  purchase_limit: null
  max_owned: 1
  show_in_main_shop: false
  show_in_village_shop: true
```

---

# ✔ Validating Your New Card

A new card is considered valid if:

- `key` is unique  
- it has **label**, **description**, **icon**  
- it has a **type**, **categorie**, and **rarity**  
- **gameplay** matches the type  
- **prices** is a list (can be empty)  
- **shop** exists (enabled or not)  

If anything is missing, the loader will reject it.

---

# 🧪 Test Cards

Any file inside `cards/debug/` is automatically loaded but **never used in production**.

Use it for experiment cards:

```
cards/debug/test_cards.yml
```

---

# 🚀 Adding New File Groups

Want a new category?

Example: `cards/tools/crafts.yml`

Just create the folder + file → the loader will automatically include it.

---

# 💬 Need help?

Ping Lloyd in LodyLand Dev Chat, or check:

- `normalize_cards_yaml.py` — auto-formatter  
- `seed_cards_from_yaml()` — database loader  
- `api_shop.py` — card shop logic  
