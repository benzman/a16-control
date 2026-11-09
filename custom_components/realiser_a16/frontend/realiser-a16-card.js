// Lovelace card for the Smyth Realiser A16 – modelled on the Centro Control app.
// Served and registered by the realiser_a16 integration; no build step.
import { IR_KEYS, PRESET_COUNT, SOURCES, SPEAKERS } from "./protocol_gen.js";

const TABS = ["control", "speakers", "meters", "tracker", "remote", "about"];

const TEXT = {
  en: {
    control: "Control", speakers: "Speakers", meters: "Meters", tracker: "Tracker",
    remote: "Remote", about: "About", audio: "Audio", format: "Format", upmixer: "Upmixer",
    legacy: "Legacy", users: "Users", htmode: "HT mode", room: "Listening room",
    layout: "Layout", subject: "Subject", hpeqFile: "HPEQ file", hpeqSubject: "HPEQ subject",
    hpeqDate: "HPEQ date", hpeqType: "HPEQ type", headphone: "Headphone", tactile: "Tactile",
    user: "User", preset: "Preset", mute: "Mute", offline: "No connection to the A16",
    standby: "Standby", tapMode: "Tap", solo: "Solo", muteMode: "Mute", all: "ALL",
    test: "TEST", noSpeakers: "No speaker layout reported", channel: "CH", outputs: "Outputs",
    azimuth: "Azimuth", elevation: "Elevation", serial: "Serial number", refresh: "Refresh",
    resetMeters: "Reset peaks", mode: "Mode", notFound: "Realiser A16 integration not loaded",
  },
  de: {
    control: "Steuerung", speakers: "Lautsprecher", meters: "Pegel", tracker: "Tracker",
    remote: "Fernbedienung", about: "Info", audio: "Audio", format: "Format",
    upmixer: "Upmixer", legacy: "Legacy", users: "Benutzer", htmode: "HT-Modus",
    room: "Hörraum", layout: "Layout", subject: "Subject", hpeqFile: "HPEQ-Datei",
    hpeqSubject: "HPEQ-Subject", hpeqDate: "HPEQ-Datum", hpeqType: "HPEQ-Typ",
    headphone: "Kopfhörer", tactile: "Tactile", user: "Benutzer", preset: "Preset",
    mute: "Stumm", offline: "Keine Verbindung zum A16", standby: "Standby", tapMode: "Tippen",
    solo: "Solo", muteMode: "Stumm", all: "ALLE", test: "TEST",
    noSpeakers: "Kein Lautsprecher-Layout gemeldet", channel: "CH", outputs: "Ausgänge",
    azimuth: "Azimut", elevation: "Elevation", serial: "Seriennummer",
    refresh: "Aktualisieren", resetMeters: "Spitzen zurücksetzen", mode: "Modus",
    notFound: "Realiser-A16-Integration nicht geladen",
  },
};

const OUTPUTS = [
  ["AHL", "A HP L"], ["AHR", "A HP R"], ["ATL", "A TACT L"], ["ATR", "A TACT R"],
  ["BHL", "B HP L"], ["BHR", "B HP R"], ["BTL", "B TACT L"], ["BTR", "B TACT R"],
];

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

