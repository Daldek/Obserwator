// „Opady” (Nogat plan M1 to M5, M7, M9): sums and normals, the monthly regime, days with
// precipitation and the intensity, heavy precipitation, the maxima of 1 to 10 days and their
// quantiles (Hydrolog's `stats flood-frequency`) beside PMAXTP of the station's point.

import { Attribution } from "../../attribution.js";
import { Chart, fmt, html, useMemo, useState } from "../../lib.js";
import { Figures, Section, Seg, Table, YearRange, useAnalysis } from "../common.js";
import {
  DatasetSeg,
  Notes,
  Option,
  ROMAN,
  Select,
  Source,
  byYear,
  date,
  dateRange,
  num,
  part,
  useOptions,
  yearAxis,
  yearReadout,
} from "./util.js";

const YEAR_OPTIONS = [
  ["calendar", "kalendarzowy"],
  ["hydrological", "hydrologiczny XI–X"],
];

const INFO_SUMS = `Sumy miesięczne liczę z opadu dobowego tylko dla miesięcy bez braków; suma wielodniowa, którą IMGW-PIB podaje po dniach bez pomiaru (flaga „accumulated”), zastępuje te dni, gdy obejmuje mniej niż 5 kolejnych dni i mniej niż 11 dni miesiąca (WMO-No. 1203, 2017, p. 4.4.1 c). Suma roczna, półroczna i sezonowa wymaga wszystkich swoich miesięcy. Normalna to średnia z okresu odniesienia (domyślnie cały zapis stacji; można go zawęzić, zalecany minimalny okres to 30 lat), liczona tylko wtedy, gdy wartości ma co najmniej 80 % lat okresu (WMO-No. 1203, p. 4.4.2). Opad względny to suma w % normalnej. Półrocza: zimowe XI–IV i letnie V–X roku hydrologicznego; pory roku meteorologiczne (zima XII–II z grudniem roku poprzedniego). Średnia roczna (M4) to średnia wszystkich lat pełnych.`;

const INFO_REGIME = `Reżim to udział średniej sumy miesięcznej okresu odniesienia w sumie rocznej (współczynnik: średnia miesięczna przez 1/12 sumy rocznej). Wskaźnik koncentracji opadu PCI = 100·Σp²/(Σp)² (Oliver 1980): ≤ 10 równomierny, 11–15 umiarkowanie skoncentrowany, 16–20 nieregularny, > 20 silnie nieregularny. Wskaźnik sezonowości SI = Σ|xₙ − R/12|/R (Walsh i Lawler 1981): < 0,20 bardzo równomierny, < 0,40 równomierny z porą wilgotniejszą, < 0,60 raczej sezonowy, < 0,80 sezonowy, < 1,00 wyraźnie sezonowy, dalej skrajny. Oba liczę z reżimu normalnej i jako średnią wartości lat pełnych. Wektor Markhama (1970): każdy miesiąc jako wektor sumy pod kątem jego środka; długość wypadkowej przez sumę to koncentracja (0–1), jej kąt to średni termin opadu.`;

const INFO_DAYS = `Dni z opadem dobowym co najmniej 0,1, 1, 10 i 20 mm. Miesiąc liczy się, gdy brakuje mniej niż 11 dni i mniej niż 5 kolejnych; liczba dni to udział dni z opadem wśród dni z pomiarem razy liczba dni miesiąca (WMO-No. 1203, p. 4.4.1 d), rok — suma dwunastu takich miesięcy. Natężenie opadu dnia mokrego (M4) to suma opadu w dniach ≥ 1 mm przez ich liczbę (SDII wg ETCCDI; obok wariant dla dni ≥ 0,1 mm), w latach o pełnych miesiącach. Suma wielodniowa po brakach nie jest dniem i tu jest pomijana.`;

const INFO_HEAVY = `Udział opadów dużych wg ETCCDI: progi to 95. i 99. percentyl opadu dni mokrych (≥ 1 mm) okresu odniesienia (kwantyl typu 8 Hyndmana i Fana 1996, jak w climdex.pcic). R95p to suma opadu w dniach powyżej progu P95 w roku, R95pTOT = 100·R95p / suma w dniach ≥ 1 mm (podobnie R99p). Liczę lata z pomiarem w każdym dniu.`;

const INFO_MAXIMA = `Największa suma opadu z n kolejnych dni (n = 1, 2, 3, 5, 10) w każdym roku z pomiarem we wszystkich dniach (jak „stats flood-frequency” Hydrologa przy szeregu dobowym: lata z brakami pomija). Okno n dni należy do roku, w którym się kończy. Maksima miesięczne opadu dobowego biorą wszystkie dni z pomiarem (WMO-No. 1203, p. 4.4.1 b); średnią maksimów miesięcznych liczę z miesięcy z mniej niż 11 brakami.`;

