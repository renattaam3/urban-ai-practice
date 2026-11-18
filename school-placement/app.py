from __future__ import annotations

import math

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap
from streamlit_folium import st_folium

import core


MAP_MODES = ["Исходное", "Сценарий", "Изменение"]

st.set_page_config(
    page_title="Оценка размещения школ",
    layout="wide",
)


@st.cache_resource(show_spinner="Загружаем данные и рассчитываем исходную обеспеченность...")
def load_data(results_dir: str | None = None) -> core.AppData:
    return core.load_app_data(results_dir)


def fmt_int(value: object) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "—"
    return f"{int(round(number)):,}".replace(",", " ")


def fmt_pct(value: object) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "—"
    return f"{number:.1%}"


def fmt_minutes(value: object) -> str:
    if value is None:
        return "нет"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "нет"
    if not math.isfinite(number):
        return "нет"
    return f"{number:.1f} мин"


def to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def init_state(data: core.AppData) -> None:
    defaults = {
        "selected_block": int(data.blocks.index[0]),
        "block_selector": int(data.blocks.index[0]),
        "pending_block_selector": None,
        "pending_map_mode": None,
        "map_mode": "Исходное",
        "scenario_schools": [],
        "scenario": None,
        "scenario_dirty": False,
        "search_results": None,
        "search_capacity": core.DEFAULT_NEW_CAPACITY,
        "last_click": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def apply_pending_state(data: core.AppData) -> None:
    pending_mode = st.session_state.get("pending_map_mode")
    if pending_mode in MAP_MODES:
        st.session_state.map_mode = pending_mode
        st.session_state.pending_map_mode = None
    pending_block = st.session_state.get("pending_block_selector")
    if pending_block is not None:
        block_id = int(pending_block)
        if block_id in data.blocks.index:
            st.session_state.block_selector = block_id
            st.session_state.selected_block = block_id
        st.session_state.pending_block_selector = None


def comparison_to_russian(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Квартал": frame["block_id"].astype(int),
            "Тип землепользования": frame["land_use"].map(core.land_use_ru),
            "Население, чел.": frame["population"].round().astype(int),
            "Спрос, мест": frame["demand"].astype(int),
            "Вместимость исх., мест": frame["capacity_base"].astype(int),
            "Вместимость сценарий, мест": frame["capacity_scenario"].astype(int),
            "Новые места": frame["new_capacity"].astype(int),
            "Дефицит исх., мест": frame["deficit_base"].astype(int),
            "Дефицит сценарий, мест": frame["deficit_scenario"].astype(int),
            "Обеспеченность исх.": frame["provision_base"].astype(float),
            "Обеспеченность сценарий": frame["provision_scenario"].astype(float),
            "Δ обеспеченности": frame["delta_provision"].astype(float),
        }
    )


def search_to_russian(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Квартал": frame["block_id"].astype(int),
            "Тип землепользования": frame["land_use"].map(core.land_use_ru),
            "Население, чел.": frame["population"].astype(int),
            "Вместимость сейчас, мест": frame["capacity_base"].astype(int),
            "Вместимость сценарий, мест": frame["capacity_scenario"].astype(int),
            "Дефицит до, мест": frame["deficit_before"].astype(int),
            "Дефицит после, мест": frame["deficit_after"].astype(int),
            "Сокращение дефицита, мест": frame["reduction"].astype(int),
            "Обеспеченность после": frame["provision_after"].astype(float),
            "Лучший": frame["is_best"].astype(bool),
        }
    )


def summary_to_russian(
    data: core.AppData,
    scenario: core.ProvisionResult,
    schools: list[dict[str, object]],
) -> pd.DataFrame:
    new_capacity = scenario.total_capacity - data.baseline.total_capacity
    deficit_reduction = data.baseline.demand_left - scenario.demand_left
    provision_delta = scenario.provision_strong - data.baseline.provision_strong
    rows = [
        ("Население, чел.", fmt_int(data.population.sum()), fmt_int(data.population.sum()), "0"),
        (
            "Спрос на школьные места",
            fmt_int(data.baseline.total_demand),
            fmt_int(scenario.total_demand),
            "0",
        ),
        (
            "Вместимость, мест",
            fmt_int(data.baseline.total_capacity),
            fmt_int(scenario.total_capacity),
            f"+{fmt_int(new_capacity)}" if new_capacity else "0",
        ),
        (
            "Дефицит, мест",
            fmt_int(data.baseline.demand_left),
            fmt_int(scenario.demand_left),
            f"−{fmt_int(deficit_reduction)}" if deficit_reduction else "0",
        ),
        (
            "Обеспеченность",
            fmt_pct(data.baseline.provision_strong),
            fmt_pct(scenario.provision_strong),
            f"{provision_delta:+.1%}" if abs(provision_delta) > 1e-12 else "0",
        ),
        ("Новых школ", "0", str(len(schools)), f"+{len(schools)}" if schools else "0"),
        (
            "Новых мест",
            "0",
            fmt_int(new_capacity),
            f"+{fmt_int(new_capacity)}" if new_capacity else "0",
        ),
    ]
    return pd.DataFrame(rows, columns=["Показатель", "Исходное", "Сценарий", "Изменение"])


