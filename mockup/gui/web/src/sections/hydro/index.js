// The sections of a hydrological station (Nogat plan H1 to H18), in the panel's order.
// Each: {id, title, component} where component({station, meta}) renders the section.

import { Characteristic } from "./characteristic.js";
import { Duration } from "./duration.js";
import { Extremes } from "./extremes.js";
import { LowFlowPeriods } from "./lowflow.js";
import { RatingCurve } from "./rating.js";
import { Regime } from "./regime.js";
import { WaterTemperature } from "./temperature.js";
import { Trends } from "./trends.js";

export const HYDRO_SECTIONS = [
  { id: "characteristic", title: "Stany charakterystyczne", component: Characteristic },
  { id: "rating", title: "Krzywa natężenia przepływu", component: RatingCurve },
  { id: "extremes", title: "Przepływy maksymalne i minimalne", component: Extremes },
  { id: "lowflow", title: "Niżówki", component: LowFlowPeriods },
  { id: "duration", title: "Czas trwania i strefy", component: Duration },
  { id: "regime", title: "Reżim i sezonowość", component: Regime },
  { id: "temperature", title: "Temperatura wody", component: WaterTemperature },
  { id: "trends", title: "Trendy i bilans", component: Trends },
];
