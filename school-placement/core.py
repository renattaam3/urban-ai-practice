from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

import geopandas as gpd
import numpy as np
import pandas as pd
from blocksnet.analysis.provision import competitive_provision
from scipy.optimize import linprog
from shapely.geometry import Point


ACCESSIBILITY_MIN = 15
DEMAND_PER_1000 = 120
DEFAULT_NEW_CAPACITY = 600
WALK_SPEED_KMH = 5.0
LIVING_DEMAND_M2_PER_PERSON = 30
WGS84 = "EPSG:4326"
METRIC_CRS = "EPSG:32637"

PROVISION_COLUMNS = [
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
]

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


@dataclass
class ProvisionResult:
    table: pd.DataFrame
    links: pd.DataFrame
    capacity: pd.Series
    total_demand: int
    total_capacity: int
    demand_within: int
    demand_left: int
    demand_without: int
    provision_strong: float
    provision_weak: float


@dataclass
class AppData:
    results_dir: Path
    blocks: gpd.GeoDataFrame
    density: pd.DataFrame
    population: pd.Series
    demand: pd.Series
    base_capacity: pd.Series
    acc_matrix: pd.DataFrame
    expected_provision: pd.DataFrame
    baseline: ProvisionResult
    baseline_check: dict
    existing_schools: gpd.GeoDataFrame | None
    reachable_pairs: dict[tuple[int, int], float]
    population_source: str


def require_positive_int(value: object) -> int:
    message = "Вместимость должна быть положительным целым числом."
    if isinstance(value, bool):
        raise ValueError(message)
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(message)
        value = int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.isdigit():
            raise ValueError(message)
        value = int(text)
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if result <= 0:
        raise ValueError(message)
    return result