def build_folium_map(
    data: core.AppData,
    scenario: core.ProvisionResult,
    mode: str,
    selected_block: int,
    schools: list[dict[str, object]],
) -> folium.Map:
    frame = core.build_map_frame(data, scenario)
    if mode == "Сценарий":
        frame["map_value"] = frame["provision_scenario"]
        caption = "Обеспеченность (provision_strong)"
    elif mode == "Изменение":
        frame["map_value"] = frame["delta_provision"]
        caption = "Изменение обеспеченности"
    else:
        frame["map_value"] = frame["provision_base"]
        caption = "Обеспеченность (provision_strong)"

    for column in [
        "population",
        "demand",
        "capacity_base",
        "capacity_scenario",
        "deficit_base",
        "deficit_scenario",
    ]:
        frame[column] = frame[column].fillna(0).astype(int)
    frame["population_label"] = frame["population"].map(fmt_int)
    frame["demand_label"] = frame["demand"].map(fmt_int)
    frame["capacity_base_label"] = frame["capacity_base"].map(fmt_int)
    frame["capacity_scenario_label"] = frame["capacity_scenario"].map(fmt_int)
    frame["deficit_base_label"] = frame["deficit_base"].map(fmt_int)
    frame["deficit_scenario_label"] = frame["deficit_scenario"].map(fmt_int)
    frame["provision_base_label"] = frame["provision_base"].map(fmt_pct)
    frame["provision_scenario_label"] = frame["provision_scenario"].map(fmt_pct)
    frame["map_value"] = frame["map_value"].apply(lambda value: float(value) if pd.notna(value) else None)
    properties = frame[
        [
            "block_id",
            "map_value",
            "population_label",
            "demand_label",
            "capacity_base_label",
            "capacity_scenario_label",
            "provision_base_label",
            "provision_scenario_label",
            "deficit_base_label",
            "deficit_scenario_label",
        ]
    ].copy()
    properties["block_id"] = properties["block_id"].astype(int)
    geo_frame = gpd.GeoDataFrame(properties, geometry=frame.geometry, crs=frame.crs)

    min_x, min_y, max_x, max_y = data.blocks.total_bounds
    center = [(min_y + max_y) / 2, (min_x + max_x) / 2]
    map_object = folium.Map(
        location=center,
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=True,
    )
    if mode == "Изменение":
        values = pd.Series(frame["map_value"]).dropna()
        max_abs = max(float(values.abs().max()), 0.05) if len(values) else 0.05
        color_map = LinearColormap(
            ["#b2182b", "#f7f7f7", "#1b7837"],
            vmin=-max_abs,
            vmax=max_abs,
            caption=caption,
        )
    else:
        color_map = LinearColormap(
            ["#d73027", "#fdae61", "#ffffbf", "#a6d96a", "#1a9850"],
            vmin=0,
            vmax=1,
            caption=caption,
        )
    color_map.add_to(map_object)

    def style(feature: dict) -> dict:
        value = feature["properties"].get("map_value")
        fill_color = "#d9d9d9" if value is None else color_map(float(value))
        return {
            "fillColor": fill_color,
            "color": "#ffffff",
            "weight": 0.6,
            "fillOpacity": 0.72,
        }

    fields = [
        "block_id",
        "population_label",
        "demand_label",
        "capacity_base_label",
        "capacity_scenario_label",
        "provision_base_label",
        "provision_scenario_label",
        "deficit_base_label",
        "deficit_scenario_label",
    ]
    aliases = [
        "Квартал",
        "Население",
        "Спрос, мест",
        "Вместимость исх., мест",
        "Вместимость сценарий, мест",
        "Обеспеченность исх.",
        "Обеспеченность сценарий",
        "Дефицит исх., мест",
        "Дефицит сценарий, мест",
    ]
    folium.GeoJson(
        geo_frame.__geo_interface__,
        name="Кварталы",
        style_function=style,
        highlight_function=lambda feature: {"weight": 2.0, "color": "#333333"},
        tooltip=folium.GeoJsonTooltip(fields=fields, aliases=aliases, sticky=True),
        popup=folium.GeoJsonPopup(fields=fields, aliases=aliases),
    ).add_to(map_object)

    selected = geo_frame[geo_frame["block_id"] == int(selected_block)]
    if len(selected):
        folium.GeoJson(
            selected.__geo_interface__,
            name="Выбранный квартал",
            style_function=lambda feature: {
                "color": "#0b5394",
                "weight": 4,
                "fill": False,
            },
        ).add_to(map_object)

    if data.existing_schools is not None and len(data.existing_schools):
        existing_group = folium.FeatureGroup(name="Существующие школы")
        for _, row in data.existing_schools.iterrows():
            geometry = row.geometry
            if geometry is None or geometry.is_empty:
                continue
            point = geometry if geometry.geom_type == "Point" else geometry.representative_point()
            name = row.get("name") if "name" in row.index else None
            label = str(name) if name else "Школа"
            folium.CircleMarker(
                [point.y, point.x],
                radius=5,
                color="#1f77b4",
                fill=True,
                fill_color="#1f77b4",
                fill_opacity=0.9,
                tooltip=label,
                popup=label,
            ).add_to(existing_group)
        existing_group.add_to(map_object)

    if mode != "Исходное" and schools:
        new_group = folium.FeatureGroup(name="Новые школы")
        for school in schools:
            block_id = int(school["block_id"])
            point = data.blocks.loc[block_id].geometry.representative_point()
            label = f"Новая школа: {fmt_int(school['capacity'])} мест"
            folium.Marker(
                [point.y, point.x],
                tooltip=label,
                popup=f"Квартал {block_id}<br>{label}",
                icon=folium.Icon(color="red", icon="education", prefix="glyphicon"),
            ).add_to(new_group)
        new_group.add_to(map_object)

    folium.LayerControl(collapsed=True).add_to(map_object)
    return map_object


