// The Mini App page: one profile card at a time, with Like and Pass.
// All visible text comes from /api/strings (bot/strings.py).
"use strict";

const tg = window.Telegram.WebApp;
tg.ready();   // tells Telegram the page has loaded, so it hides its own loader
tg.expand();  // open at full height

let text = {};
let botUsername = "";  // from /api/me, for the invite link
let busy = false;  // true while a request is running, so a double tap does nothing

const screen = document.getElementById("screen");

// --- talking to the server ---

// Every API call carries Telegram's signed login, so the server knows who is asking.
async function api(path, body) {
  const options = { headers: { Authorization: "tma " + tg.initData } };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = response.ok ? await response.json() : null;
  return { status: response.status, data };
}

// --- building the page ---

// Creates an element. Text always goes in as textContent, never as HTML:
// names and bios are typed by users.
function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function showMessage(message) {
  screen.replaceChildren(el("p", "message", message));
}

function showSpinner() {
  screen.replaceChildren(el("div", "spinner"));
}

// A full screen with an icon, a title, a short text and buttons.
// Used when there is nothing to show, so it never looks like a blank page.
function showEmptyState({ icon, title, message, buttons }) {
  const box = el("div", "empty");
  box.append(el("div", "empty-icon", icon), el("h1", null, title), el("p", null, message));
  for (const button of buttons) {
    const node = el("button", "empty-button " + (button.style || ""), button.label);
    node.addEventListener("click", button.onClick);
    box.append(node);
  }
  screen.replaceChildren(box);
}

function showNoMore() {
  showEmptyState({
    icon: "🐋",
    title: text.no_more_title,
    message: text.no_more,
    buttons: [
      { label: text.invite, style: "primary", onClick: invite },
      { label: text.check_again, onClick: checkAgain },
    ],
  });
}

function showNoProfile() {
  showEmptyState({
    icon: "📝",
    title: text.no_profile_title,
    message: text.no_profile,
    buttons: [{ label: text.create_profile, style: "primary", onClick: () => tg.close() }],
  });
}

function showError(status) {
  if (status === 401) return showMessage(text.open_in_telegram);
  if (status === 403) return showMessage(text.banned);
  if (status === 409) return showNoProfile();
  showMessage(text.error || "⚠️");
}

function haptic(kind) {
  try { tg.HapticFeedback.impactOccurred(kind); } catch (e) { /* not in Telegram */ }
}

// A small dialog at the bottom of the screen. Resolves with the chosen button's
// value, or null for Cancel or a tap outside.
function dialog({ title, message, buttons }) {
  return new Promise((resolve) => {
    const backdrop = el("div", "backdrop");
    const sheet = el("div", "sheet");
    if (title) sheet.append(el("h3", null, title));
    if (message) sheet.append(el("p", null, message));
    const close = (value) => { backdrop.remove(); resolve(value); };
    for (const button of buttons) {
      const node = el("button", "sheet-button " + (button.style || ""), button.label);
      node.addEventListener("click", () => close(button.value));
      sheet.append(node);
    }
    backdrop.addEventListener("click", (event) => { if (event.target === backdrop) close(null); });
    backdrop.append(sheet);
    document.body.append(backdrop);
  });
}

// The photo area: tap the right half for the next photo, the left half to go back.
function photoArea(urls) {
  const area = el("div", "photo");
  const img = el("img");
  img.alt = "";
  const dots = el("div", "dots");
  let index = 0;

  function show(i) {
    index = i;
    img.src = urls[i];
    dots.querySelectorAll("span").forEach((dot, n) => dot.classList.toggle("active", n === i));
  }

  urls.forEach(() => dots.append(el("span")));
  area.append(img);
  if (urls.length > 1) {
    area.append(dots);
    area.addEventListener("click", (event) => {
      const right = event.offsetX > area.clientWidth / 2;
      show((index + (right ? 1 : urls.length - 1)) % urls.length);
    });
  }
  // Load the other photos in the background, so tapping through is instant.
  urls.slice(1).forEach((url) => { new Image().src = url; });
  show(0);
  return area;
}