const STYLE = `
  :host { --a: var(--info-color, #039be5); --b: var(--error-color, #db4437); }
  ha-card { padding: 12px; }
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .title { font-size: 1.1em; font-weight: 500; flex: 1; }
  .tabs { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 12px; }
  button { font: inherit; color: var(--primary-text-color); background: var(--secondary-background-color);
    border: 1px solid var(--divider-color); border-radius: 8px; padding: 8px 10px; cursor: pointer;
    min-width: 40px; }
  button:active { filter: brightness(0.85); }
  button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  button.round { border-radius: 50%; width: 40px; height: 40px; padding: 0; }
  .tabs button { flex: 1; padding: 6px 4px; font-size: 0.85em; }
  .status { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px 12px; font-size: 0.85em; margin-bottom: 12px; }
  .status span, dt { color: var(--secondary-text-color); }
  .sources { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin-bottom: 12px; }
  .sources button { padding: 8px 2px; font-size: 0.8em; }
  .user { border-top: 1px solid var(--divider-color); padding-top: 10px; margin-top: 10px; }
  .user h3 { margin: 0 0 8px; font-size: 1em; display: flex; justify-content: space-between; }
  .user.a h3, .user.a dd { color: var(--a); } .user.b h3, .user.b dd { color: var(--b); }
  .user.a button.on { background: var(--a); } .user.b button.on { background: var(--b); }
  .cols { display: grid; grid-template-columns: auto 1fr auto; gap: 12px; align-items: start; }
  .presets { display: grid; grid-template-columns: repeat(4, 36px); gap: 4px; }
  .presets button { padding: 6px 0; min-width: 0; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 1px 8px; margin: 0; font-size: 0.8em; min-width: 0; }
  dd { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .vol { display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .vol .value { font-size: 1.6em; font-weight: 500; min-width: 2ch; text-align: center; }
  .vol small { color: var(--secondary-text-color); }
  .screen { height: 6px; background: var(--primary-text-color); opacity: 0.5; border-radius: 3px; margin: 0 20% 8px; }
  .room { display: grid; grid-template-columns: repeat(9, 1fr); grid-template-rows: repeat(7, 1fr); gap: 4px;
    aspect-ratio: 9 / 7; border: 1px solid var(--divider-color); border-radius: 8px; padding: 6px; }
  .room button { padding: 0; min-width: 0; font-size: 0.75em; border-color: transparent; color: #000; opacity: 0.3; }
  .room button.on { opacity: 1; color: #000; }
  .room .floor { background: #8bd46e; } .room .height { background: #f5a85c; }
  .room .overhead { background: #c9a7f0; } .room .under { background: #f2e24a; } .room .lfe { background: #f06a6a; }
  .seat { grid-row: 4; grid-column: 5; align-self: center; justify-self: center; font-size: 1.6em; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
  .row .grow { flex: 1; }
  .meters { display: grid; grid-template-columns: 2em minmax(3em, auto) minmax(3em, auto) 1fr; gap: 2px 8px;
    font-size: 0.8em; align-items: center; }
  .meters .out { grid-column: 1 / 4; }
  .bar { height: 10px; background: var(--secondary-background-color); border-radius: 3px; overflow: hidden; }
  .bar i { display: block; height: 100%; width: 0; background: var(--success-color, #43a047); transition: width 0.2s; }
  .meters .ca { color: var(--a); } .meters .cb { color: var(--b); }
  .angles { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; text-align: center; }
  .angles .value { font-size: 2em; } .angles .ua { color: var(--a); } .angles .ub { color: var(--b); }
  .pad { display: grid; gap: 6px; margin-bottom: 12px; }
  .pad.c3 { grid-template-columns: repeat(3, 1fr); } .pad.c4 { grid-template-columns: repeat(4, 1fr); }
  .pad.c6 { grid-template-columns: repeat(6, 1fr); } .pad button { min-width: 0; padding: 10px 2px; }
  .note { color: var(--secondary-text-color); text-align: center; padding: 24px 0; }
  .about dl { font-size: 0.95em; gap: 6px 12px; } .about dd { white-space: normal; }
`;

