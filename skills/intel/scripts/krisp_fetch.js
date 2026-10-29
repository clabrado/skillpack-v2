#!/usr/bin/env node
// Pull AI notes + speaker-labeled transcript from a public Krisp share link.
// usage: node krisp_fetch.js <krisp-url> <outprefix>
//   writes <outprefix>_notes.txt, <outprefix>_transcript.txt, <outprefix>_tree.json
// Needs playwright (resolved from ~/.cache/intel/node_modules, auto-installed) and
// any cached Chromium under ~/Library/Caches/ms-playwright.
const fs = require('fs'), path = require('path'), os = require('os'), { execSync } = require('child_process');
const [url, out] = process.argv.slice(2);
if (!url || !out || !/^https:\/\/app\.krisp\.ai\/m\//.test(url)) { console.error('usage: krisp_fetch.js https://app.krisp.ai/m/... <outprefix>'); process.exit(2); }
const dep = path.join(os.homedir(), '.cache', 'intel');
if (!fs.existsSync(path.join(dep, 'node_modules', 'playwright'))) {
  fs.mkdirSync(dep, { recursive: true });
  execSync('npm init -y >/dev/null && npm i playwright >/dev/null 2>&1', { cwd: dep, shell: '/bin/sh' });
}
const { chromium } = require(path.join(dep, 'node_modules', 'playwright'));
const cache = path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright');
const exe = (fs.existsSync(cache) ? fs.readdirSync(cache) : []).filter(d => /^chromium_headless_shell-/.test(d)).sort().reverse()
  .map(d => path.join(cache, d, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell')).find(fs.existsSync);
(async () => {
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const p = await b.newPage();
  let tree = null;
  p.on('response', async r => { if (/api\.krisp\.ai\/v2\/block\/[0-9a-f]+\/tree/.test(r.url())) { try { tree = JSON.parse(await r.text()); } catch (e) {} } });
  await p.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await p.waitForTimeout(4000);
  fs.writeFileSync(out + '_notes.txt', await p.innerText('body'));
  await b.close();
  if (!tree) { console.error('no transcript tree captured (link private or format changed); notes only'); process.exit(1); }
  fs.writeFileSync(out + '_tree.json', JSON.stringify(tree, null, 1));
  const spk = {};
  for (const r of tree.resources || []) if (r.resource_type === 'speakers_map')
    for (const [k, v] of Object.entries(r.content.data)) spk[k] = [v.person.first_name, v.person.last_name].filter(Boolean).join(' ');
  const tb = (tree.children || []).find(c => c.block_type === 'transcripts');
  const sd = tb && tb.children[0] && tb.children[0].content.speech_data || [];
  const fmt = s => { const t = Math.floor(s.speech.start); return `[${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}] ${spk[s.speakerIndex] || 'Speaker ' + s.speakerIndex}: ${s.speech.text}`; };
  fs.writeFileSync(out + '_transcript.txt', sd.map(fmt).join('\n'));
  console.log(`${out}: ${sd.length} turns; speakers: ${Object.values(spk).join(', ')}`);
})();