const INFO_QUANTILES = `Kwantyle maksimów rocznych z n dni liczy Hydrolog („stats flood-frequency”) dokładnie jak jego CLI z tymi samymi maksimami (komenda poniżej): rozkłady log-normalny, GEV, Pearsona III i Weibulla, domyślnie metodą L-momentów (Hosking i Wallis 1997), z miarami zgodności KS, A² i AIC; rozkład najlepszy wg AIC jest pierwszy. Maksima biorę z lat okresu odniesienia karty (domyślnie cały zapis stacji, zalecane co najmniej 30 lat). Punkty empiryczne mają prawdopodobieństwo przewyższenia m/(n+1). Obok PMAXTP IMGW-PIB dla punktu stacji (opad o czasie trwania 24, 48 lub 72 h, metody POT i AMP; dane pobrane z IMGW-PIB, nie liczone tu). Uwaga: suma dobowa ze stacji (doba 06–06 UTC) jest mniejsza od maksimum 24-godzinnego w przesuwanym oknie, średnio około 1,13 raza (Weiss 1964); nie przeliczam jej.`;

/** The year type, the dataset and the reference period of the card. */
function Toolbar({ data, opt, setOpt }) {
  const ref = data && data.reference;
  return html`<div class="me-toolbar">
    <${Option} label="Rok"><${Seg} value=${opt.year} label="Rodzaj roku" options=${YEAR_OPTIONS} onChange=${(v) => setOpt({ year: v })} /></${Option}>
    <${DatasetSeg} data=${data} value=${opt.dataset} onChange=${(v) => setOpt({ dataset: v })} />
    ${ref && html`<${YearRange} first=${ref.min} last=${ref.max} from=${ref.from} to=${ref.to} label="Okres odniesienia" onApply=${(a, b) => setOpt({ ref_from: a, ref_to: b })} />`}
  </div>`;
}

