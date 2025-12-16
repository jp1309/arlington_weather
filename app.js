
const DATA_URL = "data/arlington_daily.csv";
const PCTL_URL = "data/climatology_doy365_percentiles.csv";

function showError(msg){
  const el = document.getElementById("plot");
  if(!el) return;
  el.innerHTML = `<div style="padding:14px; color:#e5e7eb; font-family:system-ui;">
    <div style="font-weight:700; margin-bottom:6px;">No se pudo dibujar el gráfico</div>
    <div style="color:#9ca3af; white-space:pre-wrap;">${msg}</div>
    <div style="margin-top:10px; color:#9ca3af;">Tip: F12 → Console/Network para ver el detalle.</div>
  </div>`;
}

async function safeFetchText(url){
  const r = await fetch(url, {cache:"no-store"});
  if(!r.ok) throw new Error(`No se pudo cargar ${url}. HTTP ${r.status}`);
  return await r.text();
}

function parseCSV(text){
  const lines = text.trim().split(/\r?\n/);
  if(lines.length < 2) return [];
  const headers = lines[0].split(",");
  const rows = [];
  for(let i=1;i<lines.length;i++){
    const cols = lines[i].split(",");
    const obj = {};
    headers.forEach((h, idx) => obj[h] = (cols[idx] === undefined || cols[idx] === "") ? null : cols[idx]);
    rows.push(obj);
  }
  return rows;
}

function toNum(x){
  if(x === null) return null;
  const v = Number(x);
  return Number.isFinite(v) ? v : null;
}

function unique(arr){
  return Array.from(new Set(arr)).sort((a,b)=>a-b);
}

function pad2(n){ return String(n).padStart(2,"0"); }

// Reference year (non-leap) for month/day mapping
function doyToMD(doy){
  const dt = new Date(Date.UTC(2001, 0, 1));
  dt.setUTCDate(dt.getUTCDate() + (doy - 1));
  return {m: dt.getUTCMonth() + 1, d: dt.getUTCDate()};
}
function mdToDoy(month, day){
  const dt = new Date(Date.UTC(2001, month - 1, day));
  const start = new Date(Date.UTC(2001, 0, 1));
  const diffDays = Math.floor((dt - start) / (24*3600*1000));
  return diffDays + 1;
}
function doyToLabel(doy){
  const {m, d} = doyToMD(doy);
  const names = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];
  return `${pad2(d)}-${names[m-1]}`;
}
function dateInputToDoy(value){
  const parts = value.split("-").map(Number);
  return mdToDoy(parts[1], parts[2]);
}
function clamp(x, lo, hi){ return Math.max(lo, Math.min(hi, x)); }

function getMetricMeta(metric){
  const meta = {
    "Tavg_C": {title:"Temperatura media", unit:"°C", pctl:true},
    "Tmin_C": {title:"Temperatura mínima", unit:"°C", pctl:true},
    "Tmax_C": {title:"Temperatura máxima", unit:"°C", pctl:true},
    "PRCP_mm": {title:"Precipitación", unit:"mm", pctl:true},
    "SNOW_mm": {title:"Nieve", unit:"mm", pctl:false},
    "SNWD_mm": {title:"Profundidad de nieve", unit:"mm", pctl:false}
  };
  return meta[metric] || {title: metric, unit:"", pctl:false};
}

function computeTickMarks(startDoy, endDoy){
  const monthStarts = [1,32,60,91,121,152,182,213,244,274,305,335];
  const ticks = monthStarts.filter(v => v >= startDoy && v <= endDoy);
  if(!ticks.includes(startDoy)) ticks.unshift(startDoy);
  if(!ticks.includes(endDoy)) ticks.push(endDoy);
  const uniq = Array.from(new Set(ticks)).sort((a,b)=>a-b);
  return { tickvals: uniq, ticktext: uniq.map(doyToLabel) };
}

let DATA = [];
let PCTL = [];

function getSelectedYears(){
  const sel = document.getElementById("years");
  const out = [];
  for(const opt of sel.options){
    if(opt.selected) out.push(Number(opt.value));
  }
  return out;
}
function setDefaultYears(years){
  const sel = document.getElementById("years");
  const last = years.slice(-3);
  for(const opt of sel.options){
    opt.selected = last.includes(Number(opt.value));
  }
}

