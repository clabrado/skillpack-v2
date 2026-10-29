#!/usr/bin/env node
// Attach a file to a Slack DM/channel through the running Slack desktop app
// (debug port 9222, background, no window focus or keystrokes needed).
// usage: node slack_attach.js <channel-or-dm-id> <expected-header-name> <file>
// Refuses to send if the open conversation header doesn't match the expected name.
const path = require('path'), os = require('os');
const dep = path.join(os.homedir(), '.cache', 'intel');
if (!require('fs').existsSync(path.join(dep, 'node_modules', 'playwright'))) {
  require('fs').mkdirSync(dep, { recursive: true });
  require('child_process').execSync('npm init -y >/dev/null && npm i playwright >/dev/null 2>&1', { cwd: dep, shell: '/bin/sh' });
}
const { chromium } = require(path.join(dep, 'node_modules', 'playwright'));
const [chan, expect, file] = process.argv.slice(2);
if (!chan || !expect || !file) { console.error('usage: slack_attach.js <channel-id> <header-name> <file>'); process.exit(2); }
(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const p = b.contexts()[0].pages().find(x => /app\.slack\.com\/client\/[A-Z0-9]+/.test(x.url()));
  if (!p) { console.error('Slack app not reachable on :9222'); process.exit(1); }
  const team = p.url().match(/client\/([A-Z0-9]+)/)[1];
  if (!p.url().includes(chan)) await p.goto(`https://app.slack.com/client/${team}/${chan}`, { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('[data-qa="message_input"]', { timeout: 30000 });
  const hdr = await p.evaluate(() => (document.querySelector('[data-qa="channel_name"], .p-view_header__text') || {}).innerText || '');
  if (!hdr.includes(expect)) { console.error('WRONG CONVERSATION:', hdr); process.exit(1); }
  await p.setInputFiles('input[type=file]', file);
  await p.waitForTimeout(6000);
  await p.locator('[data-qa="texty_send_button"]').click();
  await p.waitForTimeout(4000);
  console.log('attached', path.basename(file), 'to', hdr);
  process.exit(0);
})();