function Sums({ state }) {
  const data = state.data;
  const [view, setView] = useState("mm");
  const spec = useMemo(() => {
    if (!data) return null;
    const normal = data.normal.annual;
    if (view === "pct") {
      return {
        x: yearAxis(data.annual, data.year_type === "calendar" ? "rok" : "rok hydrologiczny"),
        y: { label: "opad względny − 100 [%]", unit: "%", zero: true },
        series: [
          {
            id: "pct",
            kind: "bars",
            label: "odchylenie od normalnej",
            align: "center",
            data: data.annual.map((r) => ({ x: r.year, y: r.pct === null ? null : r.pct - 100, cls: r.pct === null ? "" : r.pct >= 100 ? "me-wet" : "me-dry" })),
          },
        ],
        readout: { x: yearReadout, value: (v) => `${fmt(v + 100, 0)} % normalnej` },
        fit: { ratio: 0.5, minHeight: 190 },
        title: "Opad roczny w % normalnej",
      };
    }
    return {
      x: yearAxis(data.annual, data.year_type === "calendar" ? "rok" : "rok hydrologiczny"),
      y: { label: "suma roczna [mm]", unit: "mm" },
      series: [{ id: "sum", kind: "bars", cls: "bar-p", label: "suma roczna", align: "center", data: byYear(data.annual, "sum") }],
      marks: normal === null ? [] : [{ kind: "hline", y: normal, label: `normalna ${fmt(normal, 0)} mm` }],
      readout: { x: yearReadout },
      fit: { ratio: 0.5, minHeight: 190 },
      title: "Sumy roczne opadu",
    };
  }, [data, view]);
  if (!data) return html`<${Section} title="Sumy opadów i normalna" info=${INFO_SUMS} state=${part(state, "sums")} />`;
  const last = [...data.annual].reverse().find((r) => r.sum !== null);
  const ref = data.reference;
  const months = data.months.map((m) => ROMAN[m - 1]);
  const monthColumns = [
    { key: "month", label: "Miesiąc", format: (v) => ROMAN[v - 1] },
    { key: "normal", label: `Normalna ${ref.from}–${ref.to}`, format: (v) => num(v, 1) },
    { key: "mean", label: "Średnia", format: (v) => num(v, 1) },
    { key: "min", label: "Min (rok)", format: (v, r) => (v === null ? "–" : `${fmt(v, 1)} (${r.min_year})`) },
    { key: "max", label: "Maks (rok)", format: (v, r) => (v === null ? "–" : `${fmt(v, 1)} (${r.max_year})`) },
    { key: "share", label: "Udział %", format: (v) => num(v, 1) },
  ];
  const halves = Object.fromEntries(data.halfyears.map((r) => [r.year, r]));
  const yearRows = [...data.annual].reverse().map((r) => ({ ...r, winter: halves[r.year]?.winter ?? null, summer: halves[r.year]?.summer ?? null }));
  const yearColumns = [
    { key: "year", label: "Rok", format: (v) => String(v) },
    { key: "sum", label: "Suma [mm]", format: (v) => num(v, 1) },
    { key: "pct", label: "% normalnej", format: (v) => num(v, 0) },
    { key: "winter", label: "XI–IV", format: (v) => num(v, 1) },
    { key: "summer", label: "V–X", format: (v) => num(v, 1) },
  ];
  const n = data.normal;
  return html`<${Section} title="Sumy opadów i normalna" info=${INFO_SUMS} state=${part(state, "sums")}>
    <${Source} data=${data} />
    <${Figures}
      items=${[
        { label: "Średnia roczna", value: num(data.stats.mean, 0, "mm"), note: `${data.stats.n} lat pełnych` },
        { label: `Normalna ${ref.from}–${ref.to}`, value: num(n.annual, 0, "mm"), note: `${ref.years} lat z sumą` },
        { label: `Rok ${last ? last.year : "–"}`, value: last ? num(last.sum, 0, "mm") : "–", note: last && last.pct !== null ? `${fmt(last.pct, 0)} % normalnej` : "" },
        { label: "Najsuchszy · najmokrzejszy", value: `${num(data.stats.min, 0)} · ${num(data.stats.max, 0)} mm`, note: `${data.stats.min_year} · ${data.stats.max_year}` },
        { label: "Współczynnik zmienności", value: num(data.stats.cv, 2) },
      ]}
    />
    <${Notes} items=${data.notes} />
    <${Option} label="Wykres"><${Seg} value=${view} label="Wykres sum" options=${[["mm", "suma [mm]"], ["pct", "% normalnej"]]} onChange=${setView} /></${Option}>
    <${Chart} spec=${spec} />
    <h4 class="me-sub">Miesiące [mm]</h4>
    <${Table} columns=${monthColumns} rows=${data.month_stats} />
    <h4 class="me-sub">Normalna półroczy i pór roku [mm]</h4>
    <${Table}
      columns=${["winter", "summer", "DJF", "MAM", "JJA", "SON"].map((k) => ({ key: k, label: { winter: "XI–IV", summer: "V–X", DJF: "XII–II", MAM: "III–V", JJA: "VI–VIII", SON: "IX–XI" }[k], format: (v) => num(v, 1) }))}
      rows=${[{ ...n.halfyears, ...n.seasons }]}
    />
    <h4 class="me-sub">Lata</h4>
    <${Table} columns=${yearColumns} rows=${yearRows} max=${10} />
    <details class="me-details"><summary>Miesiące i pory roku wszystkich lat</summary>
      <${AllYears} data=${data} months=${months} />
    </details>
  </${Section}>`;
}

/** The monthly sums of every year (mm or % of the normal) or the seasonal sums. */
function AllYears({ data, months }) {
  const [view, setView] = useState("mm");
  const year = { key: "year", label: "Rok", format: (v) => String(v) };
  let columns;
  let rows;
  if (view === "seasons") {
    const labels = { DJF: "XII–II", MAM: "III–V", JJA: "VI–VIII", SON: "IX–XI" };
    columns = [year, ...Object.entries(labels).map(([key, label]) => ({ key, label, format: (v) => num(v, 1) }))];
    rows = [...data.seasons].reverse();
  } else {
    const field = view === "pct" ? "pct" : "sums";
    columns = [year, ...months.map((label, at) => ({ key: `m${at}`, label, format: (v) => num(v, view === "pct" ? 0 : 1) }))];
    rows = [...data.monthly].reverse().map((r) => Object.fromEntries([["year", r.year], ...r[field].map((v, at) => [`m${at}`, v])]));
  }
  return html`<${Seg} value=${view} label="Tabela lat" options=${[["mm", "miesiące [mm]"], ["pct", "miesiące [% normalnej]"], ["seasons", "pory roku [mm]"]]} onChange=${setView} />
    <${Table} className="tbl me-wide" columns=${columns} rows=${rows} />`;
}

const MONTH_NAMES = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"];

