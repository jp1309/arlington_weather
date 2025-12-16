
const DATA_URL = "data/arlington_daily.csv";
const CLIM_URL = "data/climatology_doy365_mean.csv";

function parseCSV(text){
  const lines = text.trim().split(/\r?\n/);
  const headers = lines[0].split(",");
  const rows = [];
  for(let i=1;i<lines.length;i++){
    const cols = lines[i].split(",");
    const obj = {};
    headers.forEach((h, idx) => obj[h] = cols[idx] === "" ? null : cols[idx]);
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
  // selecciona los últimos 3 años por defecto
  const sel = document.getElementById("years");
  const last = years.slice(-3);
  for(const opt of sel.options){
    opt.selected = last.includes(Number(opt.value));
  }
}

function buildPlot(){
  const metric = document.getElementById("metric").value;
  const doyMode = document.getElementById("doyMode").value; // "365" o "366"
  const showClim = document.getElementById("showClim").checked;
  const showImputed = document.getElementById("showImputed").checked;

  const years = getSelectedYears();
  const xKey = doyMode === "365" ? "DOY_365" : "DOY_366";

  const traces = [];

  // climatología (solo doy365 porque la precomputamos así)
  if(showClim && doyMode === "365" && ["Tmin_C","Tmax_C","Tavg_C","PRCP_mm"].includes(metric)){
    const x = CLIM.map(r => toNum(r["DOY_365"]));
    const y = CLIM.map(r => toNum(r[metric]));
    traces.push({
      x, y,
      name: "Climatología (promedio)",
      mode: "lines",
      line: { width: 3 },
      hovertemplate: "DOY %{x}<br>" + metric + " %{y}<extra></extra>"
    });
  }

  // series por año
  for(const y of years){
    const rows = DATA.filter(r => Number(r["Year"]) === y);
    const x = rows.map(r => toNum(r[xKey]));
    const yv = rows.map(r => toNum(r[metric]));

    traces.push({
      x, y: yv,
      name: String(y),
      mode: "lines",
      hovertemplate: "Año " + y + "<br>DOY %{x}<br>" + metric + " %{y}<extra></extra>"
    });

    // marcar imputados para Tmin/Tmax/Tavg (cuando depende de Tmin/Tmax)
    if(showImputed && ["Tmin_C","Tmax_C","Tavg_C"].includes(metric)){
      const xImp = [];
      const yImp = [];
      for(const r of rows){
        const imp = toNum(r["ImputedTempFlag"]);
        const xv = toNum(r[xKey]);
        const vv = toNum(r[metric]);
        if(imp === 1 && xv !== null && vv !== null){
          xImp.push(xv);
          yImp.push(vv);
        }
      }
      if(xImp.length > 0){
        traces.push({
          x: xImp,
          y: yImp,
          name: `${y} (imputado)`,
          mode: "markers",
          marker: { size: 7, symbol: "circle-open" },
          hovertemplate: "Año " + y + "<br>Imputado<br>DOY %{x}<br>" + metric + " %{y}<extra></extra>",
          showlegend: false
        });
      }
    }
  }

  const titleMap = {
    "Tavg_C":"Tavg (°C)",
    "Tmin_C":"Tmin (°C)",
    "Tmax_C":"Tmax (°C)",
    "PRCP_mm":"Precipitación (mm)",
    "SNOW_mm":"Nieve (mm)",
    "SNWD_mm":"Profundidad de nieve (mm)"
  };

  const layout = {
    margin: {l:60, r:20, t:40, b:55},
    title: {text: `Comparación por día del año. ${titleMap[metric] || metric}`, x:0},
    xaxis: {title: doyMode === "365" ? "Día del año (1–365)" : "Día del año (1–366)"},
    yaxis: {title: titleMap[metric] || metric},
    legend: {orientation:"h", y:-0.22},
    hovermode: "closest",
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {color:"#e5e7eb"}
  };

  const config = {responsive:true, displaylogo:false};

  Plotly.newPlot("plot", traces, layout, config);

  const foot = document.getElementById("footnote");
  foot.textContent = "Fuente: NOAA GHCN-Daily. Estación USW00013743 (Reagan National). Dashboard estático para GitHub Pages.";
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

  // listeners
  ["metric","years","doyMode","showClim","showImputed"].forEach(id => {
    document.getElementById(id).addEventListener("change", buildPlot);
  });

  buildPlot();
}

init();
