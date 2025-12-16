
const DATA_URL = "data/arlington_daily.csv";
const CLIM_URL = "data/climatology_doy365_mean.csv";

function parseCSV(text){
  const lines = text.trim().split(/\r?\n/);
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
  const mm = parts[1], dd = parts[2];
  return mdToDoy(mm, dd);
}

function clamp(x, lo, hi){ return Math.max(lo, Math.min(hi, x)); }

let DATA = [];
let CLIM = [];

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

function getMetricMeta(metric){
  const meta = {
    "Tavg_C": {title:"Temperatura media", unit:"°C"},
    "Tmin_C": {title:"Temperatura mínima", unit:"°C"},
    "Tmax_C": {title:"Temperatura máxima", unit:"°C"},
    "PRCP_mm": {title:"Precipitación", unit:"mm"},
    "SNOW_mm": {title:"Nieve", unit:"mm"},
    "SNWD_mm": {title:"Profundidad de nieve", unit:"mm"}
  };
  return meta[metric] || {title: metric, unit:""};
}

function computeTickMarks(startDoy, endDoy){
  const monthStarts = [1,32,60,91,121,152,182,213,244,274,305,335];
  const ticks = monthStarts.filter(v => v >= startDoy && v <= endDoy);
  if(!ticks.includes(startDoy)) ticks.unshift(startDoy);
  if(!ticks.includes(endDoy)) ticks.push(endDoy);
  const uniq = Array.from(new Set(ticks)).sort((a,b)=>a-b);
  return { tickvals: uniq, ticktext: uniq.map(doyToLabel) };
}

function buildPlot(){
  const metric = document.getElementById("metric").value;
  const showClim = document.getElementById("showClim").checked;
  const years = getSelectedYears();

  const startVal = document.getElementById("startDate").value;
  const endVal = document.getElementById("endDate").value;

  let startDoy = dateInputToDoy(startVal);
  let endDoy = dateInputToDoy(endVal);
  if(endDoy < startDoy){
    const tmp = startDoy; startDoy = endDoy; endDoy = tmp;
  }
  startDoy = clamp(startDoy, 1, 365);
  endDoy = clamp(endDoy, 1, 365);

  const traces = [];
  const meta = getMetricMeta(metric);

  if(showClim && ["Tmin_C","Tmax_C","Tavg_C","PRCP_mm"].includes(metric)){
    const filtered = CLIM.filter(r => {
      const d = toNum(r["DOY_365"]);
      return d !== null && d >= startDoy && d <= endDoy;
    });
    const x = filtered.map(r => toNum(r["DOY_365"]));
    const y = filtered.map(r => toNum(r[metric]));
    traces.push({
      x, y,
      name: "Climatología (promedio)",
      mode: "lines",
      line: { width: 3 },
      customdata: x.map(doyToLabel),
      hovertemplate: "%{customdata}<br>" + meta.title + ": %{y} " + meta.unit + "<extra></extra>"
    });
  }

  for(const yr of years){
    const rows = DATA.filter(r => Number(r["Year"]) === yr);
    const filtered = rows.filter(r => {
      const d = toNum(r["DOY_365"]);
      return d !== null && d >= startDoy && d <= endDoy;
    });
    const x = filtered.map(r => toNum(r["DOY_365"]));
    const y = filtered.map(r => toNum(r[metric]));
    traces.push({
      x, y,
      name: String(yr),
      mode: "lines",
      customdata: x.map(doyToLabel),
      hovertemplate: "Año " + yr + "<br>%{customdata}<br>" + meta.title + ": %{y} " + meta.unit + "<extra></extra>"
    });
  }

  const {tickvals, ticktext} = computeTickMarks(startDoy, endDoy);

  const title = `Comparación por día del año. ${meta.title} (${meta.unit})`;
  const layout = {
    margin: {l:70, r:20, t:45, b:65},
    title: {text: title, x:0},
    xaxis: {
      title: "Día y mes",
      tickmode: "array",
      tickvals: tickvals,
      ticktext: ticktext,
      range: [startDoy, endDoy]
    },
    yaxis: {title: `${meta.title} (${meta.unit})`},
    legend: {orientation:"h", y:-0.22},
    hovermode: "closest",
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {color:"#e5e7eb"}
  };

  Plotly.newPlot("plot", traces, layout, {responsive:true, displaylogo:false});

  document.getElementById("footnote").textContent =
    "Fuente: NOAA GHCN-Daily. Estación USW00013743 (Reagan National). Eje X estandarizado a 365 días (Feb 29 excluido).";
}

function setIntervalMD(m1, d1, m2, d2){
  const s = `2001-${pad2(m1)}-${pad2(d1)}`;
  const e = `2001-${pad2(m2)}-${pad2(d2)}`;
  document.getElementById("startDate").value = s;
  document.getElementById("endDate").value = e;
  buildPlot();
}

async function init(){
  const [dataTxt, climTxt] = await Promise.all([
    fetch(DATA_URL).then(r => r.text()),
    fetch(CLIM_URL).then(r => r.text())
  ]);

  DATA = parseCSV(dataTxt);
  CLIM = parseCSV(climTxt);

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

  ["metric","years","startDate","endDate","showClim"].forEach(id => {
    document.getElementById(id).addEventListener("change", buildPlot);
  });

  document.getElementById("btnFull").addEventListener("click", () => setIntervalMD(1,1,12,31));
  document.getElementById("btnNovDec").addEventListener("click", () => setIntervalMD(11,1,12,31));
  document.getElementById("btnJJA").addEventListener("click", () => setIntervalMD(6,1,8,31));

  buildPlot();
}

init();