/** A month position of Markham's vector (1.0 = the middle of January) as words. */
function monthPosition(value) {
  if (value === null || value === undefined) return "–";
  const index = Math.floor(value - 0.5 + 12) % 12;
  const part = value - 0.5 - Math.floor(value - 0.5);
  const when = part < 1 / 3 ? "początek" : part < 2 / 3 ? "połowa" : "koniec";
  return `${when} ${MONTH_NAMES[index]}`;
}

function Regime({ state }) {
  const data = state.data;
  const regime = data && data.regime;
  const spec = useMemo(() => {
    if (!regime) return null;
    return {
      x: { label: "miesiąc", tickList: ROMAN.map((label, at) => ({ value: at + 1, label })), min: 0.5, max: 12.5 },
      y: { label: "udział w sumie rocznej [%]", unit: "%" },
      series: [{ id: "share", kind: "bars", cls: "bar-p", label: "udział", align: "center", data: regime.share.map((v, at) => [at + 1, v]) }],
      marks: [{ kind: "hline", y: 100 / 12, label: "1/12" }],
      readout: { x: (x) => ROMAN[Math.round(x) - 1] || "" },
      fit: { ratio: 0.45, minHeight: 170 },
      title: "Reżim opadów",
    };
  }, [regime]);
  if (!data) return html`<${Section} title="Reżim i sezonowość opadów" info=${INFO_REGIME} state=${part(state, "regime")} />`;
  if (!regime) {
    return html`<${Section} title="Reżim i sezonowość opadów" info=${INFO_REGIME} state=${part(state, "regime")}>
      <p class="muted">Normalna któregoś miesiąca okresu ${data.reference.from}–${data.reference.to} nie ma 80 % lat; wybierz inny okres odniesienia.</p>
    </${Section}>`;
  }
  return html`<${Section} title="Reżim i sezonowość opadów" info=${INFO_REGIME} state=${part(state, "regime")}>
    <${Chart} spec=${spec} />
    <${Figures}
      items=${[
        { label: "PCI normalnej", value: num(regime.pci, 1), note: regime.pci_classes[regime.pci_class] },
        { label: "PCI lat (średnia)", value: num(regime.pci_years_mean, 1), note: regime.pci_classes[regime.pci_years_class] },
        { label: "SI normalnej", value: num(regime.si, 2), note: regime.si_classes[regime.si_class] },
        { label: "SI lat (średnia)", value: num(regime.si_years_mean, 2), note: regime.si_classes[regime.si_years_class] },
        { label: "Koncentracja (Markham)", value: num(regime.markham.concentration, 2), note: `średni termin: ${monthPosition(regime.markham.month)}` },
      ]}
    />
    <${Table}
      columns=${[{ key: "name", label: "", format: (v) => v }, ...ROMAN.map((label, at) => ({ key: `m${at}`, label, format: (v) => num(v, 2) }))]}
      rows=${[{ name: "współczynnik", ...Object.fromEntries(regime.coefficient.map((v, at) => [`m${at}`, v])) }]}
      className="tbl me-wide"
    />
  </${Section}>`;
}

const THRESHOLD_KEYS = [
  ["d01", "≥ 0,1 mm"],
  ["d1", "≥ 1 mm"],
  ["d10", "≥ 10 mm"],
  ["d20", "≥ 20 mm"],
];

function Days({ state }) {
  const data = state.data;
  const [key, setKey] = useState("d10");
  const spec = useMemo(() => {
    if (!data) return null;
    const name = THRESHOLD_KEYS.find(([k]) => k === key)[1];
    return {
      x: yearAxis(data.annual, data.year_type === "calendar" ? "rok" : "rok hydrologiczny"),
      y: { label: `dni z opadem ${name}`, unit: "dni" },
      series: [{ id: key, kind: "bars", cls: "bar-pe", label: `dni ${name}`, align: "center", data: byYear(data.annual, key) }],
      marks: data.means[key] === null ? [] : [{ kind: "hline", y: data.means[key], label: `średnio ${fmt(data.means[key], 1)}` }],
      readout: { x: yearReadout, value: (v) => fmt(v, 0) },
      fit: { ratio: 0.45, minHeight: 170 },
      title: "Dni z opadem w latach",
    };
  }, [data, key]);
  if (!data) return html`<${Section} title="Dni z opadem i natężenie" info=${INFO_DAYS} state=${part(state, "days")} />`;
  const columns = [
    { key: "month", label: "Miesiąc", format: (v) => ROMAN[v - 1] },
    ...THRESHOLD_KEYS.map(([k, label]) => ({ key: k, label, format: (v) => num(v, 1) })),
    { key: "sdii", label: "SDII [mm/d]", format: (v) => num(v, 1) },
  ];
  return html`<${Section} title="Dni z opadem i natężenie" info=${INFO_DAYS} state=${part(state, "days")}>
    <${Figures}
      items=${[
        ...THRESHOLD_KEYS.map(([k, label]) => ({ label: `Dni ${label}`, value: num(data.means[k], 0), note: "średnio w roku" })),
        { label: "Natężenie dnia ≥ 1 mm", value: num(data.means.sdii, 1, "mm/d"), note: `dnia ≥ 0,1 mm: ${num(data.means.sdii01, 1, "mm/d")}` },
      ]}
    />
    <${Option} label="Próg"><${Seg} value=${key} label="Próg opadu" options=${THRESHOLD_KEYS} onChange=${setKey} /></${Option}>
    <${Chart} spec=${spec} />
    <h4 class="me-sub">Średnio w miesiącu</h4>
    <${Table} columns=${columns} rows=${data.months} />
    <h4 class="me-sub">Lata</h4>
    <${Table}
      columns=${[
        { key: "year", label: "Rok", format: (v) => String(v) },
        ...THRESHOLD_KEYS.map(([k, label]) => ({ key: k, label, format: (v) => num(v, 0) })),
        { key: "sdii", label: "SDII [mm/d]", format: (v) => num(v, 1) },
      ]}
      rows=${[...data.annual].reverse()}
      max=${10}
    />
  </${Section}>`;
}

