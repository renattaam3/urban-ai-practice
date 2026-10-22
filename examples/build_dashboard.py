from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS = SCRIPT_DIR / "data" / "suzdal" / "results"
DEFAULT_TITLE = "Суздаль: dashboard показателей"

BASE_FIELDS = [
    "residential",
    "business",
    "recreation",
    "industrial",
    "transport",
    "special",
    "agriculture",
    "land_use",
    "share",
    "site_area",
    "population",
    "capacity",
    "provision_strong",
    "provision_weak",
    "fsi",
    "gsi",
    "mxi",
    "l",
    "osr",
    "share_living",
    "share_non_living",
    "spacematrix_morphotype",
    "strelka_morphotype",
    "area_accessibility",
]

JOINED_FIELDS = [
    "school_count",
    "demand",
    "demand_left",
    "demand_within",
    "demand_without",
    "capacity_left",
    "capacity_within",
    "capacity_without",
    "provision_gap",
    "footprint_area",
    "build_floor_area",
    "living_area",
    "non_living_area",
    "cluster",
]

FIELD_KEYS = ["block_id", *BASE_FIELDS, *JOINED_FIELDS]

LAND_USE_RU = {
    "residential": "жилая",
    "business": "деловая",
    "recreation": "рекреационная",
    "industrial": "промышленная",
    "transport": "транспортная",
    "special": "специальная",
    "agriculture": "сельскохозяйственная",
    "mixed": "смешанная",
}

GROUP_ORDER = [
    "Территория",
    "Землепользование",
    "Население и школы",
    "Доступность",
    "Плотность",
    "Морфология",
    "Застройка",
]


def _spec(
    key: str,
    label: str,
    unit: str = "",
    kind: str = "numeric",
    decimals: int = 2,
    group: str = "",
    palette: str = "blue",
    description: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "kind": kind,
        "decimals": decimals,
        "group": group,
        "palette": palette,
        "description": description,
    }


FIELD_SPECS = [
    _spec("block_id", "ID квартала", kind="id", decimals=0, group="Идентификация", description="Номер квартала."),
    _spec(
        "residential",
        "Жилая функция",
        "доля",
        decimals=3,
        group="Землепользование",
        palette="green",
        description="Доля площади квартала под жильём.",
    ),
    _spec(
        "business",
        "Деловая функция",
        "доля",
        decimals=3,
        group="Землепользование",
        palette="blue",
        description="Доля площади под деловую функцию.",
    ),
    _spec(
        "recreation",
        "Рекреация",
        "доля",
        decimals=3,
        group="Землепользование",
        palette="teal",
        description="Доля площади под рекреацию.",
    ),
    _spec(
        "industrial",
        "Промышленность",
        "доля",
        decimals=3,
        group="Землепользование",
        palette="red",
        description="Доля площади под промышленность.",
    ),
    _spec(
        "transport",
        "Транспорт",
        "доля",
        decimals=3,
        group="Землепользование",
        palette="orange",
        description="Доля площади под транспорт.",
    ),
    _spec(
        "special",
        "Специальная функция",
        "доля",
        decimals=3,
        group="Землепользование",
        palette="purple",
        description="Доля площади под специальную функцию.",
    ),
    _spec(
        "agriculture",
        "Сельское хозяйство",
        "доля",
        decimals=3,
        group="Землепользование",
        palette="yellow",
        description="Доля площади под сельское хозяйство.",
    ),
    _spec(
        "land_use",
        "Землепользование",
        kind="category",
        decimals=0,
        group="Землепользование",
        description="Преобладающая функция квартала.",
    ),
    _spec(
        "share",
        "Доля главной функции",
        "доля",
        decimals=3,
        group="Землепользование",
        palette="blue",
        description="Доля площади главной функции.",
    ),
    _spec(
        "site_area",
        "Площадь квартала",
        "м²",
        decimals=0,
        group="Территория",
        palette="gray",
        description="Площадь квартала.",
    ),
    _spec(
        "population",
        "Население",
        "чел.",
        decimals=0,
        group="Население и школы",
        palette="blue",
        description="Оценка населения квартала.",
    ),
    _spec(
        "capacity",
        "Вместимость школ",
        "мест",
        decimals=0,
        group="Население и школы",
        palette="purple",
        description="Суммарная вместимость школ в квартале.",
    ),
    _spec(
        "provision_strong",
        "Сильная обеспеченность",
        "0–1",
        decimals=3,
        group="Население и школы",
        palette="green_red",
        description="Доля покрытого спроса при сильной доступности.",
    ),
    _spec(
        "provision_weak",
        "Слабая обеспеченность",
        "0–1",
        decimals=3,
        group="Население и школы",
        palette="green_red",
        description="Доля покрытого спроса при слабой доступности.",
    ),
    _spec(
        "provision_gap",
        "Разрыв обеспеченности",
        "0–1",
        decimals=3,
        group="Население и школы",
        palette="green_red",
        description="Разница между слабой и сильной обеспеченностью: provision_weak − provision_strong.",
    ),
    _spec(
        "fsi",
        "FSI",
        "м²/м²",
        decimals=3,
        group="Плотность",
        palette="orange",
        description="Floor Space Index: площадь этажей на площадь квартала.",
    ),
    _spec(
        "gsi",
        "GSI",
        "м²/м²",
        decimals=3,
        group="Плотность",
        palette="orange",
        description="Ground Space Index: площадь застройки на площадь квартала.",
    ),
    _spec(
        "mxi",
        "MXI",
        "доля",
        decimals=3,
        group="Плотность",
        palette="purple",
        description="Индекс смешанного использования.",
    ),
    _spec(
        "l",
        "Средняя этажность",
        "этажей",
        decimals=2,
        group="Плотность",
        palette="blue",
        description="Средняя этажность застройки квартала.",
    ),
    _spec("osr", "OSR", "доля", decimals=2, group="Плотность", palette="green", description="Open Space Ratio."),
    _spec(
        "share_living",
        "Жилая площадь",
        "доля",
        decimals=3,
        group="Плотность",
        palette="teal",
        description="Доля жилой площади в застройке.",
    ),
    _spec(
        "share_non_living",
        "Нежилая площадь",
        "доля",
        decimals=3,
        group="Плотность",
        palette="teal",
        description="Доля нежилой площади в застройке.",
    ),
    _spec(
        "spacematrix_morphotype",
        "Морфотип Spacematrix",
        kind="category",
        decimals=0,
        group="Морфология",
        description="Морфотип по Spacematrix.",
    ),
    _spec(
        "strelka_morphotype",
        "Морфотип Strelka",
        kind="category",
        decimals=0,
        group="Морфология",
        description="Морфотип по Strelka.",
    ),
    _spec(
        "area_accessibility",
        "Доступность",
        "мин",
        decimals=1,
        group="Доступность",
        palette="green_red_r",
        description="Среднее время доступности; больше — хуже.",
    ),
    _spec(
        "school_count",
        "Школ в квартале",
        "шт.",
        decimals=0,
        group="Население и школы",
        palette="purple",
        description="Количество школ в квартале.",
    ),
    _spec(
        "demand",
        "Спрос на школы",
        "чел.",
        decimals=0,
        group="Население и школы",
        palette="red",
        description="Оценка спроса на школьные места.",
    ),
    _spec(
        "demand_left",
        "Не покрыт спрос",
        "чел.",
        decimals=0,
        group="Население и школы",
        palette="red",
        description="Спрос, не покрытый доступными школами.",
    ),
    _spec(
        "demand_within",
        "Спрос в зоне",
        "чел.",
        decimals=0,
        group="Население и школы",
        palette="green",
        description="Спрос в пределах нормативной доступности.",
    ),
    _spec(
        "demand_without",
        "Спрос вне зоны",
        "чел.",
        decimals=0,
        group="Население и школы",
        palette="gray",
        description="Спрос вне зоны доступности.",
    ),
    _spec(
        "capacity_left",
        "Остаток мест",
        "мест",
        decimals=0,
        group="Население и школы",
        palette="green",
        description="Свободные места в доступных школах.",
    ),
    _spec(
        "capacity_within",
        "Доступные места",
        "мест",
        decimals=0,
        group="Население и школы",
        palette="green",
        description="Вместимость школ в зоне доступности.",
    ),
    _spec(
        "capacity_without",
        "Недоступные места",
        "мест",
        decimals=0,
        group="Население и школы",
        palette="gray",
        description="Вместимость школ вне зоны доступности.",
    ),
    _spec(
        "footprint_area",
        "Площадь застройки",
        "м²",
        decimals=0,
        group="Застройка",
        palette="orange",
        description="Площадь застройки в квартале.",
    ),
    _spec(
        "build_floor_area",
        "Площадь этажей",
        "м²",
        decimals=0,
        group="Застройка",
        palette="orange",
        description="Суммарная площадь этажей.",
    ),
    _spec(
        "living_area",
        "Жилая площадь",
        "м²",
        decimals=0,
        group="Застройка",
        palette="teal",
        description="Жилая площадь застройки.",
    ),
    _spec(
        "non_living_area",
        "Нежилая площадь",
        "м²",
        decimals=0,
        group="Застройка",
        palette="purple",
        description="Нежилая площадь застройки.",
    ),
    _spec(
        "cluster",
        "Кластер Spacematrix",
        kind="category",
        decimals=0,
        group="Морфология",
        description="Номер кластера Spacematrix.",
    ),
]

FIELD_BY_KEY = {item["key"]: item for item in FIELD_SPECS}

if set(FIELD_KEYS) != set(FIELD_BY_KEY):
    raise ValueError("FIELD_KEYS и FIELD_SPECS не совпадают")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def parse_value(value: str) -> Any:
    text = value.strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        if "." not in text and "e" not in text.lower():
            return int(text)
        return float(text)
    except ValueError:
        return text


def finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clean(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def empty_fc() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


def load_csv_rows(path: Path, id_first: bool = False) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        first = fieldnames[0] if fieldnames else None
        rows: list[dict[str, Any]] = []
        for raw in reader:
            row: dict[str, Any] = {}
            for key, value in raw.items():
                row[(key or "").strip()] = parse_value(value or "")
            if id_first and first is not None:
                block_id = finite(row.pop(first, None))
                if block_id is None:
                    continue
                row["block_id"] = int(block_id)
            rows.append(row)
        return rows


def fmt_num(value: Any, decimals: int = 2) -> str:
    number = finite(value)
    if number is None:
        return "—"
    text = f"{number:,.{decimals}f}"
    return text.replace(",", "\u202f").replace(".", ",")


def fmt_int(value: Any) -> str:
    return fmt_num(value, 0)


def fmt_pct(value: Any, decimals: int = 1) -> str:
    number = finite(value)
    if number is None:
        return "—"
    return f"{fmt_num(number * 100, decimals)}%"


def plural_ru(value: Any, one: str, few: str, many: str) -> str:
    number = abs(int(finite(value) or 0))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def fmt_cell(key: str, value: Any) -> str:
    number = finite(value)
    if value is None or value == "":
        return '<span class="muted">—</span>'
    spec = FIELD_BY_KEY[key]
    if spec["kind"] == "numeric":
        return esc(fmt_num(number, spec["decimals"])) if number is not None else '<span class="muted">—</span>'
    if key == "land_use":
        return esc(land_use_label(value))
    return esc(value)


def category_label(value: Any) -> str:
    if value is None or value == "":
        return "нет данных"
    number = finite(value)
    if number is not None and number.is_integer():
        return str(int(number))
    return str(value)


def land_use_label(value: Any) -> str:
    key = category_label(value)
    if key in {"нет данных", "None"}:
        return "не задано"
    return LAND_USE_RU.get(key, key)


def load_layer(path: Path, keep: list[str], allowed: set[str]) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = load_json(path)
    features = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") not in allowed:
            continue
        props = feature.get("properties") or {}
        features.append(
            {
                "type": "Feature",
                "properties": {key: clean(props.get(key)) for key in keep},
                "geometry": geometry,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def iter_points(node: Any) -> Any:
    if isinstance(node, (list, tuple)) and len(node) >= 2 and all(isinstance(item, (int, float)) for item in node[:2]):
        yield float(node[0]), float(node[1])
        return
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from iter_points(child)


def geometry_center(geometry: dict[str, Any]) -> tuple[float, float] | None:
    points = list(iter_points(geometry.get("coordinates")))
    if not points:
        return None
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return (sum(lons) / len(lons), sum(lats) / len(lats))


def load_school_points(raw_dir: Path) -> list[dict[str, Any]]:
    path = raw_dir / "schools.geojson"
    if not path.exists():
        return []
    data = load_json(path)
    points = []
    for feature in data.get("features", []):
        center = geometry_center(feature.get("geometry") or {})
        if center is None:
            continue
        props = feature.get("properties") or {}
        points.append(
            {
                "lon": center[0],
                "lat": center[1],
                "name": props.get("name") or "Школа",
                "osm_type": props.get("osm_type"),
                "osm_id": props.get("id"),
                "amenity": props.get("amenity"),
            }
        )
    return points


def build_blocks(
    results_dir: Path,
    provision_rows: list[dict[str, Any]],
    density_rows: list[dict[str, Any]],
    morph_rows: list[dict[str, Any]],
    strelka_rows: list[dict[str, Any]],
    area_rows: list[dict[str, Any]],
    school_counts: dict[int, float],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = results_dir / "blocks_results.geojson"
    data = load_json(path)
    features = data.get("features", [])
    provision = {row["block_id"]: row for row in provision_rows}
    density = {row["block_id"]: row for row in density_rows}
    morph = {row["block_id"]: row for row in morph_rows}
    strelka = {row["block_id"]: row for row in strelka_rows}
    area = {row["block_id"]: row for row in area_rows}
    blocks = []

    for index, feature in enumerate(features):
        props = feature.get("properties") or {}
        block: dict[str, Any] = {"block_id": index}
        for key in BASE_FIELDS:
            block[key] = clean(props.get(key))

        if block["area_accessibility"] is None and index in area:
            block["area_accessibility"] = area[index].get("area_accessibility")
        morph_row = morph.get(index, {})
        if block["spacematrix_morphotype"] is None:
            block["spacematrix_morphotype"] = morph_row.get("morphotype")
        if block["strelka_morphotype"] is None:
            block["strelka_morphotype"] = strelka.get(index, {}).get("morphotype")

        for key in ["footprint_area", "build_floor_area", "living_area", "non_living_area"]:
            block[key] = density.get(index, {}).get(key)
        for key in [
            "demand",
            "demand_left",
            "demand_within",
            "demand_without",
            "capacity_left",
            "capacity_within",
            "capacity_without",
        ]:
            block[key] = provision.get(index, {}).get(key)
        weak = finite(block.get("provision_weak"))
        strong = finite(block.get("provision_strong"))
        block["provision_gap"] = weak - strong if weak is not None and strong is not None else None
        block["school_count"] = school_counts.get(index)
        block["cluster"] = morph_row.get("cluster")

        feature["properties"] = {key: block.get(key) for key in FIELD_KEYS}
        blocks.append(block)

    return data, blocks


def load_links(path: Path) -> list[dict[str, Any]]:
    rows = load_csv_rows(path)
    links = []
    for row in rows:
        source = finite(row.get("source"))
        target = finite(row.get("target"))
        if source is None or target is None:
            continue
        links.append(
            {
                "source": int(source),
                "target": int(target),
                "value": finite(row.get("value")) or 0.0,
            }
        )
    return sorted(links, key=lambda item: (-item["value"], item["source"], item["target"]))


def build_stats(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats = []
    for spec in FIELD_SPECS:
        if spec["kind"] != "numeric":
            continue
        values = sorted(number for number in (finite(block.get(spec["key"])) for block in blocks) if number is not None)
        if values:
            row = {
                "key": spec["key"],
                "count": len(values),
                "missing": len(blocks) - len(values),
                "min": values[0],
                "median": statistics.median(values),
                "mean": statistics.fmean(values),
                "max": values[-1],
            }
        else:
            row = {
                "key": spec["key"],
                "count": 0,
                "missing": len(blocks),
                "min": None,
                "median": None,
                "mean": None,
                "max": None,
            }
        stats.append(row)
    return stats


def build_metrics(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = []
    for spec in FIELD_SPECS:
        if spec["key"] == "block_id":
            continue
        metric = {
            "key": spec["key"],
            "label": spec["label"],
            "unit": spec["unit"],
            "kind": spec["kind"],
            "decimals": spec["decimals"],
            "group": spec["group"],
            "palette": spec["palette"],
            "description": spec["description"],
        }
        if spec["kind"] == "numeric":
            values = [number for number in (finite(block.get(spec["key"])) for block in blocks) if number is not None]
            metric["min"] = min(values) if values else None
            metric["max"] = max(values) if values else None
        else:
            counts = Counter(category_label(block.get(spec["key"])) for block in blocks)
            metric["values"] = [value for value, _ in counts.most_common()]
            metric["counts"] = dict(counts)
            if spec["key"] == "land_use":
                metric["value_labels"] = {value: land_use_label(value) for value in metric["values"]}
        metrics.append(metric)
    return metrics


def top_counts(values: list[Any], limit: int = 10) -> list[tuple[str, int]]:
    counts = Counter(category_label(value) for value in values)
    items = counts.most_common()
    if len(items) > limit:
        items = items[:limit] + [("прочие", sum(count for _, count in items[limit:]))]
    return items


def build_chart_data(
    blocks: list[dict[str, Any]],
    provision_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    population = sorted(
        ((int(block["block_id"]), finite(block.get("population")) or 0.0) for block in blocks),
        key=lambda item: (-item[1], item[0]),
    )
    population = [item for item in population if item[1] > 0][:12]

    accessibility = sorted(
        (
            (int(block["block_id"]), finite(block.get("area_accessibility")))
            for block in blocks
            if finite(block.get("area_accessibility")) is not None
        ),
        key=lambda item: (-item[1], item[0]),
    )[:12]

    access_values = [
        number for number in (finite(block.get("area_accessibility")) for block in blocks) if number is not None
    ]
    if access_values:
        low = math.floor(min(access_values) / 5) * 5
        high = math.ceil(max(access_values) / 5) * 5
        if high == low:
            high = low + 5
        hist_labels = []
        hist_values = []
        for start in range(low, high, 5):
            hist_labels.append(f"{start}–{start + 5}")
            hist_values.append(sum(1 for value in access_values if start <= value < start + 5))
    else:
        hist_labels = []
        hist_values = []

    land_use = Counter(land_use_label(block.get("land_use")) for block in blocks)
    land_use_items = sorted(land_use.items(), key=lambda item: (-item[1], item[0]))

    demand_total = sum(finite(row.get("demand")) or 0.0 for row in provision_rows)
    capacity_total = sum(finite(row.get("capacity")) or 0.0 for row in provision_rows)
    demand_within = sum(finite(row.get("demand_within")) or 0.0 for row in provision_rows)
    demand_left = sum(finite(row.get("demand_left")) or 0.0 for row in provision_rows)

    scatter = []
    for block in blocks:
        fsi = finite(block.get("fsi"))
        gsi = finite(block.get("gsi"))
        if fsi is None or gsi is None:
            continue
        scatter.append(
            {
                "x": fsi,
                "y": gsi,
                "id": int(block["block_id"]),
                "land_use": land_use_label(block.get("land_use")),
            }
        )

    return {
        "top_population": {
            "labels": [f"Квартал {block_id}" for block_id, _ in population],
            "values": [value for _, value in population],
        },
        "top_accessibility": {
            "labels": [f"Квартал {block_id}" for block_id, _ in accessibility],
            "values": [value for _, value in accessibility],
        },
        "accessibility_hist": {"labels": hist_labels, "values": hist_values},
        "land_use": {
            "labels": [label for label, _ in land_use_items],
            "values": [value for _, value in land_use_items],
        },
        "spacematrix": {
            "labels": [label for label, _ in top_counts([block.get("spacematrix_morphotype") for block in blocks])],
            "values": [value for _, value in top_counts([block.get("spacematrix_morphotype") for block in blocks])],
        },
        "strelka": {
            "labels": [label for label, _ in top_counts([block.get("strelka_morphotype") for block in blocks])],
            "values": [value for _, value in top_counts([block.get("strelka_morphotype") for block in blocks])],
        },
        "provision": {
            "demand": demand_total,
            "capacity": capacity_total,
            "demand_within": demand_within,
            "demand_left": demand_left,
            "gap": max(demand_total - capacity_total, 0.0),
        },
        "scatter": scatter,
    }


def build_conclusions(
    blocks: list[dict[str, Any]],
    summary: dict[str, Any],
    provision_rows: list[dict[str, Any]],
    validation: list[dict[str, Any]],
) -> list[str]:
    block_count = len(blocks)
    population_total = finite(summary.get("population_total")) or 0.0
    blocks_with_population = int(finite(summary.get("blocks_with_population")) or 0)
    buildings_count = int(finite(summary.get("buildings_count")) or 0)
    schools_count = int(finite(summary.get("schools_count")) or 0)
    capacity_total = finite(summary.get("school_capacity_total")) or 0.0
    demand_total = sum(finite(row.get("demand")) or 0.0 for row in provision_rows)
    demand_left = sum(finite(row.get("demand_left")) or 0.0 for row in provision_rows)
    coverage = finite(summary.get("provision_strong_total"))
    gap = max(demand_total - capacity_total, 0.0)
    median_access = finite(summary.get("area_accessibility_median"))
    matrix = summary.get("matrix_stats") or {}
    graph = summary.get("graph") or {}
    density = summary.get("density_medians") or {}
    land_use_nan = finite(summary.get("land_use_nan_share"))

    worst = sorted(
        (
            (int(block["block_id"]), finite(block.get("area_accessibility")))
            for block in blocks
            if finite(block.get("area_accessibility")) is not None
        ),
        key=lambda item: (-item[1], item[0]),
    )[:3]
    best = sorted(
        (
            (int(block["block_id"]), finite(block.get("area_accessibility")))
            for block in blocks
            if finite(block.get("area_accessibility")) is not None
        ),
        key=lambda item: (item[1], item[0]),
    )[:3]
    top_gap = sorted(
        ((int(block["block_id"]), finite(block.get("demand_left")) or 0.0) for block in blocks),
        key=lambda item: (-item[1], item[0]),
    )[:3]
    morph_counts = Counter(
        category_label(block.get("spacematrix_morphotype")) for block in blocks if block.get("spacematrix_morphotype")
    )
    top_morph, top_morph_count = morph_counts.most_common(1)[0] if morph_counts else ("—", 0)
    land_counts = Counter(land_use_label(block.get("land_use")) for block in blocks)
    land_text = ", ".join(
        f"{label} — {count}" for label, count in sorted(land_counts.items(), key=lambda item: (-item[1], item[0]))
    )
    validation_ok = sum(1 for row in validation if str(row.get("status", "")).upper() == "OK")
    validation_warn = sum(1 for row in validation if str(row.get("status", "")).upper() == "WARNING")
    warning_names = ", ".join(
        str(row.get("note")) for row in validation if str(row.get("status", "")).upper() == "WARNING"
    )

    return [
        (
            f"В границах исследования {block_count} кварталов общей площадью "
            f"{fmt_num(summary.get('block_area_km2'), 2)} км²; оценка населения — "
            f"{fmt_int(population_total)} чел. в {blocks_with_population} кварталах."
        ),
        (
            f"Застройка представлена в {summary.get('blocks_with_buildings', 0)} кварталах, всего "
            f"{fmt_int(buildings_count)} зданий. Медианные FSI/GSI — "
            f"{fmt_num(density.get('fsi'), 3)} / {fmt_num(density.get('gsi'), 3)}, "
            f"медианная этажность — {fmt_num(density.get('l'), 2)}."
        ),
        (
            f"В городе {schools_count} {plural_ru(schools_count, 'школа', 'школы', 'школ')} "
            f"суммарной вместимостью {fmt_int(capacity_total)} мест. "
            f"Спрос в кварталах расчёта — {fmt_int(demand_total)} чел., дефицит — "
            f"{fmt_int(gap)} {plural_ru(gap, 'место', 'места', 'мест')}; "
            f"сильная обеспеченность — {fmt_pct(coverage)}. "
            f"Вне покрытия остаётся {fmt_int(demand_left)} чел."
        ),
        (
            f"Медиана доступности — {fmt_num(median_access, 1)} мин. Самые удалённые кварталы: "
            + ", ".join(f"{block_id} ({fmt_num(value, 1)} мин)" for block_id, value in worst)
            + ". Самые доступные: "
            + ", ".join(f"{block_id} ({fmt_num(value, 1)} мин)" for block_id, value in best)
            + "."
        ),
        (
            f"Землепользование: {land_text}. Доля кварталов без land_use — {fmt_pct(land_use_nan)}; "
            f"это главный пробел исходных данных."
        ),
        (
            f"Самый частый морфотип Spacematrix — «{top_morph}» ({top_morph_count} кварталов). "
            f"Наибольший неснятый спрос на школы: "
            + ", ".join(f"квартал {block_id} — {fmt_int(value)} чел" for block_id, value in top_gap)
            + "."
        ),
        (
            f"Матрица доступности {matrix.get('rows', '—')}×{matrix.get('columns', '—')}: "
            f"медиана минимального времени {fmt_num(matrix.get('median_min'), 1)} мин, "
            f"p95 — {fmt_num(matrix.get('p95_min'), 1)} мин, максимум — "
            f"{fmt_num(matrix.get('max_min'), 1)} мин. Пешеходный граф: "
            f"{graph.get('nodes', '—')} узлов, {graph.get('edges', '—')} рёбер; "
            f"компонентов связности — {graph.get('components', '—')}."
        ),
        (
            f"Валидация: {validation_ok} проверок OK, {validation_warn} "
            f"{plural_ru(validation_warn, 'предупреждение', 'предупреждения', 'предупреждений')}"
            + (f" ({warning_names})" if warning_names else "")
            + ". Все значения — оценки на основе OSM и BlocksNet, а не официальная статистика."
        ),
    ]


def wrap_table(
    headers: list[str],
    rows: list[list[str]],
    table_id: str = "",
    caption: str = "",
    note: str = "",
    min_width: str = "",
) -> str:
    id_attr = f' id="{esc(table_id)}"' if table_id else ""
    style = f' style="min-width:{esc(min_width)}"' if min_width else ""
    head = "".join(f"<th>{header}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    caption_html = f"<caption>{esc(caption)}</caption>" if caption else ""
    note_html = f'<p class="table-note">{esc(note)}</p>' if note else ""
    return (
        f'<div class="table-scroll"><table{id_attr}{style}>'
        f"{caption_html}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{note_html}"
    )


def build_kpi(summary: dict[str, Any], provision_rows: list[dict[str, Any]]) -> str:
    demand_total = sum(finite(row.get("demand")) or 0.0 for row in provision_rows)
    capacity_total = finite(summary.get("school_capacity_total")) or 0.0
    gap = max(demand_total - capacity_total, 0.0)
    density = summary.get("density_medians") or {}
    school_blocks = int(finite(summary.get("blocks_with_school_capacity")) or 0)
    cards = [
        ("Кварталы", fmt_int(summary.get("block_count")), f"{fmt_num(summary.get('block_area_km2'), 2)} км²"),
        (
            "Население",
            fmt_int(summary.get("population_total")),
            f"{summary.get('blocks_with_population', '—')} кварталов",
        ),
        (
            "Застройка",
            fmt_int(summary.get("buildings_count")),
            f"{summary.get('blocks_with_buildings', '—')} кварталов",
        ),
        (
            "Школы",
            fmt_int(summary.get("schools_count")),
            f"{school_blocks} {plural_ru(school_blocks, 'квартал', 'квартала', 'кварталов')} · {fmt_int(capacity_total)} мест",
        ),
        ("Обеспеченность", fmt_pct(summary.get("provision_strong_total")), "сильная обеспеченность"),
        ("Доступность", f"{fmt_num(summary.get('area_accessibility_median'), 1)} мин", "медиана"),
        ("Спрос / дефицит", f"{fmt_int(demand_total)} / {fmt_int(gap)}", "чел. / мест"),
        ("Плотность", f"FSI {fmt_num(density.get('fsi'), 3)}", "медиана"),
    ]
    return "".join(
        f'<article class="kpi"><div class="kpi-label">{esc(label)}</div>'
        f'<div class="kpi-value">{esc(value)}</div><div class="kpi-note">{esc(note)}</div></article>'
        for label, value, note in cards
    )


def build_summary_stats_table(stats: list[dict[str, Any]], block_count: int) -> str:
    headers = ["Показатель", "Ед.", "Есть", "Нет", "Мин", "Медиана", "Среднее", "Макс"]
    rows = []
    for row in stats:
        spec = FIELD_BY_KEY[row["key"]]
        decimals = spec["decimals"]
        rows.append(
            [
                esc(spec["label"]),
                esc(spec["unit"]),
                str(row["count"]),
                str(row["missing"]),
                esc(fmt_num(row["min"], decimals)),
                esc(fmt_num(row["median"], decimals)),
                esc(fmt_num(row["mean"], decimals)),
                esc(fmt_num(row["max"], decimals)),
            ]
        )
    return wrap_table(
        headers,
        rows,
        table_id="stats-table",
        caption="Описательные статистики по всем числовым показателям",
        note=f"N = {block_count} кварталов; «Нет» — число пустых значений.",
        min_width="980px",
    )


def build_blocks_table(blocks: list[dict[str, Any]]) -> str:
    headers = []
    for key in FIELD_KEYS:
        spec = FIELD_BY_KEY[key]
        unit = f'<span class="th-unit">{esc(spec["unit"])}</span>' if spec["unit"] else ""
        headers.append(f'<th title="{esc(spec["description"])}">{esc(spec["label"])}{unit}</th>')
    body_parts = []
    for block in blocks:
        cells = []
        for key in FIELD_KEYS:
            spec = FIELD_BY_KEY[key]
            value = block.get(key)
            classes = "num" if spec["kind"] == "numeric" else ("id" if spec["kind"] == "id" else "cat")
            if value is None or value == "":
                cells.append(f'<td class="{classes}"><span class="muted">—</span></td>')
            else:
                cells.append(f'<td class="{classes}">{fmt_cell(key, value)}</td>')
        body_parts.append(f'<tr data-block-id="{esc(block["block_id"])}">' + "".join(cells) + "</tr>")
    body = "".join(body_parts)
    head = "".join(headers)
    return (
        f'<div class="table-scroll"><table id="blocks-table" style="min-width:3600px">'
        f"<caption>Все показатели по кварталам</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
        '<p class="table-note">Пустые значения — нет данных. Таблица фильтруется по ID, функции или морфотипу.</p>'
    )


def build_provision_table(provision_rows: list[dict[str, Any]]) -> str:
    columns = [
        "block_id",
        "demand",
        "capacity",
        "demand_left",
        "demand_within",
        "demand_without",
        "capacity_left",
        "capacity_within",
        "capacity_without",
        "provision_strong",
        "provision_weak",
        "provision_gap",
    ]
    headers = [esc(FIELD_BY_KEY[key]["label"]) for key in columns]
    rows = []
    for row in sorted(provision_rows, key=lambda item: item["block_id"]):
        rows.append([fmt_cell(key, row.get(key)) for key in columns])
    return wrap_table(
        headers,
        rows,
        table_id="provision-table",
        caption="Школьное обеспечение по кварталам расчёта",
        note=f"{len(rows)} строк; кварталы с населением или вместимостью школ; provision_gap = weak − strong.",
        min_width="1220px",
    )


def build_links_table(links: list[dict[str, Any]]) -> str:
    headers = ["Квартал-источник", "Квартал школы", "Учеников"]
    rows = [[esc(link["source"]), esc(link["target"]), esc(fmt_num(link["value"], 0))] for link in links]
    return wrap_table(
        headers,
        rows,
        table_id="links-table",
        caption="Связи «квартал → школа»",
        note=f"{len(rows)} связей; target — квартал, где расположена школа; value — распределённый спрос только между кварталами.",
        min_width="420px",
    )


def count_morph_rows(values: list[Any]) -> str:
    counts = Counter(category_label(value) for value in values)
    total = sum(counts.values()) or 1
    rows = []
    for label, count in counts.most_common():
        rows.append([esc(label), str(count), esc(fmt_pct(count / total))])
    return wrap_table(
        ["Морфотип", "Кварталов", "Доля"],
        rows,
        caption="Распределение морфотипов",
        note="Доля считается среди всех кварталов; «нет данных» — отсутствующий морфотип.",
        min_width="620px",
    )


def build_morph_tables(blocks: list[dict[str, Any]]) -> str:
    spacematrix = count_morph_rows([block.get("spacematrix_morphotype") for block in blocks])
    strelka = count_morph_rows([block.get("strelka_morphotype") for block in blocks])
    return f'<div class="table-pair"><div><h4>Spacematrix</h4>{spacematrix}</div><div><h4>Strelka</h4>{strelka}</div></div>'


def build_cluster_table(rows: list[dict[str, Any]]) -> str:
    headers = ["Кластер", "L", "FSI", "MXI", "Этажность", "Плотность", "Смешанность", "Морфотип"]
    body = []
    for row in sorted(rows, key=lambda item: finite(item.get("cluster")) or 0):
        body.append(
            [
                esc(category_label(row.get("cluster"))),
                esc(fmt_num(row.get("l"), 3)),
                esc(fmt_num(row.get("fsi"), 3)),
                esc(fmt_num(row.get("mxi"), 3)),
                esc(row.get("l_interpretation") or "—"),
                esc(row.get("fsi_interpretation") or "—"),
                esc(row.get("mxi_interpretation") or "—"),
                esc(row.get("morphotype") or "—"),
            ]
        )
    return wrap_table(
        headers,
        body,
        table_id="cluster-table",
        caption="Кластеры Spacematrix",
        note="Готовые описания кластеров из spacematrix_clusters.csv.",
        min_width="980px",
    )


def build_validation_table(rows: list[dict[str, Any]]) -> str:
    headers = ["Проверка", "Статус", "Значение", "Комментарий"]
    body = []
    for row in rows:
        status = str(row.get("status") or "").upper()
        cls = "ok" if status == "OK" else ("warn" if status == "WARNING" else "error")
        body.append(
            [
                esc(row.get("check")),
                f'<span class="badge {cls}">{esc(status or "—")}</span>',
                esc(row.get("value")),
                esc(row.get("note") or "—"),
            ]
        )
    return wrap_table(
        headers,
        body,
        table_id="validation-table",
        caption="Валидация результатов",
        note=f"{len(body)} проверок.",
        min_width="760px",
    )


def build_dictionary_table() -> str:
    kind_labels = {"id": "ID", "numeric": "число", "category": "категория"}
    rows = []
    for spec in FIELD_SPECS:
        rows.append(
            [
                f'<code>{esc(spec["key"])}</code>',
                esc(spec["label"]),
                esc(spec["unit"] or "—"),
                esc(kind_labels.get(spec["kind"], spec["kind"])),
                esc(spec["description"]),
            ]
        )
    return wrap_table(
        ["Поле", "Показатель", "Ед.", "Тип", "Описание"],
        rows,
        table_id="dictionary-table",
        caption="Справочник показателей",
        note="Все поля, которые есть в таблице кварталов.",
        min_width="900px",
    )


def build_service_table(summary: dict[str, Any], warnings: list[str]) -> str:
    matrix = summary.get("matrix_stats") or {}
    graph = summary.get("graph") or {}
    density = summary.get("density_medians") or {}
    scope = summary.get("matrix_scope")
    scope_labels = {
        "all": "все кварталы",
        "populated": "кварталы с населением или школами",
    }
    scope_label = scope_labels.get(scope, scope or "—")
    rows = [
        ["Территория", esc(summary.get("territory") or "—")],
        ["Дата расчёта", esc(summary.get("created_at") or "—")],
        ["ID отношения OSM", esc(summary.get("osm_relation_id") or "—")],
        ["Источник OSM", esc(summary.get("osm_source") or "—")],
        ["Площадь границы", f'{esc(fmt_num(summary.get("boundary_area_km2"), 3))} км²'],
        ["Площадь кварталов", f'{esc(fmt_num(summary.get("block_area_km2"), 3))} км²'],
        ["Кварталы со школами", esc(fmt_int(summary.get("blocks_with_school_capacity")))],
        ["Норматив мест на 1000 жителей", esc(fmt_int(summary.get("school_demand_per_1000")))],
        ["Порог доступности школы", f'{esc(fmt_num(summary.get("school_accessibility_min"), 0))} мин'],
        ["Охват матрицы", esc(scope_label)],
        ["Матрица доступности", f'{esc(matrix.get("rows", "—"))} × {esc(matrix.get("columns", "—"))}'],
        ["Конечных значений матрицы", esc(fmt_pct(matrix.get("finite_share")))],
        ["Медиана минимального времени", f'{esc(fmt_num(matrix.get("median_min"), 2))} мин'],
        ["p95 минимального времени", f'{esc(fmt_num(matrix.get("p95_min"), 2))} мин'],
        ["Максимум минимального времени", f'{esc(fmt_num(matrix.get("max_min"), 2))} мин'],
        [
            "Пешеходный граф",
            f'{esc(graph.get("nodes", "—"))} узлов, {esc(graph.get("edges", "—"))} рёбер, {esc(graph.get("components", "—"))} {plural_ru(graph.get("components"), "компонент", "компонента", "компонентов")}',
        ],
        ["Граф рассчитан", esc(graph.get("created_at") or "—")],
        ["Скорость пешей сети", f'{esc(fmt_num(graph.get("walk_speed_kmh"), 1))} км/ч'],
        [
            "Время по рёбрам графа",
            f'медиана {esc(fmt_num(graph.get("time_min_median"), 2))} мин; p95 {esc(fmt_num(graph.get("time_min_p95"), 2))} мин',
        ],
        [
            "Медианы FSI / GSI / MXI",
            f'{esc(fmt_num(density.get("fsi"), 3))} / {esc(fmt_num(density.get("gsi"), 3))} / {esc(fmt_num(density.get("mxi"), 3))}',
        ],
        ["Медиана L / OSR", f'{esc(fmt_num(density.get("l"), 2))} / {esc(fmt_num(density.get("osr"), 2))}'],
        ["Кварталы без land_use", esc(fmt_pct(summary.get("land_use_nan_share")))],
        ["Примечание", esc(summary.get("notes") or "—")],
    ]
    if warnings:
        rows.append(["Предупреждения", esc("; ".join(warnings))])
    return wrap_table(
        ["Параметр", "Значение"],
        rows,
        table_id="service-table",
        caption="Параметры расчёта",
        note="Служебные значения из summary.json и доступность локальных слоёв.",
        min_width="720px",
    )


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {
  --bg: #f2f6f7;
  --panel: #ffffff;
  --ink: #13242b;
  --muted: #667784;
  --line: #dbe5e8;
  --accent: #0f766e;
  --accent-dark: #0b4f4a;
  --warn: #b45309;
  --radius: 18px;
  --shadow: 0 12px 32px rgba(19, 36, 43, 0.08);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
  line-height: 1.55;
}
a { color: var(--accent); }
.hero {
  background:
    radial-gradient(circle at 15% 10%, rgba(255, 255, 255, 0.16), transparent 28%),
    radial-gradient(circle at 85% 20%, rgba(125, 211, 191, 0.22), transparent 30%),
    linear-gradient(135deg, #0b2f3a 0%, #0f5b59 58%, #0f766e 100%);
  color: #fff;
  padding: 54px max(22px, calc((100vw - 1440px) / 2)) 78px;
}
.hero-inner { max-width: 1440px; margin: 0 auto; }
.eyebrow {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  padding: 6px 12px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 999px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.92;
}
h1 { font-size: clamp(30px, 4vw, 52px); line-height: 1.08; margin: 18px 0 14px; letter-spacing: -0.03em; }
.lead { max-width: 900px; font-size: clamp(16px, 1.5vw, 20px); color: rgba(255, 255, 255, 0.86); margin: 0; }
.hero-meta { margin-top: 22px; font-size: 13px; color: rgba(255, 255, 255, 0.7); }
main { max-width: 1440px; margin: -34px auto 0; padding: 0 22px 64px; }
.section { margin: 26px 0; }
.section-head { display: flex; justify-content: space-between; align-items: end; gap: 24px; margin-bottom: 14px; }
.section-head h2 { margin: 0; font-size: clamp(22px, 2.2vw, 30px); letter-spacing: -0.02em; }
.section-head p { margin: 0; max-width: 760px; color: var(--muted); font-size: 14px; }
.kpi-section { margin-top: 0; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 18px 16px; box-shadow: var(--shadow); }
.kpi-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }
.kpi-value { font-size: clamp(22px, 2.2vw, 31px); font-weight: 750; line-height: 1.2; margin-top: 8px; letter-spacing: -0.03em; }
.kpi-note { color: var(--muted); font-size: 12px; margin-top: 4px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px; box-shadow: var(--shadow); }
.map-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-bottom: 14px; }
.map-toolbar label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
select, input, button {
  font: inherit;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  color: var(--ink);
  padding: 9px 11px;
  min-height: 40px;
}
select { min-width: 280px; }
input { min-width: 160px; }
button { cursor: pointer; background: #e9f3f1; border-color: #cbe1dc; color: var(--accent-dark); font-weight: 650; }
button:hover { background: #dceeea; }
.metric-help { flex: 1 1 300px; min-width: 220px; color: var(--muted); font-size: 13px; padding-bottom: 8px; }
.map-wrap { position: relative; }
#map { height: 590px; border-radius: var(--radius); overflow: hidden; background: #dfe9ed; border: 1px solid var(--line); z-index: 1; }
.legend {
  position: absolute;
  z-index: 500;
  right: 14px;
  bottom: 26px;
  width: min(285px, calc(100% - 28px));
  max-height: 320px;
  overflow: auto;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 12px 13px;
  box-shadow: 0 12px 30px rgba(19, 36, 43, 0.14);
  font-size: 12px;
}
.legend-title { font-weight: 750; margin-bottom: 8px; }
.legend-item { display: flex; align-items: center; gap: 7px; margin: 4px 0; }
.legend-item span:nth-child(2) { flex: 1; }
.legend-count { color: var(--muted); }
.swatch { width: 15px; height: 15px; border-radius: 4px; border: 1px solid rgba(0, 0, 0, 0.15); flex: 0 0 auto; }
.leaflet-tooltip.block-tooltip {
  border: 0;
  border-radius: 12px;
  box-shadow: 0 10px 26px rgba(19, 36, 43, 0.2);
  padding: 11px 12px;
  max-width: 330px;
  white-space: normal;
  color: var(--ink);
}
.tt-title { font-weight: 800; margin-bottom: 6px; }
.tt-current { padding: 6px 0; border-bottom: 1px solid var(--line); margin-bottom: 5px; }
.tt-row { display: flex; justify-content: space-between; gap: 14px; font-size: 12px; }
.tt-row span { color: var(--muted); }
.hint { color: var(--muted); font-size: 12px; margin: 10px 2px 0; }
.hint.warn { color: var(--warn); }
.conclusions { margin: 0; padding-left: 22px; display: grid; gap: 10px; }
.conclusions li { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 13px 16px; box-shadow: var(--shadow); }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.chart-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow); min-width: 0; }
.chart-card h3 { margin: 0 0 10px; font-size: 15px; }
.chart-card.wide { grid-column: 1 / -1; }
.chart-box { position: relative; height: 320px; min-width: 0; }
.chart-box.tall { height: 360px; }
.table-card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; margin-bottom: 12px; box-shadow: var(--shadow); }
.table-card > summary { cursor: pointer; font-weight: 750; font-size: 17px; list-style: none; display: flex; align-items: center; gap: 10px; }
.table-card > summary::-webkit-details-marker { display: none; }
.table-card > summary::before { content: "+"; display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: #e9f3f1; color: var(--accent-dark); font-weight: 800; }
.table-card[open] > summary::before { content: "−"; }
.table-card[open] > summary { margin-bottom: 12px; }
.table-tools { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 0 0 10px; }
.table-tools input { min-width: 280px; flex: 1 1 320px; }
.table-scroll { overflow: auto; max-height: 680px; border: 1px solid var(--line); border-radius: 12px; }
table { border-collapse: collapse; width: 100%; background: #fff; font-size: 12px; }
caption { text-align: left; padding: 9px 11px; color: var(--muted); font-size: 12px; background: #f7fafb; border-bottom: 1px solid var(--line); }
th, td { padding: 7px 9px; border-bottom: 1px solid #edf1f3; white-space: nowrap; text-align: left; }
thead th { position: sticky; top: 0; z-index: 2; background: #eef4f5; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; }
tbody tr:nth-child(even) { background: #fbfcfd; }
tbody tr:hover { background: #f0f8f6; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.id { font-weight: 700; color: var(--accent-dark); }
td.cat { max-width: 280px; overflow: hidden; text-overflow: ellipsis; }
.th-unit { display: block; font-weight: 400; color: var(--muted); text-transform: none; letter-spacing: 0; font-size: 10px; }
.muted { color: #9aa8b1; }
.table-note { color: var(--muted); font-size: 12px; margin: 8px 2px 0; }
.table-pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.table-pair h4 { margin: 0 0 8px; font-size: 14px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 750; }
.badge.ok { background: #dcfce7; color: #166534; }
.badge.warn { background: #fef3c7; color: #92400e; }
.badge.error { background: #fee2e2; color: #991b1b; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); border: 0; }
footer { max-width: 1440px; margin: 0 auto; padding: 0 22px 40px; color: var(--muted); font-size: 12px; }
footer strong { color: var(--ink); }
@media (max-width: 900px) {
  .chart-grid, .table-pair { grid-template-columns: 1fr; }
  .section-head { display: block; }
  .section-head p { margin-top: 6px; }
  #map { height: 480px; }
  select { min-width: 100%; width: 100%; }
  .map-toolbar label { flex: 1 1 100%; }
}
</style>
</head>
<body>
<header class="hero">
  <div class="hero-inner">
    <div class="eyebrow">BlocksNet · OSM · __TERRITORY__</div>
    <h1>__TITLE__</h1>
    <p class="lead">__LEAD__</p>
    <div class="hero-meta">Сформировано __GENERATED__ · данные не скачиваются, показатели не пересчитываются</div>
  </div>
</header>
<main>
  <section class="section kpi-section" aria-label="Ключевые показатели">
    <div class="kpi-grid">__KPI_HTML__</div>
  </section>

  <section class="section" id="map-section">
    <div class="section-head">
      <div>
        <h2>Интерактивная карта</h2>
        <p>Выберите показатель, наведите курсор на квартал или найдите его по ID. Подложка собрана из локальных OSM-слоёв; внешние тайлы не используются.</p>
      </div>
    </div>
    <div class="map-toolbar">
      <label>Показатель<select id="metric-select"></select></label>
      <label>Поиск квартала<input id="block-search" inputmode="numeric" placeholder="Например, 31"></label>
      <button id="reset-view" type="button">Сбросить вид</button>
      <span id="metric-help" class="metric-help"></span>
    </div>
    <div class="map-wrap">
      <div id="map" role="application" aria-label="Интерактивная карта кварталов Суздаля"></div>
      <div id="legend" class="legend"></div>
    </div>
    <p class="hint">__MAP_NOTE__</p>
  </section>

  <section class="section" id="conclusions">
    <div class="section-head">
      <div>
        <h2>Выводы</h2>
        <p>Короткие выводы построены по уже сохранённым результатам; это интерпретация оценок OSM + BlocksNet, а не официальная статистика.</p>
      </div>
    </div>
    <ol class="conclusions">__CONCLUSIONS_HTML__</ol>
  </section>

  <section class="section" id="charts">
    <div class="section-head">
      <div>
        <h2>Графики</h2>
        <p>Основные распределения и сравнения. Полные значения — в таблицах ниже.</p>
      </div>
    </div>
    <div class="chart-grid">
      <div class="chart-card"><h3>Топ-12 кварталов по населению</h3><div class="chart-box"><canvas id="chart-population"></canvas></div></div>
      <div class="chart-card"><h3>Распределение доступности</h3><div class="chart-box"><canvas id="chart-accessibility"></canvas></div></div>
      <div class="chart-card"><h3>Покрытие спроса на школьные места</h3><div class="chart-box"><canvas id="chart-provision"></canvas></div></div>
      <div class="chart-card"><h3>Структура землепользования</h3><div class="chart-box"><canvas id="chart-land-use"></canvas></div></div>
      <div class="chart-card"><h3>Морфотипы Spacematrix</h3><div class="chart-box tall"><canvas id="chart-spacematrix"></canvas></div></div>
      <div class="chart-card"><h3>Морфотипы Strelka</h3><div class="chart-box tall"><canvas id="chart-strelka"></canvas></div></div>
      <div class="chart-card wide"><h3>FSI и GSI кварталов с застройкой</h3><div class="chart-box"><canvas id="chart-scatter"></canvas></div></div>
    </div>
  </section>

  <section class="section" id="tables">
    <div class="section-head">
      <div>
        <h2>Таблицы</h2>
        <p>Все показатели, школьное обеспечение, морфотипы, кластеры и валидация. Таблицы можно прокручивать по горизонтали.</p>
      </div>
    </div>
    <details class="table-card" open>
      <summary>Сводная статистика показателей</summary>
      __SUMMARY_TABLE__
    </details>
    <details class="table-card" open>
      <summary>Все показатели по кварталам</summary>
      <div class="table-tools">
        <input id="blocks-filter" placeholder="Фильтр: ID, функция, морфотип…">
        <span id="blocks-count" class="muted"></span>
      </div>
      __BLOCKS_TABLE__
    </details>
    <details class="table-card">
      <summary>Школьное обеспечение по кварталам</summary>
      __PROVISION_TABLE__
    </details>
    <details class="table-card">
      <summary>Связи «квартал → школа»</summary>
      __LINKS_TABLE__
    </details>
    <details class="table-card">
      <summary>Морфотипы Spacematrix и Strelka</summary>
      __MORPH_TABLE__
    </details>
    <details class="table-card">
      <summary>Кластеры Spacematrix</summary>
      __CLUSTER_TABLE__
    </details>
    <details class="table-card">
      <summary>Параметры расчёта</summary>
      __SERVICE_TABLE__
    </details>
    <details class="table-card">
      <summary>Справочник показателей</summary>
      __DICTIONARY_TABLE__
    </details>
    <details class="table-card">
      <summary>Валидация результатов</summary>
      __VALIDATION_TABLE__
    </details>
  </section>
</main>
<footer>
  <p><strong>Источник:</strong> __RESULTS_LABEL__. OpenStreetMap contributors (ODbL), Geofabrik, Pyrosm, Nominatim, BlocksNet.</p>
  <p>Dashboard читает готовые GeoJSON/CSV/JSON и не выполняет сетевые загрузки данных или повторные расчёты метрик. Для отображения карты и графиков нужны CDN-библиотеки Leaflet и Chart.js.</p>
</footer>
<noscript><p style="padding:20px">Для интерактивной карты и графиков нужен JavaScript.</p></noscript>
"""
HTML_TEMPLATE += r"""
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const DATA = __DATA_JSON__;
const LAND_USE_RU = DATA.labels.land_use;
const CATEGORICAL = ["#1d4ed8", "#0f766e", "#b45309", "#7e22ce", "#be123c", "#4d7c0f", "#0e7490", "#a16207", "#9d174d", "#374151", "#2563eb", "#65a30d"];
const PALETTES = {
  blue: ["#eff6ff", "#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa", "#3b82f6", "#1d4ed8", "#1e3a8a"],
  green: ["#f0fdf4", "#dcfce7", "#bbf7d0", "#86efac", "#4ade80", "#22c55e", "#15803d", "#14532d"],
  teal: ["#f0fdfa", "#ccfbf1", "#99f6e4", "#5eead4", "#2dd4bf", "#14b8a6", "#0f766e", "#134e4a"],
  red: ["#fef2f2", "#fee2e2", "#fecaca", "#fca5a5", "#f87171", "#ef4444", "#b91c1c", "#7f1d1d"],
  orange: ["#fff7ed", "#ffedd5", "#fed7aa", "#fdba74", "#fb923c", "#f97316", "#c2410c", "#7c2d12"],
  purple: ["#faf5ff", "#f3e8ff", "#e9d5ff", "#d8b4fe", "#c084fc", "#a855f7", "#7e22ce", "#4c1d95"],
  yellow: ["#fefce8", "#fef9c3", "#fef08a", "#fde047", "#facc15", "#eab308", "#a16207", "#713f12"],
  gray: ["#f8fafc", "#f1f5f9", "#e2e8f0", "#cbd5e1", "#94a3b8", "#64748b", "#475569", "#1e293b"],
  green_red: ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#91cf60", "#1a9850"],
  green_red_r: ["#1a9850", "#91cf60", "#d9ef8b", "#fee08b", "#fc8d59", "#d73027"]
};
const LAND_USE_COLORS = {
  "жилая": "#4c78a8", "деловая": "#f58518", "рекреационная": "#54a24b",
  "промышленная": "#e45756", "транспортная": "#9d755d", "специальная": "#b279a2",
  "сельскохозяйственная": "#eeca3b", "смешанная": "#72b7b2", "не задано": "#b8c2cc"
};
const esc = (value) => String(value ?? "—").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const fmt = (value, decimals = 2) => {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toLocaleString("ru-RU", {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
};
const fmtPct = (value, decimals = 1) => value === null || value === undefined || !Number.isFinite(Number(value)) ? "—" : fmt(Number(value) * 100, decimals) + "%";
const metricByKey = Object.fromEntries(DATA.metrics.map((metric) => [metric.key, metric]));
let currentMetric = "population";
let map;
let blockLayer;
let blockBounds;
const layerById = {};
const centroids = {};

function getPalette(name) {
  const reverse = name.endsWith("_r");
  const palette = PALETTES[reverse ? name.slice(0, -2) : name] || PALETTES.blue;
  return reverse ? [...palette].reverse() : palette;
}

function categoryKey(value) {
  return value === null || value === undefined || value === "" ? "нет данных" : String(value);
}

function displayCategory(meta, value) {
  const key = categoryKey(value);
  return meta.value_labels && meta.value_labels[key] ? meta.value_labels[key] : key;
}

function displayMetric(meta, value) {
  if (value === null || value === undefined || value === "") return "—";
  if (meta.kind === "category") return displayCategory(meta, value);
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return fmt(number, meta.decimals) + (meta.unit ? " " + meta.unit : "");
}

function colorFor(meta, value) {
  if (meta.kind === "category") {
    const key = categoryKey(value);
    if (key === "нет данных") return "#d9d9d9";
    const index = meta.values.indexOf(key);
    return index < 0 ? "#d9d9d9" : CATEGORICAL[index % CATEGORICAL.length];
  }
  const number = Number(value);
  if (!Number.isFinite(number) || meta.min === null || meta.max === null) return "#d9d9d9";
  const ratio = meta.max === meta.min ? 0.5 : (number - meta.min) / (meta.max - meta.min);
  const palette = getPalette(meta.palette);
  const index = Math.min(palette.length - 1, Math.max(0, Math.floor(ratio * (palette.length - 1))));
  return palette[index];
}

function blockStyle(feature) {
  const meta = metricByKey[currentMetric];
  return {
    fillColor: colorFor(meta, feature.properties[currentMetric]),
    fillOpacity: 0.72,
    color: "#ffffff",
    weight: 0.8,
    opacity: 0.9
  };
}

function tooltipRow(label, value) {
  return `<div class="tt-row"><span>${esc(label)}</span><b>${esc(value)}</b></div>`;
}

function blockTooltip(props) {
  const meta = metricByKey[currentMetric];
  const landUse = LAND_USE_RU[props.land_use] || props.land_use || "не задано";
  return [
    `<div class="tt-title">Квартал ${esc(props.block_id)}</div>`,
    `<div class="tt-current">${esc(meta.label)}: <b>${esc(displayMetric(meta, props[currentMetric]))}</b></div>`,
    tooltipRow("Население", fmt(props.population, 0) + " чел."),
    tooltipRow("Школы", `${fmt(props.school_count, 0)} / ${fmt(props.capacity, 0)} мест`),
    tooltipRow("Спрос / не покрыт", `${fmt(props.demand, 0)} / ${fmt(props.demand_left, 0)} чел.`),
    tooltipRow("Обеспеченность", fmtPct(props.provision_strong)),
    tooltipRow("Доступность", fmt(props.area_accessibility, 1) + " мин"),
    tooltipRow("FSI / GSI", `${fmt(props.fsi, 3)} / ${fmt(props.gsi, 3)}`),
    tooltipRow("Этажность / OSR", `${fmt(props.l, 2)} / ${fmt(props.osr, 2)}`),
    tooltipRow("Морфотип", props.spacematrix_morphotype || "—"),
    tooltipRow("Землепользование", landUse)
  ].join("");
}

function renderLegend(meta) {
  const legend = document.getElementById("legend");
  const parts = [`<div class="legend-title">${esc(meta.label)}</div>`];
  if (meta.kind === "category") {
    meta.values.slice(0, 12).forEach((value, index) => {
      const count = meta.counts[value] || 0;
      const color = value === "нет данных" ? "#d9d9d9" : CATEGORICAL[index % CATEGORICAL.length];
      parts.push(`<div class="legend-item"><span class="swatch" style="background:${color}"></span><span>${esc(displayCategory(meta, value))}</span><span class="legend-count">${count}</span></div>`);
    });
    if (meta.values.length > 12) parts.push(`<div class="legend-item"><span>…</span><span>ещё ${meta.values.length - 12}</span></div>`);
  } else if (meta.min === null || meta.max === null) {
    parts.push('<div class="legend-item"><span class="swatch" style="background:#d9d9d9"></span><span>нет данных</span></div>');
  } else {
    const palette = getPalette(meta.palette);
    const steps = 6;
    for (let index = steps - 1; index >= 0; index -= 1) {
      const from = meta.min + (meta.max - meta.min) * index / steps;
      const to = meta.min + (meta.max - meta.min) * (index + 1) / steps;
      const color = palette[Math.min(palette.length - 1, Math.floor((index + 0.5) / steps * palette.length))];
      parts.push(`<div class="legend-item"><span class="swatch" style="background:${color}"></span><span>${esc(fmt(from, meta.decimals))}–${esc(fmt(to, meta.decimals))}</span></div>`);
    }
    parts.push('<div class="legend-item"><span class="swatch" style="background:#d9d9d9"></span><span>нет данных</span></div>');
  }
  legend.innerHTML = parts.join("");
  document.getElementById("metric-help").textContent = meta.description;
}

function updateMetric(key) {
  currentMetric = key;
  const meta = metricByKey[key];
  blockLayer.eachLayer((layer) => {
    layer.setStyle(blockStyle(layer.feature));
    const content = blockTooltip(layer.feature.properties);
    if (layer.getTooltip()) layer.setTooltipContent(content);
    if (layer.getPopup()) layer.setPopupContent(content);
  });
  renderLegend(meta);
}

function buildMetricSelect() {
  const select = document.getElementById("metric-select");
  const groups = {};
  DATA.metrics.forEach((metric) => {
    const group = metric.group || "Прочее";
    if (!groups[group]) groups[group] = [];
    groups[group].push(metric);
  });
  const order = ["Территория", "Землепользование", "Население и школы", "Доступность", "Плотность", "Морфология", "Застройка"];
  order.forEach((name) => {
    if (!groups[name]) return;
    const optgroup = document.createElement("optgroup");
    optgroup.label = name;
    groups[name].forEach((metric) => {
      const option = document.createElement("option");
      option.value = metric.key;
      option.textContent = metric.label + (metric.unit ? `, ${metric.unit}` : "");
      optgroup.appendChild(option);
    });
    select.appendChild(optgroup);
  });
  Object.keys(groups).filter((name) => !order.includes(name)).forEach((name) => {
    const optgroup = document.createElement("optgroup");
    optgroup.label = name;
    groups[name].forEach((metric) => {
      const option = document.createElement("option");
      option.value = metric.key;
      option.textContent = metric.label + (metric.unit ? `, ${metric.unit}` : "");
      optgroup.appendChild(option);
    });
    select.appendChild(optgroup);
  });
  select.value = currentMetric;
  select.addEventListener("change", (event) => updateMetric(event.target.value));
}

function focusBlock(rawId) {
  const id = String(rawId).trim();
  const layer = layerById[id];
  if (!layer) {
    document.getElementById("block-search").setCustomValidity("Квартал не найден");
    document.getElementById("block-search").reportValidity();
    return;
  }
  document.getElementById("block-search").setCustomValidity("");
  map.fitBounds(layer.getBounds(), {padding: [40, 40], maxZoom: 17});
  layer.openPopup();
  layer.setStyle({color: "#111827", weight: 3, fillOpacity: 0.92});
  window.setTimeout(() => blockLayer.resetStyle(layer), 3500);
}

function initMap() {
  if (typeof L === "undefined") {
    document.getElementById("map").innerHTML = '<p style="padding:20px">Leaflet не загрузился. Проверьте доступ к CDN.</p>';
    return;
  }
  map = L.map("map", {zoomControl: true, attributionControl: true}).setView([56.42, 40.45], 13);
  map.attributionControl.setPrefix(false);
  map.attributionControl.addAttribution("Данные: OpenStreetMap contributors, ODbL; BlocksNet");

  const waterLayer = L.geoJSON(DATA.layers.water, {
    style: (feature) => feature.geometry.type.includes("Polygon")
      ? {color: "#4f8fc0", weight: 0.8, fillColor: "#8ecae6", fillOpacity: 0.62}
      : {color: "#4f8fc0", weight: 1.1, fill: false, opacity: 0.8}
  });
  const roadLayer = L.geoJSON(DATA.layers.roads, {
    style: (feature) => {
      if (feature.geometry.type.includes("Polygon")) {
        return {color: "#9aa5b1", weight: 1, fillColor: "#e5e7eb", fillOpacity: 0.45};
      }
      const highway = feature.properties.highway || "";
      const weights = {motorway: 4, trunk: 3.5, primary: 3, secondary: 2.5, tertiary: 2, residential: 1.5, service: 1, footway: 0.8, path: 0.8, pedestrian: 1.2};
      return {color: "#7c8796", weight: weights[highway] || 1, opacity: 0.65};
    }
  });
  const boundaryLayer = L.geoJSON(DATA.layers.boundary, {
    style: {color: "#1f2937", weight: 2, dashArray: "6 4", fill: false}
  });

  blockLayer = L.geoJSON(DATA.blocks, {
    style: blockStyle,
    onEachFeature: (feature, layer) => {
      const props = feature.properties;
      layerById[String(props.block_id)] = layer;
      layer.bindTooltip(blockTooltip(props), {sticky: true, className: "block-tooltip", direction: "top"});
      layer.bindPopup(blockTooltip(props), {maxWidth: 340});
    }
  });
  blockLayer.eachLayer((layer) => {
    const center = layer.getBounds().getCenter();
    centroids[String(layer.feature.properties.block_id)] = [center.lat, center.lng];
  });

  const schoolLayer = L.layerGroup(DATA.schools.map((school) => {
    return L.circleMarker([school.lat, school.lon], {
      radius: 7, color: "#ffffff", weight: 2, fillColor: "#b91c1c", fillOpacity: 1
    }).bindPopup(`<b>${esc(school.name)}</b><br>Школа · OSM ${esc(school.osm_type || "")} ${esc(school.osm_id || "")}`);
  }));

  function nearestSchool(point) {
    let best = null;
    let bestDistance = Infinity;
    DATA.schools.forEach((school) => {
      const dLat = school.lat - point[0];
      const dLon = (school.lon - point[1]) * Math.cos(point[0] * Math.PI / 180);
      const distance = dLat * dLat + dLon * dLon;
      if (distance < bestDistance) {
        bestDistance = distance;
        best = school;
      }
    });
    return best;
  }

  const linkLayer = L.layerGroup(DATA.links.map((link) => {
    const source = centroids[String(link.source)];
    const blockCenter = centroids[String(link.target)];
    if (!source || !blockCenter) return null;
    const school = nearestSchool(blockCenter);
    const target = school ? [school.lat, school.lon] : blockCenter;
    const targetLabel = school ? esc(school.name) : `школа в квартале ${link.target}`;
    return L.polyline([source, target], {
      color: "#d97706", weight: 1.4, opacity: 0.7, dashArray: "5 5"
    }).bindTooltip(`Квартал ${link.source} → ${targetLabel}: ${fmt(link.value, 0)} чел.`, {sticky: true});
  }).filter(Boolean));

  waterLayer.addTo(map);
  boundaryLayer.addTo(map);
  blockLayer.addTo(map);
  roadLayer.addTo(map);
  linkLayer.addTo(map);
  schoolLayer.addTo(map);

  blockBounds = blockLayer.getBounds();
  map.fitBounds(blockBounds, {padding: [20, 20]});
  L.control.layers({}, {
    "Кварталы": blockLayer,
    "Школы": schoolLayer,
    "Дороги": roadLayer,
    "Вода": waterLayer,
    "Граница": boundaryLayer,
    "Школьные связи": linkLayer
  }, {collapsed: true, position: "topright"}).addTo(map);
  L.control.scale({position: "bottomleft", metric: true, imperial: false}).addTo(map);

  buildMetricSelect();
  updateMetric(currentMetric);
  document.getElementById("reset-view").addEventListener("click", () => map.fitBounds(blockBounds, {padding: [20, 20]}));
  const search = document.getElementById("block-search");
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      focusBlock(search.value);
    }
  });
}

function initCharts() {
  if (typeof Chart === "undefined") {
    document.querySelectorAll(".chart-box").forEach((box) => {
      box.innerHTML = '<p class="hint warn">Chart.js не загрузился. Проверьте доступ к CDN.</p>';
    });
    return;
  }
  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
  Chart.defaults.color = "#334155";
  const charts = DATA.charts;
  const common = {responsive: true, maintainAspectRatio: false, animation: false};

  new Chart(document.getElementById("chart-population"), {
    type: "bar",
    data: {labels: charts.top_population.labels, datasets: [{data: charts.top_population.values, backgroundColor: "#2f7d6d", borderRadius: 5}]},
    options: {...common, indexAxis: "y", plugins: {legend: {display: false}, tooltip: {callbacks: {label: (ctx) => ` ${fmt(ctx.raw, 0)} чел.`}}}, scales: {x: {beginAtZero: true, title: {display: true, text: "чел."}}, y: {grid: {display: false}}}}
  });

  new Chart(document.getElementById("chart-accessibility"), {
    type: "bar",
    data: {labels: charts.accessibility_hist.labels, datasets: [{data: charts.accessibility_hist.values, backgroundColor: "#4c78a8", borderRadius: 4}]},
    options: {...common, plugins: {legend: {display: false}, tooltip: {callbacks: {label: (ctx) => ` ${fmt(ctx.raw, 0)} кварталов`}}}, scales: {x: {title: {display: true, text: "минуты"}}, y: {beginAtZero: true, title: {display: true, text: "кварталы"}}}}
  });

  new Chart(document.getElementById("chart-provision"), {
    type: "doughnut",
    data: {labels: ["Покрыто", "Не покрыто"], datasets: [{data: [charts.provision.demand_within, charts.provision.demand_left], backgroundColor: ["#1a9850", "#d73027"], borderWidth: 0}]},
    options: {...common, cutout: "58%", plugins: {legend: {position: "bottom"}, tooltip: {callbacks: {label: (ctx) => ` ${ctx.label}: ${fmt(ctx.raw, 0)} чел.`}}}}
  });

  new Chart(document.getElementById("chart-land-use"), {
    type: "doughnut",
    data: {labels: charts.land_use.labels, datasets: [{data: charts.land_use.values, backgroundColor: charts.land_use.labels.map((label) => LAND_USE_COLORS[label] || "#94a3b8"), borderWidth: 0}]},
    options: {...common, cutout: "52%", plugins: {legend: {position: "bottom"}, tooltip: {callbacks: {label: (ctx) => ` ${ctx.label}: ${fmt(ctx.raw, 0)} кварталов`}}}}
  });

  new Chart(document.getElementById("chart-spacematrix"), {
    type: "bar",
    data: {labels: charts.spacematrix.labels, datasets: [{data: charts.spacematrix.values, backgroundColor: CATEGORICAL.slice(0, charts.spacematrix.labels.length), borderRadius: 4}]},
    options: {...common, indexAxis: "y", plugins: {legend: {display: false}, tooltip: {callbacks: {label: (ctx) => ` ${fmt(ctx.raw, 0)} кварталов`}}}, scales: {x: {beginAtZero: true}, y: {grid: {display: false}, ticks: {autoSkip: false, font: {size: 10}}}}}
  });

  new Chart(document.getElementById("chart-strelka"), {
    type: "bar",
    data: {labels: charts.strelka.labels, datasets: [{data: charts.strelka.values, backgroundColor: CATEGORICAL.slice(2).concat(CATEGORICAL).slice(0, charts.strelka.labels.length), borderRadius: 4}]},
    options: {...common, indexAxis: "y", plugins: {legend: {display: false}, tooltip: {callbacks: {label: (ctx) => ` ${fmt(ctx.raw, 0)} кварталов`}}}, scales: {x: {beginAtZero: true}, y: {grid: {display: false}, ticks: {autoSkip: false, font: {size: 10}}}}}
  });

  new Chart(document.getElementById("chart-scatter"), {
    type: "scatter",
    data: {datasets: [{label: "Кварталы", data: charts.scatter, parsing: false, pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: charts.scatter.map((point) => LAND_USE_COLORS[point.land_use] || "#64748b"), pointBorderColor: "rgba(255,255,255,.8)", pointBorderWidth: 1}]},
    options: {...common, plugins: {legend: {display: false}, tooltip: {callbacks: {label: (ctx) => `Квартал ${ctx.raw.id}: FSI ${fmt(ctx.raw.x, 3)}, GSI ${fmt(ctx.raw.y, 3)}`}}}, scales: {x: {title: {display: true, text: "FSI, м²/м²"}}, y: {title: {display: true, text: "GSI, м²/м²"}}}}
  });
}

function initFilters() {
  const input = document.getElementById("blocks-filter");
  const count = document.getElementById("blocks-count");
  const rows = Array.from(document.querySelectorAll("#blocks-table tbody tr"));
  const apply = () => {
    const query = input.value.trim().toLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const matches = !query || row.textContent.toLowerCase().includes(query) || (row.dataset.blockId || "").includes(query);
      row.hidden = !matches;
      if (matches) visible += 1;
    });
    count.textContent = `${visible} из ${rows.length} строк`;
  };
  input.addEventListener("input", apply);
  apply();
}

initMap();
initCharts();
initFilters();
</script>
</body>
</html>
"""


def load_school_counts(results_dir: Path) -> dict[int, float]:
    path = results_dir / "schools_blocks.geojson"
    if not path.exists():
        return {}
    data = load_json(path)
    counts = {}
    for index, feature in enumerate(data.get("features", [])):
        count = finite((feature.get("properties") or {}).get("count"))
        if count is not None:
            counts[index] = count
    return counts


def build_payload(
    summary: dict[str, Any],
    blocks_fc: dict[str, Any],
    layers: dict[str, Any],
    schools: list[dict[str, Any]],
    links: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    charts: dict[str, Any],
    generated_at: str,
    warnings: list[str],
) -> dict[str, Any]:
    meta = dict(summary)
    meta["generated_at"] = generated_at
    meta["warnings"] = warnings
    return {
        "meta": meta,
        "labels": {"land_use": LAND_USE_RU},
        "metrics": metrics,
        "blocks": blocks_fc,
        "layers": layers,
        "schools": schools,
        "links": links,
        "charts": charts,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Собирает один dashboard.html из готовых результатов BlocksNet. Данные не скачиваются, метрики не пересчитываются."
    )
    parser.add_argument("--results", default=str(DEFAULT_RESULTS), help="Каталог с готовыми GeoJSON/CSV/JSON")
    parser.add_argument("--output", default=None, help="Путь к dashboard.html")
    parser.add_argument("--title", default=None, help="Заголовок dashboard")
    args = parser.parse_args()

    results_dir = Path(args.results).expanduser().resolve()
    if not results_dir.is_dir():
        raise SystemExit(f"Каталог результатов не найден: {results_dir}")
    output = Path(args.output).expanduser().resolve() if args.output else results_dir / "dashboard.html"

    required = [
        "blocks_results.geojson",
        "summary.json",
        "school_provision.csv",
        "school_links.csv",
        "density_indicators.csv",
        "spacematrix_morphotypes.csv",
        "spacematrix_clusters.csv",
        "strelka_morphotypes.csv",
        "area_accessibility.csv",
        "validation_report.csv",
    ]
    missing = [name for name in required if not (results_dir / name).exists()]
    if missing:
        raise SystemExit("Не найдены обязательные файлы: " + ", ".join(missing))

    summary = load_json(results_dir / "summary.json")
    provision_rows = load_csv_rows(results_dir / "school_provision.csv", id_first=True)
    for row in provision_rows:
        weak = finite(row.get("provision_weak"))
        strong = finite(row.get("provision_strong"))
        row["provision_gap"] = weak - strong if weak is not None and strong is not None else None
    density_rows = load_csv_rows(results_dir / "density_indicators.csv", id_first=True)
    morph_rows = load_csv_rows(results_dir / "spacematrix_morphotypes.csv", id_first=True)
    strelka_rows = load_csv_rows(results_dir / "strelka_morphotypes.csv", id_first=True)
    area_rows = load_csv_rows(results_dir / "area_accessibility.csv", id_first=True)
    cluster_rows = load_csv_rows(results_dir / "spacematrix_clusters.csv")
    validation = load_csv_rows(results_dir / "validation_report.csv")
    school_counts = load_school_counts(results_dir)
    blocks_fc, blocks = build_blocks(
        results_dir,
        provision_rows,
        density_rows,
        morph_rows,
        strelka_rows,
        area_rows,
        school_counts,
    )
    links = load_links(results_dir / "school_links.csv")
    raw_dir = results_dir.parent / "raw"
    warnings = []
    layers = {}
    layer_specs = [
        ("boundary", raw_dir / "boundary.geojson", ["name"], {"Polygon", "MultiPolygon"}),
        (
            "roads",
            raw_dir / "roads.geojson",
            ["highway", "name", "surface", "bridge", "tunnel"],
            {"LineString", "MultiLineString", "Polygon", "MultiPolygon"},
        ),
        (
            "water",
            raw_dir / "water.geojson",
            ["natural", "water", "waterway", "name"],
            {"Polygon", "MultiPolygon", "LineString", "MultiLineString"},
        ),
    ]
    for name, path, keep, allowed in layer_specs:
        layer = load_layer(path, keep, allowed)
        if layer is None:
            layers[name] = empty_fc()
            warnings.append(f"не найден слой {path.name}")
        else:
            layers[name] = layer
    schools = load_school_points(raw_dir)
    if not schools:
        warnings.append("не найден слой schools.geojson")

    stats = build_stats(blocks)
    metrics = build_metrics(blocks)
    charts = build_chart_data(blocks, provision_rows)
    conclusions = build_conclusions(blocks, summary, provision_rows, validation)
    generated_at = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
    territory = summary.get("territory") or "Территория"
    title = args.title or f"{territory}: dashboard показателей"
    lead = (
        f"{summary.get('block_count', len(blocks))} кварталов, "
        f"{fmt_int(summary.get('population_total'))} жителей, школ: {summary.get('schools_count', '—')}. "
        "Все показатели уже рассчитаны; dashboard читает готовые файлы."
    )
    results_label = str(results_dir)
    try:
        results_label = results_dir.relative_to(Path.cwd()).as_posix()
    except ValueError:
        pass
    map_note = (
        "Подложка: локальные слои roads/water/boundary; внешние тайлы не загружаются. "
        "Слой школ — schools.geojson; пунктирные линии — связи спроса и школ."
    )
    if warnings:
        map_note += " Предупреждения: " + "; ".join(warnings) + "."

    kpi_html = build_kpi(summary, provision_rows)
    conclusions_html = "".join(f"<li>{esc(text)}</li>" for text in conclusions)
    tables = {
        "__SUMMARY_TABLE__": build_summary_stats_table(stats, len(blocks)),
        "__BLOCKS_TABLE__": build_blocks_table(blocks),
        "__PROVISION_TABLE__": build_provision_table(provision_rows),
        "__LINKS_TABLE__": build_links_table(links),
        "__MORPH_TABLE__": build_morph_tables(blocks),
        "__CLUSTER_TABLE__": build_cluster_table(cluster_rows),
        "__SERVICE_TABLE__": build_service_table(summary, warnings),
        "__DICTIONARY_TABLE__": build_dictionary_table(),
        "__VALIDATION_TABLE__": build_validation_table(validation),
    }
    payload = build_payload(summary, blocks_fc, layers, schools, links, metrics, charts, generated_at, warnings)
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")

    document = HTML_TEMPLATE
    replacements = {
        "__TITLE__": esc(title),
        "__TERRITORY__": esc(territory),
        "__LEAD__": esc(lead),
        "__GENERATED__": esc(generated_at),
        "__KPI_HTML__": kpi_html,
        "__MAP_NOTE__": esc(map_note),
        "__CONCLUSIONS_HTML__": conclusions_html,
        "__RESULTS_LABEL__": esc(results_label),
        **tables,
    }
    for token, value in replacements.items():
        document = document.replace(token, value)
    document = document.replace("__DATA_JSON__", payload_json)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    size_mb = output.stat().st_size / 1024 / 1024
    print(f"Готово: {output}")
    print(f"Размер: {size_mb:.2f} МБ; кварталов: {len(blocks)}; школ: {len(schools)}; связей: {len(links)}")
    if warnings:
        print("Предупреждения: " + "; ".join(warnings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
