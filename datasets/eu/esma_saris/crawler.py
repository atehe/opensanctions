import csv

from zavod import Context
from zavod import helpers as h


def crawl(context: Context) -> None:
    # Set the initial cookie
    data = {
        "core": "esma_registers_saris_new",
        "pagingSize": "10",
        "start": 0,
        "keyword": "",
        "sortField": "effectiveFrom asc",
        "criteria": [],
        "wt": "json",
    }
    context.http.post(
        "https://registers.esma.europa.eu/publication/searchRegister/doMainSearch",
        json=data,
    )
    source_file = context.fetch_resource("source.csv", context.data_url)
    with open(source_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            isin = row.pop("instrumentIdentifier")
            if isin is None:
                context.log.warn("No ISIN", row=row)
                return
            entity = h.make_security(context, isin)
            entity.add("name", row.pop("instrumentFullName", isin))

            sanction = h.make_sanction(context, entity)
            sanction.add("program", "ESMA")
            sanction.add("provisions", row.pop("actionType"))
            sanction.add("reason", row.pop("reasonsForTheAction"))
            sanction.add("description", row.pop("comments"))
            sanction.add("startDate", row.pop("effectiveFrom"))
            sanction.add("country", row.pop("memberStateOfNotifyingCA"))
            sanction.set("authority", row.pop("notifyingCA"))
            if row.get("effectiveTo") is not None:
                sanction.add("endDate", row.pop("effectiveTo"))
            else:
                entity.add("topics", "sanction")
            context.emit(sanction)
            issuer_id = row.pop("issuer", "").strip()
            if issuer_id != "":
                issuer = context.make("LegalEntity")
                if len(issuer_id) == 20:
                    issuer.id = f"lei-{issuer_id}"
                    issuer.add("leiCode", issuer_id)
                else:
                    issuer.id = context.make_id(issuer_id)
                issuer.add("name", row.pop("issuerName"))
                context.emit(issuer)
                entity.add("issuer", issuer)

            context.emit(entity, target=True)
            context.audit_data(
                row,
                ignore=[
                    "sufficientlyRelatedInstrument",
                    "otherRelatedInstrument",
                    "historicalStatus",
                    "markets",
                    "timestamp",
                    "id",
                    "onGoing",
                ],
            )
