// === Percentiles shaded band + dotted gray lines ===
// This file replaces the previous app.js

function addPercentiles(figData, clim, xvals, show) {
  if (!show.p10 && !show.p50 && !show.p90) return;

  const gray = 'rgba(180,180,180,0.85)';
  const band = 'rgba(180,180,180,0.18)';

  if (show.p10) {
    figData.push({
      x: xvals,
      y: clim.p10,
      mode: 'lines',
      name: 'p10',
      line: { color: gray, width: 1, dash: 'dot' },
      hoverinfo: 'skip'
    });
  }

  if (show.p90) {
    figData.push({
      x: xvals,
      y: clim.p90,
      mode: 'lines',
      name: 'p90',
      line: { color: gray, width: 1, dash: 'dot' },
      fill: show.p10 ? 'tonexty' : 'none',
      fillcolor: band,
      hoverinfo: 'skip'
    });
  }

  if (show.p50) {
    figData.push({
      x: xvals,
      y: clim.p50,
      mode: 'lines',
      name: 'p50 (mediana)',
      line: { color: 'rgba(160,160,160,0.9)', width: 1, dash: 'dot' },
      hoverinfo: 'skip'
    });
  }
}