def render_kpi(data: core.AppData, scenario: core.ProvisionResult) -> None:
    new_capacity = scenario.total_capacity - data.baseline.total_capacity
    deficit_reduction = data.baseline.demand_left - scenario.demand_left
    provision_delta = scenario.provision_strong - data.baseline.provision_strong
    first = st.columns(4)
    first[0].metric("Население, чел.", fmt_int(data.population.sum()))
    first[1].metric("Спрос на школьные места", fmt_int(data.baseline.total_demand))
    first[2].metric("Вместимость: исходная", fmt_int(data.baseline.total_capacity))
    first[3].metric(
        "Вместимость: сценарий",
        fmt_int(scenario.total_capacity),
        delta=f"+{fmt_int(new_capacity)}" if new_capacity else None,
    )
    second = st.columns(4)
    second[0].metric("Дефицит: исходный", fmt_int(data.baseline.demand_left))
    second[1].metric(
        "Дефицит: сценарий",
        fmt_int(scenario.demand_left),
        delta=f"−{fmt_int(deficit_reduction)}" if deficit_reduction else None,
        delta_color="inverse",
    )
    second[2].metric("Обеспеченность: исходная", fmt_pct(data.baseline.provision_strong))
    second[3].metric(
        "Обеспеченность: сценарий",
        fmt_pct(scenario.provision_strong),
        delta=f"{provision_delta:+.1%}" if abs(provision_delta) > 1e-12 else None,
    )


