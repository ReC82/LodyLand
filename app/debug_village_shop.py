from app.village_shop import (
    get_all_village_offers,
    get_active_village_offers,
    get_village_excluded_card_keys,
)
import datetime as dt

if __name__ == "__main__":
    print("All offers:")
    for o in get_all_village_offers():
        print("-", o["key"])

    today = dt.date.today()
    print("\nActive offers today:", today)
    for o in get_active_village_offers(today):
        print("-", o["key"])

    print("\nExcluded card keys:")
    print(get_village_excluded_card_keys(today))
