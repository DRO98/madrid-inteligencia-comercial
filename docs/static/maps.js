/**
 * Leaflet: mapas de candidatos y calor. Expone revealMapResults() para mostrar resultados tras el análisis.
 */
(function () {
  let mapReco, mapHeat, recoLayer, heatLayer;
  let recoReady = false;
  let heatReady = false;

  const tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap',
  });

  /** Vista regional al cargar candidatos: centro Comunidad de Madrid, zoom amplio. */
  const RECO_REGION_CENTER = [40.45, -3.65];
  const RECO_REGION_ZOOM = 8;

  window.initMaps = function () {
    const elReco = document.getElementById('map-reco');
    const elHeat = document.getElementById('map-heat');
    if (!elReco || !elHeat) return;

    mapReco = L.map('map-reco').setView(RECO_REGION_CENTER, RECO_REGION_ZOOM);
    tiles.addTo(mapReco);
    recoLayer = L.layerGroup().addTo(mapReco);

    mapHeat = L.map('map-heat').setView([40.4168, -3.7038], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap',
    }).addTo(mapHeat);

    window.mapReco = mapReco;
    window.mapHeat = mapHeat;

    setTimeout(function () {
      if (mapReco) mapReco.invalidateSize();
      if (mapHeat) mapHeat.invalidateSize();
    }, 400);
    recoReady = true;
    heatReady = true;
  };

  window.refreshMapSizes = function () {
    try {
      if (mapReco) mapReco.invalidateSize(true);
      if (mapHeat) mapHeat.invalidateSize(true);
    } catch (e) {
      console.warn(e);
    }
  };

  window.revealMapResults = function () {
    var section = document.getElementById('maps-results');
    if (section) {
      section.classList.remove('maps-results--hidden');
      section.setAttribute('aria-hidden', 'false');
    }
    setTimeout(function () {
      window.refreshMapSizes();
    }, 250);
    setTimeout(function () {
      if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  window._iconoBuscarLeaflet = null;
  window.iconoBuscar = function () {
    if (!window._iconoBuscarLeaflet) {
      window._iconoBuscarLeaflet = L.divIcon({
        className: 'marker-buscar-emoji',
        html: '<div class="marker-buscar-inner" aria-hidden="true">🔍</div>',
        iconSize: [32, 32],
        iconAnchor: [16, 16],
        popupAnchor: [0, -14],
      });
    }
    return window._iconoBuscarLeaflet;
  };

  window.updateRecoMarkers = function (jsonStr) {
    if (!recoReady || !mapReco || !recoLayer) return;
    try {
      recoLayer.clearLayers();
      const items = JSON.parse(jsonStr);
      if (!items.length) {
        mapReco.setView(RECO_REGION_CENTER, RECO_REGION_ZOOM);
        var emptyP = document.getElementById('local-detail-panel');
        if (emptyP) {
          emptyP.innerHTML =
            '<p class="detail-placeholder muted">Haz clic en una lupa del mapa para ver aquí la ficha completa del local.</p>';
        }
        return;
      }
      const ic = window.iconoBuscar();
      items.forEach(function (it) {
        var mk = L.marker([it.lat, it.lon], { icon: ic });
        mk.bindPopup(it.popup_mini || '', { maxWidth: 300, className: 'popup-mini-wrap' });
        mk.on('click', function () {
          var panel = document.getElementById('local-detail-panel');
          if (panel && it.detail_html) {
            panel.innerHTML = '<div class="local-ficha-panel">' + it.detail_html + '</div>';
          }
        });
        mk.addTo(recoLayer);
      });
      mapReco.setView(RECO_REGION_CENTER, RECO_REGION_ZOOM);
      mapReco.invalidateSize(true);
    } catch (e) {
      console.error(e);
    }
  };

  window.updateHeatmap = function (jsonStr) {
    if (!heatReady || !mapHeat) return;
    try {
      if (heatLayer) {
        mapHeat.removeLayer(heatLayer);
        heatLayer = null;
      }
      const pts = JSON.parse(jsonStr);
      if (!pts.length) return;
      heatLayer = L.heatLayer(pts, { radius: 12, blur: 15, maxZoom: 13 }).addTo(mapHeat);
      mapHeat.invalidateSize(true);
    } catch (e) {
      console.error(e);
    }
  };

  window.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('map-reco')) {
      window.initMaps();
    }
  });
})();