def render_block_card(
    data: core.AppData,
    scenario: core.ProvisionResult,
    block_id: int,
    schools: list[dict[str, object]],
) -> None:
    block = data.blocks.loc[block_id]
    base_table = data.baseline.table
    scenario_table = scenario.table

    def table_value(table: pd.DataFrame, column: str, default: object = 0) -> object:
        if block_id in table.index and column in table.columns:
            return table.loc[block_id, column]
        return default

    population = int(round(float(data.population.loc[block_id])))
    demand = int(data.demand.loc[block_id])
    capacity_base = int(data.base_capacity.loc[block_id])
    capacity_scenario = int(scenario.capacity.loc[block_id])
    provision_base = table_value(base_table, "provision_strong", float("nan"))
    provision_scenario = table_value(scenario_table, "provision_strong", float("nan"))
    deficit_base = int(table_value(base_table, "demand_left", 0))
    deficit_scenario = int(table_value(scenario_table, "demand_left", 0))
    new_capacity_here = 0
    for school in schools:
        if int(school["block_id"]) == block_id:
            new_capacity_here += int(school["capacity"])
    nearest_base, count_base = core.nearest_school_info(data, block_id, data.base_capacity)
    nearest_scenario, count_scenario = core.nearest_school_info(data, block_id, scenario.capacity)
    site_area_ha = float(block.get("site_area", 0.0)) / 10000 if "site_area" in block.index else 0.0
    density_parts: list[str] = []
    if block_id in data.density.index:
        density = data.density.loc[block_id]
        for column, label in (("fsi", "FSI"), ("gsi", "GSI"), ("osr", "OSR")):
            if column in density.index and pd.notna(density[column]):
                density_parts.append(f"{label} {float(density[column]):.2f}")
    density_text = f" Плотностные показатели: {', '.join(density_parts)}." if density_parts else ""

    with st.container(border=True):
        st.subheader(f"Квартал {block_id}")
        st.caption(
            f"Тип землепользования: {core.land_use_ru(block.get('land_use'))}. "
            f"Площадь: {site_area_ha:.1f} га.{density_text}"
        )
        first = st.columns(4)
        first[0].metric("Население", fmt_int(population))
        first[1].metric("Спрос на места", fmt_int(demand))
        first[2].metric("Вместимость сейчас", fmt_int(capacity_base))
        first[3].metric(
            "Вместимость в сценарии",
            fmt_int(capacity_scenario),
            delta=f"+{fmt_int(new_capacity_here)}" if new_capacity_here else None,
        )
        second = st.columns(4)
        second[0].metric("Обеспеченность сейчас", fmt_pct(provision_base))
        second[1].metric(
            "Обеспеченность в сценарии",
            fmt_pct(provision_scenario),
            delta=(
                f"{float(provision_scenario) - float(provision_base):+.1%}"
                if pd.notna(provision_base)
                and pd.notna(provision_scenario)
                and abs(float(provision_scenario) - float(provision_base)) > 1e-12
                else None
            ),
        )
        second[2].metric("Дефицит сейчас", fmt_int(deficit_base))
        second[3].metric("Дефицит в сценарии", fmt_int(deficit_scenario))
        st.caption(
            f"Ближайшая школа: сейчас {fmt_minutes(nearest_base)}, "
            f"в сценарии {fmt_minutes(nearest_scenario)}. "
            f"Школ в пределах {core.ACCESSIBILITY_MIN} мин: сейчас {count_base}, "
            f"в сценарии {count_scenario}. Новых школ в квартале: "
            f"{len([s for s in schools if int(s['block_id']) == block_id])}."
        )


def render_schools_tab(data: core.AppData, schools: list[dict[str, object]]) -> None:
    if not schools:
        st.info("Новые школы не добавлены. Выберите квартал на карте или в списке слева и добавьте школу.")
        return
    rows = []
    for school in schools:
        block_id = int(school["block_id"])
        point = data.blocks.loc[block_id].geometry.representative_point()
        rows.append(
            {
                "Квартал": block_id,
                "Тип землепользования": core.land_use_ru(
                    data.blocks.loc[block_id, "land_use"] if "land_use" in data.blocks.columns else None
                ),
                "Население квартала, чел.": int(round(float(data.population.loc[block_id]))),
                "Вместимость школы, мест": int(school["capacity"]),
                "Широта": round(float(point.y), 6),
                "Долгота": round(float(point.x), 6),
            }
        )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Квартал": st.column_config.NumberColumn(format="%d"),
            "Население квартала, чел.": st.column_config.NumberColumn(format="%d"),
            "Вместимость школы, мест": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.caption(
        f"Всего новых школ: {len(schools)}; суммарная вместимость: {fmt_int(sum(int(s['capacity']) for s in schools))} мест."
    )


try:
    data = load_data()
except Exception as exc:
    st.error(f"Не удалось загрузить исходные данные: {exc}")
    st.stop()

init_state(data)
apply_pending_state(data)

if int(st.session_state.block_selector) not in data.blocks.index:
    st.session_state.block_selector = int(data.blocks.index[0])
if int(st.session_state.selected_block) not in data.blocks.index:
    st.session_state.selected_block = int(data.blocks.index[0])