function Heavy({ state }) {
  const data = state.data;
  const heavy = data && data.heavy;
  const spec = useMemo(() => {
    if (!heavy || heavy.p95 === undefined) return null;
    return {
      x: yearAxis(data.annual, data.year_type === "calendar" ? "rok" : "rok hydrologiczny"),
      y: { label: "udział w sumie dni ≥ 1 mm [%]", unit: "%" },
      series: [
        { id: "r95", kind: "bars", cls: "bar-pe", label: "R95pTOT", align: "center", data: byYear(data.annual, "r95_share") },
        { id: "r99", kind: "points", label: "R99pTOT", data: data.annual.filter((r) => r.r99_share !== undefined).map((r) => [r.year, r.r99_share]) },
      ],
      legend: true,
      readout: { x: yearReadout, value: (v) => `${fmt(v, 1)} %` },
      fit: { ratio: 0.45, minHeight: 170 },
      title: "Udział opadów dużych",
    };
  }, [data]);
  if (!data) return html`<${Section} title="Opady duże (R95p, R99p)" info=${INFO_HEAVY} state=${part(state, "heavy")} />`;
  if (heavy.p95 === undefined) {
    return html`<${Section} title="Opady duże (R95p, R99p)" info=${INFO_HEAVY} state=${part(state, "heavy")}><p class="muted">${heavy.note}</p></${Section}>`;
  }
  const rows = [...data.annual].reverse().filter((r) => r.r95 !== undefined);
  return html`<${Section} title="Opady duże (R95p, R99p)" info=${INFO_HEAVY} state=${part(state, "heavy")}>
    <${Figures}
      items=${[
        { label: "Próg P95", value: num(heavy.p95, 1, "mm"), note: `${heavy.reference.from}–${heavy.reference.to}, ${heavy.wet_days} dni ≥ 1 mm` },
        { label: "Próg P99", value: num(heavy.p99, 1, "mm") },
        { label: "R95pTOT średnio", value: num(heavy.r95_share_mean, 1, "%"), note: `${heavy.years} lat` },
        { label: "R99pTOT średnio", value: num(heavy.r99_share_mean, 1, "%") },
      ]}
    />
    <${Chart} spec=${spec} />
    <${Table}
      columns=${[
        { key: "year", label: "Rok", format: (v) => String(v) },
        { key: "prcptot", label: "Suma dni ≥ 1 mm", format: (v) => num(v, 1) },
        { key: "r95", label: "R95p [mm] (dni)", format: (v, r) => `${num(v, 1)} (${r.r95_days})` },
        { key: "r95_share", label: "R95pTOT %", format: (v) => num(v, 1) },
        { key: "r99", label: "R99p [mm] (dni)", format: (v, r) => `${num(v, 1)} (${r.r99_days})` },
        { key: "r99_share", label: "R99pTOT %", format: (v) => num(v, 1) },
      ]}
      rows=${rows}
      max=${8}
    />
  </${Section}>`;
}

const DAY_OPTIONS = [1, 2, 3, 5, 10].map((n) => [String(n), n === 1 ? "1 doba" : `${n} dni`]);

