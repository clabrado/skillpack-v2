#!/usr/bin/env node
// Post ONE Slack message that carries both text and a file, through the running Slack
// desktop app (debug port 9222). Variant of intel/scripts/slack_attach.js.
// usage: node slack_post_with_file.js <channel-or-dm-id> <expected-header-name> <file[|file2|...]> <text-file>
// Lines in <text-file> are joined with Shift+Enter, so the whole thing goes out as one message.
// It refuses to send if the open conversation header doesn't match the expected name.
const path = require('path'), os = require('os'), fs = require('fs');
const dep = path.join(os.homedir(), '.cache', 'intel');
if (!require('fs').existsSync(path.join(dep, 'node_modules', 'playwright'))) {
  require('fs').mkdirSync(dep, { recursive: true });
  require('child_process').execSync('npm init -y >/dev/null && npm i playwright >/dev/null 2>&1', { cwd: dep, shell: '/bin/sh' });
}
const { chromium } = require(path.join(dep, 'node_modules', 'playwright'));
const [chan, expect, file, textFile] = process.argv.slice(2);
if (!chan || !expect || !file || !textFile) { console.error('usage: slack_post_with_file.js <channel-id> <header-name> <file> <text-file>'); process.exit(2); }
const files = file.split('|');
const lines = fs.readFileSync(textFile, 'utf8').replace(/\s+$/, '').split('\n');
(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const p = b.contexts()[0].pages().find(x => /app\.slack\.com\/client\/[A-Z0-9]+/.test(x.url()));
  if (!p) { console.error('Slack app not reachable on :9222'); process.exit(1); }
  const team = p.url().match(/client\/([A-Z0-9]+)/)[1];
  if (!p.url().includes(chan)) await p.goto(`https://app.slack.com/client/${team}/${chan}`, { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('[data-qa="message_input"]', { timeout: 30000 });
  const hdr = await p.evaluate(() => (document.querySelector('[data-qa="channel_name"], .p-view_header__text') || {}).innerText || '');
  if (!hdr.includes(expect)) { console.error('WRONG CONVERSATION:', hdr); process.exit(1); }
  await p.setInputFiles('input[type=file]', files);
  await p.waitForTimeout(6000);
  const box = p.locator('[data-qa="message_input"] [contenteditable="true"]').first();
  await box.click();
  for (let i = 0; i < lines.length; i++) {
    if (i) await p.keyboard.press('Shift+Enter');
    await p.keyboard.insertText(lines[i]);
  }
  await p.waitForTimeout(800);
  // Guard: text and file must both be in the composer before anything is sent.
  const typed = await box.innerText();
  const bases = files.map(f => path.basename(f).replace(/\.[^.]+$/, ''));
  const hasFile = await p.evaluate(ns => ns.every(n => document.body.innerText.includes(n)), bases);
  if (!typed.includes(lines[0].slice(0, 40)) || !hasFile) {
    console.error('ABORT (nothing sent): composer text ok=', typed.includes(lines[0].slice(0, 40)), 'file chip ok=', hasFile);
    process.exit(1);
  }
  if (process.env.DRY_RUN) { console.log('DRY_RUN ok: text + file staged, not sent'); process.exit(0); }
  // Slack renders 2 texty_send_button elements (main composer + a hidden dialog composer); click the enabled main one.
  const send = p.locator('[data-qa="texty_send_button"][aria-disabled="false"]:not([role="dialog"] *)');
  if (await send.count() !== 1) { console.error('ABORT (nothing sent): enabled send buttons =', await send.count()); process.exit(1); }
  await send.click();
  await p.waitForTimeout(4000);
  console.log('posted text +', files.map(f => path.basename(f)).join(', '), 'to', hdr);
  process.exit(0);
})();