def land_use_ru(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "не определена"
    text = str(value)
    return LAND_USE_RU.get(text, text)


def resolve_results_dir(results_dir: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if results_dir is not None:
        candidates.append(Path(results_dir))
    env_value = os.environ.get("SCHOOL_RESULTS_DIR")
    if env_value:
        candidates.append(Path(env_value))
    here = Path(__file__).resolve().parent
    candidates.extend(
        [
            here.parent / "examples" / "data" / "suzdal" / "results",
            Path.cwd() / "examples" / "data" / "suzdal" / "results",
            Path.cwd().parent / "examples" / "data" / "suzdal" / "results",
            Path.cwd() / ".." / "examples" / "data" / "suzdal" / "results",
        ]
    )
    required = [
        "blocks_land_use.geojson",
        "density_indicators.csv",
        "school_provision.csv",
        "accessibility_matrix.csv",
    ]
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if all((candidate / name).exists() for name in required):
            return candidate
    checked = "\n".join(str(path) for path in candidates)
    raise FileNotFoundError(
        "Не найдена папка с исходными данными. Проверены пути:\n"
        f"{checked}\n"
        "Укажите путь через переменную окружения SCHOOL_RESULTS_DIR."
    )


def _read_csv_int_index(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"Файл пуст: {path}")
    first = frame.columns[0]
    if first.startswith("Unnamed") or first == "":
        frame = frame.set_index(first)
    elif "block_id" in frame.columns:
        frame = frame.set_index("block_id")
    frame.index = pd.to_numeric(frame.index, errors="coerce")
    if frame.index.isna().any():
        raise ValueError(f"Не удалось прочитать ID кварталов в файле {path.name}")
    frame.index = frame.index.astype(int)
    frame.index.name = "block_id"
    return frame


def _load_blocks(path: Path) -> gpd.GeoDataFrame:
    blocks = gpd.read_file(path)
    if blocks.empty:
        raise ValueError("Слой кварталов пуст.")
    if blocks.crs is None:
        blocks = blocks.set_crs(WGS84)
    blocks = blocks.to_crs(WGS84)
    blocks = blocks.reset_index(drop=True)
    blocks.index = pd.RangeIndex(len(blocks), name="block_id")
    if not blocks.geometry.is_valid.all():
        blocks.geometry = blocks.geometry.make_valid()
    return blocks


def _load_accessibility(path: Path, block_ids: pd.Index) -> pd.DataFrame:
    matrix = pd.read_csv(path, index_col=0)
    matrix.index = pd.to_numeric(matrix.index, errors="coerce")
    matrix.columns = pd.to_numeric(matrix.columns, errors="coerce")
    if matrix.index.isna().any() or matrix.columns.isna().any():
        raise ValueError("В матрице доступности найдены нечисловые ID кварталов.")
    matrix.index = matrix.index.astype(int)
    matrix.columns = matrix.columns.astype(int)
    matrix = matrix.apply(pd.to_numeric, errors="coerce")
    missing_rows = block_ids.difference(matrix.index)
    missing_columns = block_ids.difference(matrix.columns)
    if len(missing_rows) or len(missing_columns):
        raise ValueError("Матрица доступности не покрывает все кварталы.")
    matrix = matrix.reindex(index=block_ids, columns=block_ids)
    matrix.index.name = "block_id"
    matrix.columns.name = "block_id"
    return matrix


def _load_population(
    density: pd.DataFrame,
    blocks_results: pd.DataFrame | None,
    results_dir: Path,
    block_ids: pd.Index,
) -> tuple[pd.Series, str]:
    population: pd.Series | None = None
    source = ""
    if "population" in density.columns:
        population = pd.to_numeric(density["population"], errors="coerce")
        source = "density_indicators.csv"
    elif blocks_results is not None and "population" in blocks_results.columns:
        population = pd.to_numeric(blocks_results["population"], errors="coerce")
        source = "blocks_results.csv"
    else:
        buildings_path = results_dir / "buildings_blocks.geojson"
        if buildings_path.exists():
            buildings = gpd.read_file(buildings_path)
            if "population" in buildings.columns:
                population = pd.Series(
                    pd.to_numeric(buildings["population"], errors="coerce").to_numpy(),
                    index=block_ids,
                )
                source = "buildings_blocks.geojson"
        if population is None and "living_area" in density.columns:
            population = pd.to_numeric(density["living_area"], errors="coerce") / LIVING_DEMAND_M2_PER_PERSON
            source = "density_indicators.csv (living_area / 30)"
    if population is None:
        raise ValueError(
            "Не найден показатель населения. Нужна колонка population " "или living_area в density_indicators.csv."
        )
    population = population.reindex(block_ids).fillna(0.0).clip(lower=0.0)
    return population, source


def _load_capacity(
    expected_provision: pd.DataFrame,
    blocks_results: pd.DataFrame | None,
    block_ids: pd.Index,
) -> pd.Series:
    if "capacity" in expected_provision.columns:
        capacity = expected_provision["capacity"]
    elif blocks_results is not None and "capacity" in blocks_results.columns:
        capacity = blocks_results["capacity"]
    else:
        raise ValueError("Не найдена текущая вместимость школ (capacity).")
    capacity = pd.to_numeric(capacity, errors="coerce").reindex(block_ids, fill_value=0.0)
    return capacity.fillna(0.0).clip(lower=0.0).round().astype(int)


def _baseline_check(expected: pd.DataFrame, calculated: pd.DataFrame) -> dict:
    columns = [column for column in PROVISION_COLUMNS if column in expected.columns and column in calculated.columns]
    expected_ids = set(int(value) for value in expected.index)
    calculated_ids = set(int(value) for value in calculated.index)
    index_match = expected_ids == calculated_ids
    max_diff = 0.0
    columns_match = bool(columns)
    if columns and index_match:
        common = sorted(expected_ids)
        for column in columns:
            left = expected.loc[common, column].to_numpy(dtype=float)
            right = calculated.loc[common, column].to_numpy(dtype=float)
            if not np.allclose(left, right, equal_nan=True):
                columns_match = False
            diff = np.abs(left - right)
            if np.isfinite(diff).any():
                max_diff = max(max_diff, float(np.nanmax(diff)))
    return {
        "matches": bool(index_match and columns_match),
        "index_match": index_match,
        "columns": columns,
        "max_diff": max_diff,
        "rows_expected": len(expected),
        "rows_calculated": len(calculated),
    }


def compute_provision(
    population: pd.Series,
    capacity: pd.Series,
    acc_matrix: pd.DataFrame,
) -> ProvisionResult:
    capacity = capacity.reindex(population.index).fillna(0).clip(lower=0).round().astype(int)
    frame = pd.DataFrame(
        {
            "population": population.reindex(capacity.index).astype(float).fillna(0.0).clip(lower=0.0),
            "capacity": capacity,
        }
    )
    eligible = (frame["population"] > 0) | (frame["capacity"] > 0)
    frame = frame.loc[eligible]
    if frame.empty:
        raise ValueError("Нет кварталов с населением или вместимостью школ.")
    provision, links = competitive_provision(
        frame,
        acc_matrix,
        accessibility=ACCESSIBILITY_MIN,
        demand=DEMAND_PER_1000,
        self_supply=True,
        max_depth=1,
    )
    total_demand = int(provision["demand"].sum())
    demand_within = int(provision["demand_within"].sum())
    demand_left = int(round(provision["demand_left"].sum()))
    demand_without = int(provision["demand_without"].sum())
    provision_strong = float(demand_within / total_demand) if total_demand > 0 else 0.0
    provision_weak = float((demand_within + demand_without) / total_demand) if total_demand > 0 else 0.0
    return ProvisionResult(
        table=provision,
        links=links,
        capacity=capacity,
        total_demand=total_demand,
        total_capacity=int(capacity.sum()),
        demand_within=demand_within,
        demand_left=demand_left,
        demand_without=demand_without,
        provision_strong=provision_strong,
        provision_weak=provision_weak,
    )


def load_app_data(results_dir: str | Path | None = None) -> AppData:
    directory = resolve_results_dir(results_dir)
    blocks = _load_blocks(directory / "blocks_land_use.geojson")
    density = _read_csv_int_index(directory / "density_indicators.csv").reindex(blocks.index)
    expected = _read_csv_int_index(directory / "school_provision.csv")
    blocks_results_path = directory / "blocks_results.csv"
    blocks_results = (
        _read_csv_int_index(blocks_results_path).reindex(blocks.index) if blocks_results_path.exists() else None
    )
    population, population_source = _load_population(
        density,
        blocks_results,
        directory,
        blocks.index,
    )
    base_capacity = _load_capacity(expected, blocks_results, blocks.index)
    demand = population.apply(lambda value: math.ceil(float(value) / 1000 * DEMAND_PER_1000)).astype(int)
    acc_matrix = _load_accessibility(directory / "accessibility_matrix.csv", blocks.index)
    baseline = compute_provision(population, base_capacity, acc_matrix)
    baseline_check = _baseline_check(expected, baseline.table)
    existing_schools = None
    schools_path = directory.parent / "raw" / "schools.geojson"
    if schools_path.exists():
        try:
            existing_schools = gpd.read_file(schools_path)
            if existing_schools.crs is None:
                existing_schools = existing_schools.set_crs(WGS84)
            existing_schools = existing_schools.to_crs(WGS84)
        except Exception:
            existing_schools = None
    reachable_pairs = {
        (int(demand_id), int(capacity_id)): float(acc_matrix.loc[demand_id, capacity_id])
        for demand_id in demand.index
        if demand.loc[demand_id] > 0
        for capacity_id in blocks.index
        if pd.notna(acc_matrix.loc[demand_id, capacity_id])
        and float(acc_matrix.loc[demand_id, capacity_id]) <= ACCESSIBILITY_MIN
    }
    return AppData(
        results_dir=directory,
        blocks=blocks,
        density=density,
        population=population,
        demand=demand,
        base_capacity=base_capacity,
        acc_matrix=acc_matrix,
        expected_provision=expected,
        baseline=baseline,
        baseline_check=baseline_check,
        existing_schools=existing_schools,
        reachable_pairs=reachable_pairs,
        population_source=population_source,
    )


def capacity_with_schools(
    base_capacity: pd.Series,
    schools: Iterable[Mapping[str, object]],
) -> pd.Series:
    capacity = base_capacity.copy().astype(int)
    for school in schools:
        block_id = int(school["block_id"])
        if block_id not in capacity.index:
            raise ValueError(f"Квартал {block_id} отсутствует в исходных данных.")
        value = require_positive_int(school["capacity"])
        capacity.loc[block_id] = int(capacity.loc[block_id]) + value
    return capacity


def build_scenario(
    data: AppData,
    schools: Iterable[Mapping[str, object]],
) -> ProvisionResult:
    capacity = capacity_with_schools(data.base_capacity, schools)
    return compute_provision(data.population, capacity, data.acc_matrix)


def _lp_deficit(
    capacity: pd.Series,
    demand: pd.Series,
    reachable_pairs: Mapping[tuple[int, int], float],
) -> int:
    capacity = capacity.reindex(demand.index).fillna(0).clip(lower=0).round().astype(int)
    self_supply = np.minimum(demand.to_numpy(dtype=int), capacity.to_numpy(dtype=int))
    demand_left = pd.Series(demand.to_numpy(dtype=int) - self_supply, index=demand.index)
    capacity_left = pd.Series(capacity.to_numpy(dtype=int) - self_supply, index=capacity.index)
    demand_ids = [int(value) for value in demand.index if demand_left.loc[value] > 0]
    capacity_ids = [int(value) for value in capacity.index if capacity_left.loc[value] > 0]
    variables = [
        (demand_id, capacity_id)
        for demand_id in demand_ids
        for capacity_id in capacity_ids
        if (demand_id, capacity_id) in reachable_pairs
    ]
    if not variables:
        return int(demand.sum() - self_supply.sum())
    count = len(variables)
    costs = np.empty(count, dtype=float)
    for position, (demand_id, capacity_id) in enumerate(variables):
        weight = (
            float(demand_left.loc[demand_id])
            * float(capacity_left.loc[capacity_id])
            / (reachable_pairs[(demand_id, capacity_id)] + 1.0)
        )
        costs[position] = -weight
    demand_position = {value: position for position, value in enumerate(demand_ids)}
    capacity_position = {value: position for position, value in enumerate(capacity_ids)}
    matrix = np.zeros((len(demand_ids) + len(capacity_ids), count), dtype=float)
    for position, (demand_id, capacity_id) in enumerate(variables):
        matrix[demand_position[demand_id], position] = 1.0
        matrix[len(demand_ids) + capacity_position[capacity_id], position] = 1.0
    limits = np.array(
        [float(demand_left.loc[value]) for value in demand_ids]
        + [float(capacity_left.loc[value]) for value in capacity_ids],
        dtype=float,
    )
    bounds = [
        (0.0, float(min(demand_left.loc[demand_id], capacity_left.loc[capacity_id])))
        for demand_id, capacity_id in variables
    ]
    result = linprog(costs, A_ub=matrix, b_ub=limits, bounds=bounds, method="highs")
    if not result.success:
        raise RuntimeError(f"Не удалось решить задачу размещения: {result.message}")
    flow = float(np.sum(result.x))
    deficit = int(round(float(demand.sum()) - float(self_supply.sum()) - flow))
    return max(deficit, 0)


def search_single_school(
    data: AppData,
    new_capacity: int,
    progress_callback: Callable[[float], None] | None = None,
) -> pd.DataFrame:
    new_capacity = require_positive_int(new_capacity)
    baseline_deficit = data.baseline.demand_left
    total_demand = data.baseline.total_demand
    rows: list[dict[str, object]] = []
    block_ids = list(data.blocks.index)
    for position, block_id in enumerate(block_ids, start=1):
        capacity = data.base_capacity.copy()
        capacity.loc[block_id] = int(capacity.loc[block_id]) + new_capacity
        deficit = _lp_deficit(capacity, data.demand, data.reachable_pairs)
        rows.append(
            {
                "block_id": int(block_id),
                "land_use": data.blocks.loc[block_id, "land_use"] if "land_use" in data.blocks.columns else None,
                "population": int(round(float(data.population.loc[block_id]))),
                "capacity_base": int(data.base_capacity.loc[block_id]),
                "capacity_scenario": int(capacity.loc[block_id]),
                "new_capacity": new_capacity,
                "deficit_before": baseline_deficit,
                "deficit_after": deficit,
                "reduction": baseline_deficit - deficit,
                "provision_after": (float(total_demand - deficit) / total_demand if total_demand > 0 else 0.0),
            }
        )
        if progress_callback is not None:
            progress_callback(position / len(block_ids))
    results = pd.DataFrame(rows)
    best_deficit = int(results["deficit_after"].min())
    results["is_best"] = results["deficit_after"].astype(int) == best_deficit
    results["rank"] = results["reduction"].rank(method="min", ascending=False).fillna(0).astype(int)
    return results.sort_values(
        ["is_best", "deficit_after", "block_id"],
        ascending=[False, True, True],
    ).reset_index(drop=True)


def build_comparison(data: AppData, scenario: ProvisionResult) -> pd.DataFrame:
    base = data.baseline.table.reindex(data.blocks.index)
    current = scenario.table.reindex(data.blocks.index)
    comparison = pd.DataFrame(
        {
            "block_id": data.blocks.index.astype(int),
            "land_use": (
                data.blocks["land_use"].to_numpy() if "land_use" in data.blocks.columns else [None] * len(data.blocks)
            ),
            "population": data.population.to_numpy(dtype=float),
            "demand": data.demand.to_numpy(dtype=int),
            "capacity_base": data.base_capacity.to_numpy(dtype=int),
            "capacity_scenario": scenario.capacity.reindex(data.blocks.index).to_numpy(dtype=int),
            "new_capacity": (scenario.capacity.reindex(data.blocks.index) - data.base_capacity).to_numpy(dtype=int),
            "deficit_base": base["demand_left"].fillna(0).astype(int).to_numpy(),
            "deficit_scenario": current["demand_left"].fillna(0).astype(int).to_numpy(),
            "provision_base": base["provision_strong"].to_numpy(dtype=float),
            "provision_scenario": current["provision_strong"].to_numpy(dtype=float),
        }
    )
    comparison["delta_provision"] = comparison["provision_scenario"] - comparison["provision_base"]
    comparison["delta_deficit"] = comparison["deficit_scenario"] - comparison["deficit_base"]
    comparison["changed"] = (
        (comparison["capacity_scenario"] != comparison["capacity_base"])
        | (comparison["delta_deficit"] != 0)
        | (comparison["delta_provision"].abs() > 1e-9)
    )
    return comparison


def build_map_frame(data: AppData, scenario: ProvisionResult) -> gpd.GeoDataFrame:
    comparison = build_comparison(data, scenario)
    frame = data.blocks[["geometry"]].copy()
    frame["block_id"] = comparison["block_id"].to_numpy(dtype=int)
    for column in [
        "land_use",
        "population",
        "demand",
        "capacity_base",
        "capacity_scenario",
        "new_capacity",
        "deficit_base",
        "deficit_scenario",
        "provision_base",
        "provision_scenario",
        "delta_provision",
    ]:
        frame[column] = comparison[column].to_numpy()
    return frame


def find_block_for_point(
    blocks: gpd.GeoDataFrame,
    latitude: float,
    longitude: float,
    max_distance_m: float = 1000.0,
) -> int | None:
    point = Point(float(longitude), float(latitude))
    hits = blocks[blocks.geometry.contains(point)]
    if not hits.empty:
        return int(hits.index[0])
    metric = blocks.to_crs(METRIC_CRS)
    metric_point = gpd.GeoSeries([point], crs=WGS84).to_crs(METRIC_CRS).iloc[0]
    distances = metric.geometry.centroid.distance(metric_point)
    nearest = int(distances.idxmin())
    if float(distances.loc[nearest]) <= max_distance_m:
        return nearest
    return None


def nearest_school_info(
    data: AppData,
    block_id: int,
    capacity: pd.Series,
) -> tuple[float | None, int]:
    capacity_blocks = capacity[capacity > 0].index
    if len(capacity_blocks) == 0 or block_id not in data.acc_matrix.index:
        return None, 0
    times = data.acc_matrix.loc[block_id, capacity_blocks].dropna()
    if times.empty:
        return None, 0
    return float(times.min()), int((times <= ACCESSIBILITY_MIN).sum())
