/* TrustLayer Market — no-build React (htm) frontend. */
const { useState, useEffect, useRef, useCallback } = React;

// htm -> React adapter: lets templates use plain HTML habits (class=, style="a:b", stroke-width=)
const camel = (s) => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
function h(type, props, ...children) {
  if (props) {
    const p = {};
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") p.className = v;
      else if (k === "for") p.htmlFor = v;
      else if (k === "style" && typeof v === "string") {
        p.style = Object.fromEntries(v.split(";").map((d) => d.split(":")).filter((d) => d.length >= 2)
          .map(([a, ...b]) => [camel(a.trim()), b.join(":").trim()]));
      } else if (k.includes("-") && !k.startsWith("data-") && !k.startsWith("aria-")) p[camel(k)] = v;
      else p[k] = v;
    }
    props = p;
  }
  return React.createElement(type, props, ...children);
}
const html = htm.bind(h);

// ---------------- utils ----------------
async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = new Error(data.error || `Request failed (${res.status})`);
    e.data = data; e.status = res.status; throw e;
  }
  return data;
}
const usd = (v) => "$" + Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ago = (ts) => { const s = Math.max(0, Date.now() / 1000 - ts); return s < 60 ? `${Math.floor(s)}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : `${Math.floor(s / 3600)}h ago`; };

let toastSet = null;
function toast(msg, err = false) { toastSet && toastSet({ msg, err }); setTimeout(() => toastSet && toastSet(null), 4200); }

function useRoute() {
  const [hash, setHash] = useState(location.hash || "#/");
  useEffect(() => { const f = () => { setHash(location.hash || "#/"); window.scrollTo(0, 0); }; addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return hash.slice(1).split("/").filter(Boolean);
}
const go = (path) => { location.hash = path; };

function useFetch(path, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const load = useCallback(() => {
    if (!path) return;
    api(path).then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState({ data: null, error, loading: false }));
  }, [path]);
  useEffect(() => { setState((s) => ({ ...s, loading: true })); load(); }, [path, ...deps]);
  return [state, load];
}

// PayPal JS SDK (loaded once with intent=authorize so approvals create holds, not charges)
let sdkPromise = null;
function loadPayPal(clientId) {
  if (window.paypal) return Promise.resolve(window.paypal);
  if (!sdkPromise) {
    sdkPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=USD&intent=authorize&components=buttons&disable-funding=card,credit,paylater,venmo`;
      s.onload = () => resolve(window.paypal);
      s.onerror = () => { sdkPromise = null; reject(new Error("PayPal SDK failed to load")); };
      document.head.appendChild(s);
    });
  }
  return sdkPromise;
}

// ---------------- shell ----------------
function App() {
  const route = useRoute();
  const [cfg, setCfg] = useState(null);
  const [t, setT] = useState(null);
  toastSet = setT;
  useEffect(() => { api("/api/config").then(setCfg).catch(() => setCfg({})); }, []);
  const [page, a, b] = route;
  let body;
  if (!page) body = html`<${Market} />`;
  else if (page === "listing") body = html`<${ListingPage} id=${a} cfg=${cfg} />`;
  else if (page === "orders") body = html`<${OrdersPage} />`;
  else if (page === "order") body = html`<${OrderPage} id=${a} />`;
  else if (page === "contact") body = html`<${ContactPage} token=${a} />`;
  else if (page === "sellers") body = a ? html`<${SellerPage} id=${a} />` : html`<${SellersPage} />`;
  else if (page === "ledger") body = html`<${LedgerPage} />`;
  else body = html`<p>Not found. <a href="#/">Back to market</a></p>`;
  const on = (p) => (page || "") === p ? "on" : "";
  return html`
    <header class="top"><div class="wrap">
      <a class="logo" href="#/">🛡️ TrustLayer <small>Market</small></a>
      <span class="sandbox">PayPal SANDBOX</span>
      <nav class="nav">
        <a class=${on("") || on("listing")} href="#/">Market</a>
        <a class=${on("orders") || on("order")} href="#/orders">My orders</a>
        <a class=${on("sellers")} href="#/sellers">Seller health</a>
        <a class=${on("ledger")} href="#/ledger">Ledger</a>
      </nav>
    </div></header>
    <main><div class="wrap">${body}</div></main>
    ${t && html`<div class=${"toast " + (t.err ? "err" : "")}>${t.msg}</div>`}`;
}

