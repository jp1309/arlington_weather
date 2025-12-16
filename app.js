const DATA_URL = "data/arlington_daily.csv";
const PCTL_URL = "data/climatology_doy365_percentiles.csv";

async function loadCSV(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(url);
  return r.text();
}

function parseCSV(t){
  const [h,...r]=t.trim().split(/\r?\n/);
  const H=h.split(",");
  return r.map(l=>{
    const o={};
    l.split(",").forEach((v,i)=>o[H[i]]=v);
    return o;
  });
}

function buildPlot(DATA,PCTL){
  const metric=document.getElementById("metric").value;
  const years=[...document.getElementById("years").options].filter(o=>o.selected).map(o=>o.value);
  const traces=[];

  if(document.getElementById("p10").checked)
    traces.push({x:PCTL.map(d=>d.DOY_365),y:PCTL.map(d=>d[metric+"_p10"]),name:"p10",mode:"lines",line:{dash:"dot",width:1}});
  if(document.getElementById("p50").checked)
    traces.push({x:PCTL.map(d=>d.DOY_365),y:PCTL.map(d=>d[metric+"_p50"]),name:"p50",mode:"lines",line:{dash:"dot",width:1.5}});
  if(document.getElementById("p90").checked)
    traces.push({x:PCTL.map(d=>d.DOY_365),y:PCTL.map(d=>d[metric+"_p90"]),name:"p90",mode:"lines",line:{dash:"dot",width:1}});

  years.forEach(y=>{
    const r=DATA.filter(d=>d.Year===y);
    traces.push({
      x:r.map(d=>d.DOY_365),
      y:r.map(d=>d[metric]),
      name:y,
      mode:"lines",
      line:{width:y==="2025"?4:2}
    });
  });

  Plotly.newPlot("plot",traces,{xaxis:{title:"Día del año"},yaxis:{title:metric},legend:{orientation:"h"}});
}

async function init(){
  const DATA=parseCSV(await loadCSV(DATA_URL));
  const PCTL=parseCSV(await loadCSV(PCTL_URL));

  const ys=[...new Set(DATA.map(d=>d.Year))].sort();
  const sel=document.getElementById("years");
  ys.forEach(y=>{
    const o=document.createElement("option");
    o.value=y;o.textContent=y;
    if(y>=ys[ys.length-3]) o.selected=true;
    sel.appendChild(o);
  });

  ["metric","years","p10","p50","p90"].forEach(id=>document.getElementById(id).addEventListener("change",()=>buildPlot(DATA,PCTL)));
  buildPlot(DATA,PCTL);
}
init();
