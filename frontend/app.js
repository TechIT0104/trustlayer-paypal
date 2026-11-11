/* TrustLayer frontend: no-build React (htm), served by FastAPI. */
const { useState, useEffect, useRef, useCallback } = React;

// htm -> React adapter so templates can use plain HTML habits (class=, style="a:b", stroke-width=)
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

// ---------------- icons (stroke icons, Lucide-style geometry) ----------------
const ICONS = {
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
  shieldCheck: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  shieldAlert: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  pause: '<circle cx="12" cy="12" r="10"/><path d="M10 15V9"/><path d="M14 15V9"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  xCircle: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  arrowLeft: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
  arrowRight: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  chevronRight: '<path d="m9 18 6-6-6-6"/>',
  message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  store: '<path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7"/><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4"/><path d="M2 7h20"/><path d="M22 7v3a2 2 0 0 1-2 2a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 16 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 12 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 8 12a2.7 2.7 0 0 1-1.59-.63.7.7 0 0 0-.82 0A2.7 2.7 0 0 1 4 12a2 2 0 0 1-2-2V7"/>',
  receipt: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
  box: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
  camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
  phone: '<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>',
  gamepad: '<path d="M6 11h4"/><path d="M8 9v4"/><path d="M15 12h.01"/><path d="M18 10h.01"/><path d="M17.32 5H6.68a4 4 0 0 0-3.98 3.59C2.6 9.42 2 14.46 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.41-1.41A2 2 0 0 1 9.83 16h4.34a2 2 0 0 1 1.41.59L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.55-.6-6.58-.69-7.26A4 4 0 0 0 17.32 5z"/>',
  chair: '<path d="M7 3h10a1 1 0 0 1 1 1v8H6V4a1 1 0 0 1 1-1z"/><path d="M5 12h14"/><path d="M12 12v6"/><path d="M8 21l4-3 4 3"/><path d="M4 9v3"/><path d="M20 9v3"/>',
  headphones: '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  send: '<path d="M14.54 21.69a.5.5 0 0 0 .94-.02l6.5-19a.5.5 0 0 0-.64-.64l-19 6.5a.5.5 0 0 0-.02.94l7.93 3.18a2 2 0 0 1 1.11 1.11z"/><path d="m21.85 2.15-10.94 10.94"/>',
  sparkles: '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/>',
  dollar: '<path d="M12 2v20"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  wallet: '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  hash: '<path d="M4 9h16"/><path d="M4 15h16"/><path d="M10 3 8 21"/><path d="M16 3l-2 18"/>',
  trending: '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
};
function Icon({ name, size = 16, sw = 1.75, cls = "" }) {
  return html`<svg class=${"icon " + cls} width=${size} height=${size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width=${sw} stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
    dangerouslySetInnerHTML=${{ __html: ICONS[name] || ICONS.box }} />`;
}
const CATEGORY_ICON = { Cameras: "camera", Phones: "phone", Gaming: "gamepad", Furniture: "chair", Audio: "headphones" };

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
const usd = (v) => "$" + Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usd0 = (v) => "$" + Math.round(Number(v || 0)).toLocaleString("en-US");
const ago = (ts) => {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(ts * 1000).toLocaleDateString();
};
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const initials = (s) => (s || "?").replace(/[^A-Za-z0-9 _]/g, "").split(/[\s_]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";

let toastSet = null;
function toast(msg, err = false) { toastSet && toastSet({ msg, err, id: Math.random() }); }

function useRoute() {
  const [hash, setHash] = useState(location.hash || "#/");
  useEffect(() => {
    const f = () => { setHash(location.hash || "#/"); window.scrollTo(0, 0); };
    addEventListener("hashchange", f); return () => removeEventListener("hashchange", f);
  }, []);
  return hash.slice(1).split("/").filter(Boolean);
}
const go = (path) => { location.hash = path; };

function useFetch(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const load = useCallback(() => {
    if (!path) return Promise.resolve();
    return api(path).then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => setState((s) => ({ data: s.data, error, loading: false })));
  }, [path]);
  useEffect(() => { setState({ data: null, error: null, loading: true }); load(); }, [path]);
  return [state, load];
}

// PayPal JS SDK, loaded once with intent=authorize so approvals create holds, not charges.
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

// ---------------- shared bits ----------------
const ORDER_STATUS = {
  CREATED: ["Awaiting approval", ""], HELD: ["On hold", "accent"], PAUSED: ["Paused", "danger"],
  CAPTURED: ["Captured", "success"], PAID_OUT: ["Completed", "success"], CANCELLED: ["Cancelled", ""], CLOSED: ["Closed", ""],
};
const StatusBadge = ({ status }) => { const [l, c] = ORDER_STATUS[status] || [status, ""]; return html`<span class=${"badge " + c}><span class="dot"></span>${l}</span>`; };
const VERDICT = {
  CLEAR: { label: "No risk found", tone: "success", icon: "shieldCheck" },
  CAUTION: { label: "Proceed with care", tone: "warning", icon: "alert" },
  PAUSE: { label: "Payment paused", tone: "danger", icon: "shieldAlert" },
};
const VerdictBadge = ({ v }) => html`<span class=${"badge " + VERDICT[v].tone}><span class="dot"></span>${v === "CLEAR" ? "Clear" : v === "CAUTION" ? "Caution" : "Paused"}</span>`;
const Spinner = () => html`<span class="spinner"></span>`;
const Loading = ({ rows = 3 }) => html`<div class="stack">${Array.from({ length: rows }).map((_, i) => html`<div class="skeleton" key=${i} style="height:72px"></div>`)}</div>`;
const ErrorBox = ({ error }) => html`<div class="callout danger"><${Icon} name="alert" /><div>${error.message}</div></div>`;
function PageHead({ title, sub, right }) {
  return html`<div class="page-head"><div><h1>${title}</h1>${sub && html`<p>${sub}</p>`}</div>${right}</div>`;
}
function Back({ to, label }) { return html`<a class="back" href=${to}><${Icon} name="arrowLeft" /> ${label}</a>`; }

// ---------------- shell ----------------
function App() {
  const route = useRoute();
  const [cfg, setCfg] = useState(null);
  const [t, setT] = useState(null);
  toastSet = setT;
  useEffect(() => { if (!t) return; const id = setTimeout(() => setT(null), 4500); return () => clearTimeout(id); }, [t]);
  useEffect(() => { api("/api/config").then(setCfg).catch(() => setCfg({})); }, []);
  const [page, a] = route;
  let body;
  if (!page) body = html`<${Landing} />`;
  else if (page === "market") body = html`<${Market} />`;
  else if (page === "listing") body = html`<${ListingPage} id=${a} cfg=${cfg} />`;
  else if (page === "orders") body = html`<${OrdersPage} />`;
  else if (page === "order") body = html`<${OrderPage} id=${a} />`;
  else if (page === "contact") body = html`<${ContactPage} token=${a} />`;
  else if (page === "sellers") body = a ? html`<${SellerPage} id=${a} />` : html`<${SellersPage} />`;
  else if (page === "ledger") body = html`<${LedgerPage} />`;
  else if (page === "plus" || page === "subscriptions") body = html`<${SubscriptionsPage} cfg=${cfg} />`;
  else body = html`<div class="empty">Page not found. <a href="#/market">Back to marketplace</a></div>`;
  const tab = (p, icon, label, also = []) => {
    const on = (page || "") === p || also.includes(page);
    return html`<a class=${on ? "active" : ""} href=${"#/" + p}><${Icon} name=${icon} />${label}</a>`;
  };
  return html`
    <header class="topbar"><div class="container">
      <a class="brand" href="#/"><span class="brand-mark"><${Icon} name="shield" size=${17} sw=${2} /></span>TrustLayer</a>
      <nav class="tabs">
        ${tab("", "sparkles", "Overview")}
        ${tab("market", "store", "Marketplace", ["listing"])}
        ${tab("orders", "receipt", "Orders", ["order"])}
        ${tab("sellers", "activity", "Seller health")}
        ${tab("subscriptions", "receipt", "Subscriptions", ["plus"])}
        ${tab("ledger", "file", "Audit log")}
      </nav>
      <span class="env badge warning"><span class="dot"></span>PayPal Sandbox</span>
    </div></header>
    <main class=${page ? "" : "landing"}>${page ? html`<div class="container">${body}</div>` : body}</main>
    ${t && html`<div class=${"toast " + (t.err ? "err" : "")} key=${t.id} role="status"><${Icon} name=${t.err ? "alert" : "checkCircle"} />${t.msg}</div>`}`;
}

// Sandbox test buyer for reviewers. Sandbox accounts hold only test money; this is not a real PayPal account.
const SANDBOX_BUYER = { email: "sb-hbn8w53835765@personal.example.com", password: "YFp3sUZ?" };
function CopyField({ label, value }) {
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); toast(`${label} copied.`); }
    catch { toast("Copy failed. Select the text instead.", true); }
  };
  return html`<div class="cred"><span class="xs text-2">${label}</span><code class="mono">${value}</code>
    <button class="btn sm ghost" onClick=${copy} aria-label=${"Copy " + label}>Copy</button></div>`;
}
function SandboxLogin({ compact = false }) {
  return html`<div class=${"sandbox-login" + (compact ? " compact" : "")}>
    <div class="row" style="gap:8px;flex-wrap:nowrap;align-items:flex-start"><${Icon} name="user" size=${15} />
      <div><b>PayPal sandbox login</b>${compact ? "" : html`<span class="text-2"> for the PayPal window (checkout and subscriptions)</span>`}
        <div class="xs text-2">Test buyer with sandbox money only. Not a real PayPal account.</div></div></div>
    <${CopyField} label="Email" value=${SANDBOX_BUYER.email} />
    <${CopyField} label="Password" value=${SANDBOX_BUYER.password} />
  </div>`;
}

// ---------------- landing (overview for reviewers) ----------------
const REPO = "https://github.com/TechIT0104/trustlayer-paypal";
const scrollToId = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