// ---------------- market ----------------
function Market() {
  const [{ data, loading, error }] = useFetch("/api/listings");
  return html`
    <section class="hero">
      <h1>Buy from strangers without getting scammed.</h1>
      <p>Every payment on this marketplace runs through PayPal and TrustLayer: AI checks the chat before your money moves,
         holds it until delivery, and settles problems before they become disputes.</p>
      <div class="pill3"><span>⏸ Pay-pause scam interception</span><span>🤝 Pre-dispute resolution</span><span>📈 Seller account health</span></div>
    </section>
    ${loading && html`<p><span class="spinner"></span> Loading listings…</p>`}
    ${error && html`<p class="chip bad">${error.message}</p>`}
    <div class="grid cards">
      ${(data || []).map((l) => html`
        <a class="panel card" href=${"#/listing/" + l.id} key=${l.id}>
          <div class="thumb">${l.emoji}</div>
          <div class="small muted">${l.category} · ${l.condition}</div>
          <h3 style="margin:2px 0 6px">${l.title}</h3>
          <div class="row between">
            <div class="price">${usd(l.price)}<span class="strike">${usd(l.ref_price)}</span></div>
          </div>
          <div class="row small muted" style="margin-top:6px">
            <span>@${l.handle}</span>
            ${l.completed_sales > 0
              ? html`<span class="chip">★ ${l.rating} · ${l.completed_sales} sales</span>`
              : html`<span class="chip warn">New seller · ${l.joined_days_ago}d</span>`}
          </div>
        </a>`)}
    </div>`;
}

// ---------------- listing + checkout ----------------
function ListingPage({ id, cfg }) {
  const [{ data, loading, error }, reload] = useFetch(`/api/listings/${id}`);
  const [risk, setRisk] = useState(null);
  const [checking, setChecking] = useState(false);
  const [text, setText] = useState("");
  const [asSeller, setAsSeller] = useState(false);
  useEffect(() => setRisk(null), [id]);
  if (loading && !data) return html`<p><span class="spinner"></span> Loading…</p>`;
  if (error) return html`<p class="chip bad">${error.message}</p>`;
  const { listing, seller, messages } = data;
  const flagged = new Set((risk?.ai?.evidence || []).map((e) => e.line).concat((risk?.signals || []).filter((s) => s.line).map((s) => s.line)));

  const send = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    await api(`/api/listings/${id}/messages`, { method: "POST", body: { text, sender: asSeller ? "seller" : "buyer" } });
    setText(""); setRisk(null); reload();
  };
  const check = async () => {
    setChecking(true);
    try { setRisk(await api("/api/assess", { method: "POST", body: { listing_id: id } })); }
    catch (e) { toast(e.message, true); }
    finally { setChecking(false); }
  };

  return html`
    <p class="small"><a href="#/">← Market</a></p>
    <div class="grid two">
      <div class="grid">
        <div class="panel">
          <div class="thumb" style="height:180px;font-size:90px">${listing.emoji}</div>
          <div class="small muted">${listing.category} · ${listing.condition}</div>
          <h1>${listing.title}</h1>
          <div class="price" style="font-size:26px">${usd(listing.price)}<span class="strike">typical ${usd(listing.ref_price)}</span></div>
          <p>${listing.description}</p>
          <div class="row">
            <span class="chip brand">@${seller.handle}</span>
            ${seller.completed_sales > 0 ? html`<span class="chip">★ ${seller.rating} · ${seller.completed_sales} sales</span>` : html`<span class="chip warn">New seller · joined ${seller.joined_days_ago} days ago</span>`}
            <span class="chip">${seller.location}</span>
          </div>
        </div>
        <div class="panel">
          <div class="row between"><h2 style="margin:0">Chat with @${seller.handle}</h2>
            ${flagged.size > 0 && html`<span class="chip bad">${flagged.size} flagged line${flagged.size > 1 ? "s" : ""}</span>`}</div>
          <div class="chat" style="margin-top:10px">
            ${messages.map((m, i) => html`
              <div class=${"bubble " + m.sender + (flagged.has(i + 1) ? " flag" : "")} key=${i}>
                ${flagged.has(i + 1) && html`<span class="ln">line ${i + 1}</span>`}${m.text}
              </div>`)}
          </div>
          <form class="composer" onSubmit=${send}>
            <input value=${text} onChange=${(e) => setText(e.target.value)} placeholder=${asSeller ? "Type as the SELLER (demo)…" : "Message the seller…"} />
            <button class="btn">Send</button>
          </form>
          <label class="tiny muted row" style="margin-top:6px"><input type="checkbox" checked=${asSeller} onChange=${(e) => setAsSeller(e.target.checked)} /> Demo: write as the seller (try your own scam script)</label>
        </div>
      </div>
      <div class="grid">
        <${Checkout} listing=${listing} risk=${risk} checking=${checking} onCheck=${check} cfg=${cfg} />
      </div>
    </div>`;
}

