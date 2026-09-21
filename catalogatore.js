/*
 * catalogatore.js — schermata del «Caricamento automatico» dei libri.
 *
 * Lo usano sia il Gestore Sito sia il Gestore Biblioteca: il file e' identico in
 *     Gestore sito/evangelicimaranello/catalogatore.js
 *     Gestore biblioteca/sorgente/web/catalogatore.js
 * Se lo modifichi in uno dei due posti, copialo anche nell'altro.
 *
 * Parla con i metodi catalogo_* di catalogatore.py (window.pywebview.api).
 * Si apre con:
 *     Catalogatore.apri({
 *        onPubblicato: esito => { ... },   // esito.voci = libri aggiunti
 *        testoPubblica: "Aggiungi al sito" // facoltativo
 *     });
 * Porta con se' il suo stile: prende i colori dal programma che lo ospita.
 */
(function () {
  "use strict";

  const STILE = `
  .k-ov{--k-bg:var(--bg,#101014);--k-pan:var(--panel,var(--surface,rgba(255,255,255,.05)));
    --k-pan2:var(--panel-alt,var(--surface2,rgba(255,255,255,.09)));--k-bor:var(--border,rgba(255,255,255,.14));
    --k-txt:var(--text,var(--white,#f2f2f2));--k-dim:var(--text-dim,var(--muted,#9a9aa8));
    --k-acc:var(--accent,var(--gold,#8b6bff));--k-ok:var(--green,#4fd18b);--k-warn:var(--amber,#ffc861);
    --k-bad:var(--danger,var(--red,#e97f7f));
    position:fixed;inset:0;z-index:9000;background:var(--k-bg);color:var(--k-txt);
    display:none;flex-direction:column;font-family:inherit;font-size:14px;user-select:none}
  .k-ov.k-aperto{display:flex}
  .k-ov *{box-sizing:border-box}
  .k-ov input,.k-ov textarea,.k-ov select{user-select:text;font-family:inherit;font-size:13.5px;color:var(--k-txt);
    background:rgba(255,255,255,.05);border:1px solid var(--k-bor);border-radius:8px;padding:7px 9px;width:100%;outline:none}
  .k-ov select option{background:#222;color:#eee}
  .k-ov input:focus,.k-ov textarea:focus,.k-ov select:focus{border-color:var(--k-acc)}
  .k-ov textarea{resize:vertical;line-height:1.45}
  .k-ov input[type=checkbox]{width:auto;accent-color:var(--k-acc)}
  .k-top{display:flex;align-items:center;gap:12px;padding:14px 22px;border-bottom:1px solid var(--k-bor);flex-shrink:0}
  .k-top h2{margin:0;font-size:19px;font-weight:700;flex:1}
  .k-top .k-sub{font-size:12.5px;color:var(--k-dim);font-weight:400;margin-left:8px}
  .k-corpo{flex:1;overflow:auto;padding:20px 22px 40px}
  .k-btn{border:1px solid var(--k-bor);background:rgba(255,255,255,.06);color:var(--k-txt);border-radius:9px;
    padding:8px 14px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;white-space:nowrap}
  .k-btn:hover{border-color:var(--k-acc);background:rgba(255,255,255,.1)}
  .k-btn:disabled{opacity:.45;cursor:default}
  .k-pri{background:var(--k-acc);border-color:var(--k-acc);color:#140c05}
  .k-pri:hover{filter:brightness(1.12);background:var(--k-acc)}
  .k-sm{padding:4px 9px;font-size:12px;border-radius:7px}
  .k-centro{max-width:620px;margin:40px auto;text-align:center;line-height:1.6}
  .k-centro h3{font-size:22px;margin:0 0 10px}
  .k-centro p{color:var(--k-dim);margin:8px 0}
  .k-grande{font-size:48px;line-height:1;margin-bottom:12px}
  .k-riquadro{background:var(--k-pan);border:1px solid var(--k-bor);border-radius:12px;padding:14px 16px;text-align:left;margin:18px 0}
  .k-riquadro.k-warn{border-color:var(--k-warn)}
  .k-passi{margin:6px 0 0 0;padding-left:20px;color:var(--k-dim);font-size:13px}
  .k-barra{height:10px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;margin:18px 0 10px}
  .k-barra>div{height:100%;background:var(--k-acc);width:0;transition:width .3s}
  .k-schede{display:flex;flex-direction:column;gap:14px;max-width:1180px;margin:0 auto}
  .k-scheda{display:grid;grid-template-columns:auto 1fr;gap:16px;background:var(--k-pan);border:1px solid var(--k-bor);
    border-radius:14px;padding:14px}
  .k-scheda.k-escluso{opacity:.5}
  .k-scheda.k-escluso:hover{opacity:.85}
  .k-foto{display:flex;gap:10px}
  .k-faccia{display:flex;flex-direction:column;align-items:center;gap:5px;width:150px}
  .k-faccia .k-img{width:150px;height:210px;border-radius:8px;background:rgba(255,255,255,.04);border:1px solid var(--k-bor);
    display:flex;align-items:center;justify-content:center;overflow:hidden;color:var(--k-dim);font-size:12px;text-align:center}
  .k-faccia img{max-width:100%;max-height:100%;object-fit:contain;cursor:zoom-in}
  .k-faccia .k-lab{font-size:11px;letter-spacing:.8px;text-transform:uppercase;color:var(--k-dim)}
  .k-rig{display:flex;gap:5px;flex-wrap:wrap;justify-content:center}
  .k-dati{display:flex;flex-direction:column;gap:9px;min-width:0}
  .k-testa{display:flex;gap:10px;align-items:center}
  .k-testa .k-tit{font-size:16px;font-weight:700}
  .k-griglia{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
  .k-campo{display:flex;flex-direction:column;gap:3px}
  .k-campo>span{font-size:11px;color:var(--k-dim);letter-spacing:.3px}
  .k-campo.k-l2{grid-column:span 2}
  .k-avvisi{display:flex;flex-wrap:wrap;gap:6px}
  .k-chip{font-size:12px;border-radius:99px;padding:3px 10px;background:rgba(255,255,255,.07);border:1px solid var(--k-bor)}
  .k-chip.cattolico,.k-chip.doppione{border-color:var(--k-bad);color:var(--k-bad)}
  .k-chip.retro,.k-chip.titolo,.k-chip.verso,.k-chip.ocr{border-color:var(--k-warn);color:var(--k-warn)}
  .k-fonte{font-size:11.5px;color:var(--k-dim)}
  .k-sugg{display:flex;flex-direction:column;gap:5px}
  .k-sugg button{text-align:left;white-space:normal;font-weight:400}
  .k-azioni{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
  .k-filtri{display:flex;gap:6px;align-items:center;max-width:1180px;margin:0 auto 14px;flex-wrap:wrap}
  .k-filtri .k-btn.k-att{border-color:var(--k-acc);color:var(--k-acc)}
  .k-filtri .k-spazio{flex:1}
  .k-zoom{position:fixed;inset:0;z-index:9500;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;cursor:zoom-out}
  .k-zoom img{max-width:92vw;max-height:92vh;border-radius:8px}
  details.k-bio summary{cursor:pointer;font-size:12px;color:var(--k-dim)}
  details.k-bio textarea{margin-top:5px}
  .k-err{color:var(--k-bad)}
  @media (max-width:900px){.k-scheda{grid-template-columns:1fr}.k-griglia{grid-template-columns:repeat(2,minmax(0,1fr))}}
  `;

  let ov = null;            // l'overlay
  let opz = {};             // opzioni di chi apre
  let R = null;             // risultato dell'analisi {libri, foto, generi, avvisi}
  let filtro = "tutti";
  let timer = null;
  const mini = {};          // fid -> data URI

  /* ── utilità ─────────────────────────────────────────────── */
  async function chiama(nome, ...args) {
    const a = window.pywebview && window.pywebview.api;
    if (!a || !a[nome]) throw new Error("funzione " + nome + " non disponibile");
    const r = await a[nome](...args);
    return typeof r === "string" ? JSON.parse(r) : r;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function $(sel) { return ov.querySelector(sel); }
  function libro(id) { return R.libri.find(l => l.id === id); }

  function crea() {
    if (ov) return;
    const st = document.createElement("style");
    st.textContent = STILE;
    document.head.appendChild(st);
    ov = document.createElement("div");
    ov.className = "k-ov";
    ov.innerHTML = `
      <div class="k-top">
        <h2>⚡ Caricamento automatico <span class="k-sub" id="kSub"></span></h2>
        <span id="kTopAzioni" class="k-azioni"></span>
        <button class="k-btn" id="kChiudi">✕ Chiudi</button>
      </div>
      <div class="k-corpo" id="kCorpo"></div>`;
    document.body.appendChild(ov);
    $("#kChiudi").onclick = chiudi;
    // i campi scrivono direttamente nel libro
    ov.addEventListener("input", e => {
      const el = e.target, id = el.dataset.libro, campo = el.dataset.campo;
      if (!id || !campo) return;
      const l = libro(id);
      if (!l) return;
      l[campo] = el.type === "checkbox" ? el.checked : el.value;
      if (campo === "includi") { ridisegnaScheda(id); aggiornaTop(); }
      if (campo === "titolo") {
        const t = ov.querySelector(`[data-tit="${id}"]`);
        if (t) t.textContent = el.value || "(senza titolo)";
      }
    });
    ov.addEventListener("change", e => {
      if (e.target.dataset && e.target.dataset.campo === "includi") return;
      if (e.target.dataset && e.target.dataset.campo) aggiornaTop();
    });
  }

  function chiudi() {
    if (R && R.libri && R.libri.some(l => l.includi) && !R.pubblicato &&
        !confirm("Chiudere? I libri analizzati non sono ancora stati aggiunti al sito.")) return;
    clearInterval(timer);
    chiama("catalogo_annulla").catch(() => {});
    ov.classList.remove("k-aperto");
  }

  /* ── 1. inizio ───────────────────────────────────────────── */
  async function apri(o) {
    opz = o || {};
    crea();
    R = null;
    ov.classList.add("k-aperto");
    $("#kSub").textContent = "";
    $("#kTopAzioni").innerHTML = "";
    $("#kCorpo").innerHTML = '<div class="k-centro"><p>Controllo gli strumenti…</p></div>';
    let d = {};
    try { d = await chiama("catalogo_disponibile"); } catch (e) { d = { ok: false, errore: e.message }; }
    schermataInizio(d);
  }

  function schermataInizio(d) {
    let ocr = "";
    if (d.ok === false) {
      ocr = `<div class="k-riquadro k-warn"><b>Non disponibile:</b> ${esc(d.errore || "manca Pillow, rilancia build_exe.bat")}</div>`;
    } else if (!d.ocr) {
      ocr = `<div class="k-riquadro k-warn">
        <b>Manca il lettore di testo (Tesseract).</b> Senza, le foto vengono comunque accoppiate e raddrizzate,
        ma titolo, autore e sintesi andranno scritti a mano.
        <div style="margin-top:10px" class="k-azioni">
          <button class="k-btn" id="kInstalla">⬇ Installa Tesseract (gratis)</button>
          <span class="k-fonte">Serve Internet e il permesso di Windows; va nella cartella «strumenti» di Gestione Chiesa.</span>
        </div></div>`;
    } else if (d.lingua !== "ita") {
      ocr = `<div class="k-riquadro k-warn">Manca il dizionario italiano di Tesseract: il testo verrà letto peggio.</div>`;
    }
    $("#kCorpo").innerHTML = `
      <div class="k-centro">
        <div class="k-grande">📚</div>
        <h3>Carica i libri da una cartella di foto</h3>
        <p>Scegli la cartella con le foto delle copertine, fronte e retro. Il programma le raddrizza,
           le accoppia, legge il testo e compila le schede. Prima di pubblicare le rivedi tutte.</p>
        ${ocr}
        <div class="k-riquadro">
          <b>Per un risultato migliore</b>
          <ul class="k-passi">
            <li>fotografa prima il fronte e subito dopo il retro di ogni libro;</li>
            <li>se vuoi, chiama i file «titolo fronte» e «titolo retro»: il titolo sarà preso da lì;</li>
            <li>per le copie, metti nella cartella un file di testo con una riga per libro: <i>titolo  numero</i>.</li>
          </ul>
          <label style="display:flex;gap:8px;align-items:center;margin-top:12px;cursor:pointer">
            <input type="checkbox" id="kRete" checked>
            <span>Cerca anche su Internet (Google Books e Open Library, gratuiti) con l'ISBN o il titolo</span>
          </label>
        </div>
        <button class="k-btn k-pri" id="kScegli" style="font-size:15px;padding:11px 22px">📁 Scegli la cartella delle foto…</button>
      </div>`;
    $("#kScegli").onclick = scegli;
    const inst = $("#kInstalla");
    if (inst) inst.onclick = async () => {
      inst.disabled = true; inst.textContent = "Installazione in corso… (conferma la richiesta di Windows)";
      let r = {};
      try { r = await chiama("catalogo_installa_ocr"); } catch (e) { r = { ok: false, errore: e.message }; }
      if (r.ocr) schermataInizio(r);
      else { inst.disabled = false; inst.textContent = "⬇ Riprova l'installazione";
             alert("Installazione non riuscita" + (r.errore ? ":\n" + r.errore : ".")); }
    };
  }

  async function scegli() {
    let s;
    try { s = await chiama("catalogo_scegli_cartella"); } catch (e) { s = { ok: false, errore: e.message }; }
    if (!s.ok) { if (!s.annullato) alert(s.errore || "Cartella non valida"); return; }
    if (!s.immagini) { alert("In quella cartella non ci sono immagini."); return; }
    const rete = $("#kRete") ? $("#kRete").checked : true;
    $("#kSub").textContent = s.cartella;
    await chiama("catalogo_avvia", s.cartella, rete);
    schermataLavoro(s.immagini);
  }

  /* ── 2. analisi in corso ─────────────────────────────────── */
  function schermataLavoro(n) {
    $("#kCorpo").innerHTML = `
      <div class="k-centro">
        <div class="k-grande">🔎</div>
        <h3>Sto analizzando ${n} foto…</h3>
        <div class="k-barra"><div id="kBarra"></div></div>
        <p id="kMsg">Preparo…</p>
        <p class="k-fonte">Ci vogliono alcuni secondi per foto. Puoi aspettare qui.</p>
        <button class="k-btn" id="kStop">Annulla</button>
      </div>`;
    $("#kStop").onclick = () => chiama("catalogo_annulla");
    clearInterval(timer);
    timer = setInterval(async () => {
      let s;
      try { s = await chiama("catalogo_stato"); } catch (e) { return; }
      const fasi = { lettura: 0, foto: 0, coppie: .72, copertine: .74, schede: .86, fatto: 1 };
      let p = fasi[s.fase] || 0;
      if (s.fase === "foto" && s.totale) p = .72 * s.fatti / s.totale;
      if (s.fase === "schede" && s.totale) p = .86 + .14 * s.fatti / s.totale;
      const b = $("#kBarra"); if (b) b.style.width = Math.round(p * 100) + "%";
      const m = $("#kMsg"); if (m) m.textContent = s.messaggio || "";
      if (s.finito) {
        clearInterval(timer);
        if (s.fase === "errore") {
          const annullato = (s.errore || "").indexOf("annullato") >= 0;
          $("#kCorpo").innerHTML = `<div class="k-centro"><div class="k-grande">${annullato ? "⏹" : "⚠️"}</div>
            <h3>${annullato ? "Analisi annullata" : "Analisi non riuscita"}</h3>
            <p class="k-err">${annullato ? "" : esc(s.messaggio)}</p>
            <button class="k-btn k-pri" id="kDiNuovo">Ricomincia</button></div>`;
          $("#kDiNuovo").onclick = () => apri(opz);
          return;
        }
        R = await chiama("catalogo_risultato");
        filtro = "tutti";
        schermataRevisione();
      }
    }, 700);
  }

  /* ── 3. revisione ────────────────────────────────────────── */
  function daControllare(l) { return (l.avvisi || []).length > 0 || !l.titolo || !l.autore || !l.genere; }

  function aggiornaTop() {
    if (!R) return;
    const sel = R.libri.filter(l => l.includi).length;
    $("#kTopAzioni").innerHTML =
      `<button class="k-btn k-pri" id="kPubblica" ${sel ? "" : "disabled"}>
         ${esc(opz.testoPubblica || "Aggiungi al sito")} (${sel} ${sel === 1 ? "libro" : "libri"})</button>`;
    $("#kPubblica").onclick = pubblica;
    const f = ov.querySelectorAll(".k-filtri [data-f]");
    f.forEach(b => {
      const k = b.dataset.f;
      const n = k === "tutti" ? R.libri.length : k === "controllo" ? R.libri.filter(daControllare).length
        : R.libri.filter(l => !l.includi).length;
      b.querySelector("b").textContent = n;
    });
  }

  function schermataRevisione() {
    const avvisi = (R.avvisi || []).map(a => `<div class="k-riquadro k-warn" style="max-width:1180px;margin:0 auto 12px">${esc(a)}</div>`).join("");
    $("#kCorpo").innerHTML = `
      ${avvisi}
      <div class="k-filtri">
        <button class="k-btn k-sm" data-f="tutti">Tutti <b></b></button>
        <button class="k-btn k-sm" data-f="controllo">Da controllare <b></b></button>
        <button class="k-btn k-sm" data-f="esclusi">Esclusi <b></b></button>
        <span class="k-spazio"></span>
        <button class="k-btn k-sm" id="kTutti">Includi tutti</button>
        <button class="k-btn k-sm" id="kNessuno">Nessuno</button>
      </div>
      <datalist id="kGeneri">${(R.generi || []).map(g => `<option value="${esc(g)}">`).join("")}</datalist>
      <div class="k-schede" id="kSchede"></div>`;
    ov.querySelectorAll(".k-filtri [data-f]").forEach(b => {
      b.classList.toggle("k-att", b.dataset.f === filtro);
      b.onclick = () => { filtro = b.dataset.f; schermataRevisione(); };
    });
    $("#kTutti").onclick = () => { R.libri.forEach(l => l.includi = true); schermataRevisione(); };
    $("#kNessuno").onclick = () => { R.libri.forEach(l => l.includi = false); schermataRevisione(); };
    disegnaSchede();
    aggiornaTop();
  }

  function visibili() {
    if (filtro === "controllo") return R.libri.filter(daControllare);
    if (filtro === "esclusi") return R.libri.filter(l => !l.includi);
    return R.libri;
  }

  function disegnaSchede() {
    const box = $("#kSchede");
    const v = visibili();
    box.innerHTML = v.length ? v.map(htmlScheda).join("")
      : '<div class="k-centro"><p>Nessun libro in questo elenco.</p></div>';
    v.forEach(l => { caricaMini(l.fronte); if (l.retro) caricaMini(l.retro); collega(l.id); });
  }

  function ridisegnaScheda(id) {
    const el = ov.querySelector(`.k-scheda[data-id="${id}"]`);
    const l = libro(id);
    if (!el || !l) return;
    el.outerHTML = htmlScheda(l);
    caricaMini(l.fronte); if (l.retro) caricaMini(l.retro);
    collega(id);
  }

  function campo(l, nome, etichetta, extra) {
    extra = extra || {};
    const v = l[nome] == null || (nome === "pagine" && !+l[nome]) ? "" : l[nome];
    return `<label class="k-campo ${extra.cls || ""}"><span>${etichetta}</span>
      <input data-libro="${l.id}" data-campo="${nome}" value="${esc(v)}" ${extra.attr || ""}></label>`;
  }

  function htmlFaccia(l, faccia) {
    const fid = l[faccia];
    const nome = fid && R.foto[fid] ? R.foto[fid].nome : "";
    const img = fid ? `<img data-mini="${fid}" alt="" title="${esc(nome)}" src="${mini[fid] || ""}" ${mini[fid] ? "" : 'style="visibility:hidden"'}>`
      : "nessuna foto";
    const bottoni = fid ? `
        <button class="k-btn k-sm" data-az="ruota" data-fid="${fid}" data-g="270" title="Ruota a sinistra">⟲</button>
        <button class="k-btn k-sm" data-az="ruota" data-fid="${fid}" data-g="90" title="Ruota a destra">⟳</button>
        ${faccia === "retro" ? `<button class="k-btn k-sm" data-az="separa" title="Fai del retro un libro a parte">✂</button>` : ""}` : "";
    return `<div class="k-faccia"><span class="k-lab">${faccia}</span>
      <div class="k-img">${img}</div><div class="k-rig">${bottoni}</div></div>`;
  }

  function htmlScheda(l) {
    const i = R.libri.indexOf(l);
    const prec = i > 0 ? R.libri[i - 1] : null;
    const avvisi = (l.avvisi || []).map(a => `<span class="k-chip ${esc(a.tipo)}">${esc(a.testo)}</span>`).join("");
    const sugg = (l.suggerimenti || []).map((s, k) =>
      `<button class="k-btn k-sm" data-az="usa" data-k="${k}">↳ Usa: <b>${esc(s.titolo)}</b>${s.autore ? " – " + esc(s.autore) : ""}${s.anno ? " (" + esc(s.anno) + ")" : ""}${s.editore ? ", " + esc(s.editore) : ""}</button>`).join("");
    return `
    <div class="k-scheda ${l.includi ? "" : "k-escluso"}" data-id="${l.id}">
      <div>
        <div class="k-foto">${htmlFaccia(l, "fronte")}${htmlFaccia(l, "retro")}</div>
        <div class="k-rig" style="margin-top:8px">
          ${l.retro ? `<button class="k-btn k-sm" data-az="scambia">⇄ Scambia fronte e retro</button>` : ""}
          ${!l.retro && prec && !prec.retro ? `<button class="k-btn k-sm" data-az="unisci" title="Questa foto è il retro del libro sopra">↑ È il retro del libro sopra</button>` : ""}
        </div>
      </div>
      <div class="k-dati">
        <div class="k-testa">
          <input type="checkbox" data-libro="${l.id}" data-campo="includi" ${l.includi ? "checked" : ""} title="Includi nel sito" style="transform:scale(1.3)">
          <span class="k-tit" data-tit="${l.id}">${esc(l.titolo || "(senza titolo)")}</span>
          <span class="k-fonte">${l.fonte ? "titolo da: " + esc(l.fonte) : ""}</span>
        </div>
        <div class="k-griglia">
          ${campo(l, "titolo", "Titolo", { cls: "k-l2" })}
          ${campo(l, "autore", "Autore", { cls: "k-l2" })}
          ${campo(l, "editore", "Editore")}
          ${campo(l, "anno", "Anno")}
          ${campo(l, "genere", "Genere", { attr: 'list="kGeneri"' })}
          ${campo(l, "copie", "Copie", { attr: 'type="number" min="0"' })}
          ${campo(l, "isbn", "ISBN")}
          ${campo(l, "pagine", "Pagine", { attr: 'type="number" min="0"' })}
          ${campo(l, "lingua", "Lingua")}
          ${campo(l, "note", "Note")}
        </div>
        <label class="k-campo"><span>Sintesi (dal retro di copertina)</span>
          <textarea rows="4" data-libro="${l.id}" data-campo="descrizione">${esc(l.descrizione)}</textarea></label>
        <details class="k-bio" ${l.autore_bio ? "open" : ""}><summary>Presentazione dell'autore</summary>
          <textarea rows="2" data-libro="${l.id}" data-campo="autore_bio">${esc(l.autore_bio)}</textarea></details>
        ${avvisi ? `<div class="k-avvisi">${avvisi}</div>` : ""}
        <div class="k-azioni">
          <button class="k-btn k-sm" data-az="cerca">🔎 Cerca su Internet</button>
          <span class="k-fonte" data-stato-cerca></span>
        </div>
        ${sugg ? `<div class="k-sugg">${sugg}</div>` : ""}
      </div>
    </div>`;
  }

  function collega(id) {
    const el = ov.querySelector(`.k-scheda[data-id="${id}"]`);
    if (!el) return;
    el.querySelectorAll("[data-az]").forEach(b => b.onclick = () => azione(id, b.dataset.az, b));
    el.querySelectorAll("img[data-mini]").forEach(im => im.onclick = () => ingrandisci(im.src));
  }

  async function caricaMini(fid) {
    if (!fid) return;
    if (!mini[fid]) {
      try {
        const r = await chiama("catalogo_miniatura", fid);
        if (r.ok) mini[fid] = r.src;
      } catch (e) { return; }
    }
    ov.querySelectorAll(`img[data-mini="${fid}"]`).forEach(im => { im.src = mini[fid]; im.style.visibility = ""; });
  }

  function ingrandisci(src) {
    if (!src) return;
    const z = document.createElement("div");
    z.className = "k-zoom";
    z.innerHTML = `<img src="${src}" alt="">`;
    z.onclick = () => z.remove();
    ov.appendChild(z);
  }

  async function azione(id, az, btn) {
    const l = libro(id);
    if (!l) return;
    if (az === "ruota") {
      btn.disabled = true;
      try {
        const r = await chiama("catalogo_ruota", btn.dataset.fid, parseInt(btn.dataset.g, 10));
        if (r.ok) { mini[btn.dataset.fid] = r.src; caricaMini(btn.dataset.fid); }
        l.avvisi = (l.avvisi || []).filter(a => a.tipo !== "verso");
      } finally { btn.disabled = false; }
      return;
    }
    if (az === "scambia") {
      [l.fronte, l.retro] = [l.retro, l.fronte];
      ridisegnaScheda(id);
      return;
    }
    if (az === "separa") {
      const nuovo = {
        id: "b" + Date.now(), fronte: l.retro, retro: "", titolo: "", titolo_file: "", autore: "",
        autore_bio: "", editore: "", anno: "", pagine: 0, genere: "", lingua: "Italiano", isbn: "",
        descrizione: "", note: "", copie: 1, fonte: "", suggerimenti: [], includi: true,
        avvisi: [{ tipo: "titolo", testo: "Libro separato a mano: scrivi i dati" },
                 { tipo: "retro", testo: "Retro non trovato" }],
      };
      l.retro = "";
      if (!(l.avvisi || []).some(a => a.tipo === "retro")) l.avvisi.push({ tipo: "retro", testo: "Retro non trovato" });
      R.libri.splice(R.libri.indexOf(l) + 1, 0, nuovo);
      schermataRevisione();
      return;
    }
    if (az === "unisci") {
      const i = R.libri.indexOf(l);
      const prec = R.libri[i - 1];
      if (!prec || prec.retro) return;
      prec.retro = l.fronte;
      prec.avvisi = (prec.avvisi || []).filter(a => a.tipo !== "retro");
      R.libri.splice(i, 1);
      schermataRevisione();
      return;
    }
    if (az === "usa") {
      const s = (l.suggerimenti || [])[parseInt(btn.dataset.k, 10)];
      if (!s) return;
      if (!l.titolo_file && s.titolo) l.titolo = s.titolo;
      ["autore", "editore", "anno", "isbn"].forEach(k => { if (s[k]) l[k] = s[k]; });
      if (s.pagine) l.pagine = s.pagine;
      if (s.descrizione && (!l.descrizione || l.descrizione.length < 120)) l.descrizione = s.descrizione;
      l.fonte = "Internet · " + (s.fonte || "");
      l.avvisi = (l.avvisi || []).filter(a => a.tipo !== "ocr" && a.tipo !== "titolo");
      ridisegnaScheda(id);
      return;
    }
    if (az === "cerca") {
      const stato = ov.querySelector(`.k-scheda[data-id="${id}"] [data-stato-cerca]`);
      btn.disabled = true;
      if (stato) stato.textContent = "cerco…";
      let r;
      try { r = await chiama("catalogo_cerca", l.titolo || "", l.autore || "", l.isbn || ""); }
      catch (e) { r = { ok: false, errore: e.message }; }
      btn.disabled = false;
      if (!r.ok) { if (stato) stato.textContent = "ricerca non riuscita: " + (r.errore || "nessuna rete?"); return; }
      l.suggerimenti = (r.risultati || []).filter(Boolean);
      ridisegnaScheda(id);
      const st2 = ov.querySelector(`.k-scheda[data-id="${id}"] [data-stato-cerca]`);
      if (st2 && !l.suggerimenti.length) st2.textContent = "niente trovato";
    }
  }

  /* ── 4. pubblicazione ────────────────────────────────────── */
  async function pubblica() {
    const scelti = R.libri.filter(l => l.includi);
    const senza = scelti.filter(l => !(l.titolo || "").trim());
    if (senza.length) {
      alert(senza.length + (senza.length === 1 ? " libro selezionato non ha" : " libri selezionati non hanno") +
            " il titolo: scrivilo oppure togli la spunta.");
      filtro = "controllo"; schermataRevisione();
      return;
    }
    const cattolici = scelti.filter(l => (l.avvisi || []).some(a => a.tipo === "cattolico"));
    if (cattolici.length && !confirm("Tra i selezionati ci sono " + cattolici.length +
        " libri segnalati come possibili cattolici. Aggiungerli comunque?")) return;
    const b = $("#kPubblica");
    b.disabled = true; b.textContent = "Preparo le copertine…";
    let r;
    try { r = await chiama("catalogo_conferma", JSON.stringify(scelti)); }
    catch (e) { r = { ok: false, errore: e.message }; }
    if (!r.ok) {
      alert("Non riuscito: " + (r.errore || r.messaggio || "errore sconosciuto"));
      aggiornaTop();
      return;
    }
    R.pubblicato = true;
    let seguito = "";
    try { seguito = (opz.onPubblicato && await opz.onPubblicato(r)) || ""; } catch (e) { seguito = ""; }
    $("#kTopAzioni").innerHTML = "";
    const n = (r.voci || []).length;
    $("#kCorpo").innerHTML = `<div class="k-centro"><div class="k-grande">✅</div>
      <h3>${n} ${n === 1 ? "libro aggiunto" : "libri aggiunti"}</h3>
      <p>${esc(seguito || r.messaggio || "Le copertine sono nella cartella «libreria» del sito.")}</p>
      <div class="k-azioni" style="justify-content:center;margin-top:16px">
        <button class="k-btn" id="kAltri">Carica un'altra cartella</button>
        <button class="k-btn k-pri" id="kFine">Fatto</button></div></div>`;
    $("#kAltri").onclick = () => apri(opz);
    $("#kFine").onclick = () => ov.classList.remove("k-aperto");
  }

  window.Catalogatore = { apri };
})();
