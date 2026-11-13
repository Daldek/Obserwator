// The sections of a hydrological station (Nogat plan H1 to H18), in the panel's order. Each
// entry: {id, title (catalog key), component, available(station, ids)}; the panel renders
// component({station, session, analyses}) and leaves out a section none of whose analysis
// ids applies to the station (`ids`: the Set of `api/analyses/{code}`).

import { Characteristic } from "./characteristic.js";
import { Duration } from "./duration.js";
import { Extremes } from "./extremes.js";
import { LowFlowPeriods } from "./lowflow.js";
import { RatingCurve } from "./rating.js";
import { Regime } from "./regime.js";
import { WaterTemperature } from "./temperature.js";
import { Trends } from "./trends.js";

const VARIABLES = ["H", "Q", "T"];
const STATISTICS = ["max", "mean", "min"];

/** Whether any of the ids applies to the station. */
function some(...wanted) {
  return (station, ids) => wanted.some((id) => ids.has(id));
}

export const HYDRO_SECTIONS = [
  {
    id: "characteristic",
    title: "hydro.section.characteristic",
    component: Characteristic,
    available: some(...VARIABLES.flatMap((v) => [`characteristic.${v}`, `characteristic.${v}.half_years`])),
  },
  { id: "rating", title: "hydro.section.rating", component: RatingCurve, available: some("rating_curve", "rating_curve.periods") },
  { id: "extremes", title: "hydro.section.extremes", component: Extremes, available: some("flood_frequency.Q", "low_flow.Q", "homogeneity.Q") },
  { id: "lowflow", title: "hydro.section.lowflow", component: LowFlowPeriods, available: some("low_flow_sequences.Q") },
  {
    id: "duration",
    title: "hydro.section.duration",
    component: Duration,
    available: some("duration_curve.H", "duration_curve.Q", "water_level_zones.H"),
  },
  {
    id: "regime",
    title: "hydro.section.regime",
    component: Regime,
    available: some(...VARIABLES.flatMap((v) => [`daily.${v}`, `monthly.${v}`]), "regime.Q", "seasonality.Q.max", "seasonality.Q.min"),
  },
  {
    id: "temperature",
    title: "hydro.section.temperature",
    component: WaterTemperature,
    available: some("harmonics.T", ...["ge15", "ge20", "ge25", "lt1"].map((key) => `threshold_events.T.${key}`)),
  },
  {
    id: "trends",
    title: "hydro.section.trends",
    component: Trends,
    available: some(...VARIABLES.flatMap((v) => STATISTICS.map((s) => `mann_kendall.${v}.${s}`)), "runoff_volume.Q", "baseflow.Q"),
  },
];