function Checkout({ listing, risk, checking, onCheck, cfg }) {
  const [ack, setAck] = useState(false);
  const [contact, setContact] = useState("");
  const [contactOk, setContactOk] = useState(false);
  useEffect(() => { setAck(false); setContactOk(false); }, [risk]);
  const authorized = (o) => { toast(o.status === "PAUSED" ? "Payment authorized and paused for cooling-off." : "Payment authorized — money is on hold until delivery."); go("/order/" + o.id); };

  if (!risk) return html`
    <div class="panel">
      <h2>Checkout</h2>
      <div class="row between"><span>${listing.title}</span><b>${usd(listing.price)}</b></div>
      <div class="escrow">🔒 <span>Payments are <b>authorized, not charged</b>. PayPal holds the money until you confirm delivery, and the seller is paid out after that.</span></div>
      <button class="btn primary big" onClick=${onCheck} disabled=${checking}>
        ${checking ? html`<span class="spinner"></span> Checking this payment…` : `Continue to pay ${usd(listing.price)}`}
      </button>
      <p class="tiny muted" style="margin-bottom:0">Before any money moves, TrustLayer checks the listing and chat for scam tactics (rules + AI, about 1–2 s).</p>
    </div>`;

  const ai = risk.ai || {};
  if (risk.verdict === "PAUSE" && !(ack && contactOk)) return html`
    <div class="verdict PAUSE">
      <div class="head">⏸ We paused this payment</div>
      <div class="spell">${ai.spell_breaker || ai.explanation || "This conversation matches known scam patterns."}</div>
      ${(ai.evidence || []).length > 0 && html`<h3>What we saw in the chat</h3>
        ${ai.evidence.map((e) => html`<div class="quote" key=${e.line}><b>line ${e.line}</b>“${e.quote}”${e.why && html`<div class="tiny muted">${e.why}</div>`}</div>`)}`}
      <h3 style="margin-top:14px">Warning signs</h3>
      ${risk.signals.map((s) => html`<div class="signal" key=${s.key}><span class=${"dot " + (s.strong ? "strong" : "weak")}></span>${s.label}</div>`)}
      ${ai.safe_next_step && html`<div class="escrow">✅ <span><b>Safer move:</b> ${ai.safe_next_step}</span></div>`}
      <button class="btn danger big" onClick=${() => { toast("Good call. No money moved."); go("/"); }}>Don't pay — take me back</button>
      ${!ack
        ? html`<button class="btn ghost" style="width:100%;margin-top:8px" onClick=${() => setAck(true)}>I know this seller personally — continue with protection</button>`
        : html`<div class="panel" style="margin-top:12px;box-shadow:none">
            <h3>Continue with a safety net</h3>
            <p class="small muted" style="margin-top:0">Your payment will be <b>held for a ${Math.round((cfg?.cooling_off_seconds || 120) / 60)}-minute cooling-off period</b> (24 hours in production). You can cancel any time before delivery, and someone you trust gets a link to double-check it.</p>
            <input class="field" style="width:100%" placeholder="Trusted contact (name or email, e.g. Mom)" value=${contact} onChange=${(e) => setContact(e.target.value)} />
            <button class="btn primary" style="width:100%;margin-top:8px" disabled=${!contact.trim()} onClick=${() => setContactOk(true)}>Continue to PayPal</button>
          </div>`}
      <${RiskMeta} risk=${risk} />
    </div>`;

  return html`
    <div class=${"verdict " + risk.verdict}>
      <div class="head">${risk.verdict === "PAUSE" ? "⏸ Paused payment — protected checkout" : risk.verdict === "CAUTION" ? "⚠️ Proceed with care" : "✅ Looks safe"}</div>
      ${risk.verdict === "CLEAR" && html`<p class="small" style="margin:0">No scam tactics found in the listing or chat. ${ai.explanation || ""}</p>`}
      ${risk.verdict === "CAUTION" && html`<p class="small" style="margin:0">${ai.explanation}</p>${risk.signals.map((s) => html`<div class="signal" key=${s.key}><span class=${"dot " + (s.strong ? "strong" : "weak")}></span>${s.label}</div>`)}`}
      ${risk.verdict === "PAUSE" && html`<p class="small" style="margin:0">Cooling-off + trusted contact (<b>${contact}</b>) enabled. You can cancel until delivery.</p>`}
      <div class="escrow">🔒 <span>You're approving a <b>hold</b> of ${usd(listing.price)} — nothing is charged until you confirm delivery.</span></div>
      <${PayButtons} listing=${listing} cfg=${cfg} acknowledged=${risk.verdict === "PAUSE"} contact=${contact} onAuthorized=${authorized} />
      <${RiskMeta} risk=${risk} />
    </div>`;
}

function RiskMeta({ risk }) {
  const ai = risk.ai || {};
  return html`<div class="meta">
    Score ${risk.score} (rules ${risk.rule_score}${ai.risk !== undefined ? `, AI ${ai.risk}` : ""}) · tactic: <b>${ai.scam_type || "n/a"}</b>
    ${ai.provider ? ` · ${ai.model} via ${ai.provider} in ${ai.latency_ms} ms${ai.cached ? " (cached)" : ""}` : ` · AI unavailable, rules only`}
    ${ai.dropped_evidence ? ` · ${ai.dropped_evidence} unverifiable AI quote(s) discarded` : ""}
  </div>`;
}

