from collections import defaultdict
from typing import Dict, List, Any, Optional, Set
from followthemoney import model
from followthemoney.types import registry
from zavod.context import Context

from zavod.entity import Entity
from zavod.archive import STATISTICS_FILE
from zavod.exporters.common import Exporter
from zavod.meta.assertion import Action, Assertion, Comparison
from zavod.util import write_json


def get_schema_facets(schemata: Dict[str, int]) -> List[Any]:
    facets: List[Any] = []
    for name, count in sorted(schemata.items(), key=lambda s: s[1], reverse=True):
        schema = model.get(name)
        if schema is None:
            continue
        facet = {
            "name": name,
            "count": count,
            "label": schema.label,
            "plural": schema.plural,
        }
        facets.append(facet)
    return facets


def get_country_facets(countries: Dict[str, int]) -> List[Any]:
    facets: List[Any] = []
    for code, count in sorted(countries.items(), key=lambda s: s[1], reverse=True):
        facet = {
            "code": code,
            "count": count,
            "label": registry.country.caption(code),
        }
        facets.append(facet)
    return facets


def compare_threshold(value: int, comparison: Comparison, threshold: int) -> bool:
    match comparison:
        case Comparison.GT:
            return value > threshold
        case Comparison.LT:
            return value < threshold
        case _:
            raise ValueError(f"Unknown comparison: {comparison}")


def check_assertion(context: Context, stats: Dict, assertion: Assertion) -> None:
    things = stats.get("things")
    match assertion.filter_attribute:
        case "schema":
            items = things.get("schemata")
            filter_key = "name"
        case "country":
            items = things.get("countries")
            filter_key = "code"
        case _:
            raise ValueError(f"Unknown filter attribute: {assertion.filter_attribute}")
    items = [i for i in items if i[filter_key] == assertion.filter_value]
    assert len(items) == 1, "Value not found for assertion with filter %s=%s" % (
        assertion.filter_attribute,
        assertion.filter_value,
    )
    value = items[0]["count"]
    if not compare_threshold(value, assertion.comparison, assertion.threshold):
        msg = f"Assertion failed for value {value}: {assertion}"
        match assertion.action:
            case Action.WARN:
                context.log.warning(msg)
            case Action.FAIL:
                raise ValueError(msg)
            case _:
                raise ValueError(f"Unknown assertion action: {assertion.action}")


class StatisticsExporter(Exporter):
    TITLE = "Dataset statistics"
    FILE_NAME = STATISTICS_FILE
    MIME_TYPE = "application/json"

    def setup(self) -> None:
        super().setup()
        self.entity_count = 0
        self.last_change: Optional[str] = None
        self.schemata: Set[str] = set()
        self.qnames: Set[str] = set()

        self.thing_count = 0
        self.thing_countries: Dict[str, int] = defaultdict(int)
        self.thing_schemata: Dict[str, int] = defaultdict(int)

        self.target_count = 0
        self.target_countries: Dict[str, int] = defaultdict(int)
        self.target_schemata: Dict[str, int] = defaultdict(int)

    def feed(self, entity: Entity) -> None:
        self.entity_count += 1
        self.schemata.add(entity.schema.name)
        for prop in entity.iterprops():
            self.qnames.add(prop.qname)

        if entity.schema.is_a("Thing"):
            self.thing_count += 1
            self.thing_schemata[entity.schema.name] += 1
            for country in entity.countries:
                self.thing_countries[country] += 1

        if entity.target:
            self.target_count += 1
            self.target_schemata[entity.schema.name] += 1
            for country in entity.countries:
                self.target_countries[country] += 1

        if entity.last_change is not None:
            if self.last_change is None:
                self.last_change = entity.last_change
            else:
                self.last_change = max(self.last_change, entity.last_change)

    def finish(self) -> None:
        stats = {
            "last_change": self.last_change,
            "schemata": list(self.schemata),
            "properties": list(self.qnames),
            "entity_count": self.entity_count,
            "target_count": self.target_count,
            "targets": {
                "total": self.target_count,
                "countries": get_country_facets(self.target_countries),
                "schemata": get_schema_facets(self.target_schemata),
            },
            "things": {
                "total": self.thing_count,
                "countries": get_country_facets(self.thing_countries),
                "schemata": get_schema_facets(self.thing_schemata),
            },
        }

        for assertion in self.dataset.assertions:
            check_assertion(self.context, stats, assertion)

        with open(self.path, "wb") as fh:
            write_json(stats, fh)
        super().finish()
