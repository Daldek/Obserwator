// The sections of a meteorological station (Nogat plan M1 to M14), in the panel's order.
// Each: {id, title, component, available} where component({station, meta}) renders the
// section and available(station) says whether the station's data allow it: a precipitation
// post shows no „Temperatura”, a ČHMÚ station no „Śnieg”.

import { Opady } from "./opady.js";
import { Snieg } from "./snieg.js";
import { Susze } from "./susze.js";
import { Temperatura } from "./temperatura.js";
import { Trendy } from "./trendy.js";
import { stationHas } from "./util.js";

const P_SETS = ["pl.imgw.meteo_climate_daily", "pl.imgw.meteo_precip_daily", "cz.chmi.meteo_daily"];
const T_SETS = ["pl.imgw.meteo_climate_daily", "cz.chmi.meteo_daily"];
const SNOW_SETS = ["pl.imgw.meteo_climate_daily", "pl.imgw.meteo_precip_daily"];

const hasP = (station) => stationHas(station, "P", P_SETS);
const hasT = (station) => ["Tmean", "Tmax", "Tmin"].some((v) => stationHas(station, v, T_SETS));

export const METEO_SECTIONS = [
  { id: "opady", title: "Opady", component: Opady, available: hasP },
  { id: "susze", title: "Susze i okresy bezopadowe", component: Susze, available: hasP },
  { id: "temperatura", title: "Temperatura", component: Temperatura, available: hasT },
  { id: "snieg", title: "Śnieg", component: Snieg, available: (station) => stationHas(station, "snow_cover", SNOW_SETS) },
  { id: "trendy", title: "Trendy", component: Trendy, available: (station) => hasP(station) || hasT(station) },
];