scenario = st.session_state.scenario
effective_scenario = scenario if scenario is not None else data.baseline
schools = st.session_state.scenario_schools
selected_block = int(st.session_state.selected_block)
comparison = core.build_comparison(data, effective_scenario)
comparison_ru = comparison_to_russian(comparison)
summary_ru = summary_to_russian(data, effective_scenario, schools)
search_results = st.session_state.search_results
search_ru = search_to_russian(search_results) if search_results is not None else None

st.title("Оценка размещения школ")
st.caption("Суздаль · обеспеченность школьными местами и подбор кварталов для новых школ")

check = data.baseline_check
if check["matches"]:
    st.success(
        f"Исходная обеспеченность воспроизведена: {check['rows_calculated']} кварталов, "
        f"максимальное расхождение с school_provision.csv — {check['max_diff']:.3g}."
    )
else:
    st.error(
        "Расчёт не совпал с school_provision.csv. "
        f"Строк в эталоне: {check['rows_expected']}, в расчёте: {check['rows_calculated']}, "
        f"максимальное расхождение: {check['max_diff']:.6g}."
    )

if st.session_state.scenario_dirty:
    st.warning(
        "Список новых школ изменён. Нажмите «Рассчитать сценарий» в панели слева, " "чтобы обновить карту и показатели."
    )
elif scenario is None and not schools:
    st.caption("Сценарий не задан — показана исходная обеспеченность.")

render_kpi(data, effective_scenario)

st.subheader("Карта кварталов")
map_mode = st.radio(
    "Режим карты",
    MAP_MODES,
    horizontal=True,
    key="map_mode",
)
if map_mode == "Изменение":
    st.caption(
        "Зелёный — обеспеченность выросла, красный — снизилась. "
        "Серые кварталы без спроса или без данных. Нажмите на квартал, чтобы выбрать его."
    )
else:
    st.caption(
        "Цвет — обеспеченность школьными местами. "
        "Серые кварталы без спроса или без данных. Нажмите на квартал, чтобы выбрать его."
    )
map_object = build_folium_map(data, effective_scenario, map_mode, selected_block, schools)
map_result = st_folium(
    map_object,
    key="school_map",
    height=620,
    use_container_width=True,
    returned_objects=["last_clicked"],
)
click = map_result.get("last_clicked") if isinstance(map_result, dict) else None
if click and click.get("lat") is not None and click.get("lng") is not None:
    signature = (round(float(click["lat"]), 6), round(float(click["lng"]), 6))
    if st.session_state.last_click != signature:
        st.session_state.last_click = signature
        block_id = core.find_block_for_point(data.blocks, float(click["lat"]), float(click["lng"]))
        if block_id is not None:
            st.session_state.selected_block = block_id
            st.session_state.pending_block_selector = block_id
            st.rerun()
        else:
            st.warning("Клик вне кварталов. Выберите квартал на карте или в списке слева.")

render_block_card(data, effective_scenario, selected_block, schools)

tab_compare, tab_search, tab_schools, tab_method = st.tabs(
    ["Сравнение по кварталам", "Автоподбор", "Новые школы", "Методика"]
)

with tab_compare:
    st.subheader("Итоговые показатели сценария")
    st.dataframe(summary_ru, hide_index=True, width="stretch")
    st.divider()
    show_changed = st.checkbox(
        "Показывать только изменившиеся кварталы",
        value=True,
        key="show_changed",
    )
    if show_changed:
        display_comparison = comparison_ru.loc[comparison["changed"].to_numpy()].reset_index(drop=True)
    else:
        display_comparison = comparison_ru
    if display_comparison.empty:
        st.info("Изменений по кварталам нет. Показана исходная обеспеченность.")
    else:
        st.dataframe(
            display_comparison,
            hide_index=True,
            width="stretch",
            height=480,
            column_config={
                "Квартал": st.column_config.NumberColumn(format="%d"),
                "Население, чел.": st.column_config.NumberColumn(format="%d"),
                "Спрос, мест": st.column_config.NumberColumn(format="%d"),
                "Вместимость исх., мест": st.column_config.NumberColumn(format="%d"),
                "Вместимость сценарий, мест": st.column_config.NumberColumn(format="%d"),
                "Новые места": st.column_config.NumberColumn(format="%d"),
                "Дефицит исх., мест": st.column_config.NumberColumn(format="%d"),
                "Дефицит сценарий, мест": st.column_config.NumberColumn(format="%d"),
                "Обеспеченность исх.": st.column_config.NumberColumn(format="percent"),
                "Обеспеченность сценарий": st.column_config.NumberColumn(format="percent"),
                "Δ обеспеченности": st.column_config.NumberColumn(format="percent"),
            },
        )
    st.caption(
        "Δ обеспеченности = сценарий − исходное. "
        "Дефицит — неудовлетворённый спрос после распределения мест в пределах времени доступности."
    )
    st.download_button(
        "Скачать сравнение кварталов (CSV)",
        data=to_csv_bytes(comparison_ru),
        file_name="scenario_comparison.csv",
        mime="text/csv",
        key="download_comparison_tab",
    )

