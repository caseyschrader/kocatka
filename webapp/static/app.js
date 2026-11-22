// The Mini App page. All visible text comes from /api/strings (bot/strings.py).
"use strict";

const tg = window.Telegram.WebApp;
tg.ready();   // tells Telegram the page has loaded, so it hides its own loader
tg.expand();  // open at full height

let text = {};

// Every API call carries Telegram's signed login, so the server knows who is asking.
async function api(path) {
  const response = await fetch(path, { headers: { Authorization: "tma " + tg.initData } });
  const body = response.ok ? await response.json() : null;
  return { status: response.status, body };
}

function show(title, message) {
  const screen = document.getElementById("screen");
  screen.replaceChildren();
  if (title) {
    const h1 = document.createElement("h1");
    h1.textContent = title;  // textContent, never innerHTML: names are user input
    screen.append(h1);
  }
  if (message) {
    const p = document.createElement("p");
    p.textContent = message;
    screen.append(p);
  }
}

async function main() {
  text = await (await fetch("/api/strings")).json();
  const me = await api("/api/me");

  if (me.status === 401) return show(null, text.open_in_telegram);
  if (me.status === 403) return show(null, text.banned);
  if (me.status !== 200) return show(null, text.error);
  if (!me.body.has_profile) return show(null, text.no_profile);
  show(text.hello.replace("{name}", me.body.first_name), text.coming_soon);
}

main().catch(() => show(null, text.error || "⚠️"));