function Maxima({ state, days, onDays }) {
  const data = state.data;
  const spec = useMemo(() => {
    if (!data) return null;
    return {
      x: yearAxis(data.annual, data.year_type === "calendar" ? "rok" : "rok hydrologiczny"),
      y: { label: `maksimum ${days === 1 ? "dobowe" : `${days}-dniowe`} [mm]`, unit: "mm" },
      series: [{ id: "max", kind: "bars", cls: "bar-p", label: "maksimum roczne", align: "center", data: byYear(data.annual, `p${days}`) }],
      marks: data.summary[days] ? [{ kind: "hline", y: data.summary[days].mean, label: `średnio ${fmt(data.summary[days].mean, 1)} mm` }] : [],
      readout: { x: yearReadout },
      fit: { ratio: 0.45, minHeight: 170 },
      title: "Maksima roczne",
    };
  }, [data, days]);
  if (!data) return html`<${Section} title="Opady maksymalne 1–10 dni" info=${INFO_MAXIMA} state=${state} />`;
  const s = data.summary[days];
  const columns = [
    { key: "year", label: "Rok", format: (v) => String(v) },
    ...data.durations.map((n) => ({ key: `p${n}`, label: n === 1 ? "1 d" : `${n} d`, format: (v) => num(v, 1) })),
    { key: `p${days}_start`, label: `Termin (${days} d)`, format: (v, r) => dateRange(v, r[`p${days}_end`]) },
  ];
  return html`<${Section} title="Opady maksymalne 1–10 dni" info=${INFO_MAXIMA} state=${state}>
    <${Option} label="Czas"><${Seg} value=${String(days)} label="Liczba dni" options=${DAY_OPTIONS} onChange=${(v) => onDays(+v)} /></${Option}>
    <${Figures}
      items=${[
        { label: "Średnie maksimum", value: num(s.mean, 1, "mm"), note: `mediana ${num(s.median, 1)} mm` },
        { label: "Największe", value: num(s.max, 1, "mm"), note: dateRange(s.max_start, s.max_end) },
        { label: "Najmniejsze", value: num(s.min, 1, "mm") },
        { label: "Lat pełnych", value: String(s.n), note: data.incomplete.length ? `pominięte niepełne: ${data.incomplete.length}` : "" },
      ]}
    />
    <${Chart} spec=${spec} />
    <h4 class="me-sub">Maksima roczne [mm]</h4>
    <${Table} columns=${columns} rows=${[...data.annual].reverse()} max=${10} />
    ${data.incomplete.length ? html`<p class="muted me-caption">Lata pominięte (braki dni): ${data.incomplete.join(", ")}.</p>` : null}
    <h4 class="me-sub">Maksima miesięczne opadu dobowego</h4>
    <${Table}
      columns=${[
        { key: "month", label: "Miesiąc", format: (v) => ROMAN[v - 1] },
        { key: "max", label: "Najwyższy [mm]", format: (v, r) => (v === null ? "–" : `${fmt(v, 1)} (${date(r.date)})`) },
        { key: "mean_max", label: "Średnie maks. [mm]", format: (v) => num(v, 1) },
        { key: "annual_max", label: "Maks. roczne", format: (v) => (v === undefined ? "–" : `${v}×`) },
      ]}
      rows=${data.months}
    />
    <details class="me-details"><summary>Dziesięć największych opadów dobowych</summary>
      <${Table} columns=${[{ key: "date", label: "Data", format: (v) => date(v) }, { key: "value", label: "Opad [mm]", format: (v) => num(v, 1) }]} rows=${data.top} />
    </details>
  </${Section}>`;
}

const DIST = { gev: "GEV", log_normal: "log-normalny", pearson3: "Pearson III", weibull: "Weibull" };
const DIST_CLASS = { gev: "s1", log_normal: "s2", pearson3: "s3", weibull: "s6" };

