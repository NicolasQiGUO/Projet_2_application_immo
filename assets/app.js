const ORLEANS_CENTER = [47.9029, 1.9093];

const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const dateFmt = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "long", year: "numeric" });

let map;
let quartiersLayer;
let ventesLayer;
let quartiersGeojson;
let ventes = [];
let currentQuartier = "__all__";

async function loadJson(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`Impossible de charger ${path} (${res.status})`);
  return res.json();
}

function markerForVente(v) {
  const marker = L.circleMarker([v.lat, v.lon], {
    radius: 7,
    color: "#2f6b4f",
    weight: 1.5,
    fillColor: "#5aa480",
    fillOpacity: 0.85,
  });

  const prixM2 = v.prix_m2 ? `${eur.format(v.prix_m2)}/m²` : "prix/m² inconnu";
  const adresse = v.adresse || "Adresse non précisée";
  marker.bindPopup(`
    <b>${v.type_local}</b> — ${adresse}<br/>
    ${dateFmt.format(new Date(v.date))}<br/>
    Prix : <b>${eur.format(v.prix)}</b><br/>
    Surface : ${v.surface_m2} m² (${prixM2})
    ${v.pieces ? `<br/>Pièces : ${v.pieces}` : ""}
  `);
  return marker;
}

function renderQuartierList(meta) {
  const listEl = document.getElementById("quartier-list");
  listEl.innerHTML = "";

  const names = Object.keys(meta.ventes_par_quartier || {}).sort((a, b) => a.localeCompare(b, "fr"));
  for (const name of names) {
    const btn = document.createElement("button");
    btn.className = "quartier-item";
    btn.dataset.quartier = name;
    btn.innerHTML = `<span class="quartier-nom">${name}</span><span class="quartier-count">${meta.ventes_par_quartier[name]}</span>`;
    btn.addEventListener("click", () => selectQuartier(name));
    listEl.appendChild(btn);
  }

  document.getElementById("count-all").textContent = meta.nb_ventes;
  document.querySelector('[data-quartier="__all__"]').addEventListener("click", () => selectQuartier("__all__"));
}

function setActiveButton(quartier) {
  document.querySelectorAll(".quartier-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.quartier === quartier);
  });
}

function selectQuartier(quartier) {
  currentQuartier = quartier;
  setActiveButton(quartier);

  ventesLayer.clearLayers();
  const filtered = quartier === "__all__" ? ventes : ventes.filter((v) => v.quartier === quartier);
  filtered.forEach((v) => ventesLayer.addLayer(markerForVente(v)));

  if (quartier === "__all__") {
    quartiersLayer.setStyle({ weight: 1, color: "#9aa39c", fillOpacity: 0.03 });
    map.fitBounds(quartiersLayer.getBounds(), { padding: [16, 16] });
  } else {
    quartiersLayer.eachLayer((layer) => {
      const isSelected = layer.feature.properties.__nom === quartier;
      layer.setStyle({
        weight: isSelected ? 3 : 1,
        color: isSelected ? "#2f6b4f" : "#9aa39c",
        fillOpacity: isSelected ? 0.08 : 0.02,
      });
      if (isSelected) {
        map.fitBounds(layer.getBounds(), { padding: [24, 24] });
      }
    });
  }
}

function quartierName(props) {
  for (const key of ["nom", "libelle", "lib_quartier", "quartier", "name", "nom_quartier"]) {
    if (props[key]) return String(props[key]);
  }
  return "Quartier inconnu";
}

async function init() {
  map = L.map("map").setView(ORLEANS_CENTER, 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);

  ventesLayer = L.layerGroup().addTo(map);

  try {
    const [meta, quartiers, ventesData] = await Promise.all([
      loadJson("data/meta.json"),
      loadJson("data/quartiers.geojson"),
      loadJson("data/ventes.json"),
    ]);

    ventes = ventesData;
    quartiersGeojson = quartiers;

    quartiersLayer = L.geoJSON(quartiers, {
      style: { weight: 1, color: "#9aa39c", fillOpacity: 0.03 },
      onEachFeature: (feature, layer) => {
        feature.properties.__nom = quartierName(feature.properties);
        layer.feature = feature;
        layer.on("click", () => selectQuartier(feature.properties.__nom));
      },
    }).addTo(map);

    renderQuartierList(meta);

    const periodeEl = document.getElementById("periode");
    if (meta.periode_debut && meta.periode_fin) {
      periodeEl.textContent = `${meta.nb_ventes} ventes trouvées, du ${dateFmt.format(new Date(meta.periode_debut))} au ${dateFmt.format(new Date(meta.periode_fin))} — données mises à jour le ${dateFmt.format(new Date(meta.generated_at))}`;
    } else {
      periodeEl.textContent = "Aucune vente sur la période disponible.";
    }
    document.getElementById("source-info").textContent =
      `Sources : ${meta.source_ventes} ; ${meta.source_quartiers}`;

    selectQuartier("__all__");

    if (!ventes.length) {
      document.getElementById("empty-state").hidden = false;
    }
  } catch (err) {
    console.error(err);
    document.getElementById("periode").textContent = "Données indisponibles pour le moment.";
    document.getElementById("empty-state").hidden = false;
  }
}

init();