function buildPlot(){
  try{
    if(typeof Plotly === "undefined"){
      showError("Plotly no está disponible (falló el CDN).");
      return;
    }

    const metric = document.getElementById("metric").value;
    const meta = getMetricMeta(metric);

    const startVal = document.getElementById("startDate").value;
    const endVal = document.getElementById("endDate").value;

    let startDoy = dateInputToDoy(startVal);
    let endDoy = dateInputToDoy(endVal);
    if(endDoy < startDoy){ const t = startDoy; startDoy = endDoy; endDoy = t; }
    startDoy = clamp(startDoy, 1, 365);
    endDoy = clamp(endDoy, 1, 365);

    const years = getSelectedYears();
    const traces = [];

    // Percentiles (only for supported metrics)
    const note = document.getElementById("pctlNote");
    const p10on = document.getElementById("p10").checked;
    const p50on = document.getElementById("p50").checked;
    const p90on = document.getElementById("p90").checked;

    if(!meta.pctl){
      if(note) note.textContent = "Percentiles disponibles solo para temperatura y precipitación.";
    } else {
      if(note) note.textContent = "Percentiles por día del año (1995–último). Líneas punteadas.";
      const rows = PCTL.filter(r => {
        const d = toNum(r["DOY_365"]);
        return d !== null && d >= startDoy && d <= endDoy;
      });
      const x = rows.map(r => toNum(r["DOY_365"]));
      const xlbl = x.map(doyToLabel);

      const c10 = `${metric}_p10`;
      const c50 = `${metric}_p50`;
      const c90 = `${metric}_p90`;

      const addP = (name, col, width) => {
        traces.push({
          x,
          y: rows.map(r => toNum(r[col])),
          name,
          mode: "lines",
          line: {dash:"dot", width},
          customdata: xlbl,
          hovertemplate: name + "<br>%{customdata}<br>" + meta.title + ": %{y} " + meta.unit + "<extra></extra>"
        });
      };

      if(p10on) addP("p10", c10, 1);
      if(p50on) addP("p50", c50, 1.5);
      if(p90on) addP("p90", c90, 1);
    }

    // Year series
    for(const yr of years){
      const rows = DATA.filter(r => Number(r["Year"]) === yr).filter(r => {
        const d = toNum(r["DOY_365"]);
        return d !== null && d >= startDoy && d <= endDoy;
      });
      const x = rows.map(r => toNum(r["DOY_365"]));
      const y = rows.map(r => toNum(r[metric]));
      traces.push({
        x, y,
        name: String(yr),
        mode: "lines",
        line: {width: (yr === 2025 ? 4 : 2)},
        customdata: x.map(doyToLabel),
        hovertemplate: "Año " + yr + "<br>%{customdata}<br>" + meta.title + ": %{y} " + meta.unit + "<extra></extra>"
      });
    }

    const {tickvals, ticktext} = computeTickMarks(startDoy, endDoy);
    const title = `Comparación por día del año. ${meta.title} (${meta.unit})`;

    Plotly.react("plot", traces, {
      margin: {l:70, r:20, t:45, b:65},
      title: {text: title, x:0},
      xaxis: {title:"Día y mes", tickmode:"array", tickvals, ticktext, range:[startDoy, endDoy]},
      yaxis: {title:`${meta.title} (${meta.unit})`},
      legend: {orientation:"h", y:-0.22},
      hovermode: "closest",
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: {color:"#e5e7eb"}
    }, {responsive:true, displaylogo:false});

    document.getElementById("footnote").textContent =
      "Fuente: NOAA GHCN-Daily. Estación USW00013743 (Reagan National). Eje X estandarizado a 365 días (Feb 29 excluido).";
  } catch(e){
    showError(String(e));
  }
}

function setIntervalMD(m1, d1, m2, d2){
  const s = `2001-${pad2(m1)}-${pad2(d1)}`;
  const e = `2001-${pad2(m2)}-${pad2(d2)}`;
  document.getElementById("startDate").value = s;
  document.getElementById("endDate").value = e;
  buildPlot();
}

async function init(){
  try{
    const [dataTxt, pctlTxt] = await Promise.all([
      safeFetchText(DATA_URL),
      safeFetchText(PCTL_URL)
    ]);

    DATA = parseCSV(dataTxt);
    PCTL = parseCSV(pctlTxt);

    const years = unique(DATA.map(r => Number(r["Year"]))).filter(x => Number.isFinite(x));
    const yearsSel = document.getElementById("years");
    yearsSel.innerHTML = "";
    for(const y of years){
      const opt = document.createElement("option");
      opt.value = y;
      opt.textContent = y;
      yearsSel.appendChild(opt);
    }
    setDefaultYears(years);

    ["metric","years","startDate","endDate","p10","p50","p90"].forEach(id => {
      document.getElementById(id).addEventListener("change", buildPlot);
    });

    document.getElementById("btnFull").addEventListener("click", () => setIntervalMD(1,1,12,31));
    document.getElementById("btnNovDec").addEventListener("click", () => setIntervalMD(11,1,12,31));
    document.getElementById("btnJJA").addEventListener("click", () => setIntervalMD(6,1,8,31));

    buildPlot();
  } catch(e){
    showError(String(e));
  }
}

init();
