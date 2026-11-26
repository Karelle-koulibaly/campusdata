"use strict";

// Zone de message commune : succès, attente et erreurs.
const message = document.querySelector("#message");
let currentDataset = null;
let followId = 0; // numéro du suivi en cours : un nouveau suivi (ou une suppression) arrête l'ancien

// Appeler l'API et renvoyer le JSON, ou lever une Error avec un message lisible.
async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Serveur injoignable : vérifiez que l'API est démarrée.");
  }
  if (response.status === 204) return null; // suppression : pas de corps
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null; // réponse non JSON (ex. page d'erreur de Nginx)
  }
  if (!response.ok) {
    let detail = body && body.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join(" ; "); // erreurs 422
    throw new Error(`Erreur ${response.status} : ${detail || response.statusText}`);
  }
  return body;
}

// Créer une cellule <td> avec du texte (jamais de HTML).
function cell(text) {
  const td = document.createElement("td");
  td.textContent = text ?? "-";
  return td;
}

// Afficher la liste des jeux. textContent : un nom contenant <b> reste du texte.
function renderDatasets(datasets) {
  const list = document.querySelector("#datasets");
  list.replaceChildren();
  if (datasets.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "Aucun jeu de données pour l'instant.";
    list.append(empty);
    return;
  }
  for (const dataset of datasets) {
    const item = document.createElement("li");
    const open = document.createElement("button");
    open.type = "button";
    open.textContent = `${dataset.name} (${dataset.measurement_count} mesures)`;
    open.addEventListener("click", () => openDataset(dataset));

    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Supprimer";
    remove.addEventListener("click", () => deleteDataset(dataset));

    item.append(open, " ", remove);
    list.append(item);
  }
}

async function loadDatasets() {
  const list = document.querySelector("#datasets");
  list.textContent = "Chargement…"; // état « chargement », visible dans la liste
  try {
    renderDatasets(await request("/api/datasets"));
  } catch (error) {
    list.textContent = ""; // état « erreur » : on n'affiche pas une fausse liste vide
    message.textContent = error.message;
  }
}

// Supprimer un jeu après confirmation. Annuler n'envoie aucune requête.
async function deleteDataset(dataset) {
  const ok = confirm(
    `Supprimer « ${dataset.name} » et ses ${dataset.measurement_count} mesures ?`,
  );
  if (!ok) return;
  try {
    await request(`/api/datasets/${dataset.id}`, { method: "DELETE" }); // 204 : pas de corps
    message.textContent = `Jeu « ${dataset.name} » supprimé.`;
    if (currentDataset && currentDataset.id === dataset.id) {
      followId++; // arrêter le suivi d'un dépôt de ce jeu
      currentDataset = null;
      document.querySelector("#dataset-detail").hidden = true;
    }
    await loadDatasets();
  } catch (error) {
    message.textContent = error.message;
  }
}

function openDataset(dataset) {
  currentDataset = dataset;
  document.querySelector("#dataset-detail").hidden = false;
  document.querySelector("#detail-title").textContent = dataset.name;
  document.querySelector("#report").replaceChildren();
  loadIngestions();
  loadStats();
}

// Afficher les dépôts du jeu ouvert, avec un bouton « Rapport » et « Relancer ».
async function loadIngestions() {
  if (!currentDataset) return; // aucun jeu ouvert (ex. il vient d'être supprimé)
  const body = document.querySelector("#ingestions");
  body.replaceChildren();
  let ingestions;
  try {
    ingestions = await request(`/api/datasets/${currentDataset.id}/ingestions`);
  } catch (error) {
    message.textContent = error.message;
    return;
  }
  if (ingestions.length === 0) {
    const row = document.createElement("tr");
    const td = cell("Aucun dépôt pour ce jeu.");
    td.colSpan = 6;
    row.append(td);
    body.append(row);
    return;
  }
  for (const ingestion of ingestions) {
    const row = document.createElement("tr");
    row.append(
      cell(ingestion.filename),
      cell(ingestion.status), // le statut est écrit en toutes lettres, pas seulement en couleur
      cell(ingestion.rows_accepted),
      cell(ingestion.rows_rejected),
      cell(ingestion.rows_duplicate),
    );
    const actions = document.createElement("td");
    const report = document.createElement("button");
    report.type = "button";
    report.textContent = "Rapport";
    report.addEventListener("click", () => showReport(ingestion));
    actions.append(report);
    if (ingestion.status === "failed") {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "Relancer";
      retry.addEventListener("click", () => retryIngestion(ingestion, retry));
      actions.append(" ", retry);
    }
    row.append(actions);
    body.append(row);
  }
}

// Rapport d'un dépôt : compteurs, message d'échec et lignes rejetées (20 au plus).
function showReport(ingestion) {
  const zone = document.querySelector("#report");
  zone.replaceChildren();
  const title = document.createElement("h4");
  title.textContent = `Rapport : ${ingestion.filename} (${ingestion.status})`;
  zone.append(title);
  if (ingestion.error_message) {
    const p = document.createElement("p");
    p.textContent = `Fichier refusé : ${ingestion.error_message}`;
    zone.append(p);
  }
  if (ingestion.errors.length === 0) {
    const p = document.createElement("p");
    p.textContent = "Aucune ligne rejetée.";
    zone.append(p);
    return;
  }
  const list = document.createElement("ul");
  for (const error of ingestion.errors) {
    const item = document.createElement("li");
    item.textContent = `Ligne ${error.line} : ${error.reason}`;
    list.append(item);
  }
  zone.append(list);
  if (ingestion.rows_rejected > ingestion.errors.length) {
    const more = document.createElement("p");
    more.textContent = `… et ${ingestion.rows_rejected - ingestion.errors.length} autres lignes rejetées.`;
    zone.append(more);
  }
}

