import pytest

from tests import factories


@pytest.fixture
def exchange_rate(db):
    return factories.create_exchange_rate()


def build_checkout_post(plan, product_lines=None, origin="profile"):
    """Minimal POST body for ChargeCheckoutView (flexible plan, no cut-day fields)."""
    data = {
        "origin": origin,
        "plan_id": str(plan.pk),
    }
    product_ids = []
    for line in product_lines or []:
        item_id = line["item_id"]
        product_ids.append(str(item_id))
        data["product_qty_{}".format(item_id)] = str(line.get("qty", 1))
        if line.get("locker_id"):
            data["locker_id_{}".format(item_id)] = str(line["locker_id"])
        if line.get("locker_start"):
            data["locker_start_{}".format(item_id)] = line["locker_start"]
        if line.get("locker_end"):
            data["locker_end_{}".format(item_id)] = line["locker_end"]
    if product_ids:
        data["product_ids"] = product_ids
    return data