function PayButtons({ listing, cfg, acknowledged, contact, onAuthorized }) {
  const ref = useRef(null);
  const orderRef = useRef(null);
  const [state, setState] = useState("loading");
  const [redirect, setRedirect] = useState(null);
  useEffect(() => {
    if (!cfg?.paypal_client_id) { setState("nosdk"); return; }
    let dead = false;
    loadPayPal(cfg.paypal_client_id).then((paypal) => {
      if (dead || !ref.current) return;
      ref.current.innerHTML = "";
      paypal.Buttons({
        style: { layout: "vertical", color: "gold", shape: "rect", label: "paypal", height: 45 },
        createOrder: async () => {
          const r = await api("/api/orders", { method: "POST", body: { listing_id: listing.id, acknowledged, trusted_contact: contact || null } });
          orderRef.current = r.order_id; return r.paypal_order_id;
        },
        onApprove: async () => {
          try { onAuthorized(await api(`/api/orders/${orderRef.current}/authorize`, { method: "POST" })); }
          catch (e) { toast(e.message, true); }
        },
        onCancel: () => toast("PayPal window closed — nothing was charged."),
        onError: (e) => toast("PayPal error: " + (e?.message || e), true),
      }).render(ref.current).then(() => !dead && setState("ready")).catch(() => setState("nosdk"));
    }).catch(() => !dead && setState("nosdk"));
    return () => { dead = true; };
  }, [listing.id, acknowledged, contact, cfg?.paypal_client_id]);

  const startRedirect = async () => {
    try {
      const r = await api("/api/orders", { method: "POST", body: { listing_id: listing.id, acknowledged, trusted_contact: contact || null } });
      setRedirect(r); window.open(r.approve_url, "_blank");
    } catch (e) { toast(e.message, true); }
  };
  const finishRedirect = async () => {
    try { onAuthorized(await api(`/api/orders/${redirect.order_id}/authorize`, { method: "POST" })); }
    catch (e) { toast(e.status === 502 ? "Not approved yet — finish approving in the PayPal tab first." : e.message, true); }
  };
  return html`<div>
    ${state === "loading" && html`<p class="small"><span class="spinner"></span> Loading PayPal…</p>`}
    <div ref=${ref}></div>
    <details class="tiny muted" style="margin-top:6px" open=${state === "nosdk"}>
      <summary>PayPal button not showing? Use redirect checkout</summary>
      ${!redirect
        ? html`<button class="btn" style="margin-top:6px" onClick=${startRedirect}>Open PayPal approval in a new tab</button>`
        : html`<div class="row" style="margin-top:6px"><a class="btn" href=${redirect.approve_url} target="_blank">Reopen PayPal</a><button class="btn primary" onClick=${finishRedirect}>I've approved it</button></div>`}
      <div style="margin-top:4px">Sandbox buyer login: use a PayPal sandbox <b>personal</b> account.</div>
    </details>
  </div>`;
}

// ---------------- orders ----------------
const STATUS_CHIP = { CREATED: "", PAUSED: "bad", HELD: "brand", CAPTURED: "ok", PAID_OUT: "ok", CANCELLED: "", CLOSED: "" };
function OrdersPage() {
  const [{ data, loading }] = useFetch("/api/orders");
  return html`
    <h1>My orders</h1><p class="sub">Every payment is a PayPal authorization held in escrow until you confirm delivery.</p>
    ${loading && html`<p><span class="spinner"></span></p>`}
    ${data && data.length === 0 && html`<div class="panel">No orders yet. <a href="#/">Buy something</a> to see the flow.</div>`}
    <div class="grid">
      ${(data || []).map((o) => html`
        <a class="panel card row between" href=${"#/order/" + o.id} key=${o.id}>
          <div class="row"><span style="font-size:30px">${o.listing?.emoji}</span>
            <div><b>${o.listing?.title}</b><div class="tiny muted">${o.id} · ${ago(o.created_at)} · @${o.seller?.handle}</div></div></div>
          <div class="row"><b>${usd(o.amount)}</b><span class=${"chip " + (STATUS_CHIP[o.status] || "")}>${o.status.replace("_", " ")}</span>
            ${o.issue?.status === "RESOLVED" && html`<span class="chip ok">resolved</span>`}</div>
        </a>`)}
    </div>`;
}

function Steps({ o }) {
  const order = ["CREATED", "HELD", "CAPTURED", "PAID_OUT"];
  const idx = o.status === "PAUSED" ? 1 : order.indexOf(o.status);
  const labels = ["Approved", o.status === "PAUSED" ? "Paused (cooling-off)" : "On hold (escrow)", "Captured", "Seller paid"];
  if (o.status === "CANCELLED") return html`<div class="steps"><div class="step done">Approved</div><div class="step done">On hold</div><div class="step bad">Cancelled · voided</div></div>`;
  return html`<div class="steps">${labels.map((l, i) => html`<div class=${"step " + (i <= idx ? (o.status === "PAUSED" && i === 1 ? "bad" : "done") : "")} key=${i}>${l}</div>`)}</div>`;
}

function OrderPage({ id }) {
  const [{ data: o, error }, reload] = useFetch(`/api/orders/${id}`);
  const [busy, setBusy] = useState(false);
  const [secs, setSecs] = useState(0);
  const [link, setLink] = useState(null);
  useEffect(() => { if (o) setSecs(o.seconds_left); }, [o]);
  useEffect(() => {
    if (!o || o.status !== "PAUSED") return;
    const t = setInterval(() => setSecs((s) => { if (s <= 1) { clearInterval(t); setTimeout(reload, 800); return 0; } return s - 1; }), 1000);
    return () => clearInterval(t);
  }, [o?.status, o?.id]);
  useEffect(() => { if (o?.status === "PAUSED") api(`/api/orders/${id}/contact-link`).then(setLink).catch(() => {}); }, [o?.status]);
  if (error) return html`<p class="chip bad">${error.message}</p>`;
  if (!o) return html`<p><span class="spinner"></span></p>`;
  const act = async (path, msg) => {
    setBusy(true);
    try { await api(`/api/orders/${id}/${path}`, { method: "POST" }); toast(msg); reload(); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const ids = [["PayPal order", o.paypal_order_id], ["Authorization (hold)", o.authorization_id], ["Capture", o.capture_id], ["Payout batch", o.payout_batch_id]].filter(([, v]) => v);
  return html`
    <p class="small"><a href="#/orders">← My orders</a></p>
    <div class="grid two">
      <div class="grid">
        <div class="panel">
          <div class="row between"><div class="row"><span style="font-size:34px">${o.listing?.emoji}</span>
            <div><h2 style="margin:0">${o.listing?.title}</h2><div class="tiny muted">${o.id} · seller @${o.seller?.handle}</div></div></div>
            <div class="price">${usd(o.amount)}</div></div>
          <${Steps} o=${o} />
          ${o.status === "PAUSED" && html`
            <div class="verdict PAUSE" style="margin-bottom:12px">
              <div class="head">⏸ Cooling-off in progress</div>
              <div class="countdown">${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}</div>
              <p class="small">Your ${usd(o.amount)} is <b>authorized but not charged</b>. Take a breath — scammers rely on urgency. Cancel now and the hold is voided instantly.</p>
              ${link && html`<p class="small">Trusted contact <b>${link.contact}</b> was sent a link to double-check. <a href=${"#/contact/" + link.token} target="_blank">Open their view ↗</a></p>`}
              <button class="btn danger big" disabled=${busy} onClick=${() => act("cancel", "Cancelled — the hold was voided. You were not charged.")}>Cancel payment (void hold)</button>
            </div>`}
          ${o.status === "HELD" && html`
            <div class="escrow">🔒 <span>${usd(o.amount)} is on hold with PayPal. The seller is paid only after you confirm delivery.</span></div>
            <div class="row">
              <button class="btn ok" disabled=${busy} onClick=${() => act("received", "Delivery confirmed — payment captured and seller paid out.")}>✓ Item received — release payment</button>
              <button class="btn" disabled=${busy} onClick=${() => act("cancel", "Order cancelled — hold voided.")}>Cancel order</button>
            </div>`}
          ${o.status === "CAPTURED" && html`<div class="row"><button class="btn ok" disabled=${busy} onClick=${() => act("received", "Seller paid out via PayPal Payouts.")}>Pay out seller</button></div>`}
          ${o.status === "CANCELLED" && html`<div class="verdict CLEAR"><div class="head">🛡️ No money moved</div><p class="small" style="margin:0">The PayPal authorization was voided. The buyer was never charged.</p></div>`}
          ${o.status === "PAID_OUT" && html`<div class="verdict CLEAR"><div class="head">✅ Complete</div><p class="small" style="margin:0">Captured ${usd(o.captured_amount)}${o.refunded_amount ? `, refunded ${usd(o.refunded_amount)}` : ""}. Seller received ${usd(o.payout_amount)} via PayPal Payouts after a ${usd(o.fee)} platform fee.</p></div>`}
          <hr class="sep" />
          <dl class="kv">
            ${ids.map(([k, v]) => html`<dt key=${k}>${k}</dt><dd class="mono">${v}</dd>`)}
            ${o.seller_protection && html`<dt>Seller Protection</dt><dd><span class=${"chip " + (o.seller_protection === "ELIGIBLE" ? "ok" : "")}>${o.seller_protection}</span></dd>`}
            ${o.risk && html`<dt>Pay-pause verdict</dt><dd><span class=${"chip " + (o.risk.verdict === "PAUSE" ? "bad" : o.risk.verdict === "CAUTION" ? "warn" : "ok")}>${o.risk.verdict}</span> score ${o.risk.score}</dd>`}
          </dl>
        </div>
        <div class="panel">
          <h2>Audit trail <span class="tiny muted">(hash-chained ledger)</span></h2>
          <div class="tablewrap"><table><tbody>
            ${(o.events || []).map((e) => html`<tr key=${e.seq}><td class="mono">#${e.seq}</td><td><b>${e.type}</b><div class="tiny muted">${ago(e.ts)}</div></td>
              <td class="tiny mono">${Object.entries(e.data).filter(([, v]) => v !== null && typeof v !== "object").slice(0, 4).map(([k, v]) => `${k}=${v}`).join("  ")}</td></tr>`)}
          </tbody></table></div>
        </div>
      </div>
      <div class="grid">
        ${["HELD", "CAPTURED", "PAID_OUT"].includes(o.status) || o.issue
          ? html`<${Resolution} order=${o} onChange=${reload} />`
          : html`<div class="panel"><h2>Problem with this order?</h2><p class="small muted">Once your payment is on hold you can report a problem here and get it settled before any dispute.</p></div>`}
      </div>
    </div>`;
}

// ---------------- resolution agent ----------------
function Resolution({ order, onChange }) {
  const [issue, setIssue] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef(null);
  useEffect(() => { if (order.issue) api(`/api/issues/${order.issue.id}`).then(setIssue).catch(() => {}); }, [order.issue?.id]);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [issue]);
  const send = async (e) => {
    e.preventDefault(); if (!text.trim()) return;
    setBusy(true);
    try { setIssue(await api(`/api/orders/${order.id}/issue`, { method: "POST", body: { text } })); setText(""); onChange(); }
    catch (err) { toast(err.message, true); } finally { setBusy(false); }
  };
  const accept = async () => {
    setBusy(true);
    try { setIssue(await api(`/api/issues/${issue.id}/accept`, { method: "POST" })); toast("Settled on PayPal — dispute avoided."); onChange(); }
    catch (err) { toast(err.message, true); } finally { setBusy(false); }
  };
  const last = issue?.transcript?.filter((t) => t.role === "agent").slice(-1)[0];
  const resolved = issue?.status === "RESOLVED";
  const starters = ["It arrived 4 days late and I missed my trip.", "The item has a crack that wasn't in the photos.", "I changed my mind, can I get a refund?"];
  return html`<div class="panel">
    <h2>🤝 Resolve a problem</h2>
    <p class="small muted" style="margin-top:-6px">An AI assistant for <b>${order.seller?.handle}</b> settles issues within the seller's policy — before anyone has to open a PayPal dispute.</p>
    <div class="chat" ref=${box}>
      ${(issue?.transcript || []).map((t, i) => html`<div class=${"bubble " + (t.role === "buyer" ? "buyer" : "agent")} key=${i}>${t.text}
        ${t.role === "agent" && t.issue_type && html`<div class="tiny muted" style="margin-top:4px">${t.issue_type} · dispute risk ${Math.round((t.dispute_risk || 0) * 100)}% · ${t.provider}</div>`}
        ${(t.policy_notes || []).map((n, j) => html`<div class="tiny" style="margin-top:4px;color:var(--warn)" key=${j}>⚖️ ${n}</div>`)}
      </div>`)}
      ${busy && html`<div class="bubble agent"><span class="spinner"></span></div>`}
    </div>
    ${!issue && html`<div class="row" style="margin-top:8px">${starters.map((s) => html`<button class="btn tiny" key=${s} onClick=${() => setText(s)}>${s}</button>`)}</div>`}
    ${last?.offer && ["partial_refund", "full_refund"].includes(last.offer.type) && !resolved && html`
      <div class="offer row between">
        <div><b>Offer: ${usd(last.offer.amount)} back</b><div class="tiny muted">${order.status === "HELD" ? "Released from your hold — never charged" : "Refunded to your PayPal via the Refunds API"}</div></div>
        <button class="btn ok" disabled=${busy} onClick=${accept}>Accept ${usd(last.offer.amount)}</button>
      </div>`}
    ${resolved && html`<div class="verdict CLEAR" style="margin-top:10px"><div class="head">✅ Resolved — dispute avoided</div>
      <p class="small" style="margin:0">${usd(issue.outcome.amount)} settled on PayPal (${issue.outcome.method}). Logged to the ledger and the seller's health score.</p></div>`}
    ${!resolved && html`<form class="composer" onSubmit=${send}>
      <input value=${text} onChange=${(e) => setText(e.target.value)} placeholder="Describe the problem…" disabled=${busy} />
      <button class="btn primary" disabled=${busy}>Send</button></form>`}
  </div>`;
}

// ---------------- trusted contact ----------------
function ContactPage({ token }) {
  const [{ data, error }, reload] = useFetch(`/api/contact/${token}`);
  const [busy, setBusy] = useState(false);
  if (error) return html`<p class="chip bad">${error.message}</p>`;
  if (!data) return html`<p><span class="spinner"></span></p>`;
  const { order: o, risk } = data;
  const vote = async (verdict) => {
    setBusy(true);
    try { await api(`/api/contact/${token}`, { method: "POST", body: { verdict } }); toast(verdict === "scam" ? "Stopped. The hold was voided." : "Thanks — the payment continues in escrow."); reload(); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const done = o.contact_verdict || !["PAUSED", "HELD"].includes(o.status);
  return html`<div style="max-width:560px;margin:0 auto">
    <div class="panel">
      <div class="tiny muted">📱 Trusted-contact view</div>
      <h1>Can you double-check a payment?</h1>
      <p>Someone who listed you as their trusted contact is about to pay <b>${usd(o.amount)}</b> to <b>@${o.seller?.handle}</b> for “${o.listing?.title}”. TrustLayer paused it because:</p>
      ${(risk.signals || []).slice(0, 4).map((s) => html`<div class="signal" key=${s.key}><span class=${"dot " + (s.strong ? "strong" : "weak")}></span>${s.label}</div>`)}
      ${risk.ai?.explanation && html`<p class="small muted">${risk.ai.explanation}</p>`}
      ${done
        ? html`<div class=${"verdict " + (o.status === "CANCELLED" ? "CLEAR" : "CAUTION")}><div class="head">${o.status === "CANCELLED" ? "🛡️ Payment stopped — no money moved" : "Payment continues in escrow"}</div></div>`
        : html`<div class="grid" style="grid-template-columns:1fr 1fr;margin-top:14px">
            <button class="btn danger big" disabled=${busy} onClick=${() => vote("scam")}>This looks like a scam — stop it</button>
            <button class="btn big" disabled=${busy} onClick=${() => vote("safe")}>I know them — it's fine</button></div>`}
    </div></div>`;
}

// ---------------- seller health ----------------
function Ring({ score, size = 96 }) {
  const r = 40, c = 2 * Math.PI * r, color = score >= 80 ? "var(--ok)" : score >= 60 ? "#e3a008" : "var(--bad)";
  return html`<svg class="ring" viewBox="0 0 100 100" style=${{ width: size, height: size }} role="img" aria-label=${"Health score " + score}>
    <circle cx="50" cy="50" r=${r} fill="none" stroke="var(--chip)" stroke-width="10" />
    <circle cx="50" cy="50" r=${r} fill="none" stroke=${color} stroke-width="10" stroke-linecap="round" stroke-dasharray=${`${(score / 100) * c} ${c}`} transform="rotate(-90 50 50)" />
    <text x="50" y="57" text-anchor="middle" font-size="24" font-weight="800" fill="var(--ink)">${score}</text></svg>`;
}
const statusChip = (s) => html`<span class=${"chip " + (s === "Healthy" ? "ok" : s === "Watch" ? "warn" : "bad")}>${s}</span>`;

function SellersPage() {
  const [{ data, loading }] = useFetch("/api/sellers");
  return html`<h1>Seller account health</h1>
    <p class="sub">Holds and limitations usually arrive without warning. TrustLayer watches the public signals that trigger reviews and explains them before they bite.</p>
    ${loading && html`<p><span class="spinner"></span></p>`}
    <div class="grid cards">${(data || []).map((s) => html`
      <a class="panel card row" href=${"#/sellers/" + s.seller.id} key=${s.seller.id} style="gap:14px">
        <${Ring} score=${s.score} size=${72} />
        <div><b>${s.seller.name}</b><div class="tiny muted">@${s.seller.handle} · ${s.kpis.transactions_30d} sales / 30d</div>
          <div class="row" style="margin-top:6px">${statusChip(s.status)}<span class="chip">disputes ${s.kpis.dispute_rate}%</span></div></div>
      </a>`)}</div>`;
}

function SellerPage({ id }) {
  const [{ data: m, error }] = useFetch(`/api/sellers/${id}/health`);
  const [{ data: ex, loading: exLoading }] = useFetch(`/api/sellers/${id}/explain`);
  if (error) return html`<p class="chip bad">${error.message}</p>`;
  if (!m) return html`<p><span class="spinner"></span></p>`;
  const k = m.kpis, max = Math.max(1, ...m.series.map((d) => d.orders));
  const scaleMax = Math.max(2.5, k.dispute_rate_without_prevention + 0.3);
  const pct = (v) => `${Math.min(100, (v / scaleMax) * 100)}%`;
  return html`
    <p class="small"><a href="#/sellers">← All sellers</a></p>
    <div class="panel row" style="gap:20px;margin-bottom:16px">
      <${Ring} score=${m.score} />
      <div style="flex:1;min-width:240px">
        <div class="row">${statusChip(m.status)}<span class="tiny muted">@${m.seller.handle} · joined ${m.seller.joined_days_ago} days ago</span></div>
        <h1 style="margin-top:4px">${m.seller.name}</h1>
        ${exLoading ? html`<p class="small"><span class="spinner"></span> Writing a plain-English explanation…</p>`
          : ex && html`<p style="margin:4px 0 0"><b>${ex.headline}</b> ${ex.summary}</p>`}
      </div>
    </div>
    <div class="grid kpis" style="margin-bottom:16px">
      <div class="kpi"><div class="v">${k.transactions_30d}</div><div class="l">sales, last 30 days</div></div>
      <div class="kpi"><div class="v" style=${{ color: k.dispute_rate >= m.thresholds.dispute_line ? "var(--bad)" : "inherit" }}>${k.dispute_rate}%</div><div class="l">dispute rate</div></div>
      <div class="kpi"><div class="v" style="color:var(--ok)">${k.prevented_30d}</div><div class="l">disputes avoided</div></div>
      <div class="kpi"><div class="v">${k.refund_rate}%</div><div class="l">refund rate</div></div>
      <div class="kpi"><div class="v">${k.volume_spike_x ?? "–"}×</div><div class="l">this week vs baseline</div></div>
      <div class="kpi"><div class="v">${usd(k.gross_30d).replace(".00", "")}</div><div class="l">gross, 30 days</div></div>
    </div>
    <div class="grid two">
      <div class="grid">
        <div class="panel">
          <h2>Dispute rate vs the ${m.thresholds.dispute_line}% monitoring line</h2>
          <div class="small muted">Now</div>
          <div class="bar"><div class="fill" style=${{ width: pct(k.dispute_rate), background: k.dispute_rate >= m.thresholds.dispute_line ? "var(--bad)" : "var(--brand)" }}></div>
            <div class="line" style=${{ left: pct(m.thresholds.dispute_line) }}><span>${m.thresholds.dispute_line}% line</span></div></div>
          <div class="small muted" style="margin-top:14px">Without TrustLayer's early resolution</div>
          <div class="bar"><div class="fill" style=${{ width: pct(k.dispute_rate_without_prevention), background: "#c7d2e2" }}></div>
            <div class="line" style=${{ left: pct(m.thresholds.dispute_line) }}></div></div>
          <p class="tiny muted">Card networks (e.g. Visa's VAMP program) flag merchants above this ratio. TrustLayer can't see PayPal's internal models; these are the public signals.</p>
        </div>
        <div class="panel">
          <h2>Daily sales, last 30 days</h2>
          <svg viewBox="0 0 300 110" preserveAspectRatio="none" style="width:100%;height:150px" role="img" aria-label="Daily sales chart">
            ${m.series.map((d, i) => { const h = (d.orders / max) * 90; return html`<g key=${i}>
              <rect x=${i * 10 + 1} y=${100 - h} width="8" height=${h} rx="2" fill=${i >= 23 ? "var(--brand)" : "#b9cbe6"}><title>${d.orders} sales, ${d.disputes} disputes</title></rect>
              ${d.disputes > 0 && html`<circle cx=${i * 10 + 5} cy=${100 - h - 6} r="3" fill="var(--bad)" />`}</g>`; })}
            <line x1="0" y1="100" x2="300" y2="100" stroke="var(--line)" />
          </svg>
          <div class="tiny muted">Dark bars = last 7 days · red dots = days with disputes</div>
        </div>
      </div>
      <div class="grid">
        <div class="panel"><h2>What we found</h2>
          ${m.findings.length === 0 && html`<p class="muted">No warning signs.</p>`}
          ${m.findings.map((f, i) => html`<div class="finding" key=${i}><span class=${"lvl " + f.level}></span><div><b>${f.title}</b><div class="small muted">${f.detail}</div></div></div>`)}
        </div>
        ${ex?.actions?.length > 0 && html`<div class="panel"><h2>Do this next</h2><ol style="margin:0;padding-left:20px">${ex.actions.map((a, i) => html`<li key=${i} style="margin:6px 0">${a}</li>`)}</ol>
          <div class="tiny muted" style="margin-top:8px">Written by ${ex.model} via ${ex.provider}</div></div>`}
      </div>
    </div>`;
}

// ---------------- ledger ----------------
function LedgerPage() {
  const [{ data }, reload] = useFetch("/api/ledger");
  const [busy, setBusy] = useState(false);
  const tamper = async () => { setBusy(true); try { const r = await api("/api/ledger/tamper", { method: "POST" }); toast(`Edited record #${r.tampered_seq} behind the app's back…`); reload(); } finally { setBusy(false); } };
  const reset = async () => { if (!confirm("Reset all demo data (orders, ledger)?")) return; await api("/api/admin/reset", { method: "POST" }); toast("Demo data reset."); reload(); };
  const v = data?.verify;
  return html`<h1>Ledger</h1><p class="sub">Every PayPal money movement and every AI decision, SHA-256 hash-chained. Edit any record and verification names the break.</p>
    <div class="panel row between" style="margin-bottom:16px">
      <div class="row">${v && (v.ok ? html`<span class="chip ok">✓ Chain intact · ${v.count} records</span>` : html`<span class="chip bad">✗ Tampering detected at record #${v.broken_at} (${v.type})</span>`)}</div>
      <div class="row"><button class="btn" onClick=${reload}>Verify</button><button class="btn" disabled=${busy} onClick=${tamper}>Tamper with a record (demo)</button><button class="btn ghost" onClick=${reset}>Reset demo</button></div>
    </div>
    <div class="panel tablewrap"><table>
      <thead><tr><th>#</th><th>Event</th><th>Order</th><th>Details</th><th>Hash</th></tr></thead>
      <tbody>${(data?.events || []).map((e) => html`<tr key=${e.seq} style=${{ background: v && !v.ok && e.seq === v.broken_at ? "var(--bad-soft)" : "" }}>
        <td class="mono">${e.seq}</td><td><b>${e.type}</b><div class="tiny muted">${ago(e.ts)}</div></td>
        <td class="mono">${e.order_id ? html`<a href=${"#/order/" + e.order_id}>${e.order_id}</a>` : e.seller_id || ""}</td>
        <td class="tiny mono">${Object.entries(e.data || {}).filter(([, x]) => x !== null && typeof x !== "object").slice(0, 5).map(([a, b]) => `${a}=${b}`).join("  ")}</td>
        <td class="mono tiny">${e.hash.slice(0, 12)}…</td></tr>`)}</tbody></table></div>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