class RealiserA16Card extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._tab = "control";
    this._state = null;
    this._connected = false;
    this._error = null;
    this._levels = {};
    this._unsub = null;
    this._subKey = null;
    this.shadowRoot.addEventListener("click", (event) => this._click(event));
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    const tabs = (config.tabs || TABS).filter((tab) => TABS.includes(tab));
    if (!tabs.length) throw new Error("tabs: no valid tab name");
    this._config = { ...config, tabs };
    this._tab = tabs.includes(config.default_tab) ? config.default_tab : tabs[0];
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._render();
    this._subscribe();
  }

  connectedCallback() {
    this._subscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  getCardSize() {
    return 8;
  }

  // ---- data -------------------------------------------------------------

  _t(key) {
    const lang = (this._hass?.language || "en").slice(0, 2);
    return (TEXT[lang] || TEXT.en)[key] ?? TEXT.en[key] ?? key;
  }

  _unsubscribe() {
    const pending = this._unsub;
    this._unsub = this._subKey = null;
    if (pending) pending.then((unsub) => unsub && unsub()).catch(() => {});
  }

  _subscribe() {
    if (!this._hass || !this.isConnected) return;
    // Meters and tracker are only polled from the A16 while their tab is open.
    const key = this._tab === "meters" ? "levels" : this._tab === "tracker" ? "tracker" : "state";
    if (this._subKey === key) return;
    this._unsubscribe();
    this._subKey = key;
    const message = { type: "realiser_a16/subscribe", levels: key === "levels", tracker: key === "tracker" };
    if (this._config.entry_id) message.entry_id = this._config.entry_id;
    this._unsub = this._hass.connection
      .subscribeMessage((event) => this._event(event), message)
      .then((unsub) => {
        this._error = null;
        return unsub;
      })
      .catch((err) => {
        this._error = err?.message || String(err);
        this._subKey = null;
        this._render();
        setTimeout(() => this._subscribe(), 5000);
        return null;
      });
  }

  _event(event) {
    if (event.type === "state") {
      this._state = event.state;
      this._connected = event.connected;
      this._render();
    } else if (event.type === "levels") {
      this._levels = event.levels;
      this._paintLevels();
    } else if (event.type === "tracker") {
      this._state.user_a.ht_azimuth = event.a[0];
      this._state.user_a.ht_elevation = event.a[1];
      this._state.user_b.ht_azimuth = event.b[0];
      this._state.user_b.ht_elevation = event.b[1];
      if (this._tab === "tracker") this._render();
    }
  }

  _send(...commands) {
    this._hass
      .callWS({ type: "realiser_a16/send", commands, ...(this._config.entry_id ? { entry_id: this._config.entry_id } : {}) })
      .catch((err) => {
        this._hass.callService?.("persistent_notification", "create", {
          title: "Realiser A16",
          message: err?.message || String(err),
        });
      });
  }

  _click(event) {
    const target = event.target.closest("[data-cmd],[data-tab]");
    if (!target) return;
    if (target.dataset.tab) {
      this._tab = target.dataset.tab;
      this._subscribe();
      this._render();
    } else {
      this._send(...target.dataset.cmd.split(","));
    }
  }

  // ---- rendering --------------------------------------------------------

  _render() {
    if (!this._hass) return;
    const s = this._state;
    const tabs = this._config.tabs || TABS;
    let body;
    if (!s) body = `<div class="note">${esc(this._error || this._t("offline"))}</div>`;
    else if (!this._connected) body = `<div class="note">${this._t("offline")}</div>`;
    else body = this[`_${this._tab}`](s);

    const on = s?.power === "ON";
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head">
          <div class="title">${esc(this._config.title || "Realiser A16")}${
            s && this._connected && !on ? ` · ${esc(s.power || "")}` : ""
          }</div>
          <button class="round ${on ? "on" : ""}" title="Power"
            data-cmd="${on ? "power_standby" : "power_on"}">⏻</button>
        </div>
        ${
          tabs.length > 1
            ? `<div class="tabs">${tabs
                .map((tab) => `<button class="${tab === this._tab ? "on" : ""}" data-tab="${tab}">${this._t(tab)}</button>`)
                .join("")}</div>`
            : ""
        }
        ${body}
      </ha-card>`;
    if (this._tab === "meters") this._paintLevels();
  }

  _btn(label, cmd, on = false, title = "") {
    return `<button class="${on ? "on" : ""}" data-cmd="${cmd}" title="${esc(title)}">${esc(label)}</button>`;
  }

  _volume(s, u) {
    const user = s[`user_${u}`];
    return `<div class="vol">
        ${this._btn("▲", `vol_${u}_up`)}
        <div class="value">${user.volume ?? "–"}</div>
        ${user.tri_level ? `<small>TRI ${user.tri_level}</small>` : ""}
        ${this._btn("▼", `vol_${u}_down`)}
        ${this._btn(user.muted ? "🔇" : "🔈", `mute_${u}`, !!user.muted, this._t("mute"))}
      </div>`;
  }

  _control(s) {
    const status = [
      ["audio", s.decoder], ["format", s.format], ["legacy", s.legacy],
      ["upmixer", s.upmixer], ["users", s.user_mode], ["htmode", s.ht_mode],
    ];
    const user = (u) => {
      const d = s[`user_${u}`];
      const info = [
        ["room", d.room], ["layout", d.layout], ["subject", d.subject], ["hpeqFile", d.hpeq_file],
        ["hpeqSubject", d.hpeq_subject], ["hpeqDate", d.hpeq_date], ["hpeqType", d.hpeq_type],
        ["headphone", d.headphone], ["tactile", d.tactile == null ? "" : d.tactile ? "ON" : "OFF"],
      ];
      let presets = "";
      for (let n = 1; n <= PRESET_COUNT; n++) presets += this._btn(n, `preset_${u}_${n}`, d.preset === n);
      return `<div class="user ${u}">
          <h3><span>${this._t("user")} ${u.toUpperCase()}${d.name ? ` · ${esc(d.name)}` : ""}</span>
              <span>${this._t("preset")} ${d.preset ?? "–"}</span></h3>
          <div class="cols">
            <div class="presets">${presets}</div>
            <dl>${info.map(([k, v]) => `<dt>${this._t(k)}</dt><dd title="${esc(v)}">${esc(v) || "–"}</dd>`).join("")}</dl>
            ${this._volume(s, u)}
          </div>
        </div>`;
    };
    return `
      <div class="status">${status.map(([k, v]) => `<div><span>${this._t(k)}</span> ${esc(v) || "–"}</div>`).join("")}</div>
      <div class="sources">${SOURCES.map(([id, label]) => this._btn(label, `source_${id}`, s.source === label)).join("")}</div>
      ${user("a")}${s.user_mode === "SINGLE" ? "" : user("b")}`;
  }

  _speakers(s) {
    const visible = new Set(s.visible_speakers);
    const active = new Set(s.active_speakers);
    if (!visible.size) return `<div class="note">${this._t("noSpeakers")}</div>`;
    const cells = SPEAKERS.filter(([id]) => visible.has(id))
      .map(
        ([id, name, type, row, col]) =>
          `<button class="${type} ${active.has(id) ? "on" : ""}" style="grid-row:${row + 1};grid-column:${col + 1}"
             ${id <= 50 ? `data-cmd="speaker_${id}"` : "disabled"}>${esc(name)}</button>`
      )
      .join("");
    const mute = s.solo_mode === "MUTE";
    return `
      <div style="text-align:center;margin-bottom:8px">${this._t("layout")} <b>${esc(s.user_a.layout) || "–"}</b></div>
      <div class="screen"></div>
      <div class="room">${cells}${visible.has(24) ? "" : `<div class="seat">🪑</div>`}</div>
      <div class="row">
        ${this._btn(this._t("test"), "test", !!s.test)}
        ${this._btn("SVS", "headphone", s.mode === "SVS")}
        ${this._btn(s.mode && s.mode !== "SVS" ? s.mode : "AV/MIX", "speaker", !!s.mode && s.mode !== "SVS")}
        <span class="grow"></span>
        <span>${this._t("tapMode")}: <b>${mute ? this._t("muteMode") : this._t("solo")}</b></span>
        ${this._btn(this._t("all"), "all", !!s.all_active)}
        <span class="grow"></span>
        ${this._btn("−", "vol_a_down")}<b>${s.user_a.volume ?? "–"}</b>${this._btn("+", "vol_a_up")}
      </div>`;
  }

  _meters(s) {
    let rows = `<b>${this._t("channel")}</b><b class="ca">A</b><b class="cb">B</b><span></span>`;
    for (let ch = 1; ch <= 24; ch++) {
      rows += `<span>${ch}</span><span class="ca">${esc(s.user_a.assignments[ch])}</span>
        <span class="cb">${esc(s.user_b.assignments[ch])}</span>
        <div class="bar"><i data-level="L${ch}"></i></div>`;
    }
    rows += `<b class="out" style="margin-top:8px">${this._t("outputs")}</b><span></span>`;
    for (const [key, label] of OUTPUTS) {
      rows += `<span class="out ${key[0] === "A" ? "ca" : "cb"}">${label}</span><div class="bar"><i data-level="${key}"></i></div>`;
    }
    return `<div class="meters">${rows}</div>
      <div class="row"><span class="grow"></span>${this._btn(this._t("resetMeters"), "reset_levels")}</div>`;
  }

  _paintLevels() {
    for (const bar of this.shadowRoot.querySelectorAll("[data-level]")) {
      const value = Number(this._levels[bar.dataset.level]) || 0;
      bar.style.width = `${Math.max(0, Math.min(100, value))}%`;
    }
  }

  _tracker(s) {
    const user = (u) => {
      const d = s[`user_${u}`];
      const deg = (v) => (v == null ? "–" : `${v}°`);
      return `<div class="u${u}"><div>${this._t("user")} ${u.toUpperCase()}</div>
        <div class="value">${deg(d.ht_azimuth)}</div><small>${this._t("azimuth")}</small>
        <div class="value">${deg(d.ht_elevation)}</div><small>${this._t("elevation")}</small></div>`;
    };
    return `<div class="angles">${user("a")}${user("b")}</div>
      <div class="row"><span>${this._t("htmode")}: <b>${esc(s.ht_mode) || "–"}</b></span>
        <span class="grow"></span>${this._btn("HT", "ht", !!s.ht_active)}</div>`;
  }

  _remote(s) {
    const labels = Object.fromEntries(IR_KEYS);
    const key = (name, label) => this._btn(label ?? labels[name], name);
    const gap = "<span></span>";
    return `
      <div class="pad c3">
        ${key("menu")}${key("up", "▲")}${key("back")}
        ${key("left", "◀")}${key("enter", "OK")}${key("right", "▶")}
        ${key("cancel")}${key("down", "▼")}${gap}
        ${key("adj_minus")}${gap}${key("adj_plus")}
      </div>
      <div class="pad c3">
        ${["1", "2", "3", "4", "5", "6", "7", "8", "9", "star", "0", "hash"].map((k) => key(k)).join("")}
      </div>
      <div class="pad c4">
        ${key("cal")}${key("spk")}${key("hp")}${key("test")}
        ${key("pa")}${key("pb")}${key("ht")}${key("all")}
        ${key("headphone", "SVS")}${key("speaker", "AV/MIX")}${key("mute_a")}${key("mute_b")}
        ${key("vol_a_down", "A −")}${key("vol_a_up", "A +")}${key("vol_b_down", "B −")}${key("vol_b_up", "B +")}
      </div>
      <div class="pad c6">
        ${["l", "c", "r", "lw", "rw", "lfe", "ls", "rs", "lb", "rb", "oh"].map((k) => key(k)).join("")}
        ${key("power", "⏻")}
      </div>
      <div class="note" style="padding:0">${this._t("mode")}: ${esc(s.mode) || "–"}${
        s.page != null ? ` · Page ${s.page}` : ""
      }</div>`;
  }

  _about(s) {
    const fw = s.firmware || {};
    const rows = [
      ["A16 Firmware", fw.A16FW], ["HT Firmware", fw.HTFW], ["APM Firmware", fw.APMFW],
      ["HSR Firmware", fw.HSRFW], [this._t("serial"), fw.A16SN],
    ];
    return `<div class="about"><dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v) || "–"}</dd>`).join("")}</dl></div>
      <div class="row"><span class="grow"></span>
        ${this._btn(this._t("refresh"), "power_status,user_a_info,user_b_info,speaker_visibility,firmware,assignments")}</div>`;
  }
}

if (!customElements.get("realiser-a16-card")) {
  customElements.define("realiser-a16-card", RealiserA16Card);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "realiser-a16-card",
    name: "Realiser A16",
    description: "Control, speaker map, meters, head tracker and remote for the Smyth Realiser A16",
  });
}