const L_PROBLEMS = [
  { icon: "shieldAlert", moment: "Before paying", stat: "71%",
    text: "of UK authorised-push-payment fraud cases are purchase scams: £576M lost in 2025. If you were tricked into paying, it isn't “unauthorized”, so it is rarely refunded." },
  { icon: "message", moment: "When something goes wrong", stat: "43.8%",
    text: "of chargebacks are friendly fraud, and 85% of people who file one say bad service pushed them to it. A small fix early would have saved both sides." },
  { icon: "activity", moment: "For sellers", stat: "1.5%",
    text: "is the dispute ratio at which card networks flag a merchant. About 1 in 5 PayPal reviews mention sudden holds with no explanation." },
  { icon: "clock", moment: "Every month after", stat: "Trial traps",
    text: "A free trial quietly turns into a charge for something never used, and cancelling is hidden. The buyer's only lever is a chargeback, which hurts the seller too." },
];
const L_TODAY = [
  ["Before paying", "Generic warnings about Friends & Family. Protection applies after a claim. A few banks (Revolut) run AI scam checks inside the payment flow.",
    "Not about this chat, and the money has already left.", "Reads this chat, quotes the risky lines, and holds the money (authorize, not capture) with a cooling-off and a trusted contact."],
  ["Something goes wrong", "Open a dispute, escalate to a claim, wait. Or a chargeback through the card network.",
    "Slow and adversarial. The seller pays fees even when a small refund would have done.", "An assistant offers a fix within the seller's own policy. Code caps it. Accepting runs a partial capture or refund on PayPal."],
  ["Seller account", "Holds and limitations, explained after the fact. Dispute ratios watched by card networks.",
    "Sellers find out they are at risk when it is too late.", "A live health score against the 1.5% line, explained in plain English with next steps."],
  ["Subscriptions", "Reminders are optional. Cancellation flows are designed by the merchant.",
    "Dark patterns turn into chargebacks.", "An honest pre-charge reminder, one-click cancel, and an AI terms review where code blocks the traps."],
];
const L_JOURNEY = [
  { t: "Chat and checkout", ai: "Pay-pause reads the listing and chat with rules, an LLM that must quote the exact lines, and a model we fine-tuned.", pp: "Orders v2, intent AUTHORIZE", href: "#/listing/L2" },
  { t: "Money on hold", ai: "Risky payments get a cooling-off timer, and someone the buyer trusts can stop them. Nothing is charged.", pp: "Authorizations: void, reauthorize", href: "#/listing/L2" },
  { t: "Something goes wrong", ai: "A resolution assistant offers a fix within the seller's refund policy. Code enforces the limit.", pp: "Partial capture, refunds", href: "#/listing/L1" },
  { t: "Seller gets paid", ai: "Payout after delivery. Seller health explains dispute risk in plain English, before a hold.", pp: "Payouts, Webhooks", href: "#/sellers/gadgethub" },
  { t: "Every month after", ai: "A real trial, a truthful reminder before the first charge, and one-click cancel. Sellers get a terms review.", pp: "Subscriptions, billing plans", href: "#/subscriptions" },
];
const L_TOUR = [
  ["Pay-pause", "#/listing/L2", "Open the iPhone listing and press Continue to payment.", "The payment is paused. The flagged chat lines are highlighted, and the AI's quotes are checked against the real chat."],
  ["Cooling-off and trusted contact", "#/listing/L2", "Choose “I know this seller”, add a contact, approve in the PayPal popup.", "A countdown runs while PayPal only holds the money. The contact presses Stop and the authorization is voided: $0 charged."],
  ["Resolution before dispute", "#/listing/L1", "Buy the Canon camera, then report “arrived 4 days late” in the order.", "An offer within the seller's policy. Accepting captures less of the hold on PayPal. No dispute is ever opened."],
  ["Seller health", "#/sellers/gadgethub", "Open GadgetHub Outlet.", "Over the 1.5% dispute line, what it would be without early resolution, and plain-English next steps."],
  ["Honest subscriptions", "#/subscriptions", "Start a trial, simulate five days, read the reminder, cancel.", "The reminder says whether you used it. Cancelling is one confirmation. Sellers' trap terms are blocked."],
  ["Audit log", "#/ledger", "Press Verify chain, then Simulate tampering.", "Every PayPal call and AI decision is hash-chained. The edited record is found and highlighted."],
];