with tab_search:
    if search_results is None:
        st.info(
            "Автоподбор ещё не выполнялся. Задайте вместимость новой школы "
            "в панели слева и нажмите «Разместить автоматически»."
        )
    else:
        best = search_results[search_results["is_best"]]
        tied_ids = [int(value) for value in best["block_id"].tolist()]
        st.success(
            f"Проверено кварталов: {len(search_results)}. "
            f"Лучшее сокращение дефицита: {fmt_int(best.iloc[0]['reduction'])} мест. "
            f"Дефицит после размещения: {fmt_int(best.iloc[0]['deficit_after'])} мест."
        )
        if len(tied_ids) > 1:
            st.info("Одинаковые лучшие результаты: " + ", ".join(f"квартал {block_id}" for block_id in tied_ids) + ".")
            chosen_block = st.selectbox(
                "Применить другой лучший квартал",
                tied_ids,
                key="tied_choice",
            )
            if st.button("Применить выбранный квартал", key="apply_tied"):
                capacity_value = int(st.session_state.search_capacity)
                try:
                    new_scenario = core.build_scenario(
                        data,
                        [{"block_id": int(chosen_block), "capacity": capacity_value}],
                    )
                except Exception as exc:
                    st.error(f"Не удалось рассчитать сценарий: {exc}")
                else:
                    st.session_state.scenario_schools = [{"block_id": int(chosen_block), "capacity": capacity_value}]
                    st.session_state.scenario = new_scenario
                    st.session_state.scenario_dirty = False
                    st.session_state.selected_block = int(chosen_block)
                    st.session_state.pending_block_selector = int(chosen_block)
                    st.session_state.pending_map_mode = "Сценарий"
                    st.rerun()
        else:
            st.caption(f"Лучший квартал: {tied_ids[0]}.")
        st.caption(
            "Дефицит рассчитан по той же LP-модели, что и BlocksNet: "
            f"спрос {core.DEMAND_PER_1000} мест на 1000 жителей, "
            f"доступность {core.ACCESSIBILITY_MIN} мин, самопокрытие квартала."
        )
        if search_ru is not None:
            st.dataframe(
                search_ru,
                hide_index=True,
                width="stretch",
                height=520,
                column_config={
                    "Квартал": st.column_config.NumberColumn(format="%d"),
                    "Население, чел.": st.column_config.NumberColumn(format="%d"),
                    "Вместимость сейчас, мест": st.column_config.NumberColumn(format="%d"),
                    "Вместимость сценарий, мест": st.column_config.NumberColumn(format="%d"),
                    "Дефицит до, мест": st.column_config.NumberColumn(format="%d"),
                    "Дефицит после, мест": st.column_config.NumberColumn(format="%d"),
                    "Сокращение дефицита, мест": st.column_config.NumberColumn(format="%d"),
                    "Обеспеченность после": st.column_config.NumberColumn(format="percent"),
                    "Лучший": st.column_config.CheckboxColumn(),
                },
            )
            st.download_button(
                "Скачать результаты автоподбора (CSV)",
                data=to_csv_bytes(search_ru),
                file_name="search_results.csv",
                mime="text/csv",
                key="download_search_tab",
            )

with tab_schools:
    st.subheader("Новые школы сценария")
    render_schools_tab(data, schools)
    if schools:
        st.download_button(
            "Скачать список новых школ (CSV)",
            data=to_csv_bytes(
                pd.DataFrame(
                    [
                        {
                            "Квартал": int(school["block_id"]),
                            "Вместимость, мест": int(school["capacity"]),
                        }
                        for school in schools
                    ]
                )
            ),
            file_name="scenario_schools.csv",
            mime="text/csv",
            key="download_schools_tab",
        )