function Quantiles({ state, opt, setOpt }) {
  const data = state.data;
  const spec = useMemo(() => {
    if (!data) return null;
    const h = data.hydrolog;
    const series = h.distributions.map((d, at) => ({
      id: d.distribution_name,
      kind: "line",
      cls: `${DIST_CLASS[d.distribution_name] || "s4"}${at === 0 ? " best" : ""}`,
      label: DIST[d.distribution_name] || d.distribution_name,
      data: d.return_periods.map((t, k) => [100 / t, d.quantiles[k]]),
    }));
    const legend = h.distributions.map((d, at) => ({ label: `${DIST[d.distribution_name] || d.distribution_name}${at === 0 ? " (najlepszy AIC)" : ""}`, kind: "stroke", cls: DIST_CLASS[d.distribution_name] || "s4" }));
    series.push({ id: "emp", kind: "points", label: "maksima roczne", data: h.empirical.values_sorted.map((v, k) => [100 * h.empirical.exceedance_prob[k], v]), readout: false });
    legend.push({ label: "maksima roczne (m/(n+1))", kind: "points" });
    const pm = data.pmaxtp;
    if (pm && pm.available) {
      for (const [method, cls] of [["POT", "s4"], ["AMP", "s5"]]) {
        if (!pm[method] || !pm[method].quantiles) continue;
        series.push({ id: `pmaxtp-${method}`, kind: "line", cls, label: `PMAXTP ${method}`, data: pm.periods.map((t, k) => [100 / t, pm[method].quantiles[k]]) });
        legend.push({ label: `PMAXTP ${method} (${pm.duration_min / 60} h)`, kind: "stroke", cls });
      }
    }
    return {
      x: { scale: "gumbel", domain: [99, 0.1], label: "prawdopodobieństwo przewyższenia" },
      y: { label: `opad maksymalny ${data.days === 1 ? "dobowy" : `${data.days}-dniowy`} [mm]`, unit: "mm" },
      series,
      legend,
      readout: { series: series[0].id },
      fit: { ratio: 0.66, minHeight: 240 },
      title: "Rozkłady maksimów rocznych opadu na siatce Gumbela",
    };
  }, [data]);
  const toolbar = html`<div class="me-options">
    <${Option} label="Czas"><${Seg} value=${String(opt.days)} label="Liczba dni" options=${DAY_OPTIONS} onChange=${(v) => setOpt({ days: +v })} /></${Option}>
    <${Option} label="Rozkład"><${Select} value=${opt.distribution} label="Rozkład" options=${[["all", "wszystkie cztery"], ["log_normal", "log-normalny"], ["gev", "GEV"], ["pearson3", "Pearson III"], ["weibull", "Weibull"]]} onChange=${(v) => setOpt({ distribution: v })} /></${Option}>
    <${Option} label="Metoda"><${Select} value=${opt.fit_method} label="Metoda estymacji" options=${[["l_moments", "L-momenty (domyślna)"], ["mle", "największa wiarygodność"], ["moments", "momenty"], ["least_squares", "najmniejsze kwadraty"]]} onChange=${(v) => setOpt({ fit_method: v })} /></${Option}>
  </div>`;
  if (!data) return html`<${Section} title="Opad maksymalny o prawdopodobieństwie p" info=${INFO_QUANTILES} state=${state}>${toolbar}</${Section}>`;
  const h = data.hydrolog;
  const best = h.distributions[0];
  const pm = data.pmaxtp;
  const at = (t) => best.return_periods.findIndex((r) => Math.abs(r - t) < 1e-9);
  const rows = data.table_periods.map((t, k) => {
    const row = { p: 100 / t, T: t, best: best.quantiles[at(t)] };
    if (pm && pm.available) {
      row.pot = pm.POT && pm.POT.quantiles ? pm.POT.quantiles[k] : null;
      row.amp = pm.AMP && pm.AMP.quantiles ? pm.AMP.quantiles[k] : null;
    }
    return row;
  });
  const columns = [
    { key: "p", label: "p [%]", format: (v) => fmt(v, v >= 1 ? 0 : 1) },
    { key: "T", label: "T [lata]", format: (v) => fmt(v, 0) },
    { key: "best", label: `${DIST[best.distribution_name] || best.distribution_name} [mm]`, format: (v) => num(v, 1) },
    ...(pm && pm.available ? [{ key: "pot", label: `POT ${pm.duration_min / 60} h`, format: (v) => num(v, 1) }, { key: "amp", label: `AMP ${pm.duration_min / 60} h`, format: (v) => num(v, 1) }] : []),
  ];
  const allColumns = [
    { key: "T", label: "T [lata]", format: (v) => fmt(v, 0) },
    ...h.distributions.map((d) => ({ key: d.distribution_name, label: DIST[d.distribution_name] || d.distribution_name, format: (v) => num(v, 1) })),
  ];
  const allRows = data.table_periods.map((t) => Object.fromEntries([["T", t], ...h.distributions.map((d) => [d.distribution_name, d.quantiles[d.return_periods.findIndex((r) => Math.abs(r - t) < 1e-9)]])]));
  const fitColumns = [
    { key: "name", label: "Rozkład", format: (v) => DIST[v] || v },
    { key: "aic", label: "AIC", format: (v) => num(v, 1) },
    { key: "ks", label: "KS (p)", format: (v, r) => `${num(r.ks_statistic, 3)} (${num(v, 2)}${r.ks_valid === false ? "*" : ""})` },
    { key: "ad", label: "A²", format: (v) => num(v, 3) },
    { key: "params", label: "parametry", format: (v) => v },
  ];
  const fitRows = h.distributions.map((d) => ({
    name: d.distribution_name,
    aic: d.aic,
    ks: d.ks_p_value,
    ks_statistic: d.ks_statistic,
    ks_valid: d.ks_valid,
    ad: d.ad_statistic,
    params: Object.entries(d.parameters || {}).map(([k, v]) => `${k} ${fmt(v, Math.abs(v) >= 100 ? 1 : 3)}`).join(", "),
  }));
  const shown = (h.notices || []).filter((n) => n.level !== "info");
  return html`<${Section} title="Opad maksymalny o prawdopodobieństwie p" info=${INFO_QUANTILES} state=${state}>
    ${toolbar}
    <${Figures}
      items=${[
        { label: "Lat (maksimów)", value: String(h.n_years), note: `${data.maxima[0].year}–${data.maxima[data.maxima.length - 1].year}` },
        { label: "Najlepszy (AIC)", value: DIST[best.distribution_name] || best.distribution_name },
        { label: "p = 1 % (T = 100)", value: num(best.quantiles[at(100)], 1, "mm") },
        ...(pm && pm.available && pm.POT && pm.POT.quantiles ? [{ label: `PMAXTP POT, p = 1 %`, value: num(pm.POT.quantiles[data.table_periods.indexOf(100)], 1, "mm"), note: `${pm.duration_min / 60} h, punkt stacji` }] : []),
      ]}
    />
    <${Chart} spec=${spec} />
    <h4 class="me-sub">Opad maksymalny P_p [mm]</h4>
    <${Table} columns=${columns} rows=${rows} />
    ${pm && !pm.available ? html`<p class="muted me-caption">PMAXTP: ${pm.reason}</p>` : null}
    ${pm && pm.available
      ? html`<p class="muted me-caption">POT i AMP: PMAXTP IMGW-PIB (opad o czasie trwania ${pm.duration_min / 60} h) dla punktu ${fmt(pm.latitude, 4)}° N, ${fmt(pm.longitude, 4)}° E. Dane PMAXTP mają własny regulamin:</p>
          <${Attribution} fields=${pm} className="sec-attrib" />`
      : null}
    <details class="me-details"><summary>Wszystkie rozkłady i miary zgodności</summary>
      <${Table} columns=${allColumns} rows=${allRows} />
      <${Table} columns=${fitColumns} rows=${fitRows} />
      <p class="muted me-caption">* p-value KS orientacyjne: parametry oszacowano z tej samej próby (Hydrolog: porządkuj wg AIC).</p>
    </details>
    ${shown.length ? html`<details class="me-details"><summary>Komunikaty Hydrologa (${shown.length})</summary><ul>${shown.map((n) => html`<li><code>${n.code}</code> ${n.message}</li>`)}</ul></details>` : null}
    <details class="me-details"><summary>Ta sama komenda w terminalu</summary><pre class="me-cli">${h.cli}</pre></details>
    ${data.incomplete.length ? html`<p class="muted me-caption">Lata pominięte (braki dni): ${data.incomplete.join(", ")}.</p>` : null}
  </${Section}>`;
}