function Landing() {
  return html`
    <section class="l-hero"><div class="container l-hero-grid">
      <div>
        <span class="badge accent"><span class="dot"></span>PayPal AI Hackathon 2026 · running on PayPal Sandbox</span>
        <h1 class="l-h1">AI that protects the whole life of a payment.</h1>
        <p class="l-lead">Card fraud tools look at the card. Scams, disputes and subscription traps happen in the
          conversation around the payment. TrustLayer reads that context, has PayPal <b>hold</b> the money while it decides,
          and settles problems before they become disputes.</p>
        <div class="row" style="gap:12px;margin-top:28px">
          <a class="btn primary lg" href="#/market">Open the live marketplace<${Icon} name="arrowRight" /></a>
          <button class="btn lg" onClick=${() => scrollToId("problem")}>Why we built it</button>
        </div>
        <div class="l-trust">
          <span><${Icon} name="lock" size=${14} />Authorize first, capture later</span>
          <span><${Icon} name="file" size=${14} />AI must quote its evidence</span>
          <span><${Icon} name="shieldCheck" size=${14} />Code enforces every money limit</span>
        </div>
      </div>
      <div class="l-mock" aria-label="Example: a scam chat paused before payment">
        <div class="l-mock-head"><span class="avatar">Q</span><div><b>quickdeals_2291</b><div class="xs text-2">Joined 5 days ago · 0 sales</div></div><span class="badge warning" style="margin-left:auto">New seller</span></div>
        <div class="l-mock-chat">
          <div class="msg"><div class="bubble">yes brand new sealed, my company gave it as bonus</div></div>
          <div class="msg mine"><div class="bubble">Can I just pay with the checkout on the site?</div></div>
          <div class="msg flagged"><div><div class="bubble">send $420 on paypal friends and family and I ship today</div>
            <div class="lineref"><${Icon} name="alert" size=${12} />Line 4 · quoted by the AI, verified</div></div></div>
          <div class="msg flagged"><div><div class="bubble">please no goods and services</div>
            <div class="lineref"><${Icon} name="alert" size=${12} />Line 5 · rule: avoids buyer protection</div></div></div>
        </div>
        <div class="l-mock-verdict">
          <span class="ic danger" style="width:36px;height:36px;border-radius:10px;display:grid;place-items:center"><${Icon} name="shieldAlert" size=${18} /></span>
          <div><b>Payment paused</b><div class="xs text-2">Tactic: protection bypass · $420 held by PayPal · $0 charged</div></div>
        </div>
      </div>
    </div></section>

    <section class="l-sec" id="problem"><div class="container">
      <div class="l-head"><span class="eyebrow">The problem</span>
        <h2 class="l-h2">Trust breaks at four moments, and the money usually moves before anyone checks.</h2></div>
      <div class="l-problems">${L_PROBLEMS.map((p) => html`<div class="card l-problem" key=${p.moment}>
        <div class="row" style="gap:8px"><span class="ic accent l-ic"><${Icon} name=${p.icon} size=${16} /></span><span class="sm" style="font-weight:600">${p.moment}</span></div>
        <div class=${"l-stat" + (p.stat.length > 6 ? " word" : "")}>${p.stat}</div><p class="sm text-2" style="margin:0">${p.text}</p></div>`)}</div>
      <p class="xs text-3" style="margin-top:14px">Sources: UK Finance / PSR APP-fraud statistics 2025; Chargebacks911 2026 field report; Visa VAMP threshold (Apr 2026); public PayPal review analysis. Full list in the README.</p>
    </div></section>

    <section class="l-sec alt" id="today"><div class="container">
      <div class="l-head"><span class="eyebrow">Today's answers, and where we stand</span>
        <h2 class="l-h2">Existing tools react after the money has moved. TrustLayer acts in the moment, with evidence.</h2></div>
      <div class="card table-wrap"><table class="table l-table">
        <thead><tr><th>Moment</th><th>What exists today</th><th>The gap</th><th class="l-us">TrustLayer</th></tr></thead>
        <tbody>${L_TODAY.map(([m, today, gap, us]) => html`<tr key=${m}><td class="cell-main" style="white-space:nowrap">${m}</td>
          <td class="text-2">${today}</td><td class="text-2">${gap}</td><td class="l-us"><div class="row" style="gap:8px;align-items:flex-start;flex-wrap:nowrap"><${Icon} name="checkCircle" cls="l-ok" />${us}</div></td></tr>`)}</tbody>
      </table></div>
    </div></section>

    <section class="l-sec" id="idea"><div class="container">
      <div class="l-head"><span class="eyebrow">The idea</span>
        <h2 class="l-h2">Authorize first. Let AI decide with evidence. Then move the money.</h2>
        <p class="l-sub">PayPal already has the primitive most checkouts never use: an authorization holds the buyer's money without
          charging it. That hold gives AI time to look, to ask a trusted person, or to settle a problem, and it can be
          voided at no cost. We wrap that hold in three rules.</p></div>
      <div class="l-three">
        <div class="card card-body"><span class="l-num">1</span><h3>Hold, don't charge</h3><p class="sm text-2">Every checkout is a PayPal authorization. Until the buyer is safe and the item arrives, the money can still be voided or partly captured.</p></div>
        <div class="card card-body"><span class="l-num">2</span><h3>Evidence, not opinions</h3><p class="sm text-2">The AI must quote the exact chat lines behind a warning, and code checks every quote. Invented evidence is thrown away.</p></div>
        <div class="card card-body"><span class="l-num">3</span><h3>AI advises, code moves money</h3><p class="sm text-2">Refund limits, blocked subscription terms and payouts are enforced in code, and every step lands in a tamper-evident log.</p></div>
      </div>
    </div></section>

    <section class="l-sec alt" id="journey"><div class="container">
      <div class="l-head"><span class="eyebrow">The story</span>
        <h2 class="l-h2">One payment, five moments, AI at each one.</h2>
        <p class="l-sub">Follow a single payment through its life. At each moment TrustLayer adds one AI safeguard on top of a real PayPal API call.</p></div>
      <ol class="l-journey">${L_JOURNEY.map((j, i) => html`<li key=${j.t}>
        <span class="l-node">${i + 1}</span>
        <div class="l-jt">${j.t}</div>
        <p class="sm text-2">${j.ai}</p>
        <div class="l-pp"><span class="xs text-3">PayPal</span> <span class="xs">${j.pp}</span></div>
        <a class="sm l-try" href=${j.href}>See it<${Icon} name="chevronRight" size=${14} /></a></li>`)}</ol>
      <div class="callout info" style="margin-top:20px"><${Icon} name="hash" /><div>Underneath every moment: each PayPal call and AI decision is written to a SHA-256 hash chain, so any edit afterwards is detected. <a href="#/ledger">Open the audit log</a></div></div>
    </div></section>

    <section class="l-sec" id="tour"><div class="container">
      <div class="l-head"><span class="eyebrow">About this site</span>
        <h2 class="l-h2">A working marketplace, not a mock-up. Here is what to try.</h2>
        <p class="l-sub">Five sellers and five listings, two of them scams. Every button calls the real PayPal Sandbox and a live AI model.
          Each step below takes under a minute.</p></div>
      <div style="max-width:560px;margin-bottom:20px"><${SandboxLogin} /></div>
      <div class="l-tour">${L_TOUR.map(([t, href, doIt, see], i) => html`<a class="card link l-step" href=${href} key=${t}>
        <span class="l-num">${i + 1}</span>
        <div style="flex:1;min-width:0"><div class="row spread"><b>${t}</b><${Icon} name="arrowRight" size=${16} cls="text-3" /></div>
          <div class="sm" style="margin-top:6px"><span class="text-3">Do</span> ${doIt}</div>
          <div class="sm text-2" style="margin-top:4px"><span class="text-3">You'll see</span> ${see}</div></div></a>`)}</div>
    </div></section>

    <section class="l-sec alt" id="results"><div class="container">
      <div class="l-head"><span class="eyebrow">Measured, not claimed</span>
        <h2 class="l-h2">Scored once on 80 chats no part of the system was tuned on.</h2></div>
      <div class="l-results">
        <div class="card stat"><div class="l">Scams paused</div><div class="v">40 / 40</div><div class="h">every scam held before money moved</div></div>
        <div class="card stat"><div class="l">Honest buyers wrongly paused</div><div class="v">3 / 40</div><div class="h">each one analysed in NUMBERS.md</div></div>
        <div class="card stat"><div class="l">If every LLM is down</div><div class="v">80%</div><div class="h">of scams still paused, vs 35% for rules alone</div></div>
        <div class="card stat"><div class="l">Our fine-tuned model</div><div class="v">~80 ms</div><div class="h">on a CPU, no API key, names the tactic</div></div>
      </div>
      <p class="sm text-2" style="margin-top:14px">DistilBERT fine-tuned from a public scam classifier on marketplace chats, with a second head that names the tactic.
        <a href=${REPO + "/blob/main/NUMBERS.md"} target="_blank" rel="noopener">Every number and every miss</a>.</p>
    </div></section>

    <section class="l-cta"><div class="container">
      <h2 class="l-h2" style="color:#fff">See it work in five minutes.</h2>
      <p>Start with the iPhone listing. It is a scam.</p>
      <div class="row" style="gap:12px;justify-content:center;margin-top:20px">
        <a class="btn lg" href="#/listing/L2">Start with the scam listing<${Icon} name="arrowRight" /></a>
        <a class="btn lg l-ghost" href=${REPO} target="_blank" rel="noopener">Source on GitHub<${Icon} name="external" size=${15} /></a>
      </div>
      <p class="xs" style="margin-top:28px;opacity:.7">PayPal Orders v2, Payments v2, Payouts, Subscriptions, Webhooks, JS SDK · Groq gpt-oss-120b, Gemini, fine-tuned DistilBERT · FastAPI, React</p>
    </div></section>`;
}

// ---------------- marketplace ----------------
function Market() {
  const [{ data, loading, error }] = useFetch("/api/listings");
  return html`
    <${PageHead} title="Marketplace" sub="Buy from independent sellers. Every payment is screened before money moves, held by PayPal until delivery, and protected if something goes wrong." />
    <div class="steps3">
      <div><span class="ic"><${Icon} name="shieldCheck" size=${18} /></span><div><b>Screened before you pay</b><span>The listing and chat are checked for known scam tactics.</span></div></div>
      <div><span class="ic"><${Icon} name="lock" size=${18} /></span><div><b>Held until delivery</b><span>PayPal authorizes the payment; the seller is paid after you confirm.</span></div></div>
      <div><span class="ic"><${Icon} name="message" size=${18} /></span><div><b>Resolved before disputes</b><span>Problems are settled within the seller's policy in minutes.</span></div></div>
    </div>
    ${error && html`<${ErrorBox} error=${error} />`}
    ${loading ? html`<div class="grid cols-listings">${[1, 2, 3, 4].map((i) => html`<div class="skeleton" key=${i} style="height:300px"></div>`)}</div>` : html`
    <div class="grid cols-listings">
      ${(data || []).map((l) => html`
        <a class="card link listing-card" href=${"#/listing/" + l.id} key=${l.id}>
          <div style="padding:12px 12px 0"><div class=${"tile t-" + l.category}><${Icon} name=${CATEGORY_ICON[l.category] || "box"} size=${44} sw=${1.25} /></div></div>
          <div class="body">
            <div class="xs text-2">${l.category} · ${l.condition}</div>
            <div class="title">${l.title}</div>
            <div style="margin:6px 0 12px"><span class="price">${usd0(l.price)}</span><span class="ref">typically ${usd0(l.ref_price)}</span></div>
            <div class="row spread">
              <div class="seller-line"><span class="avatar">${initials(l.seller_name)}</span>${l.handle}</div>
              ${l.completed_sales > 0
                ? html`<span class="xs text-2 num">${l.rating} · ${l.completed_sales} sales</span>`
                : html`<span class="badge warning">New seller</span>`}
            </div>
          </div>
        </a>`)}
    </div>`}`;
}

// ---------------- listing + checkout ----------------
function ListingPage({ id, cfg }) {
  const [{ data, loading, error }, reload] = useFetch(`/api/listings/${id}`);
  const [risk, setRisk] = useState(null);
  const [checking, setChecking] = useState(false);
  const [text, setText] = useState("");
  const [asSeller, setAsSeller] = useState(false);
  useEffect(() => setRisk(null), [id]);
  if (loading && !data) return html`<${Loading} rows=${4} />`;
  if (error && !data) return html`<${ErrorBox} error=${error} />`;
  const { listing, seller, messages } = data;
  const flagged = new Set([...(risk?.ai?.evidence || []).map((e) => e.line), ...(risk?.signals || []).filter((s) => s.line && s.strong).map((s) => s.line)]);

  const send = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    try {
      await api(`/api/listings/${id}/messages`, { method: "POST", body: { text, sender: asSeller ? "seller" : "buyer" } });
      setText(""); setRisk(null); reload();
    } catch (err) { toast(err.message, true); }
  };
  const check = async () => {
    setChecking(true);
    try { setRisk(await api("/api/assess", { method: "POST", body: { listing_id: id } })); }
    catch (err) { toast(err.message, true); }
    finally { setChecking(false); }
  };

  return html`
    <${Back} to="#/market" label="Marketplace" />
    <div class="grid cols-main">
      <div class="stack">
        <div class="card"><div class="card-body">
          <div class="listing-hero">
            <div class=${"tile t-" + listing.category}><${Icon} name=${CATEGORY_ICON[listing.category] || "box"} size=${56} sw=${1.2} /></div>
            <div>
              <div class="xs text-2">${listing.category} · ${listing.condition}</div>
              <h1 style="font-size:22px;line-height:30px;margin:4px 0 8px;letter-spacing:-.02em">${listing.title}</h1>
              <div><span class="price lg">${usd(listing.price)}</span><span class="ref">typically ${usd0(listing.ref_price)}</span></div>
              <p class="text-2" style="margin:12px 0 0">${listing.description}</p>
            </div>
          </div>
          <hr class="divider" />
          <div class="row spread">
            <div class="row" style="gap:12px"><span class="avatar lg">${initials(seller.name)}</span>
              <div><div style="font-weight:600">${seller.name}</div><div class="xs text-2">@${seller.handle} · ${seller.location} · member for ${seller.joined_days_ago} days</div></div></div>
            ${seller.completed_sales > 0
              ? html`<span class="badge">${seller.rating} rating · ${seller.completed_sales} sales</span>`
              : html`<span class="badge warning"><span class="dot"></span>New seller, no sales yet</span>`}
          </div>
        </div></div>

        <div class="card">
          <div class="card-head"><div><h2>Conversation</h2><div class="sub">Messages between you and the seller</div></div>
            ${flagged.size > 0 && html`<span class="badge danger"><span class="dot"></span>${flagged.size} message${flagged.size > 1 ? "s" : ""} flagged</span>`}</div>
          <div class="card-body">
            <div class="convo">
              ${messages.map((m, i) => {
                const mine = m.sender === "buyer", bad = flagged.has(i + 1);
                return html`<div class=${"msg " + (mine ? "mine " : "") + (bad ? "flagged" : "")} key=${i}>
                  <span class="avatar">${mine ? "You" : initials(seller.name)}</span>
                  <div><div class="bubble">${m.text}</div>
                    ${bad && html`<div class="lineref"><${Icon} name="alert" size=${12} />Line ${i + 1} cited as evidence</div>`}</div>
                </div>`;
              })}
            </div>
            <form class="composer" style="margin-top:16px" onSubmit=${send}>
              <input class="input" value=${text} onChange=${(e) => setText(e.target.value)} placeholder=${asSeller ? "Write a message as the seller" : "Write a message"} aria-label="Message" />
              <button class="btn" aria-label="Send"><${Icon} name="send" /></button>
            </form>
            <label class="check" style="margin-top:10px"><input type="checkbox" checked=${asSeller} onChange=${(e) => setAsSeller(e.target.checked)} /> Demo control: post as the seller to test your own scam script</label>
          </div>
        </div>
      </div>
      <div class="sticky"><${Checkout} listing=${listing} seller=${seller} risk=${risk} checking=${checking} onCheck=${check} cfg=${cfg} /></div>
    </div>`;
}

function Signals({ risk }) {
  return html`${risk.signals.map((s) => html`<div class="signal" key=${s.key}>
    <span class=${"sev " + (s.strong ? "high" : "med")}>${s.strong ? "High" : "Medium"}</span><span>${s.label}</span></div>`)}`;
}

function Evidence({ ai, compact = false }) {
  return html`${(ai.evidence || []).map((e) => html`<div class="evidence" key=${e.line + e.quote}>
    <div class="m">Message line ${e.line}</div><div class="q">"${e.quote}"</div>${!compact && e.why && html`<div class="w">${e.why}</div>`}</div>`)}`;
}

function ModelLine({ risk }) {
  const ai = risk.ai || {};
  return html`<div class="model-line">
    <${Icon} name="sparkles" size=${12} />
    ${ai.provider ? html`<span>${ai.model} · ${ai.latency_ms} ms${ai.cached ? " (cached)" : ""}</span>`
      : html`<span>LLM unavailable: ${risk.local_model ? "rules + local model" : "rules only"}</span>`}
    ${risk.local_model && html`<span>· local model p=${risk.local_model.p_scam.toFixed(2)} in ${risk.local_model.latency_ms} ms</span>`}
    ${risk.tactic && html`<span>· tactic: ${risk.tactic.name.replaceAll("_", " ")} (${risk.tactic.source})</span>`}
    <span>· score ${risk.score.toFixed(2)}</span>
    ${ai.dropped_evidence ? html`<span>· ${ai.dropped_evidence} unverifiable quote${ai.dropped_evidence > 1 ? "s" : ""} discarded</span>` : ""}
  </div>`;
}

function PauseModal({ risk, cfg, onCancel, onProceed }) {
  const ai = risk.ai || {};
  const [step, setStep] = useState("warn");
  const [contact, setContact] = useState("");
  const mins = Math.round((cfg?.cooling_off_seconds || 120) / 60);
  useEffect(() => {
    const f = (e) => e.key === "Escape" && onCancel();
    addEventListener("keydown", f);
    document.body.style.overflow = "hidden";
    return () => { removeEventListener("keydown", f); document.body.style.overflow = ""; };
  }, []);
  // Portal to <body>: the checkout column is position:sticky, which would trap the overlay under the header.
  return ReactDOM.createPortal(html`<div class="backdrop" role="dialog" aria-modal="true" aria-labelledby="pause-title">
    <div class="modal">
      ${step === "warn" ? html`
        <div class="m-head">
          <div class="feat-ic danger"><${Icon} name="pause" size=${22} /></div>
          <h2 id="pause-title">We paused this payment</h2>
          <p class="text-2" style="margin:6px 0 0">${ai.spell_breaker || ai.explanation || "This conversation matches known scam patterns."}</p>
        </div>
        <div class="m-body stack compact" style="gap:12px">
          ${(ai.evidence || []).length > 0 && html`<div><div class="eyebrow">From the conversation</div><${Evidence} ai=${ai} compact /></div>`}
          <div><div class="eyebrow" style="margin-bottom:2px">Risk signals</div><${Signals} risk=${risk} /></div>
          ${ai.safe_next_step && html`<div class="callout info"><${Icon} name="info" /><div><b>Safer option.</b> ${ai.safe_next_step}</div></div>`}
          <${ModelLine} risk=${risk} />
        </div>
        <div class="m-foot">
          <button class="btn dark lg block" onClick=${onCancel} autofocus>Don't send money</button>
          <button class="btn ghost block" onClick=${() => setStep("safeguard")}>I know this seller personally, continue with safeguards</button>
        </div>` : html`
        <div class="m-head">
          <div class="feat-ic danger" style="background:var(--accent-soft);color:var(--accent);box-shadow:0 0 0 8px #f5faff"><${Icon} name="lock" size=${22} /></div>
          <h2 id="pause-title">Continue with safeguards</h2>
          <p class="text-2" style="margin:6px 0 0">Your payment will be authorized but not charged. Two protections stay on until delivery:</p>
        </div>
        <div class="m-body stack" style="gap:12px">
          <div class="signal"><${Icon} name="clock" /><span><b>${mins}-minute cooling-off.</b> Scams rely on urgency. You can cancel at any time and the hold is voided. (24 hours in production.)</span></div>
          <div class="signal"><${Icon} name="users" /><span><b>A trusted contact reviews it.</b> They get a summary of the warning signs and can stop the payment.</span></div>
          <div><label class="field" for="contact">Trusted contact</label>
            <input id="contact" class="input" placeholder="Name or email, for example a family member" value=${contact} onChange=${(e) => setContact(e.target.value)} /></div>
        </div>
        <div class="m-foot">
          <button class="btn primary lg block" disabled=${!contact.trim()} onClick=${() => onProceed(contact.trim())}>Continue to PayPal</button>
          <button class="btn ghost block" onClick=${onCancel}>Cancel, don't pay</button>
        </div>`}
    </div></div>`, document.body);
}

function Checkout({ listing, seller, risk, checking, onCheck, cfg }) {
  const [modal, setModal] = useState(false);
  const [contact, setContact] = useState(null);
  useEffect(() => { setContact(null); setModal(risk?.verdict === "PAUSE"); }, [risk]);
  const authorized = (o) => {
    toast(o.status === "PAUSED" ? "Payment authorized and paused for cooling-off." : "Payment authorized. Funds are on hold until delivery.");
    go("/order/" + o.id);
  };
  const fee = (listing.price * (cfg?.platform_fee_pct || 5)) / 100;
  const summary = html`<div class="card-body" style="padding-bottom:0">
    <div class="ledger-lines">
      <span class="k">Item</span><span class="v">${usd(listing.price)}</span>
      <span class="k">Buyer fees</span><span class="v">${usd(0)}</span>
      <span class="k total">Authorized now</span><span class="v total">${usd(listing.price)}</span>
    </div>
    <div class="xs text-3" style="margin-top:8px">Seller receives the sale minus a ${cfg?.platform_fee_pct || 5}% platform fee (${usd(fee)}) after you confirm delivery.</div>
  </div>`;

  if (!risk) return html`<div class="card">
    <div class="card-head"><div><h2>Checkout</h2><div class="sub">Paid with PayPal</div></div><${Icon} name="lock" cls="text-3" /></div>
    ${summary}
    <div class="card-body">
      <div class="callout info" style="margin-bottom:16px"><${Icon} name="shieldCheck" /><div>Before any money moves, TrustLayer checks this listing and conversation for scam tactics. It takes about two seconds.</div></div>
      <button class="btn primary lg block" onClick=${onCheck} disabled=${checking}>
        ${checking ? html`<${Spinner} /> Checking payment safety` : html`Continue to payment <${Icon} name="arrowRight" />`}
      </button>
    </div></div>`;

  const v = VERDICT[risk.verdict];
  const ai = risk.ai || {};
  const paused = risk.verdict === "PAUSE";
  return html`
    ${modal && paused && html`<${PauseModal} risk=${risk} cfg=${cfg}
        onCancel=${() => { setModal(false); toast("Payment cancelled. No money moved."); go("/market"); }}
        onProceed=${(c) => { setContact(c); setModal(false); }} />`}
    <div class="stack">
      <div class="status-card">
        <div class="status-head">
          <span class=${"ic " + v.tone}><${Icon} name=${v.icon} size=${20} /></span>
          <div style="flex:1"><div class="row spread"><div class="t">${paused && contact ? "Protected checkout" : v.label}</div><${VerdictBadge} v=${risk.verdict} /></div>
            <div class="d">${risk.verdict === "CLEAR" ? (ai.explanation || "No scam tactics found in the listing or conversation.")
              : paused && contact ? `Cooling-off and trusted contact (${contact}) will be enabled.` : ai.explanation}</div></div>
        </div>
        ${risk.verdict === "CAUTION" && html`<div class="section"><${Signals} risk=${risk} /></div>`}
        ${paused && !contact && html`<div class="section stack" style="gap:8px">
          <button class="btn dark block" onClick=${() => go("/market")}>Don't send money</button>
          <button class="btn ghost block" onClick=${() => setModal(true)}>Review the warning</button></div>`}
        <div class="section"><${ModelLine} risk=${risk} /></div>
      </div>
      ${(!paused || contact) && html`<div class="card">
        <div class="card-head"><div><h2>Checkout</h2><div class="sub">Approve a hold with PayPal</div></div><${Icon} name="lock" cls="text-3" /></div>
        ${summary}
        <div class="card-body">
          <div class="callout info" style="margin-bottom:16px"><${Icon} name="lock" /><div>You're approving a <b>hold</b> of ${usd(listing.price)}. Nothing is charged until you confirm delivery.</div></div>
          <${PayButtons} listing=${listing} cfg=${cfg} acknowledged=${paused} contact=${contact} onAuthorized=${authorized} />
        </div></div>`}
    </div>`;
}

function PayButtons({ listing, cfg, acknowledged, contact, onAuthorized }) {
  const ref = useRef(null);
  const orderRef = useRef(null);
  const [state, setState] = useState("loading");
  const [redirect, setRedirect] = useState(null);
  const body = { listing_id: listing.id, acknowledged, trusted_contact: contact || null };
  useEffect(() => {
    if (!cfg?.paypal_client_id) { setState("nosdk"); return; }
    let dead = false;
    loadPayPal(cfg.paypal_client_id).then((paypal) => {
      if (dead || !ref.current) return;
      ref.current.innerHTML = "";
      paypal.Buttons({
        style: { layout: "vertical", color: "gold", shape: "rect", label: "paypal", height: 44 },
        createOrder: async () => { const r = await api("/api/orders", { method: "POST", body }); orderRef.current = r.order_id; return r.paypal_order_id; },
        onApprove: async (_data, actions) => {
          try { onAuthorized(await api(`/api/orders/${orderRef.current}/authorize`, { method: "POST" })); }
          catch (e) {
            toast(e.message, true);
            if (e.data?.restart) return actions.restart();  // PayPal's recovery path for INSTRUMENT_DECLINED
          }
        },
        onCancel: () => toast("PayPal window closed. Nothing was charged."),
        onError: (e) => toast("PayPal error: " + (e?.message || e), true),
      }).render(ref.current).then(() => !dead && setState("ready")).catch(() => setState("nosdk"));
    }).catch(() => !dead && setState("nosdk"));
    return () => { dead = true; };
  }, [listing.id, acknowledged, contact, cfg?.paypal_client_id]);
  const startRedirect = async () => {
    try { const r = await api("/api/orders", { method: "POST", body }); setRedirect(r); window.open(r.approve_url, "_blank"); }
    catch (e) { toast(e.message, true); }
  };
  const finishRedirect = async () => {
    try { onAuthorized(await api(`/api/orders/${redirect.order_id}/authorize`, { method: "POST" })); }
    catch (e) { toast(e.status === 502 ? "Not approved yet. Finish approving in the PayPal tab first." : e.message, true); }
  };
  return html`<div>
    ${state === "loading" && html`<div class="skeleton" style="height:44px"></div>`}
    <div ref=${ref}></div>
    <div style="margin-top:10px"><${SandboxLogin} compact /></div>
    <details class="fallback" style="margin-top:10px" open=${state === "nosdk"}>
      <summary>PayPal button not loading? Use redirect checkout</summary>
      <div class="row" style="margin-top:10px">
        ${!redirect ? html`<button class="btn sm" onClick=${startRedirect}><${Icon} name="external" size=${14} />Open PayPal in a new tab</button>`
          : html`<a class="btn sm" href=${redirect.approve_url} target="_blank">Reopen PayPal</a><button class="btn sm primary" onClick=${finishRedirect}>I've approved it</button>`}
      </div>
      <div class="xs text-3" style="margin-top:8px">Sign in with the sandbox login above.</div>
    </details>
  </div>`;
}

// ---------------- orders ----------------
function OrdersPage() {
  const [{ data, loading, error }] = useFetch("/api/orders");
  return html`
    <${PageHead} title="Orders" sub="Every payment is a PayPal authorization held until you confirm delivery." />
    ${error && html`<${ErrorBox} error=${error} />`}
    ${loading ? html`<${Loading} />` : data.length === 0 ? html`<div class="card empty">
        <div class="ic neutral" style="width:44px;height:44px;border-radius:10px;display:grid;place-items:center"><${Icon} name="receipt" size=${20} /></div>
        <b>No orders yet</b><div class="sm" style="margin-top:4px">Buy something from the <a href="#/market">marketplace</a> to see the payment flow.</div></div>`
      : html`<div class="card table-wrap"><table class="table">
        <thead><tr><th>Order</th><th>Item</th><th>Seller</th><th>Screening</th><th style="text-align:right">Amount</th><th>Status</th></tr></thead>
        <tbody>${data.map((o) => html`<tr class="click" key=${o.id} onClick=${() => go("/order/" + o.id)}>
          <td><div class="cell-main mono">${o.id}</div><div class="cell-sub">${ago(o.created_at)}</div></td>
          <td><div class="cell-main">${o.listing?.title}</div></td>
          <td class="text-2">@${o.seller?.handle}</td>
          <td>${o.risk ? html`<${VerdictBadge} v=${o.risk.verdict} />` : ""}</td>
          <td class="num" style="text-align:right;font-weight:500">${usd(o.amount)}</td>
          <td><div class="row"><${StatusBadge} status=${o.status} />${o.issue?.status === "RESOLVED" && html`<span class="badge success">Resolved</span>`}
            ${o.issue?.status === "ESCALATED" && html`<span class="badge warning">With seller</span>`}</div></td>
        </tr>`)}</tbody></table></div>`}`;
}

function Progress({ o }) {
  if (o.status === "CANCELLED") return html`<div class="progress" style="grid-template-columns:repeat(3,1fr)">
    <div class="p done"><div class="bar"></div>Approved</div><div class="p done"><div class="bar"></div>Held</div><div class="p alert"><div class="bar"></div>Voided, not charged</div></div>`;
  const idx = { CREATED: 0, HELD: 1, PAUSED: 1, CAPTURED: 2, PAID_OUT: 3, CLOSED: 3 }[o.status] ?? 0;
  const labels = ["Approved", o.status === "PAUSED" ? "Cooling-off" : "Held by PayPal", "Captured", "Seller paid"];
  return html`<div class="progress">${labels.map((l, i) => html`<div key=${i} class=${"p " + (i <= idx ? (o.status === "PAUSED" && i === 1 ? "alert" : i === 3 && idx === 3 ? "done ok" : "done") : "")}><div class="bar"></div>${l}</div>`)}</div>`;
}

const EVENT_UI = {
  "order.created": ["file", "", (d) => ["Order created", `PayPal order ${d.paypal_order_id} · intent AUTHORIZE`]],
  "payment.authorized": ["lock", "accent", (d) => [d.mode === "cooling_off" ? "Payment authorized, cooling-off started" : "Payment authorized and held", `Authorization ${d.authorization_id} · ${usd(d.amount)}`]],
  "pause.expired": ["clock", "", () => ["Cooling-off ended", "Funds remain on hold until delivery"]],
  "pause.released": ["users", "success", () => ["Trusted contact approved", "Cooling-off ended early"]],
  "contact.verdict": ["users", "warning", (d) => [`Trusted contact: ${d.verdict === "scam" ? "flagged as scam" : "looks fine"}`, d.contact || ""]],
  "payment.voided": ["xCircle", "danger", (d) => ["Authorization voided", `Buyer not charged · ${(d.reason || "").replaceAll("_", " ")}`]],
  "resolution.opened": ["message", "", () => ["Problem reported", "Resolution assistant engaged"]],
  "resolution.turn": ["sparkles", "", (d) => [`Assistant proposed: ${(d.offer?.type || "").replaceAll("_", " ")}`, d.offer?.amount ? usd(d.offer.amount) + (d.policy_adjustments?.length ? " · adjusted to policy" : "") : (d.issue_type || "").replaceAll("_", " ")]],
  "resolution.escalated": ["inbox", "warning", () => ["Escalated to seller", "Waiting for the seller's decision"]],
  "resolution.settled": ["checkCircle", "success", (d) => ["Resolved without a dispute", `${usd(d.amount)} · ${d.method}`]],
  "resolution.declined": ["xCircle", "", () => ["Seller declined", "Buyer may still contact PayPal"]],
  "payment.captured": ["dollar", "success", (d) => [`Captured ${usd(d.amount)}`, d.released_to_buyer > 0 ? `${usd(d.released_to_buyer)} of the hold released to buyer` : `Capture ${d.capture_id}`]],
  "payment.refunded": ["undo", "warning", (d) => [`Refunded ${usd(d.amount)}`, `Refund ${d.refund_id}`]],
  "payout.sent": ["wallet", "success", (d) => [`Seller payout sent: ${usd(d.amount)}`, `Batch ${d.payout_batch_id} · fee ${usd(d.platform_fee)}`]],
  "payout.status": ["wallet", "", (d) => [`Payout ${String(d.status).toLowerCase()}`, `Batch ${d.payout_batch_id}`]],
  "webhook.received": ["link", "", (d) => [`PayPal webhook: ${d.event_type}`, d.verified ? "Signature verified" : "Unverified"]],
  "paypal.error": ["alert", "danger", (d) => ["PayPal error", `${d.action} · ${d.status}`]],
};
function Timeline({ events }) {
  const list = [...(events || [])].reverse().filter((e) => EVENT_UI[e.type]);
  return html`<div class="timeline">${list.map((e) => {
    const [icon, tone, fn] = EVENT_UI[e.type]; const [t, d] = fn(e.data || {});
    return html`<div class="tl-item" key=${e.seq}><span class=${"tl-ic " + tone}><${Icon} name=${icon} size=${14} /></span>
      <div><div class="tl-t">${t}</div><div class="tl-d">${d}${d ? " · " : ""}${clock(e.ts)}</div></div></div>`;
  })}</div>`;
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
  useEffect(() => { if (o?.status === "PAUSED" || o?.trusted_contact) api(`/api/orders/${id}/contact-link`).then(setLink).catch(() => {}); }, [o?.status]);
  useEffect(() => {  // payout status settles a few seconds after sending
    if (o?.status === "PAID_OUT" && ["PENDING", "PROCESSING", null, undefined].includes(o.payout_status)) {
      const t = setTimeout(() => api(`/api/orders/${id}/payout-status`, { method: "POST" }).then(reload).catch(() => {}), 3000);
      return () => clearTimeout(t);
    }
  }, [o?.status, o?.payout_status]);
  if (error && !o) return html`<${ErrorBox} error=${error} />`;
  if (!o) return html`<${Loading} rows=${3} />`;
  const act = async (path, msg) => {
    setBusy(true);
    try { await api(`/api/orders/${id}/${path}`, { method: "POST" }); toast(msg); await reload(); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const released = o.captured_amount ? Math.max(0, o.amount - o.captured_amount) : 0;
  const refs = [["PayPal order", o.paypal_order_id], ["Authorization", o.authorization_id], ["Capture", o.capture_id], ["Payout batch", o.payout_batch_id]].filter(([, v]) => v);
  return html`
    <${Back} to="#/orders" label="Orders" />
    <div class="page-head"><div>
      <div class="row"><h1>${o.listing?.title}</h1><${StatusBadge} status=${o.status} /></div>
      <p><span class="mono">${o.id}</span> · sold by @${o.seller?.handle} · ${ago(o.created_at)}</p></div>
      <div class="price lg">${usd(o.amount)}</div></div>
    <div class="grid cols-main">
      <div class="stack">
        <div class="card"><div class="card-body stack" style="gap:20px">
          <${Progress} o=${o} />
          ${o.status === "PAUSED" && html`<div class="callout danger" style="align-items:center">
            <${Icon} name="clock" size=${20} />
            <div style="flex:1"><div style="font-weight:600;color:var(--text)">Cooling-off in progress</div>
              <div class="text-2">Your ${usd(o.amount)} is authorized, not charged. Cancel now and the hold is voided instantly.</div>
              ${link && html`<div class="text-2" style="margin-top:4px">${link.contact} has been asked to review it. <a href=${"#/contact/" + link.token} target="_blank">Open their view <${Icon} name="external" size=${12} /></a></div>`}</div>
            <div class="countdown">${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}</div></div>`}
          ${o.status === "CANCELLED" && html`<div class="callout success"><${Icon} name="shieldCheck" /><div><b>No money moved.</b> The PayPal authorization was voided and the buyer was never charged.</div></div>`}
          ${o.status === "PAID_OUT" && html`<div class="callout success"><${Icon} name="checkCircle" /><div><b>Order complete.</b> The seller was paid ${usd(o.payout_amount)} through PayPal Payouts${o.payout_status ? ` (status: ${o.payout_status.toLowerCase()})` : ""}.</div></div>`}
          ${o.auth_expires && ["HELD", "PAUSED"].includes(o.status) && html`<div class="xs text-3">Authorization valid until ${new Date(o.auth_expires).toLocaleString()}</div>`}
          <div class="row">
            ${o.status === "PAUSED" && html`<button class="btn danger" disabled=${busy} onClick=${() => act("cancel", "Payment cancelled. The hold was voided.")}><${Icon} name="xCircle" />Cancel payment</button>`}
            ${o.status === "HELD" && html`
              <button class="btn primary" disabled=${busy} onClick=${() => act("received", "Delivery confirmed. Payment captured and seller paid.")}><${Icon} name="check" />Confirm delivery and release payment</button>
              <button class="btn" disabled=${busy} onClick=${() => act("cancel", "Order cancelled. Hold voided.")}>Cancel order</button>`}
            ${o.status === "CAPTURED" && html`<button class="btn primary" disabled=${busy} onClick=${() => act("received", "Seller paid through PayPal Payouts.")}><${Icon} name="wallet" />Pay out seller</button>`}
            ${busy && html`<span class="text-2 sm"><${Spinner} /> Talking to PayPal</span>`}
          </div>
        </div></div>
        <div class="card"><div class="card-head"><h2>Activity</h2><span class="xs text-3">Recorded in the audit log</span></div>
          <div class="card-body"><${Timeline} events=${o.events} /></div></div>
      </div>
      <div class="stack sticky">
        <div class="card"><div class="card-head"><h2>Payment</h2></div><div class="card-body">
          <div class="ledger-lines">
            <span class="k">Authorized (held)</span><span class="v">${usd(o.amount)}</span>
            ${released > 0 && html`<span class="k">Released to buyer</span><span class="v">− ${usd(released)}</span>`}
            ${o.captured_amount > 0 && html`<span class="k">Captured</span><span class="v">${usd(o.captured_amount)}</span>`}
            ${o.refunded_amount > 0 && html`<span class="k">Refunded</span><span class="v">− ${usd(o.refunded_amount)}</span>`}
            ${o.fee > 0 && html`<span class="k">Platform fee</span><span class="v">− ${usd(o.fee)}</span>`}
            ${o.payout_amount > 0 && html`<span class="k total">Seller payout</span><span class="v total">${usd(o.payout_amount)}</span>`}
          </div>
          ${refs.length > 0 && html`<hr class="divider" /><dl class="refs">${refs.map(([k, v]) => html`<dt key=${k}>${k}</dt><dd class="mono">${v}</dd>`)}
            ${o.seller_protection && html`<dt>Seller Protection</dt><dd><span class=${"badge " + (o.seller_protection === "ELIGIBLE" ? "success" : "")}>${o.seller_protection.toLowerCase()}</span></dd>`}
            ${o.risk && html`<dt>Screening</dt><dd><${VerdictBadge} v=${o.risk.verdict} /></dd>`}</dl>`}
        </div></div>
        ${["HELD", "CAPTURED", "PAID_OUT"].includes(o.status) || o.issue
          ? html`<${Resolution} order=${o} onChange=${reload} />`
          : html`<div class="card"><div class="card-body"><h3>Problem with this order?</h3><p class="sm text-2" style="margin:0">Once your payment is on hold you can report a problem and get it settled here, before anyone opens a PayPal dispute.</p></div></div>`}
      </div>
    </div>`;
}

// ---------------- resolution assistant ----------------
function Resolution({ order, onChange }) {
  const [issue, setIssue] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef(null);
  useEffect(() => { if (order.issue) api(`/api/issues/${order.issue.id}`).then(setIssue).catch(() => {}); }, [order.issue?.id, order.issue?.status]);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [issue, busy]);
  const send = async (e) => {
    e.preventDefault(); if (!text.trim()) return;
    setBusy(true);
    try { setIssue(await api(`/api/orders/${order.id}/issue`, { method: "POST", body: { text } })); setText(""); onChange(); }
    catch (err) { toast(err.message, true); } finally { setBusy(false); }
  };
  const accept = async () => {
    setBusy(true);
    try { setIssue(await api(`/api/issues/${issue.id}/accept`, { method: "POST" })); toast("Settled on PayPal. Dispute avoided."); onChange(); }
    catch (err) { toast(err.message, true); } finally { setBusy(false); }
  };
  const last = issue?.transcript?.filter((t) => t.role === "agent").slice(-1)[0];
  const status = issue?.status;
  const done = status === "RESOLVED" || status === "DECLINED";
  const starters = ["It arrived 4 days late and I missed my trip.", "There's a crack that wasn't in the photos.", "I changed my mind. Can I get a refund?"];
  return html`<div class="card">
    <div class="card-head"><div><h2>Resolution center</h2><div class="sub">Settled within ${order.seller?.handle}'s policy, before a dispute</div></div>
      ${status && html`<span class=${"badge " + (status === "RESOLVED" ? "success" : status === "ESCALATED" ? "warning" : "accent")}>${status.toLowerCase()}</span>`}</div>
    <div class="card-body">
      <div class="convo" ref=${box} style="max-height:380px">
        ${!issue && !busy && html`<div class="text-2 sm">Tell us what went wrong. An assistant acting for the seller will propose a fair fix you can accept in one click.</div>`}
        ${(issue?.transcript || []).map((t, i) => {
          const mine = t.role === "buyer", seller = t.role === "seller";
          return html`<div class=${"msg " + (mine ? "mine" : "")} key=${i}>
            <span class="avatar">${mine ? "You" : seller ? initials(order.seller?.handle) : html`<${Icon} name="sparkles" size=${13} />`}</span>
            <div><div class="who">${mine ? "You" : seller ? "Seller" : "Resolution assistant"}</div><div class="bubble">${t.text}</div>
              ${(t.policy_notes || []).map((n, j) => html`<div class="note" key=${j}><${Icon} name="info" size=${12} />${n}</div>`)}
              ${t.role === "agent" && t.issue_type && html`<div class="agent-meta">${t.issue_type.replaceAll("_", " ")} · dispute risk ${Math.round((t.dispute_risk || 0) * 100)}% · ${t.model}</div>`}</div></div>`;
        })}
        ${busy && html`<div class="msg"><span class="avatar"><${Icon} name="sparkles" size=${13} /></span><div class="bubble"><${Spinner} /></div></div>`}
      </div>
      ${!issue && html`<div class="suggest" style="margin-top:12px">${starters.map((s) => html`<button key=${s} onClick=${() => setText(s)}>${s}</button>`)}</div>`}
      ${last?.offer && ["partial_refund", "full_refund"].includes(last.offer.type) && status === "OFFERED" && html`
        <div class="offer" style="margin-top:14px">
          <div><b>${usd(last.offer.amount)} back to you</b><div class="xs text-2">${order.status === "HELD" ? "Released from your hold, so it is never charged" : "Refunded to your PayPal account"}</div></div>
          <button class="btn success" disabled=${busy} onClick=${accept}>Accept offer</button></div>`}
      ${status === "ESCALATED" && html`<div class="callout warning" style="margin-top:14px"><${Icon} name="inbox" /><div>This needs the seller's decision. They have been notified and can respond from their inbox.</div></div>`}
      ${status === "RESOLVED" && html`<div class="callout success" style="margin-top:14px"><${Icon} name="checkCircle" /><div><b>Resolved, no dispute needed.</b> ${usd(issue.outcome.amount)} settled on PayPal (${issue.outcome.method}).</div></div>`}
      ${!done && html`<form class="composer" style="margin-top:14px" onSubmit=${send}>
        <input class="input" value=${text} onChange=${(e) => setText(e.target.value)} placeholder="Describe the problem" disabled=${busy} aria-label="Describe the problem" />
        <button class="btn primary" disabled=${busy} aria-label="Send"><${Icon} name="send" /></button></form>`}
    </div></div>`;
}

// ---------------- trusted contact ----------------
function ContactPage({ token }) {
  const [{ data, error }, reload] = useFetch(`/api/contact/${token}`);
  const [busy, setBusy] = useState(false);
  if (error && !data) return html`<${ErrorBox} error=${error} />`;
  if (!data) return html`<${Loading} rows=${2} />`;
  const { order: o, risk } = data;
  const vote = async (verdict) => {
    setBusy(true);
    try { await api(`/api/contact/${token}`, { method: "POST", body: { verdict } }); toast(verdict === "scam" ? "Payment stopped. The hold was voided." : "Thanks. The payment continues on hold."); reload(); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const done = o.contact_verdict || !["PAUSED", "HELD"].includes(o.status);
  return html`<div style="max-width:560px;margin:24px auto 0">
    <div class="card">
      <div class="card-body">
        <div class="feat-ic danger"><${Icon} name="users" size=${22} /></div>
        <h1 style="font-size:20px;margin:0 0 6px;letter-spacing:-.02em">Can you double-check a payment?</h1>
        <p class="text-2" style="margin:0">You were added as a trusted contact. They are about to pay <b>${usd(o.amount)}</b> to <b>@${o.seller?.handle}</b> for "${o.listing?.title}". TrustLayer paused it because:</p>
      </div>
      <div class="section"><${Signals} risk=${risk} />${risk.ai?.explanation && html`<p class="sm text-2" style="margin:8px 0 0">${risk.ai.explanation}</p>`}</div>
      <div class="section">
        ${done ? html`<div class=${"callout " + (o.status === "CANCELLED" ? "success" : "info")}><${Icon} name=${o.status === "CANCELLED" ? "shieldCheck" : "info"} />
            <div>${o.status === "CANCELLED" ? "Payment stopped. No money moved." : "Thanks. The payment stays on hold until delivery."}</div></div>`
          : html`<div class="grid cols-2" style="gap:8px">
            <button class="btn danger lg" disabled=${busy} onClick=${() => vote("scam")}>Stop this payment</button>
            <button class="btn lg" disabled=${busy} onClick=${() => vote("safe")}>It's fine, I know them</button></div>`}
      </div>
    </div></div>`;
}

// ---------------- seller health ----------------
function Score({ score, size = 88 }) {
  const r = 38, c = 2 * Math.PI * r, color = score >= 80 ? "var(--success-solid)" : score >= 60 ? "var(--warning-solid)" : "var(--danger-solid)";
  return html`<div class="score" style=${{ width: size, height: size }}><svg viewBox="0 0 88 88" width=${size} height=${size} role="img" aria-label=${"Health score " + score}>
    <circle cx="44" cy="44" r=${r} fill="none" stroke="var(--border)" stroke-width="8" />
    <circle cx="44" cy="44" r=${r} fill="none" stroke=${color} stroke-width="8" stroke-linecap="round" stroke-dasharray=${`${(score / 100) * c} ${c}`} transform="rotate(-90 44 44)" /></svg>
    <span class="n" style=${{ fontSize: size < 60 ? "15px" : "24px" }}>${score}</span></div>`;
}
const HealthBadge = ({ s }) => html`<span class=${"badge " + (s === "Healthy" ? "success" : s === "Watch" ? "warning" : "danger")}><span class="dot"></span>${s}</span>`;

function SellersPage() {
  const [{ data, loading }] = useFetch("/api/sellers");
  return html`<${PageHead} title="Seller health" sub="Holds and limitations usually arrive without warning. TrustLayer tracks the public signals that trigger account reviews and explains them early." />
    ${loading ? html`<${Loading} />` : html`<div class="card table-wrap"><table class="table">
      <thead><tr><th>Seller</th><th>Health</th><th style="text-align:right">Sales (30d)</th><th style="text-align:right">Dispute rate</th><th style="text-align:right">Refund rate</th><th style="text-align:right">Disputes avoided</th><th>Open cases</th><th></th></tr></thead>
      <tbody>${data.map((s) => html`<tr class="click" key=${s.seller.id} onClick=${() => go("/sellers/" + s.seller.id)}>
        <td><div class="row" style="gap:12px"><span class="avatar lg">${initials(s.seller.name)}</span><div><div class="cell-main">${s.seller.name}</div><div class="cell-sub">@${s.seller.handle}</div></div></div></td>
        <td><div class="row" style="gap:10px"><${Score} score=${s.score} size=${40} /><${HealthBadge} s=${s.status} /></div></td>
        <td class="num" style="text-align:right">${s.kpis.transactions_30d}</td>
        <td class="num" style=${{ textAlign: "right", color: s.kpis.dispute_rate >= s.thresholds.dispute_line ? "var(--danger)" : "inherit", fontWeight: 500 }}>${s.kpis.dispute_rate.toFixed(2)}%</td>
        <td class="num" style="text-align:right">${s.kpis.refund_rate.toFixed(1)}%</td>
        <td class="num" style="text-align:right">${s.kpis.prevented_30d}</td>
        <td>${s.open_cases > 0 ? html`<span class="badge warning">${s.open_cases} waiting</span>` : html`<span class="text-3">None</span>`}</td>
        <td><${Icon} name="chevronRight" cls="text-3" /></td></tr>`)}</tbody></table></div>`}`;
}

function SellerInbox({ id, onChange }) {
  const [{ data }, reload] = useFetch(`/api/sellers/${id}/issues`);
  const [amount, setAmount] = useState({});
  const [busy, setBusy] = useState(null);
  const open = (data || []).filter((i) => i.status === "ESCALATED");
  if (!open.length) return null;
  const decide = async (iss, action) => {
    setBusy(iss.id);
    try {
      await api(`/api/issues/${iss.id}/seller-decision`, { method: "POST", body: { action, amount: Number(amount[iss.id] || 0) } });
      toast(action === "refund" ? "Refund sent on PayPal." : "Case declined."); reload(); onChange && onChange();
    } catch (e) { toast(e.message, true); } finally { setBusy(null); }
  };
  return html`<div class="card" style="border-color:var(--warning-border)">
    <div class="card-head"><div><h2>Seller inbox</h2><div class="sub">Cases the assistant could not settle within your policy</div></div><span class="badge warning">${open.length} waiting</span></div>
    ${open.map((iss) => {
      const lastBuyer = iss.transcript.filter((t) => t.role === "buyer").slice(-1)[0];
      return html`<div class="section" key=${iss.id}>
        <div class="row spread"><div><div class="cell-main">${iss.order.listing?.title}</div><div class="cell-sub mono">${iss.order.id} · ${usd(iss.order.amount)}</div></div><${StatusBadge} status=${iss.order.status} /></div>
        <div style="margin:10px 0;background:var(--subtle);border:1px solid var(--border);border-radius:10px;padding:10px 12px">"${lastBuyer?.text}"</div>
        <div class="row">
          <input class="input" type="number" min="0" step="0.01" style="width:140px" placeholder="Refund amount" value=${amount[iss.id] || ""} onChange=${(e) => setAmount({ ...amount, [iss.id]: e.target.value })} />
          <button class="btn primary sm" disabled=${busy === iss.id || !(Number(amount[iss.id]) > 0)} onClick=${() => decide(iss, "refund")}>Send refund</button>
          <button class="btn sm" disabled=${busy === iss.id} onClick=${() => decide(iss, "decline")}>Decline</button>
        </div></div>`;
    })}</div>`;
}

function SellerPage({ id }) {
  const [{ data: m, error }, reload] = useFetch(`/api/sellers/${id}/health`);
  const [{ data: ex, loading: exLoading }] = useFetch(`/api/sellers/${id}/explain`);
  if (error && !m) return html`<${ErrorBox} error=${error} />`;
  if (!m) return html`<${Loading} rows=${3} />`;
  const k = m.kpis, max = Math.max(1, ...m.series.map((d) => d.orders));
  const scaleMax = Math.max(2.5, k.dispute_rate_without_prevention + 0.4);
  const pct = (v) => `${Math.min(100, (v / scaleMax) * 100)}%`;
  const over = k.dispute_rate >= m.thresholds.dispute_line;
  return html`
    <${Back} to="#/sellers" label="Seller health" />
    <div class="card" style="margin-bottom:16px"><div class="card-body row" style="gap:20px;align-items:flex-start;flex-wrap:nowrap">
      <${Score} score=${m.score} />
      <div style="flex:1;min-width:0">
        <div class="row"><h1 style="font-size:22px;margin:0;letter-spacing:-.02em">${m.seller.name}</h1><${HealthBadge} s=${m.status} /></div>
        <div class="xs text-2" style="margin-top:2px">@${m.seller.handle} · member for ${m.seller.joined_days_ago} days · ${m.seller.location}</div>
        ${exLoading ? html`<div class="skeleton" style="height:40px;margin-top:12px"></div>` : ex && html`<p style="margin:12px 0 0"><b>${ex.headline}</b> <span class="text-2">${ex.summary}</span></p>`}
      </div></div></div>
    <div class="stack">
      <${SellerInbox} id=${id} onChange=${reload} />
      <${SellerSubscriptions} id=${id} onChange=${reload} />
      <div class="card grid cols-stats" style="gap:0">
        ${[["Sales, 30 days", k.transactions_30d, ""], ["Dispute rate", k.dispute_rate.toFixed(2) + "%", `Line at ${m.thresholds.dispute_line}%`],
           ["Disputes avoided", k.prevented_30d, "by early resolution"], ["Refund rate", k.refund_rate.toFixed(1) + "%", ""],
           ["This week vs baseline", (k.volume_spike_x ?? "–") + "×", "sales velocity"], ["Gross, 30 days", usd0(k.gross_30d), ""]]
          .map(([l, v, hint], i) => html`<div class="stat" key=${i} style=${{ borderLeft: i ? "1px solid var(--border)" : "0" }}>
            <div class="l">${l}</div><div class="v" style=${{ color: l === "Dispute rate" && over ? "var(--danger)" : "inherit" }}>${v}</div>${hint && html`<div class="h">${hint}</div>`}</div>`)}
      </div>
      <div class="grid cols-2">
        <div class="stack">
          <div class="card"><div class="card-head"><div><h2>Dispute rate against the monitoring line</h2><div class="sub">Card networks such as Visa (VAMP) flag merchants above ${m.thresholds.dispute_line}%</div></div></div>
            <div class="card-body">
              <div class="row spread sm"><span class="text-2">Current</span><b class="num" style=${{ color: over ? "var(--danger)" : "inherit" }}>${k.dispute_rate.toFixed(2)}%</b></div>
              <div class="gauge"><div class="fill" style=${{ width: pct(k.dispute_rate), background: over ? "var(--danger-solid)" : "var(--accent)" }}></div>
                <div class="mark" style=${{ left: pct(m.thresholds.dispute_line) }}><span>${m.thresholds.dispute_line}%</span></div></div>
              <div class="row spread sm" style="margin-top:18px"><span class="text-2">Without early resolution</span><b class="num">${k.dispute_rate_without_prevention.toFixed(2)}%</b></div>
              <div class="gauge" style="margin-top:10px"><div class="fill" style=${{ width: pct(k.dispute_rate_without_prevention), background: "var(--border-strong)" }}></div>
                <div class="mark" style=${{ left: pct(m.thresholds.dispute_line) }}></div></div>
              <p class="xs text-3" style="margin:14px 0 0">TrustLayer does not see PayPal's internal risk models. These are the public signals that commonly trigger reviews.</p>
            </div></div>
          <div class="card"><div class="card-head"><div><h2>Daily sales</h2><div class="sub">Last 30 days · markers show days with disputes</div></div></div>
            <div class="card-body">
              <svg viewBox="0 0 300 120" preserveAspectRatio="none" style="width:100%;height:160px;display:block" role="img" aria-label="Daily sales over the last 30 days">
                ${[0.25, 0.5, 0.75].map((f) => html`<line key=${f} x1="0" x2="300" y1=${108 - f * 96} y2=${108 - f * 96} stroke="var(--border)" stroke-dasharray="2 3" stroke-width="0.6" />`)}
                ${m.series.map((d, i) => { const hgt = (d.orders / max) * 96; return html`<g key=${i}>
                  <rect x=${i * 10 + 1.5} y=${108 - hgt} width="7" height=${hgt} rx="1.5" fill=${i >= 23 ? "var(--accent)" : "#b2ccff"}><title>${d.orders} sales, ${d.disputes} disputes</title></rect>
                  ${d.disputes > 0 && html`<rect x=${i * 10 + 3} y=${112} width="4" height="4" rx="1" fill="var(--danger-solid)" />`}</g>`; })}
              </svg>
              <div class="row xs text-2" style="margin-top:8px;gap:16px"><span class="row" style="gap:6px"><span style="width:10px;height:10px;border-radius:2px;background:#b2ccff"></span>Prior weeks</span>
                <span class="row" style="gap:6px"><span style="width:10px;height:10px;border-radius:2px;background:var(--accent)"></span>Last 7 days</span>
                <span class="row" style="gap:6px"><span style="width:8px;height:8px;border-radius:2px;background:var(--danger-solid)"></span>Dispute filed</span></div>
            </div></div>
        </div>
        <div class="stack">
          <div class="card"><div class="card-head"><h2>Findings</h2></div><div class="card-body">
            ${m.findings.length === 0 && html`<div class="text-2">No warning signs.</div>`}
            ${m.findings.map((f, i) => html`<div class="finding" key=${i}>
              <span class=${"ic " + ({ high: "danger", medium: "warning", good: "success", info: "accent" }[f.level])} style="width:28px;height:28px;border-radius:8px;display:grid;place-items:center;flex:none">
                <${Icon} name=${{ high: "alert", medium: "alert", good: "checkCircle", info: "info" }[f.level]} size=${14} /></span>
              <div><div style="font-weight:500">${f.title}</div><div class="sm text-2">${f.detail}</div></div></div>`)}
          </div></div>
          ${ex?.actions?.length > 0 && html`<div class="card"><div class="card-head"><h2>Recommended next steps</h2></div><div class="card-body">
            <ol class="actions">${ex.actions.map((a, i) => html`<li key=${i}>${a}</li>`)}</ol>
            <div class="model-line" style="margin-top:12px"><${Icon} name="sparkles" size=${12} />Written by ${ex.model}</div></div></div>`}
        </div>
      </div>
    </div>`;
}

// ---------------- Subscriptions (PayPal Subscriptions: TrustLayer Plus + seller kit) ----------------
let subSdkPromise = null;
function loadPayPalSubs(clientId) {
  if (window.paypalSubs) return Promise.resolve(window.paypalSubs);
  if (!subSdkPromise) {
    subSdkPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&vault=true&intent=subscription&components=buttons`;
      s.setAttribute("data-namespace", "paypalSubs");  // separate SDK instance: checkout uses intent=authorize
      s.onload = () => resolve(window.paypalSubs);
      s.onerror = () => { subSdkPromise = null; reject(new Error("PayPal SDK failed to load")); };
      document.head.appendChild(s);
    });
  }
  return subSdkPromise;
}

