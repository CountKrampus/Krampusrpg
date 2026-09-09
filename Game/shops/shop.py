from Server.services import load_data


def get_shop_items():
    return load_data("items.json")


def get_item(item_id: str):
    for item in get_shop_items():
        if item.get("id") == item_id:
            return item

    return None
