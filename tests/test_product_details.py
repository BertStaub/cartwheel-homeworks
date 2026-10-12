"""HW1 additional tool: get_product_details (offline, no LLM)."""

from __future__ import annotations

from agent import tools
from agent.auth import AuthContext

SHOPPER_1 = AuthContext(user_id=1, role="shopper")


def test_valid_product_has_title_price_and_no_issues(world: dict) -> None:
    result = tools.get_product_details(SHOPPER_1, 1)
    assert result["ok"] is True
    product = result["product"]
    assert product["title"] == "Heavy-Duty Vase"
    assert product["price_usd"] == 298.0
    assert product["store_name"] == "Blue Heron Ceramics"
    assert product["data_issues"] == []


def test_missing_title_is_reported_not_invented(world: dict) -> None:
    product = tools.get_product_details(SHOPPER_1, 3)["product"]
    assert product["title"] == "N/A"
    assert any("title" in issue for issue in product["data_issues"])


def test_invalid_price_is_not_presented_as_an_offer(world: dict) -> None:
    product = tools.get_product_details(SHOPPER_1, 4)["product"]
    assert product["price_usd"] == "N/A"
    assert any("price" in issue for issue in product["data_issues"])


def test_unknown_product_is_not_found(world: dict) -> None:
    result = tools.get_product_details(SHOPPER_1, 999999)
    assert result["ok"] is False
    assert result["error"] == "not_found"
