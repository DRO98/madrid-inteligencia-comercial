/**
 * Asistente paso a paso (solo en explorar.html). El botón oculto #btn-run dispara el análisis PyScript.
 */
(function () {
  var totalSteps = 6;
  var step = 1;
  var epigrafesReady = false;
  var catalogo = [];
  var porSector = {};
  var sectoresOrdenados = [];

  var REGLAS_SECTOR = [
    { label: 'Hostelería y ocio', rx: /(bar|restaur|caf|hostel|hotel|discoteca|ocio|espect[aá]culo|cine)/i },
    { label: 'Alimentación', rx: /(aliment|panader|carnicer|fruter|pescader|supermerc|bebida|dulce)/i },
    { label: 'Moda y belleza', rx: /(peluquer|est[eé]tica|moda|ropa|calzado|perfumer|joyer|complemento)/i },
    { label: 'Salud y bienestar', rx: /(farmacia|salud|cl[ií]nic|fisioter|dental|[oó]ptica|bienestar|gimnas)/i },
    { label: 'Hogar y construcción', rx: /(mueble|decoraci[oó]n|ferreter|pintur|reforma|carpinter|fontaner|electricidad|bricolaje)/i },
    { label: 'Tecnología y telecom', rx: /(inform[aá]tic|telefon|electr[oó]nic|software|tecnolog)/i },
    { label: 'Transporte y automoción', rx: /(taller|autom[oó]vil|moto|veh[ií]culo|transporte|log[ií]stica|gasolin)/i },
    { label: 'Servicios profesionales', rx: /(asesor|abogad|consultor|agencia|seguros|inmobiliari|gestor[ií]a|financier)/i },
    { label: 'Educación y cultura', rx: /(academia|colegio|escuela|formaci[oó]n|librer|papeler|cultura|idioma)/i },
  ];

  function showStep(n) {
    step = n;
    document.querySelectorAll('.wizard-step').forEach(function (el) {
      var sn = parseInt(el.dataset.step, 10);
      el.classList.toggle('is-active', sn === n);
      el.hidden = sn !== n;
    });
    var label = document.getElementById('wizard-step-label');
    if (label) label.textContent = 'Paso ' + n + ' de ' + totalSteps;
    var bar = document.querySelector('.wizard-progress-bar-fill');
    if (bar) bar.style.width = (100 * n) / totalSteps + '%';

    var back = document.getElementById('wizard-back');
    if (back) back.hidden = n === 1;

    var next = document.getElementById('wizard-next');
    if (next) {
      if (n === totalSteps) {
        next.textContent = 'Analizar y ver mapas';
        next.dataset.action = 'run';
      } else {
        next.textContent = 'Siguiente';
        next.dataset.action = 'next';
      }
    }

    if (n === totalSteps) {
      updateSummary();
    }

    var err = document.getElementById('err-msg');
    if (err) err.textContent = '';
  }

  function updateSummary() {
    var box = document.getElementById('wizard-summary');
    if (!box) return;
    var secSel = document.getElementById('sector-select');
    var negSel = document.getElementById('negocio-select');
    var secTxt =
      secSel && secSel.options[secSel.selectedIndex] ? secSel.options[secSel.selectedIndex].text : '—';
    var negTxt =
      negSel && negSel.options[negSel.selectedIndex] ? negSel.options[negSel.selectedIndex].text : '—';
    var pubs = [];
    document.querySelectorAll('input[name="publico_obj"]:checked').forEach(function (c) {
      var lab = c.closest('label');
      pubs.push(lab ? lab.innerText.replace(/\s+/g, ' ').trim() : c.value);
    });
    var perf = document.getElementById('perfil_renta');
    var perfTxt = perf && perf.options[perf.selectedIndex] ? perf.options[perf.selectedIndex].text : '—';
    var m = document.getElementById('metros');
    var p = document.getElementById('presupuesto');
    box.innerHTML =
      '<ul class="wizard-summary-list">' +
      '<li><span>Grupo sector</span> ' +
      escapeHtml(secTxt) +
      '</li>' +
      '<li><span>Negocio</span> ' +
      escapeHtml(negTxt) +
      '</li>' +
      '<li><span>Público</span> ' +
      escapeHtml(pubs.join(', ') || '—') +
      '</li>' +
      '<li><span>Renta zona</span> ' +
      escapeHtml(perfTxt) +
      '</li>' +
      '<li><span>Superficie buscada</span> ' +
      escapeHtml((m && m.value) || '—') +
      ' m²</li>' +
      '<li><span>Presupuesto mensual</span> ' +
      escapeHtml((p && p.value) || '—') +
      ' €</li>' +
      '</ul>';
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function normalizaTexto(s) {
    return (s || '')
      .toString()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim();
  }

  function deduceSector(etiqueta) {
    for (var i = 0; i < REGLAS_SECTOR.length; i += 1) {
      if (REGLAS_SECTOR[i].rx.test(etiqueta)) return REGLAS_SECTOR[i].label;
    }
    return 'Otros sectores';
  }

  /** Texto Python: "NOMBRE EPÍGRAFE (N locales)" */
  function parseEpLabel(full) {
    var m = String(full).match(/\s*\((\d+)\s+locales?\)\s*$/i);
    if (!m) return { nombre: String(full).trim(), numLocales: null };
    var nombre = String(full).slice(0, full.length - m[0].length).trim();
    return { nombre: nombre, numLocales: parseInt(m[1], 10) };
  }

  /** Mayúsculas del censo → más legible en listas (palabra a palabra). */
  function aTituloDisplay(s) {
    var t = String(s || '').trim();
    if (!t) return t;
    return t.replace(/[^\s()/,/-]+/g, function (w) {
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    });
  }

  /**
   * Texto corto solo para el selector: sin prefijos tipo “menor/mayor”, sin recuento de locales.
   */
  function acortarNombreEpigrafe(nombre) {
    var raw = String(nombre || '').replace(/\s+/g, ' ').trim();
    var s = raw;
    var prefijos = [
      [/^COMERCIO AL POR MENOR DE /i, ''],
      [/^COMERCIO AL POR MAYOR DE /i, ''],
      [/^COMERCIO AL POR MENOR EN /i, ''],
      [/^COMERCIO AL POR MENOR,?\s*/i, ''],
      [/^COMERCIO AL POR MAYOR,?\s*/i, ''],
      [/^ACTIVIDADES AUXILIARES /i, ''],
      [/^ACTIVIDADES DE /i, ''],
      [/^SERVICIOS DE /i, ''],
      [/^SERVICIOS FINANCIEROS,?\s*/i, ''],
      [/^ESTABLECIMIENTOS DE /i, ''],
      [/^INDUSTRIA DE /i, ''],
      [/^INDUSTRIAS DE /i, ''],
      [/^OTROS SERVICIOS RELACIONADOS CON /i, ''],
      [/^OTROS APARATOS,?\s*/i, ''],
    ];
    for (var p = 0; p < prefijos.length; p += 1) {
      s = s.replace(prefijos[p][0], prefijos[p][1]);
    }

    var frases = [
      [/,\s*DE VIDEO Y DE TELEVISION\b/i, ', video y televisión'],
      [/,\s*DE PROGRAMACION\b/i, ', programación'],
      [/,\s*DE GRABACION\b/i, ', grabación'],
      [/\bPRODUCTOS ALIMENTICIOS\b/i, 'productos alimenticios'],
      [/\bPARA LA AUTOMOCION\b/i, 'para automoción'],
      [/\bCOMBUSTIBLE PARA LA AUTOMOCION\b/i, 'combustible para automoción'],
      [/\bCOMBUSTIBLE PARA\b/i, 'combustible para '],
      [/\bEN ESTABLECIMIENTOS ESPECIALIZADOS\b/i, 'en establecim. especializados'],
      [/\bEN ESTABLECIMIENTOS NO ESPECIALIZADOS\b/i, 'en establecim. no especializados'],
      [/\bEN ESTABLECIMIENTOS\b/i, 'en establecimientos'],
      [/\bCON OBRADOR-BARRA DEGUSTACION\b/i, 'con obrador, barra degustación'],
      [/\bCON OBRADOR-SIN BARRA DEGUSTACION\b/i, 'con obrador, sin barra degustación'],
      [/\bCON OBRADOR-BUFE\b/i, 'con obrador bufé'],
      [/\bPASTELERIA,\s*CONFITERIA,\s*REPOSTERIA\b/i, 'pastelería, confitería y repostería'],
      [/\bCON OBRADOR-/gi, 'con obrador '],
      [/\bBARRA DEGUSTACION\b/i, 'barra degustación'],
      [/\bSIN BARRA\b/i, 'sin barra'],
      [/\bSIN ACTUACIONES\b/i, 'sin actuaciones'],
      [/\bNO ESPECIALIZADOS,\s*CON PREDOMINIO EN\b/i, 'no especializados, con predominio en'],
      [/\bHOTELES Y MOTELES CON RESTAURANTE\b/i, 'hoteles y moteles con restaurante'],
      [/\bCREACION,\s*ARTISTICAS Y ESPECTACULOS\b/i, 'creación, artísticas y espectáculos'],
      [/\bPROMOCION INMOBILIARIA\b/i, 'promoción inmobiliaria'],
    ];
    for (var f = 0; f < frases.length; f += 1) {
      s = s.replace(frases[f][0], frases[f][1]);
    }

    s = s.replace(/\s+/g, ' ').trim();
    if (!s) s = raw;

    s = aTituloDisplay(s);

    var maxLen =
      raw.length > 120 ? 72 : raw.length > 95 ? 78 : raw.length > 75 ? 84 : 92;
    if (s.length <= maxLen) return s;
    var cut = s.slice(0, maxLen - 1);
    var sp = cut.lastIndexOf(' ');
    if (sp > maxLen * 0.38) cut = cut.slice(0, sp);
    return cut.trim() + '\u2026';
  }

  function etiquetaOpcionNegocio(it) {
    return acortarNombreEpigrafe(it.nombre);
  }

  function buildCatalogoDesdeEpigrafe() {
    var ep = document.getElementById('epigrafe');
    var sectorSel = document.getElementById('sector-select');
    if (!ep || !sectorSel || ep.options.length < 1) return false;
    if (ep.options.length === 1 && !ep.options[0].value) return false;

    catalogo = [];
    porSector = {};
    sectoresOrdenados = [];

    for (var i = 0; i < ep.options.length; i += 1) {
      var opt = ep.options[i];
      if (!opt.value) continue;
      var parsed = parseEpLabel(String(opt.text || opt.value));
      var item = {
        value: String(opt.value),
        nombre: parsed.nombre,
        numLocales: parsed.numLocales,
        labelFull: String(opt.text || opt.value).trim(),
      };
      item.search = normalizaTexto(item.nombre + ' ' + item.labelFull);
      item.sector = deduceSector(item.nombre);
      catalogo.push(item);
      if (!porSector[item.sector]) porSector[item.sector] = [];
      porSector[item.sector].push(item);
    }

    sectoresOrdenados = Object.keys(porSector).sort(function (a, b) {
      return porSector[b].length - porSector[a].length || a.localeCompare(b, 'es');
    });
    sectoresOrdenados.forEach(function (s) {
      porSector[s].sort(function (a, b) {
        return a.nombre.localeCompare(b.nombre, 'es');
      });
    });

    sectorSel.innerHTML = '<option value="">Selecciona un sector…</option>';
    sectoresOrdenados.forEach(function (sec) {
      var o = document.createElement('option');
      o.value = sec;
      o.textContent = sec + ' (' + porSector[sec].length + ')';
      sectorSel.appendChild(o);
    });
    epigrafesReady = true;

    if (typeof console !== 'undefined' && console.table && /\bdebug=1\b/.test(location.search)) {
      console.table(
        catalogo.map(function (it) {
          return {
            locales: it.numLocales,
            lista: etiquetaOpcionNegocio(it),
            nombre_original: it.nombre,
          };
        })
      );
    }

    return true;
  }

  function filtraItems() {
    var sectorSel = document.getElementById('sector-select');
    var items = [];
    if (!epigrafesReady || !sectorSel) return items;
    var sec = sectorSel.value;
    if (sec && porSector[sec]) {
      items = porSector[sec].slice();
    } else {
      items = catalogo.slice();
    }
    return items.slice(0, 250);
  }

  function renderNegociosList() {
    var negocioSel = document.getElementById('negocio-select');
    if (!negocioSel) return;

    var items = filtraItems();
    negocioSel.innerHTML = '';

    var emptyOpt = document.createElement('option');
    emptyOpt.value = '';
    emptyOpt.textContent = items.length ? 'Selecciona un negocio…' : 'No hay coincidencias';
    negocioSel.appendChild(emptyOpt);

    items.forEach(function (it) {
      var o1 = document.createElement('option');
      o1.value = it.value;
      o1.textContent = etiquetaOpcionNegocio(it);
      o1.setAttribute('title', aTituloDisplay(it.nombre));
      negocioSel.appendChild(o1);
    });
  }

  function sincronizaEpigrafeDesdeInput() {
    var ep = document.getElementById('epigrafe');
    var negocioSel = document.getElementById('negocio-select');
    if (!ep || !negocioSel) return;

    if (negocioSel.value) {
      ep.value = negocioSel.value;
      return;
    }
    ep.value = '';
  }

  function validateStep(n) {
    var err = document.getElementById('err-msg');
    if (err) err.textContent = '';
    if (n === 1) {
      sincronizaEpigrafeDesdeInput();
      var ep = document.getElementById('epigrafe');
      if (!ep || !ep.value) {
        if (err) err.textContent = 'Selecciona sector y negocio antes de continuar.';
        return false;
      }
    }
    if (n === 2) {
      if (!document.querySelectorAll('input[name="publico_obj"]:checked').length) {
        if (err) err.textContent = 'Marca al menos un público objetivo.';
        return false;
      }
    }
    if (n === 4) {
      var m = document.getElementById('metros');
      var mv = m ? parseFloat(m.value) : NaN;
      if (!m || !isFinite(mv) || mv < 20) {
        if (err) err.textContent = 'Indica una superficie válida (mín. 20 m²).';
        return false;
      }
    }
    if (n === 5) {
      var pr = document.getElementById('presupuesto');
      var pv = pr ? parseFloat(pr.value) : NaN;
      if (!pr || !isFinite(pv) || pv < 500) {
        if (err) err.textContent = 'Indica un presupuesto mensual válido (mín. 500 €).';
        return false;
      }
    }
    return true;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var next = document.getElementById('wizard-next');
    var back = document.getElementById('wizard-back');
    var ep = document.getElementById('epigrafe');
    var sectorSel = document.getElementById('sector-select');
    var negocioSel = document.getElementById('negocio-select');
    if (!next || !document.querySelector('.wizard-step')) return;

    function onCatalogMaybeReady() {
      if (buildCatalogoDesdeEpigrafe()) {
        renderNegociosList();
      }
    }

    if (ep) {
      onCatalogMaybeReady();
      var obs = new MutationObserver(onCatalogMaybeReady);
      obs.observe(ep, { childList: true, subtree: true });
    }

    if (sectorSel) {
      sectorSel.addEventListener('change', function () {
        renderNegociosList();
        sincronizaEpigrafeDesdeInput();
      });
    }

    if (negocioSel) {
      negocioSel.addEventListener('change', sincronizaEpigrafeDesdeInput);
    }

    next.addEventListener('click', function () {
      if (next.dataset.action === 'run') {
        if (!validateStep(5)) {
          showStep(5);
          return;
        }
        updateSummary();
        var btn = document.getElementById('btn-run');
        if (btn) btn.click();
        return;
      }
      if (!validateStep(step)) return;
      if (step < totalSteps) showStep(step + 1);
    });

    if (back) {
      back.addEventListener('click', function () {
        if (step > 1) showStep(step - 1);
      });
    }

    showStep(1);
  });
})();