/** The card „Opady”. */
export function Opady({ station }) {
  const code = station.code;
  const [opt, setOpt] = useOptions({ year: "calendar", dataset: undefined, ref_from: undefined, ref_to: undefined, days: 1, distribution: "all", fit_method: "l_moments" }, code);
  const common = { year: opt.year, dataset: opt.dataset };
  const sums = useAnalysis("meteo-precip-sums", code, { ...common, ref_from: opt.ref_from, ref_to: opt.ref_to });
  const days = useAnalysis("meteo-precip-days", code, { ...common, ref_from: opt.ref_from, ref_to: opt.ref_to });
  const maxima = useAnalysis("meteo-precip-maxima", code, common);
  const quantiles = useAnalysis("meteo-precip-quantiles", code, { ...common, ref_from: opt.ref_from, ref_to: opt.ref_to, days: opt.days, distribution: opt.distribution, fit_method: opt.fit_method });
  return html`<div class="me-card">
    <${Toolbar} data=${sums.data} opt=${opt} setOpt=${setOpt} />
    <${Sums} state=${sums} />
    <${Regime} state=${sums} />
    <${Days} state=${days} />
    <${Heavy} state=${days} />
    <${Maxima} state=${maxima} days=${opt.days} onDays=${(n) => setOpt({ days: n })} />
    <${Quantiles} state=${quantiles} opt=${opt} setOpt=${setOpt} />
  </div>`;
}