// Relancer un dépôt failed : il repasse à pending, puis on suit son traitement.
async function retryIngestion(ingestion, button) {
  button.disabled = true;
  try {
    await request(`/api/ingestions/${ingestion.id}/retry`, { method: "POST" });
    message.textContent = `Dépôt « ${ingestion.filename} » relancé.`;
    await loadIngestions();
    await followIngestion(ingestion.id);
    await loadIngestions();
  } catch (error) {
    message.textContent = error.message; // ex. 409 si le dépôt n'est plus failed
    button.disabled = false;
  }
}

// Convertir la valeur d'un champ datetime-local (heure locale) en date ISO avec fuseau.
function toIso(value) {
  return value ? new Date(value).toISOString() : null;
}

// Tableau des indicateurs, avec les filtres salle et période.
async function loadStats() {
  if (!currentDataset) return;
  const body = document.querySelector("#stats");
  body.replaceChildren();
  const params = new URLSearchParams();
  const room = document.querySelector("#room").value.trim();
  const from = toIso(document.querySelector("#from").value);
  const to = toIso(document.querySelector("#to").value);
  if (room) params.set("room", room);
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  let stats;
  try {
    stats = await request(`/api/datasets/${currentDataset.id}/stats?${params}`);
  } catch (error) {
    message.textContent = error.message; // ex. 422 si la période est inversée
    return;
  }
  if (stats.rooms.length === 0) {
    const row = document.createElement("tr");
    const td = cell("Aucune mesure ne correspond à ce filtre.");
    td.colSpan = 8;
    row.append(td);
    body.append(row);
    return;
  }
  for (const r of stats.rooms) {
    const row = document.createElement("tr");
    row.append(
      cell(r.room),
      cell(r.measurements),
      cell(r.co2_avg),
      cell(r.co2_min),
      cell(r.co2_max),
      cell(r.temperature_avg),
      cell(r.humidity_avg),
      cell(new Date(r.last_measured_at).toLocaleString("fr-FR")),
    );
    body.append(row);
  }
}

document.querySelector("#stats-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadStats();
});

document.querySelector("#dataset-form").addEventListener("submit", async (event) => {
  event.preventDefault(); // ne pas recharger la page
  const button = event.submitter;
  button.disabled = true; // éviter un double clic
  try {
    const dataset = await request("/api/datasets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.querySelector("#name").value,
        owner: document.querySelector("#owner").value,
      }),
    });
    message.textContent = `Jeu « ${dataset.name} » créé.`;
    event.target.reset();
    await loadDatasets();
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false; // toujours réactiver, même après une erreur
  }
});

// Interroger le dépôt toutes les 2 s, au plus 60 fois, jusqu'à succeeded ou failed.
async function followIngestion(id) {
  const mine = ++followId;
  const status = document.querySelector("#ingestion-status");
  for (let attempt = 0; attempt < 60; attempt++) {
    if (mine !== followId) return null; // un autre suivi a pris le relais
    const ingestion = await request(`/api/ingestions/${id}`);
    status.textContent = `Statut : ${ingestion.status}`;
    if (ingestion.status === "succeeded") {
      status.textContent += ` - ${ingestion.rows_accepted} acceptées, ${ingestion.rows_rejected} rejetées, ${ingestion.rows_duplicate} doublons`;
      return ingestion;
    }
    if (ingestion.status === "failed") {
      status.textContent += ` - ${ingestion.error_message}`;
      return ingestion;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  status.textContent += " - pas encore traité (le worker tourne-t-il ?)";
}

document.querySelector("#upload").addEventListener("click", async (event) => {
  const file = document.querySelector("#file").files[0];
  if (!file || !currentDataset) {
    message.textContent = "Choisissez d'abord un jeu et un fichier.";
    return;
  }
  event.target.disabled = true;
  document.querySelector("#ingestion-status").textContent = "Envoi du fichier…";
  try {
    const url = `/api/datasets/${currentDataset.id}/ingestions?filename=${encodeURIComponent(file.name)}`;
    // Fixer le type : sinon certains systèmes envoient un type vide (refusé en 415).
    const ingestion = await request(url, {
      method: "POST",
      headers: { "Content-Type": "text/csv" },
      body: file,
    });
    message.textContent = "Fichier reçu (202) : traitement en attente.";
    await loadIngestions(); // le nouveau dépôt apparaît tout de suite en pending
    await followIngestion(ingestion.id);
    await loadIngestions();
    await loadStats();
    await loadDatasets();
  } catch (error) {
    message.textContent = error.message;
  } finally {
    event.target.disabled = false;
  }
});

async function loadVersion() {
  try {
    document.querySelector("#version").textContent = (await request("/api/version")).version;
  } catch {
    document.querySelector("#version").textContent = "inconnue";
  }
}

loadDatasets();
loadVersion();