with tab_method:
    st.subheader("Методика расчёта")
    st.markdown(
        f"""
- Спрос на школьные места: `ceil(население / 1000 × {core.DEMAND_PER_1000})`.
- Доступность: `{core.ACCESSIBILITY_MIN}` минут пешком при скорости `{core.WALK_SPEED_KMH}` км/ч.
- Расчёт обеспеченности: BlocksNet `competitive_provision` с самопокрытием квартала и `max_depth=1`.
- Новая школа добавляет вместимость в выбранный квартал. Места распределяются между жителями квартала и соседних кварталов в пределах времени доступности.
- Дефицит — сумма `demand_left`, то есть неудовлетворённый спрос после распределения мест.
- Автоподбор перебирает все `{len(data.blocks)}` кварталов. Для каждого независимо решается та же LP-задача (решатель HiGHS), затем лучший вариант пересчитывается через BlocksNet.
- Одинаковые лучшие результаты не отбрасываются: в таблице и в сообщении показываются все кварталы с максимальным сокращением дефицита.
        """
    )
    st.subheader("Данные и проверка")
    st.write(f"Папка с данными: `{data.results_dir}`")
    st.write(f"Источник населения: `{data.population_source}`")
    st.write(
        f"Кварталов: {len(data.blocks)}; с населением: {int((data.population > 0).sum())}; "
        f"с текущей вместимостью школ: {int((data.base_capacity > 0).sum())}."
    )
    st.write(
        f"Матрица доступности: {data.acc_matrix.shape[0]}×{data.acc_matrix.shape[1]}; "
        f"параметры: {core.DEMAND_PER_1000} мест на 1000 жителей, {core.ACCESSIBILITY_MIN} мин."
    )
    if check["matches"]:
        st.success(
            f"Исходный расчёт совпадает с school_provision.csv по {len(check['columns'])} показателям "
            f"для {check['rows_calculated']} кварталов."
        )
    else:
        st.error(
            f"Исходный расчёт не совпал с school_provision.csv. " f"Максимальное расхождение: {check['max_diff']:.6g}."
        )
    st.caption(
        "В текущем наборе density_indicators.csv не содержит колонку population, "
        "поэтому население берётся из blocks_results.csv. Если в другом наборе "
        "population есть в density_indicators.csv, приложение использует её автоматически."
    )
    st.caption(
        "Сценарии рассчитываются в памяти и не изменяют файлы в папке results. "
        "Кнопка «Сбросить сценарий» возвращает исходные показатели."
    )