function SubscribeButton({ cfg, off, onDone }) {
  const ref = useRef(null);
  const [state, setState] = useState("loading");
  useEffect(() => {
    if (!cfg?.paypal_client_id || !off.plan_id) return;
    let dead = false;
    loadPayPalSubs(cfg.paypal_client_id).then((pp) => {
      if (dead || !ref.current) return;
      ref.current.innerHTML = "";
      pp.Buttons({
        style: { layout: "vertical", color: "gold", shape: "rect", label: "subscribe", height: 42 },
        createSubscription: (_d, actions) => actions.subscription.create({ plan_id: off.plan_id }),
        onApprove: async (data) => {
          try {
            onDone(await api("/api/subscriptions", { method: "POST", body: { subscription_id: data.subscriptionID, offering_id: off.id } }));
            toast(off.trial_days ? `Trial started. You won't be charged for ${off.trial_days} days.` : "Subscribed.");
          } catch (e) { toast(e.message, true); }
        },
        onError: (e) => toast("PayPal error: " + (e?.message || e), true),
      }).render(ref.current).then(() => !dead && setState("ready")).catch(() => setState("error"));
    }).catch(() => setState("error"));
    return () => { dead = true; };
  }, [cfg?.paypal_client_id, off.plan_id]);
  if (!off.plan_id) return html`<div class="callout warning"><${Icon} name="alert" /><div>This plan isn't available on PayPal right now.</div></div>`;
  return html`<div>${state === "loading" && html`<div class="skeleton" style="height:42px"></div>`}<div ref=${ref}></div>
    ${state === "error" && html`<div class="callout danger"><${Icon} name="alert" /><div>The PayPal subscription button could not load.</div></div>`}</div>`;
}