function showCard(card) {
  const info = el("div", "info");
  info.append(el("h2", null, `${card.name}, ${card.age}`));
  info.append(el("div", "city", card.city));
  if (card.bio) info.append(el("p", "bio", card.bio));

  const safety = el("div", "safety");
  const report = el("button", "link", text.report);
  const block = el("button", "link", text.block);
  report.addEventListener("click", () => reportCard(card));
  block.addEventListener("click", () => blockCard(card));
  safety.append(report, block);
  info.append(safety);

  const cardNode = el("div", "card");
  cardNode.append(photoArea(card.photos), info);

  const actions = el("div", "actions");
  const pass = el("button", "action pass", text.pass);
  const like = el("button", "action like", text.like);
  pass.addEventListener("click", () => swipe(card, "pass"));
  like.addEventListener("click", () => swipe(card, "like"));
  actions.append(pass, like);

  screen.replaceChildren(cardNode, actions);
  window.scrollTo(0, 0);
}

// --- what the buttons do ---

async function loadNext() {
  const { status, data } = await api("/api/next");
  if (status !== 200) return showError(status);
  if (data.card === null) return showNoMore();
  showCard(data.card);
}

// Opens Telegram's share sheet with a link to the bot.
function invite() {
  haptic("light");
  const botLink = "https://t.me/" + botUsername;
  const share = "https://t.me/share/url?url=" + encodeURIComponent(botLink) +
    "&text=" + encodeURIComponent(text.invite_text);
  try {
    tg.openTelegramLink(share);
  } catch (e) {
    window.open(share, "_blank");  // an ordinary browser, when testing locally
  }
}

async function checkAgain() {
  if (busy) return;
  busy = true;
  try {
    haptic("light");
    showSpinner();
    await loadNext();
  } finally {
    busy = false;
  }
}

async function swipe(card, action) {
  if (busy) return;
  busy = true;
  try {
    haptic(action === "like" ? "medium" : "light");
    const { status, data } = await api("/api/swipe", { target_id: card.user_id, action });
    if (status !== 200) return showError(status);
    if (data.match) {
      const choice = await dialog({
        title: text.match_title,
        message: text.match.replace("{name}", data.match.name),
        buttons: [
          { label: text.match_to_chat, value: "chat", style: "primary" },
          { label: text.match_keep_browsing, value: "browse" },
        ],
      });
      if (choice === "chat") return tg.close();  // back to the bot chat
    }
    await loadNext();
  } finally {
    busy = false;
  }
}

async function reportCard(card) {
  if (busy) return;
  const reasons = Object.entries(text.report_reasons).map(([value, label]) => ({ label, value }));
  const reason = await dialog({
    title: text.report_title,
    buttons: [...reasons, { label: text.cancel, value: null, style: "cancel" }],
  });
  if (!reason) return;
  busy = true;
  try {
    const { status } = await api("/api/report", { target_id: card.user_id, reason });
    if (status !== 200) return showError(status);
    await dialog({ message: text.report_sent, buttons: [{ label: text.ok, value: true, style: "primary" }] });
    await loadNext();
  } finally {
    busy = false;
  }
}

async function blockCard(card) {
  if (busy) return;
  const sure = await dialog({
    message: text.block_confirm.replace("{name}", card.name),
    buttons: [
      { label: text.block, value: true, style: "danger" },
      { label: text.cancel, value: null, style: "cancel" },
    ],
  });
  if (!sure) return;
  busy = true;
  try {
    const { status } = await api("/api/block", { target_id: card.user_id });
    if (status !== 200) return showError(status);
    await loadNext();
  } finally {
    busy = false;
  }
}

async function main() {
  text = await (await fetch("/api/strings")).json();
  const me = await api("/api/me");
  if (me.status !== 200) return showError(me.status);
  botUsername = me.data.bot_username;
  if (!me.data.has_profile) return showNoProfile();
  await loadNext();
}

main().catch(() => showError(0));