with st.sidebar:
    st.header("Данные")
    st.caption(f"Папка: `{data.results_dir}`")
    st.caption(f"Население: {data.population_source}")
    st.caption(f"Кварталов: {len(data.blocks)}; школ с вместимостью: {int((data.base_capacity > 0).sum())}.")
    st.caption(f"Методика: {core.DEMAND_PER_1000} мест на 1000 жителей, " f"доступность {core.ACCESSIBILITY_MIN} мин.")
    st.divider()

    st.subheader("Ручной сценарий")
    st.caption("Нажмите квартал на карте или выберите ID. Затем задайте вместимость и добавьте школу.")
    block_options = [int(value) for value in data.blocks.index]
    st.selectbox(
        "Квартал",
        block_options,
        key="block_selector",
        format_func=lambda value: f"Квартал {int(value)}",
    )
    manual_capacity = st.number_input(
        "Вместимость школы, мест",
        min_value=1,
        max_value=100000,
        value=core.DEFAULT_NEW_CAPACITY,
        step=1,
        format="%d",
        key="manual_capacity",
    )
    if st.button("Добавить школу", width="stretch"):
        try:
            capacity_value = core.require_positive_int(manual_capacity)
            block_id = int(st.session_state.block_selector)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.scenario_schools.append({"block_id": block_id, "capacity": capacity_value})
            st.session_state.scenario_dirty = True
            st.toast(f"Школа на {capacity_value} мест добавлена в квартал {block_id}.")
            st.rerun()

    if st.session_state.scenario_schools:
        st.caption(
            f"Добавлено школ: {len(st.session_state.scenario_schools)}; "
            f"новых мест: {fmt_int(sum(int(s['capacity']) for s in st.session_state.scenario_schools))}."
        )
        for index, school in enumerate(list(st.session_state.scenario_schools)):
            columns = st.columns([4, 1])
            columns[0].write(f"Квартал {int(school['block_id'])} — {fmt_int(school['capacity'])} мест")
            if columns[1].button("×", key=f"remove_school_{index}", help="Удалить школу"):
                st.session_state.scenario_schools.pop(index)
                st.session_state.scenario_dirty = True
                st.rerun()

    if st.button("Рассчитать сценарий", type="primary", width="stretch"):
        try:
            new_scenario = core.build_scenario(data, st.session_state.scenario_schools)
        except Exception as exc:
            st.error(f"Не удалось рассчитать сценарий: {exc}")
        else:
            st.session_state.scenario = new_scenario
            st.session_state.scenario_dirty = False
            st.session_state.pending_map_mode = "Сценарий"
            st.toast("Сценарий рассчитан.")
            st.rerun()

    if st.button("Сбросить сценарий", width="stretch"):
        st.session_state.scenario_schools = []
        st.session_state.scenario = None
        st.session_state.scenario_dirty = False
        st.session_state.search_results = None
        st.session_state.search_capacity = core.DEFAULT_NEW_CAPACITY
        st.session_state.last_click = None
        st.session_state.pending_block_selector = None
        st.session_state.pending_map_mode = "Исходное"
        st.toast("Сценарий сброшен.")
        st.rerun()

    st.divider()
    st.subheader("Автоматический подбор")
    auto_capacity = st.number_input(
        "Вместимость новой школы, мест",
        min_value=1,
        max_value=100000,
        value=core.DEFAULT_NEW_CAPACITY,
        step=1,
        format="%d",
        key="auto_capacity",
    )
    st.caption("Автоподбор заменит текущий сценарий одной новой школой.")
    if st.button("Разместить автоматически", type="primary", width="stretch"):
        try:
            capacity_value = core.require_positive_int(auto_capacity)
        except ValueError as exc:
            st.error(str(exc))
        else:
            progress = st.progress(0.0, text="Проверяем кварталы...")
            last_progress = {"value": -1.0}

            def update_progress(fraction: float) -> None:
                if fraction >= 1.0 or fraction - last_progress["value"] >= 0.02:
                    last_progress["value"] = fraction
                    progress.progress(
                        min(max(fraction, 0.0), 1.0),
                        text=f"Проверяем кварталы: {int(fraction * 100)}%",
                    )

            try:
                results = core.search_single_school(
                    data,
                    capacity_value,
                    progress_callback=update_progress,
                )
            except Exception as exc:
                progress.empty()
                st.error(f"Не удалось выполнить автоподбор: {exc}")
            else:
                progress.empty()
                best = results[results["is_best"]]
                best_block = int(best.iloc[0]["block_id"])
                new_scenario = core.build_scenario(
                    data,
                    [{"block_id": best_block, "capacity": capacity_value}],
                )
                st.session_state.search_results = results
                st.session_state.search_capacity = capacity_value
                st.session_state.scenario_schools = [{"block_id": best_block, "capacity": capacity_value}]
                st.session_state.scenario = new_scenario
                st.session_state.scenario_dirty = False
                st.session_state.selected_block = best_block
                st.session_state.pending_block_selector = best_block
                st.session_state.pending_map_mode = "Сценарий"
                tied = [int(value) for value in best["block_id"].tolist()]
                st.toast(
                    f"Лучшие кварталы: {', '.join(map(str, tied))}. "
                    f"Сокращение дефицита: {fmt_int(best.iloc[0]['reduction'])} мест."
                )
                st.rerun()

    st.divider()
    st.subheader("Экспорт")
    st.download_button(
        "Сравнение кварталов (CSV)",
        data=to_csv_bytes(comparison_ru),
        file_name="scenario_comparison.csv",
        mime="text/csv",
        width="stretch",
        key="download_comparison_sidebar",
    )
    st.download_button(
        "Сводка сценария (CSV)",
        data=to_csv_bytes(summary_ru),
        file_name="scenario_summary.csv",
        mime="text/csv",
        width="stretch",
        key="download_summary_sidebar",
    )
    if search_ru is not None:
        st.download_button(
            "Результаты автоподбора (CSV)",
            data=to_csv_bytes(search_ru),
            file_name="search_results.csv",
            mime="text/csv",
            width="stretch",
            key="download_search_sidebar",
        )
    st.caption("CSV сохраняется в UTF-8 с BOM и корректно открывается в Excel.")

    if int(st.session_state.block_selector) != int(st.session_state.selected_block):
        st.session_state.selected_block = int(st.session_state.block_selector)
        st.rerun()