const SUB_STATUS = { ACTIVE: ["Active", "success"], APPROVED: ["Approved", "accent"], SUSPENDED: ["Paused", "warning"], CANCELLED: ["Cancelled", ""], EXPIRED: ["Expired", ""] };
const fmtDate = (ts) => ts ? new Date(ts * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "–";
const SubBadge = ({ sub }) => { const [l, t] = sub.in_trial ? ["Free trial", "success"] : (SUB_STATUS[sub.status] || [sub.status, ""]); return html`<span class=${"badge " + t}><span class="dot"></span>${l}</span>`; };

function usageTiles(sub) {
  const u = sub.usage || {};
  if ("deliveries_received" in u) return [["Deliveries received", u.deliveries_received]];
  return [["Payments protected", u.payments_protected], ["Money kept safe", usd(u.money_kept_safe)]];
}

function SubscriptionCard({ sub: initial, cfg, onChange }) {
  const [sub, setSub] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [assist, setAssist] = useState(null);
  useEffect(() => setSub(initial), [initial]);
  async function act(path, msg, body) {
    setBusy(true);
    try { const s = await api(`/api/subscriptions/${sub.id}/${path}`, { method: "POST", body }); setSub(s); if (msg) toast(msg); onChange && onChange(); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  }
  useEffect(() => { if (sub.reminder_due && !sub.reminder && !busy) act("reminder", null); }, [sub.reminder_due, sub.reminder]);
  const openCancel = async () => { setAssist({ loading: true }); try { setAssist(await api(`/api/subscriptions/${sub.id}/cancel-assist`)); } catch { setAssist({ message: "Cancelling takes one confirmation.", offer_pause: false }); } };
  const off = sub.offering, live = ["ACTIVE", "APPROVED", "SUSPENDED"].includes(sub.status);
  const tiles = [["First charge", sub.in_trial ? `${usd(sub.price)} on ${fmtDate(sub.next_billing_at)}` : `${usd(sub.price)}/mo`],
    ["Days until charge", sub.status === "SUSPENDED" ? "Paused" : !live ? "–" : sub.days_until_charge], ...usageTiles(sub)];
  return html`<div class="card">
    <div class="card-head"><div><h2>${off.name}</h2><div class="sub">${off.seller ? `Sold by ${off.seller.name}` : "TrustLayer membership"} · <span class="mono">${sub.id}</span></div></div><${SubBadge} sub=${sub} /></div>
    <div class="card-body">
      <div class="grid cols-stats" style="gap:0;border:1px solid var(--border);border-radius:10px">
        ${tiles.map(([l, val], i) => html`<div class="stat" key=${l} style=${{ borderLeft: i ? "1px solid var(--border)" : "0" }}><div class="l">${l}</div><div class="v" style="font-size:19px">${val}</div></div>`)}
      </div>
      ${sub.reminder && live && html`<div class=${"callout " + (sub.reminder.recommendation === "cancel" ? "warning" : "info")} style="margin-top:16px">
        <${Icon} name="clock" /><div><b>${sub.reminder.headline}</b><div style="margin-top:2px">${sub.reminder.body}</div>
          <div style="margin-top:6px;font-weight:600">${sub.reminder.fact}</div>
          ${sub.reminder.why && html`<div class="xs" style="margin-top:4px">Our recommendation: <b>${sub.reminder.recommendation}</b>. ${sub.reminder.why}</div>`}</div></div>`}
      ${!live && html`<div class="callout info" style="margin-top:16px"><${Icon} name="info" /><div>Cancelled on ${fmtDate(sub.cancelled_at)}. No further charges.</div></div>`}
      ${live && (assist ? html`<div class="callout danger" style="margin-top:16px;align-items:center">
          <${Icon} name="xCircle" /><div style="flex:1">${assist.loading ? html`<${Spinner} />` : assist.message}</div></div>
        <div class="row" style="margin-top:10px">
          <button class="btn danger" disabled=${busy || assist.loading} onClick=${() => { setAssist(null); act("cancel", "Cancelled. You will not be charged.", { reason: "cancelled from Subscriptions" }); }}>Cancel now</button>
          ${assist.offer_pause && html`<button class="btn" disabled=${busy} onClick=${() => { setAssist(null); act("pause", "Paused. No charges while paused."); }}>Pause instead</button>`}
          <button class="btn ghost" onClick=${() => setAssist(null)}>Keep subscription</button></div>`
      : html`<div class="row" style="margin-top:16px">
          <button class="btn" disabled=${busy} onClick=${openCancel}><${Icon} name="xCircle" />Cancel subscription</button>
          ${sub.status === "SUSPENDED" && html`<button class="btn primary" disabled=${busy} onClick=${() => act("resume", "Resumed.")}>Resume</button>`}
          ${busy && html`<span class="sm text-2"><${Spinner} /> Talking to PayPal</span>`}</div>`)}
    </div>
    ${cfg?.demo_mode !== false && sub.in_trial && live && html`<div class="card-foot row spread"><span class="xs text-2">Demo control: move this trial's clock forward${sub.simulated_days ? ` (now +${sub.simulated_days} days)` : ""}</span>
      <button class="btn sm" disabled=${busy} onClick=${() => act("simulate", "Moved forward 5 days.", { days: 5 })}><${Icon} name="clock" size=${14} />Simulate +5 days</button></div>`}
  </div>`;
}

function OfferingCard({ off, cfg, onSubscribed }) {
  return html`<div class="card">
    <div class="card-body">
      <div class="row spread" style="align-items:flex-start"><div><div class="eyebrow">${off.seller ? off.seller.name : "TrustLayer"}</div><h2 style="font-size:18px;margin-top:4px">${off.name}</h2></div>
        <div style="text-align:right"><div class="price">${usd(off.price)}</div><div class="xs text-2">per month${off.trial_days ? ` · ${off.trial_days}-day free trial` : ""}</div></div></div>
      <p class="sm text-2" style="margin:10px 0 6px">${off.description}</p>
      ${(off.benefits || []).map((b) => html`<div class="signal" key=${b}><${Icon} name="check" cls="text-2" /><span>${b}</span></div>`)}
      <div class="xs text-2" style="margin-top:10px;padding-top:10px;border-top:1px dashed var(--border)">${off.disclosure}</div>
    </div>
    <div class="card-foot"><${SubscribeButton} cfg=${cfg} off=${off} onDone=${onSubscribed} /></div></div>`;
}

function SubscriptionsPage({ cfg }) {
  const [{ data: subs, loading }, reloadSubs] = useFetch("/api/subscriptions");
  const [{ data: offers }, reloadOffers] = useFetch("/api/offerings");
  const reload = () => { reloadSubs(); reloadOffers(); };
  if (loading && !subs) return html`<${Loading} rows=${3} />`;
  const liveIds = new Set((subs || []).filter((s) => ["ACTIVE", "APPROVED", "SUSPENDED"].includes(s.status)).map((s) => s.offering.id));
  const available = (offers || []).filter((o) => !liveIds.has(o.id));
  const promises = [["clock", "A reminder 2 days before the first charge", "With exactly when and how much, and whether you've actually used it."],
    ["xCircle", "Cancel in one confirmation, any time", "No calls, no hidden menus, no fees. The cancel button is always on this page."],
    ["activity", "We tell you if you're not using it", "If it isn't paying off, the reminder suggests cancelling."],
    ["file", "Terms checked before launch", "Every seller's terms are reviewed for traps; the price-and-renewal disclosure is written by code."]];
  return html`
    <${PageHead} title="Subscriptions" sub="Memberships from TrustLayer and from sellers, all on PayPal Subscriptions and all held to the same rules: a real free trial, an honest reminder before the first charge, and cancellation in one confirmation." />
    <div class="grid cols-main">
      <div class="stack">
        ${(subs || []).length > 0 && html`<h2>Your subscriptions</h2>${subs.map((s) => html`<${SubscriptionCard} key=${s.id} sub=${s} cfg=${cfg} onChange=${reload} />`)}`}
        ${available.length > 0 && html`<h2 style="margin-top:8px">Available</h2>
          <div class="grid cols-2">${available.map((o) => html`<${OfferingCard} key=${o.id} off=${o} cfg=${cfg} onSubscribed=${reload} />`)}</div>`}
      </div>
      <div class="stack sticky">
        <div class="card"><div class="card-head"><h2>Our rules for every subscription</h2></div><div class="card-body">
          ${promises.map(([icon, t, d]) => html`<div class="finding" key=${t}><span class="ic accent" style="width:28px;height:28px;border-radius:8px;display:grid;place-items:center;flex:none"><${Icon} name=${icon} size=${14} /></span>
            <div><div style="font-weight:500">${t}</div><div class="sm text-2">${d}</div></div></div>`)}
        </div></div>
        <${SandboxLogin} compact />
        <div class="card"><div class="card-body"><div class="xs text-2">About 7 in 10 US adults have been charged after forgetting a free trial (2026 surveys), and 20+ US states now require click-to-cancel. Forgotten-trial charges often come back as chargebacks, which hurts sellers too.</div></div></div>
      </div>
    </div>`;
}

function SellerSubscriptions({ id, onChange }) {
  const [{ data }, reload] = useFetch(`/api/sellers/${id}/subscribers`);
  const [form, setForm] = useState({ name: "", description: "", price: "9.99", trial_days: "7" });
  const [review, setReview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const body = () => ({ name: form.name.trim(), description: form.description.trim(), price: Number(form.price), trial_days: Number(form.trial_days) });
  const valid = form.name.trim().length >= 3 && form.description.trim().length >= 10 && Number(form.price) > 0;
  const doReview = async () => { setBusy(true); try { setReview(await api(`/api/sellers/${id}/offerings/review`, { method: "POST", body: body() })); } catch (e) { toast(e.message, true); } finally { setBusy(false); } };
  const publish = async () => {
    setBusy(true);
    try { await api(`/api/sellers/${id}/offerings`, { method: "POST", body: body() }); toast("Published on PayPal Subscriptions."); setOpen(false); setReview(null); setForm({ ...form, name: "", description: "" }); reload(); onChange && onChange(); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const record = async (sid) => { try { await api(`/api/subscriptions/${sid}/delivery`, { method: "POST" }); toast("Delivery recorded."); reload(); onChange && onChange(); } catch (e) { toast(e.message, true); } };
  const set = (k) => (e) => { setForm({ ...form, [k]: e.target.value }); setReview(null); };
  const s = data.summary;
  return html`<div class="card">
    <div class="card-head"><div><h2>Subscriptions kit</h2><div class="sub">Sell memberships on PayPal Subscriptions without the traps that turn into chargebacks</div></div>
      ${s.at_risk > 0 ? html`<span class="badge warning">${s.at_risk} at risk</span>` : html`<span class="badge">${s.active} active</span>`}</div>
    <div class="section">
      <div class="grid cols-stats" style="gap:0;border:1px solid var(--border);border-radius:10px">
        ${[["Active subscribers", s.active], ["In free trial", s.in_trial], ["Monthly revenue", usd(s.monthly_revenue)], ["Forgotten-trial risk", s.at_risk]].map(([l, v], i) => html`
          <div class="stat" key=${l} style=${{ borderLeft: i ? "1px solid var(--border)" : "0" }}><div class="l">${l}</div><div class="v" style=${{ fontSize: "19px", color: l === "Forgotten-trial risk" && v > 0 ? "var(--warning)" : "inherit" }}>${v}</div></div>`)}
      </div>
    </div>
    <div class="section">
      <div class="row spread"><h3 style="margin:0">Your offerings</h3>${!open && html`<button class="btn sm" onClick=${() => setOpen(true)}><${Icon} name="sparkles" size=${14} />New offering</button>`}</div>
      ${data.offerings.length === 0 && !open && html`<div class="sm text-2" style="margin-top:6px">No subscription offerings yet.</div>`}
      ${data.offerings.map((o) => html`<div class="row spread" key=${o.id} style="padding:10px 0;border-bottom:1px solid var(--border)">
        <div><div class="cell-main">${o.name}</div><div class="cell-sub">${o.disclosure}</div></div><span class="mono xs text-3">${o.plan_id || ""}</span></div>`)}
      ${open && html`<div class="stack" style="gap:10px;margin-top:12px">
        <div><label class="field">Name</label><input class="input" value=${form.name} onChange=${set("name")} placeholder="e.g. Film Roll Club" /></div>
        <div><label class="field">What subscribers get</label><textarea class="input" style="height:76px;padding-top:8px;resize:vertical" value=${form.description} onChange=${set("description")} placeholder="Describe the offer in your own words"></textarea></div>
        <div class="grid cols-2" style="gap:10px"><div><label class="field">Price per month (USD)</label><input class="input" type="number" min="1" step="0.01" value=${form.price} onChange=${set("price")} /></div>
          <div><label class="field">Free trial (days)</label><input class="input" type="number" min="0" max="30" value=${form.trial_days} onChange=${set("trial_days")} /></div></div>
        ${review && html`<div class="stack" style="gap:8px">
          ${review.blocking.map((b) => html`<div class="callout danger" key=${b}><${Icon} name="xCircle" /><div><b>Not allowed:</b> ${b}</div></div>`)}
          ${review.issues.map((i, k) => html`<div class="signal" key=${k}><span class=${"sev " + (i.severity === "high" ? "high" : "med")}>${i.severity}</span><span><b>${i.problem}.</b> ${i.fix}</span></div>`)}
          ${review.improved_description && review.improved_description !== form.description && html`<div class="callout info"><${Icon} name="sparkles" /><div style="flex:1"><b>Clearer wording:</b> ${review.improved_description}
            <div><button class="btn sm" style="margin-top:8px" onClick=${() => setForm({ ...form, description: review.improved_description })}>Use this wording</button></div></div></div>`}
          <div class="callout success"><${Icon} name="file" /><div><b>Shown to every subscriber (written by TrustLayer, not editable):</b> ${review.disclosure}</div></div>
          ${review.model && html`<div class="model-line"><${Icon} name="sparkles" size=${12} />Terms reviewed by ${review.model}</div>`}</div>`}
        <div class="row">
          <button class="btn" disabled=${busy || !valid} onClick=${doReview}>${busy && !review ? html`<${Spinner} />` : html`<${Icon} name="shieldCheck" size=${14} />`} Review terms</button>
          <button class="btn primary" disabled=${busy || !review || review.blocking.length > 0} onClick=${publish}>Publish on PayPal</button>
          <button class="btn ghost" onClick=${() => { setOpen(false); setReview(null); }}>Cancel</button></div>
      </div>`}
    </div>
    ${data.subscribers.length > 0 && html`<div class="table-wrap"><table class="table">
      <thead><tr><th>Subscriber</th><th>Plan</th><th>Status</th><th style="text-align:right">Charge in</th><th style="text-align:right">Deliveries</th><th></th></tr></thead>
      <tbody>${data.subscribers.map((sb) => html`<tr key=${sb.id}>
        <td class="mono">${sb.id}</td><td>${sb.offering.name}</td><td><div class="row"><${SubBadge} sub=${sb} />${sb.chargeback_risk && html`<span class="badge warning">Unused, charge soon</span>`}</div></td>
        <td class="num" style="text-align:right">${["ACTIVE", "APPROVED"].includes(sb.status) ? `${sb.days_until_charge} d` : "–"}</td>
        <td class="num" style="text-align:right">${sb.usage.deliveries_received ?? "–"}</td>
        <td>${["ACTIVE", "APPROVED"].includes(sb.status) && html`<button class="btn sm" onClick=${() => record(sb.id)}>Record delivery</button>`}</td></tr>`)}</tbody></table></div>`}
  </div>`;
}

// ---------------- audit log ----------------
function LedgerPage() {
  const [{ data, loading }, reload] = useFetch("/api/ledger");
  const [busy, setBusy] = useState(false);
  const tamper = async () => { setBusy(true); try { const r = await api("/api/ledger/tamper", { method: "POST" }); toast(`Record #${r.tampered_seq} was edited directly in the database.`); await reload(); } catch (e) { toast(e.message, true); } finally { setBusy(false); } };
  const reset = async () => { if (!confirm("Reset all demo data, including orders and the audit log?")) return; await api("/api/admin/reset", { method: "POST" }); toast("Demo data reset."); reload(); };
  const [checked, setChecked] = useState(null);
  const [verifying, setVerifying] = useState(false);
  // Re-reads every record from the database and recomputes each SHA-256 link on the server.
  const verify = async () => {
    setVerifying(true);
    const t0 = performance.now();
    try {
      const r = await api("/api/ledger");
      await reload();
      const ms = Math.round(performance.now() - t0);
      setChecked({ at: Date.now() / 1000, ms, ok: r.verify.ok, count: r.verify.count });
      toast(r.verify.ok ? `Recomputed ${r.verify.count} hashes: chain intact.` : `Chain broken at record #${r.verify.broken_at}.`, !r.verify.ok);
    } catch (e) { toast(e.message, true); } finally { setVerifying(false); }
  };
  const v = data?.verify;
  return html`<${PageHead} title="Audit log" sub="Every PayPal call and every AI decision, in an append-only SHA-256 hash chain. Changing any record breaks the chain at that point."
      right=${html`<div class="row"><button class="btn sm" disabled=${verifying} onClick=${verify}>${verifying ? html`<${Spinner} />` : html`<${Icon} name="refresh" size=${14} />`}Verify chain</button>
        <button class="btn sm" disabled=${busy} onClick=${tamper}>Simulate tampering</button><button class="btn sm ghost" onClick=${reset}>Reset demo</button></div>`} />
    ${v && html`<div class=${"callout " + (v.ok ? "success" : "danger")} style="margin-bottom:16px">
      <${Icon} name=${v.ok ? "shieldCheck" : "shieldAlert"} />
      <div>${v.ok ? html`<b>Chain verified.</b> ${v.count} records, head <span class="mono">${v.head?.slice(0, 16)}…</span>`
        : html`<b>Tampering detected at record #${v.broken_at}</b> (${v.type}). Every record after it can no longer be trusted.`}
        <div class="xs" style="opacity:.85;margin-top:2px">${checked
          ? `Last check ${clock(checked.at)}: every record re-read from the database and its SHA-256 link recomputed (${checked.ms} ms).`
          : "Verify chain re-reads every record and recomputes each link. Simulate tampering edits one record behind the app's back to show the break."}</div></div></div>`}
    ${loading ? html`<${Loading} />` : html`<div class="card table-wrap"><table class="table">
      <thead><tr><th>#</th><th>Event</th><th>Reference</th><th>Details</th><th>Hash</th><th>Time</th></tr></thead>
      <tbody>${(data?.events || []).map((e) => html`<tr key=${e.seq} class=${v && !v.ok && e.seq === v.broken_at ? "bad" : ""}>
        <td class="mono text-2">${e.seq}</td><td class="cell-main">${e.type}</td>
        <td class="mono">${e.order_id ? html`<a href=${"#/order/" + e.order_id}>${e.order_id}</a>` : html`<span class="text-2">${e.seller_id || "system"}</span>`}</td>
        <td class="xs text-2 mono" style="max-width:420px">${Object.entries(e.data || {}).filter(([, x]) => x !== null && typeof x !== "object").slice(0, 4).map(([a, b]) => `${a}=${b}`).join("  ")}</td>
        <td class="mono xs text-3">${e.hash.slice(0, 10)}</td><td class="xs text-2" style="white-space:nowrap">${clock(e.ts)}</td></tr>`)}</tbody></table></div>`}`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
