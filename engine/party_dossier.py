"""Validate the data contract shared by the party dossier and its visualizations."""

from datetime import date
from urllib.parse import urlsplit

EVENT_TYPES = {"fundacao", "registro", "fusao", "incorporacao", "renomeacao", "extincao", "federacao", "contexto"}
SOURCE_TYPES = {"official", "declaration", "press_report", "analysis"}
FUNDS = {"fefc", "partidario"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_party_dossier(doc: dict) -> None:
    items = doc["items"]
    ids = [item["id"] for item in items]
    require(len(ids) == len(set(ids)), "duplicate item id")
    parties = [item["payload"]["partyId"] for item in items if item["kind"] == "party"]
    known = set(parties)
    require(known and len(known) == len(parties), "missing or duplicate party id")
    periods = {}
    comparisons = []

    def references(ids, context):
        unknown = set(ids) - known
        require(not unknown, f"{context}: unknown party id: {', '.join(sorted(unknown))}")

    for item in items:
        ident, kind, payload = item["id"], item["kind"], item["payload"]
        for source in item["sources"]:
            url = source["url"]
            link = urlsplit(url)
            require(link.scheme in {"http", "https"} and link.hostname and "." in link.hostname
                    and not any(c.isspace() for c in url) and not link.username and not link.password,
                    f"{ident}: invalid source URL")
            require(source["kind"] in SOURCE_TYPES and source["outlet"], f"{ident}: invalid source attribution")
        match kind:
            case "party":
                require(payload["abbreviation"] and payload["name"], f"{ident}: missing party name")
            case "event":
                event_type = payload["type"]
                require(event_type in EVENT_TYPES, f"{ident}: invalid event type")
                timestamp = payload["date"]
                require(len(timestamp) in {4, 7, 10}, f"{ident}: invalid date")
                date.fromisoformat(timestamp + {4: "-01-01", 7: "-01", 10: ""}[len(timestamp)])
                references(payload["from"] + payload["to"], ident)
                if payload.get("declared"):
                    require(any(s["kind"] == "declaration" for s in item["sources"]),
                            f"{ident}: declared motive without declaration source")
            case "funding":
                fund, year = payload["fund"], payload["year"]
                key = (fund, year)
                total = payload["totalCents"]
                require(fund in FUNDS and type(year) is int and 1900 <= year <= 2100 and key not in periods,
                        f"{ident}: invalid or duplicate funding period")
                require(type(total) is int and total > 0, f"{ident}: invalid funding total")
                rows = payload["allocations"]
                recipients = [row["partyId"] for row in rows]
                references(recipients, ident)
                require(len(set(recipients)) == len(recipients), f"{ident}: duplicate allocation")
                require(all(type(row["cents"]) is int and row["cents"] >= 0 for row in rows),
                        f"{ident}: invalid allocation")
                if rows:
                    require(abs(sum(row["cents"] for row in rows) - total) <= len(rows),
                            f"{ident}: total differs from allocation sum after rounding")
                if fund == "partidario":
                    require(payload["budgetCents"] + payload["finesCents"] == total,
                            f"{ident}: budget plus fines does not equal total")
                periods[key] = set(recipients)
            case "comparison":
                comparisons.append(item)
            case "site":
                references([payload["partyId"]], ident)
            case "analysis":
                require(payload["title"] and payload["text"], f"{ident}: missing analysis")
            case _:
                raise ValueError(f"{ident}: unknown item kind")

    for item in comparisons:
        payload = item["payload"]
        for side in (payload["before"], payload["after"]):
            recipients = side["partyIds"]
            references(recipients, item["id"])
            require(recipients and set(recipients) <= periods.get((payload["fund"], side["year"]), set()),
                    f"{item['id']}: comparison has no funding data")
